"""Real native setup variants, exact mesh reuse and frozen historical output."""

import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.domain.models import GeometryMetadata
from tests.native import test_step_import as step
from tests.native.test_face_decks import assign
from tests.native.test_local_jobs import prepared, submit, wait_job
from tests.native.test_mesh_controls import controls
from tests.unit.test_materials import custom

application = step.application
client = step.client


def duplicate(client: TestClient, path: str) -> str:
    revision = client.get(path).json()["revision"]
    result = client.post(
        path + "/duplicates",
        json={"name": "Independent copy", "source_revision": revision},
        headers={"If-Match": f'"{revision}"'},
    )
    assert result.status_code == 201, result.text
    return "/api/v1/analyses/" + str(result.json()["id"])


def choices(client: TestClient, path: str) -> dict[str, Any]:
    response = client.get(path + "/compatible-meshes")
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


def rejected_run(client: TestClient, path: str, mesh: str) -> Any:
    return client.post(
        path + "/runs",
        json={"mesh_job_id": mesh},
        headers={
            "If-Match": f'"{client.get(path).json()["revision"]}"',
            "Idempotency-Key": str(uuid4()),
        },
    )


def axial(
    client: TestClient, run: dict[str, Any], mesh: dict[str, Any], pressure: float, modulus: float
) -> dict[str, float]:
    assert run["status"] == "succeeded", run
    result = client.get(f"/api/v1/jobs/{run['id']}/artifacts/results.json").json()
    nodes = client.get(f"/api/v1/jobs/{mesh['id']}/artifacts/mesh.json").json()["nodes"]
    error_u = max(
        abs(u[axis] - (-pressure / modulus * nodes[node][0] if axis == 0 else 0))
        for node, u in result["dat"]["displacements_m"].items()
        for axis in range(3)
    )
    error_s = max(
        abs(p["tensor_pa"][axis] - (-pressure if axis == 0 else 0))
        for p in result["integration_points"]
        for axis in range(6)
    )
    assert error_u <= 1e-13
    assert error_s <= 0.01
    assert client.get(f"/api/v1/runs/{run['id']}/results").status_code == 200
    return {"displacement_error_m": error_u, "stress_error_pa": error_s}


def test_real_duplicate_variants_reuse_exact_mesh_and_keep_old_runs(client: TestClient) -> None:
    path, geometry = prepared(client)
    mesh = wait_job(client, submit(client, path)["id"])
    original = wait_job(client, submit(client, path, mesh["id"])["id"])
    measurements = [axial(client, original, mesh, 1000, 210e9)]
    retained = {
        name: client.get(f"/api/v1/jobs/{original['id']}/artifacts/{name}").content
        for name in (
            "snapshot.json",
            "analysis.inp",
            "analysis.dat",
            "analysis.frd",
            "results.json",
        )
    }
    copy = duplicate(client, path)
    selected = choices(client, copy)
    assert [item["job"]["id"] for item in selected["items"]] == [mesh["id"]]
    contract = selected["compatibility_sha256"]
    assert selected["items"][0]["mesh_sha256"] == mesh["artifacts"]["mesh.json"]["sha256"]
    assert client.get(copy + "/jobs").json() == []
    material = custom()
    material["material"]["values"]["young_modulus"] = 420000
    material["material"]["values"]["poisson_ratio"] = 0
    assert (
        client.put(
            copy + "/materials/" + geometry["bodies"][0]["id"],
            json=material,
            headers={"If-Match": '"1"'},
        ).status_code
        == 200
    )
    assert choices(client, copy)["compatibility_sha256"] == contract
    run = wait_job(client, submit(client, copy, mesh["id"])["id"])
    measurements.append(axial(client, run, mesh, 1000, 420e9))
    mismatch = client.post(
        f"/api/v1/runs/{original['id']}/comparisons",
        json={
            "compared_run_id": run["id"],
            "field": "sxx",
            "points": [
                {
                    "label": "Material mismatch",
                    "body_id": geometry["bodies"][0]["id"],
                    "point_m": [0, 0, 0],
                    "reference_element_id": 1,
                    "compared_element_id": 1,
                }
            ],
        },
    )
    assert mismatch.status_code == 409 and "materials" in mismatch.json()["message"]

    frozen = client.get(f"/api/v1/jobs/{run['id']}/artifacts/snapshot.json").json()
    assert frozen["mesh"]["job_id"] == mesh["id"]
    assert frozen["mesh"]["compatibility_sha256"] == contract
    assert frozen["snapshot"]["analysis"]["id"] != original["analysis_id"]
    pressure = next(
        a
        for a in client.get(copy + "/loads").json()["setup"]["assignments"]
        if a["kind"] == "pressure"
    )
    assert (
        client.delete(copy + "/loads/" + pressure["id"], headers={"If-Match": '"2"'}).status_code
        == 200
    )
    loaded = next(f["id"] for f in geometry["faces"] if f["signature"]["center_m"][0] == 1)
    assign(client, copy, geometry, "pressure", [loaded], units="m-N-Pa", pressure=2000)
    another = wait_job(client, submit(client, copy, mesh["id"])["id"])
    measurements.append(axial(client, another, mesh, 2000, 420e9))
    assert client.get(path + "/loads").json()["setup"]["assignments"][-1]["pressure_pa"] == 1000
    for name, raw in retained.items():
        assert client.get(f"/api/v1/jobs/{original['id']}/artifacts/{name}").content == raw
    for item in [original, run, another]:
        assert client.get(f"/api/v1/runs/{item['id']}/results").status_code == 200
    output = Path("work/T018-variant-measurements.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "cases": measurements,
                "u_tolerance_m": 1e-13,
                "stress_tolerance_pa": 0.01,
                "compatibility_sha256": contract,
                "mesh_sha256": mesh["artifacts"]["mesh.json"]["sha256"],
                "original_raw_hashes": {
                    name: hashlib.sha256(raw).hexdigest() for name, raw in retained.items()
                },
            },
            indent=2,
        )
        + "\n"
    )


@pytest.mark.parametrize("change", ["size", "local", "curvature", "policy"])
def test_real_stale_mesh_is_never_offered_or_admitted(
    client: TestClient, application: FastAPI, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    path, geometry = prepared(client)
    mesh = wait_job(client, submit(client, path)["id"])
    assert mesh["status"] == "succeeded", mesh
    copy = duplicate(client, path)
    if change == "policy":
        service = application.state.job_service
        policy = service.policy()
        monkeypatch.setattr(service, "policy", lambda: policy | {"test_changed_contract": True})
    elif change == "local":
        controls(
            client,
            copy,
            global_size=0.5,
            local_sizes=[{"kind": "face", "entity_id": geometry["faces"][0]["id"], "size": 0.25}],
        )
    else:
        controls(
            client,
            copy,
            **({"global_size": 0.3} if change == "size" else {"curvature_elements": 8}),
        )
    assert choices(client, copy)["items"] == []
    response = rejected_run(client, copy, mesh["id"])
    assert response.status_code == (409 if change == "policy" else 422), response.text
    assert client.get(copy + "/jobs").json() == []


def test_same_brep_new_geometry_revision_and_other_project_refuse_reuse(
    client: TestClient, application: FastAPI
) -> None:
    path, geometry = prepared(client)
    mesh = wait_job(client, submit(client, path)["id"])
    store, owner = application.state.repository, application.state.owner
    source = store.get_geometry(owner, UUID(geometry["id"]))
    project = store.get_project(owner, source.project_id)
    new = store.register_geometry(
        owner,
        project.id,
        project.revision,
        GeometryMetadata.model_validate(
            source.model_dump(exclude={"id", "project_id", "parent_id", "created_at"})
        ),
        parent=source.id,
    )
    response = client.post(
        f"/api/v1/projects/{project.id}/analyses",
        json={"name": "Same bytes different revision", "geometry_revision_id": str(new.id)},
        headers={"If-Match": f'"{project.revision + 1}"'},
    )
    new_path = "/api/v1/analyses/" + response.json()["id"]
    assert choices(client, new_path)["items"] == []
    # Prepare complete same-shape setup through real validated editor routes.
    assert (
        client.put(
            new_path + "/materials/" + geometry["bodies"][0]["id"],
            json=custom(),
            headers={"If-Match": '"1"'},
        ).status_code
        == 200
    )
    fixed = next(f["id"] for f in geometry["faces"] if f["signature"]["center_m"][0] == 0)
    loaded = next(f["id"] for f in geometry["faces"] if f["signature"]["center_m"][0] == 1)
    metadata = geometry | {"id": str(new.id)}
    assign(client, new_path, metadata, "fixed", [fixed])
    assign(client, new_path, metadata, "pressure", [loaded], units="m-N-Pa", pressure=1000)
    assert rejected_run(client, new_path, mesh["id"]).json()["code"] == "incompatible_mesh"
    other, _ = prepared(client)
    assert choices(client, other)["items"] == []
    assert rejected_run(client, other, mesh["id"]).json()["code"] == "incompatible_mesh"


@pytest.mark.parametrize("artifact", ["snapshot.json", "mesh.json"])
def test_corrupted_source_mesh_artifact_refuses_cross_analysis_reuse(
    client: TestClient, application: FastAPI, artifact: str
) -> None:
    path, _ = prepared(client)
    mesh = wait_job(client, submit(client, path)["id"])
    copy = duplicate(client, path)
    digest = mesh["artifacts"][artifact]["sha256"]
    stored = application.state.job_service.storage.blob_path(UUID(mesh["project_id"]), digest)
    stored.chmod(0o600)  # Explicit test-only tampering of an otherwise read-only blob.
    stored.write_bytes(b"corrupted artifact")
    assert client.get(copy + "/compatible-meshes").status_code == 503
    assert rejected_run(client, copy, mesh["id"]).status_code == 503
    assert client.get(copy + "/jobs").json() == []
