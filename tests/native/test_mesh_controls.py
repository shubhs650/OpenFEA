"""Real quadratic sizing/curvature, controlled recovery, cap and old-mesh guards."""

import json
import math
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.native import test_step_import as step_tests
from tests.native.test_geometry_edits import accepted, analysis
from tests.native.test_local_jobs import prepared, submit, wait_job
from worker.mesh_quality import mesh_quality

application = step_tests.application
client = step_tests.client


def controls(client: TestClient, path: str, **values: Any) -> dict[str, Any]:
    response = client.put(
        path + "/mesh-controls",
        json={"units": "m-N-Pa", **values},
        headers={"If-Match": f'"{client.get(path).json()["revision"]}"'},
    )
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


def mesh(client: TestClient, path: str) -> tuple[dict[str, Any], dict[str, Any]]:
    job = wait_job(client, submit(client, path)["id"])
    assert job["status"] == "succeeded", job
    return job, client.get(f"/api/v1/jobs/{job['id']}/artifacts/mesh.json").json()


@pytest.mark.parametrize("kind", ["face", "body"])
def test_real_local_size_increases_connectivity_and_old_mesh_refuses_new_sizes(
    client: TestClient,
    kind: str,
) -> None:
    path, geometry = prepared(client)
    coarse_job, coarse = mesh(client, path)
    target = geometry["bodies"][0]["id"] if kind == "body" else geometry["faces"][0]["id"]
    state = controls(
        client,
        path,
        global_size=0.5,
        local_sizes=[{"kind": kind, "entity_id": target, "size": 0.25}],
    )
    refined_job, refined = mesh(client, path)
    assert len(refined["elements"]) > len(coarse["elements"])
    assert refined["quality"]["accepted"] and refined["quality"]["all_affine"]
    assert refined["mesh_controls"]["body_sizes_m"] == ([0.25] if kind == "body" else [0.5])
    assert client.get(f"/api/v1/jobs/{coarse_job['id']}/artifacts/mesh.json").json() == coarse
    response = client.post(
        path + "/runs",
        json={"mesh_job_id": coarse_job["id"]},
        headers={"If-Match": f'"{state["analysis_revision"]}"', "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 422 and response.json()["code"] == "incompatible_mesh_controls"
    run = wait_job(client, submit(client, path, refined_job["id"])["id"])
    assert run["status"] == "succeeded", run
    result = client.get(f"/api/v1/runs/{run['id']}/results")
    assert result.status_code == 200, result.text
    assert abs(result.json()["data"]["von_mises"]["maximum"]["value"] - 1000) <= 0.01
    frozen = client.get(f"/api/v1/jobs/{refined_job['id']}/artifacts/snapshot.json").json()
    assert frozen["snapshot"]["mesh_setup"]["local_sizes"][0]["size_m"] == 0.25


def test_actual_cylinder_projected_quadratic_quality_curvature_and_solve_boundary(
    client: TestClient,
) -> None:
    geometry = accepted(client, "cylinder-m.step")
    path = analysis(client, geometry)
    counts = []
    records = []
    for curvature in (8, 16):
        state = controls(client, path, global_size=0.4, curvature_elements=curvature)
        assert not state["blockers"], state
        job, data = mesh(client, path)
        counts.append(len(data["elements"]))
        curved_ref = next(
            f["id"]
            for f in geometry["faces"]
            if f["signature"]["surface_type"].endswith("GeomAbs_Cylinder")
        )
        surface_nodes = {n for face in data["boundary"][curved_ref] for n in face["nodes"]}
        radial_error = max(abs(math.hypot(*data["nodes"][str(n)][:2]) - 0.5) for n in surface_nodes)
        assert radial_error <= 1e-12  # Independent cylinder radius, including quadratic midsides.

        assert not data["quality"]["all_affine"] and data["quality"]["accepted"]
        checked = mesh_quality(data)
        assert checked["minimum_jacobian_m3"] > 1e-15
        assert len(job["summary"]["mesh_attempts"]) == 1
        preview = client.get(f"/api/v1/jobs/{job['id']}/mesh-display")
        assert preview.status_code == 200, preview.text
        assert preview.json()["quality_display"]["faces"]
        records.append(
            {
                "curvature": curvature,
                "elements": len(data["elements"]),
                "maximum_cylinder_radius_error_m": radial_error,
                "quality": {k: v for k, v in checked.items() if k != "cells"},
            }
        )
    assert counts[1] > counts[0]
    evidence = Path(".local/native/validation/T014")
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "curved.json").write_text(json.dumps(records, indent=2) + "\n")
    response = client.post(
        path + "/runs",
        json={"mesh_job_id": job["id"]},
        headers={"If-Match": f'"{state["analysis_revision"]}"', "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 422


def test_oversize_settings_propose_coarsening_without_automatic_native_run(
    client: TestClient,
) -> None:
    path, geometry = prepared(client)
    state = controls(client, path, global_size=0.01)
    assert state["estimated_elements_upper"] > 3000 and state["coarsening_proposal_m"] > 0.01
    assert client.get(path + "/mesh-controls").json()["setup"]["global_size_m"] == 0.01
    response = client.post(
        path + "/mesh-jobs",
        json={},
        headers={"If-Match": f'"{state["analysis_revision"]}"', "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 422
    assert client.get(path + "/jobs").json() == []
    state = controls(client, path, global_size=state["coarsening_proposal_m"], curvature_elements=0)
    assert not state["blockers"]
    _, checked = mesh(client, path)
    assert len(checked["elements"]) <= 3000


@pytest.mark.parametrize("recovery,attempts", [(False, 1), (True, 3)])
def test_actual_sliver_quality_failure_exhausts_only_approved_attempts(
    client: TestClient,
    recovery: bool,
    attempts: int,
) -> None:
    geometry = accepted(client, "sliver-m.step")
    path = analysis(client, geometry)
    controls(client, path, global_size=0.5, recovery_enabled=recovery)
    job = wait_job(client, submit(client, path)["id"])
    assert job["status"] == "failed", job
    assert len(job["summary"]["mesh_attempts"]) == attempts
    assert job["summary"]["sizing_unchanged"] is True
    assert job["summary"]["max_mesh_attempts"] == attempts
    for i, attempt in enumerate(job["summary"]["mesh_attempts"], 1):
        assert attempt["settings"]["body_sizes_m"] == [0.5]
        assert attempt["number"] == i
        assert (
            client.get(f"/api/v1/jobs/{job['id']}/artifacts/mesh-attempt-{i}.log").status_code
            == 200
        )
        assert (
            client.get(
                f"/api/v1/jobs/{job['id']}/artifacts/mesh-attempt-{i}-resources.json"
            ).status_code
            == 200
        )
    preview = client.get(f"/api/v1/jobs/{job['id']}/mesh-display")
    assert preview.status_code == 200, preview.text
    assert not preview.json()["quality"]["accepted"]
    assert preview.json()["quality"]["bad_elements"]
    replay = client.get(f"/api/v1/jobs/{job['id']}").json()
    assert replay["status"] == "failed" and replay["summary"] == job["summary"]
    evidence = Path(".local/native/validation/T014")
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / f"recovery-{attempts}.json").write_text(json.dumps(job, indent=2) + "\n")


@pytest.mark.parametrize("profile", [0, 1, 2])
@pytest.mark.parametrize("curved", [False, True])
def test_all_declared_mesh_profiles_execute_real_native_and_keep_sizing(
    client: TestClient,
    application: FastAPI,
    tmp_path: Path,
    profile: int,
    curved: bool,
) -> None:
    # Trusted direct native profile check; product profile choice is server-owned.
    if curved:
        geometry = accepted(client, "cylinder-m.step")
        path = analysis(client, geometry)
    else:
        path, geometry = prepared(client)
    job, _ = mesh(client, path)
    from uuid import UUID

    from worker.deck_mesh import _mesh_attempt

    directory = application.state.job_service.storage.directory("jobs", UUID(job["id"]))
    config = {
        "body_sizes_m": [0.5],
        "face_sizes_m": {},
        "curvature_elements": 16,
        "profile": profile,
    }
    (directory / "inputs/mesh-controls.json").write_text(json.dumps(config))
    native = _mesh_attempt(directory / "inputs", tmp_path / "profile", [0.5])
    assert native["quality"]["accepted"] and native["mesh_controls"] == config
    assert native["revision"] == geometry["brep_sha256"]


def test_local_body_control_isolates_independently_meshed_bodies(client: TestClient) -> None:
    geometry = accepted(client, "two-m.step")
    path = analysis(client, geometry)
    _, original = mesh(client, path)
    first, second = [b["id"] for b in geometry["bodies"]]
    controls(client, path, local_sizes=[{"kind": "body", "entity_id": first, "size": 0.25}])
    _, refined = mesh(client, path)
    assert list(refined["owners"].values()).count(first) > list(original["owners"].values()).count(
        first
    )
    assert list(refined["owners"].values()).count(second) == list(
        original["owners"].values()
    ).count(second)


def test_geometry_cleanup_blocks_old_local_controls_and_undo_restores_them(
    client: TestClient,
) -> None:
    from tests.native.test_geometry_edits import commit, preview

    geometry = accepted(client)
    path = analysis(client, geometry)
    before = controls(
        client,
        path,
        local_sizes=[{"kind": "body", "entity_id": geometry["bodies"][0]["id"], "size": 0.4}],
    )
    edit = preview(client, geometry, path)
    assert edit["status"] == "ready", edit
    applied = commit(client, geometry, edit)
    blocked = client.get(path + "/mesh-controls").json()
    assert any(geometry["bodies"][0]["id"] in b for b in blocked["blockers"])
    response = client.post(
        path + "/mesh-jobs",
        json={},
        headers={
            "If-Match": f'"{applied["analysis"]["revision"]}"',
            "Idempotency-Key": str(uuid4()),
        },
    )
    assert response.status_code == 422
    restored = client.post(f"/api/v1/geometry-edits/{edit['id']}/undo", headers={"If-Match": '"3"'})
    assert restored.status_code == 200, restored.text
    after = client.get(path + "/mesh-controls").json()
    assert after["setup"]["local_sizes"] == before["setup"]["local_sizes"]
    assert after["setup"]["geometry_revision_id"] == restored.json()["geometry"]["id"]
    assert not after["blockers"]
