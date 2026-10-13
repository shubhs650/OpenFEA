"""Actual isolated OCCT cleanup -> owned preview/apply/undo -> mesh/CCX/history."""

import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.native import test_step_import as step_tests
from tests.native.test_face_decks import assign
from tests.native.test_local_jobs import submit, wait_job
from tests.unit.test_materials import custom

application = step_tests.application
client = step_tests.client


def accepted(client: TestClient, fixture: str = "hole-m.step") -> dict[str, Any]:
    project, inspection = step_tests.import_fixture(client, fixture)
    assert inspection["status"] == "ready", inspection
    response = client.post(
        f"/api/v1/geometry-imports/{inspection['id']}/confirm",
        json={"dimensions_confirmed": True},
        headers={"If-Match": '"1"'},
    )
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


def preview(
    client: TestClient,
    geometry: dict[str, Any],
    path: str | None = None,
    face_id: str | None = None,
) -> dict[str, Any]:
    project = client.get(f"/api/v1/projects/{geometry['project_id']}").json()
    feature = face_id or next(
        f["id"]
        for f in geometry["faces"]
        if f["signature"]["surface_type"].endswith("GeomAbs_Cylinder")
    )
    payload: dict[str, Any] = {"operation": "remove_feature", "face_id": feature}
    if path:
        analysis = client.get(path).json()
        payload.update(analysis_id=analysis["id"], analysis_revision=analysis["revision"])
    response = client.post(
        f"/api/v1/geometry/{geometry['id']}/edits",
        json=payload,
        headers={"If-Match": f'"{project["revision"]}"'},
    )
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


def commit(client: TestClient, geometry: dict[str, Any], edit: dict[str, Any]) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/geometry/{geometry['id']}/edit-commits",
        json={"preview_id": edit["id"], "reviewed": True},
        headers={"If-Match": f'"{edit["project_revision"]}"'},
    )
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


def analysis(client: TestClient, geometry: dict[str, Any]) -> str:
    created = client.post(
        f"/api/v1/projects/{geometry['project_id']}/analyses",
        json={"name": "Cleanup analysis", "geometry_revision_id": geometry["id"]},
        headers={"If-Match": '"2"'},
    )
    assert created.status_code == 201, created.text
    path = f"/api/v1/analyses/{created.json()['id']}"
    assert (
        client.put(
            path + "/materials/" + geometry["bodies"][0]["id"],
            json=custom(),
            headers={"If-Match": '"1"'},
        ).status_code
        == 200
    )
    return path


@pytest.mark.parametrize("kind", ["hole", "fillet"])
def test_real_bounded_preview_apply_undo_and_unchanged_source(
    client: TestClient, application: FastAPI, kind: str
) -> None:
    geometry = accepted(client, f"{kind}-m.step")
    storage = application.state.import_service.storage
    original = {
        name: storage.read(UUID(geometry["project_id"]), descriptor["sha256"])
        for name, descriptor in geometry["validation"]["artifacts"].items()
    }
    edit = preview(client, geometry)
    assert edit["status"] == "ready", edit
    data = edit["preview"]
    assert data["feature"] == kind
    assert data["preview_volume_m3"] == pytest.approx(1, abs=1e-10)
    assert abs(data["volume_delta_m3"] - data["expected_delta_m3"]) <= 1e-10
    assert len(edit["metadata"]["faces"]) == 6
    assert {m["status"] for m in data["mappings"]} == {
        "unchanged",
        "removed",
        "changed_or_ambiguous",
    }
    assert sum(m["status"] == "unchanged" for m in data["mappings"]) == (4 if kind == "hole" else 2)
    for lod in ("coarse", "fine"):
        display = client.get(f"/api/v1/geometry-edits/{edit['id']}/display?lod={lod}")
        assert display.status_code == 200, display.text
        assert len(display.json()["faces"]) == 6
    assert client.get(f"/api/v1/projects/{geometry['project_id']}/geometry").json()["total"] == 1
    applied = commit(client, geometry, edit)
    assert applied["geometry"]["parent_id"] == geometry["id"]
    assert applied["geometry"]["brep_sha256"] != geometry["brep_sha256"]
    replay = commit(client, geometry, edit)
    assert replay == applied
    undo = client.post(f"/api/v1/geometry-edits/{edit['id']}/undo", headers={"If-Match": '"3"'})
    assert undo.status_code == 200, undo.text
    restored = undo.json()["geometry"]
    assert restored["id"] != geometry["id"]
    assert restored["brep_sha256"] == geometry["brep_sha256"]
    assert restored["parent_id"] == applied["geometry"]["id"]
    assert client.get(f"/api/v1/geometry/{restored['id']}/display").status_code == 200
    assert original == {
        name: storage.read(UUID(geometry["project_id"]), descriptor["sha256"])
        for name, descriptor in geometry["validation"]["artifacts"].items()
    }
    evidence = Path(".local/native/validation/T013")
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / f"{kind}.json").write_text(
        json.dumps({"edit": edit, "applied": applied, "restored": restored}, indent=2) + "\n"
    )


@pytest.mark.parametrize("kind", ["hole", "fillet"])
def test_changed_assignment_blocks_mesh_solve_and_explicit_reselection_preserves_si(
    client: TestClient,
    kind: str,
) -> None:
    geometry = accepted(client, f"{kind}-m.step")
    path = analysis(client, geometry)
    side = next(
        f["id"]
        for f in geometry["faces"]
        if abs(f["signature"]["center_m"][0] - (1 if kind == "fillet" else 0)) < 1e-10
    )
    top = next(f["id"] for f in geometry["faces"] if f["signature"]["center_m"][2] == 1)
    assign(client, path, geometry, "fixed", [side])
    assign(client, path, geometry, "pressure", [top], pressure=1000, units="m-N-Pa")
    before = client.get(path + "/loads").json()
    before_material = client.get(path + "/materials").json()["setup"]
    edit = preview(client, geometry, path)
    assert edit["status"] == "ready", edit
    applied = commit(client, geometry, edit)
    new = applied["geometry"]
    state = client.get(path + "/loads").json()
    fixed = next(a for a in state["setup"]["assignments"] if a["kind"] == "fixed")
    pressure = next(a for a in state["setup"]["assignments"] if a["kind"] == "pressure")
    assert not fixed["review_faces"] and fixed["geometry_revision_id"] == new["id"]
    assert pressure["review_faces"] == [top]
    assert pressure["face_ids"] == [top] and pressure["geometry_revision_id"] == geometry["id"]
    assert any(top in b for b in state["blockers"])
    assert not any(m["assignment_id"] == pressure["id"] for m in state["markers"])
    assert (
        client.get(path + "/materials").json()["setup"]["assignments"][0]["material"]
        == before_material["assignments"][0]["material"]
    )
    for suffix, payload in [("/mesh-jobs", {}), ("/runs", {"mesh_job_id": str(uuid4())})]:
        response = client.post(
            path + suffix,
            json=payload,
            headers={
                "If-Match": f'"{state["analysis_revision"]}"',
                "Idempotency-Key": str(uuid4()),
            },
        )
        assert response.status_code == 422, response.text
        assert top in response.json()["message"]
    target = next(f["id"] for f in new["faces"] if f["signature"]["center_m"][2] == 1)
    response = client.put(
        path + f"/loads/{pressure['id']}/faces",
        json={"geometry_revision_id": new["id"], "face_ids": [target, target], "reviewed": True},
        headers={"If-Match": f'"{state["analysis_revision"]}"'},
    )
    assert response.status_code == 200, response.text
    reselected = next(
        a for a in response.json()["setup"]["assignments"] if a["id"] == pressure["id"]
    )
    assert reselected["face_ids"] == [target] and not reselected["review_faces"]
    for key in ("pressure_pa", "source_pressure", "source_units", "force_n", "source_force"):
        assert reselected[key] == pressure[key]
    assert not response.json()["blockers"]
    mesh = wait_job(client, submit(client, path)["id"])
    assert mesh["status"] == "succeeded", mesh
    run = wait_job(client, submit(client, path, mesh["id"])["id"])
    assert run["status"] == "succeeded", run
    assert client.get(f"/api/v1/runs/{run['id']}/results").status_code == 200
    assert client.get(path + f"/revisions/{before['analysis_revision']}/loads").json() == before


@pytest.mark.parametrize(
    "fixture,choose",
    [
        ("hole-m.step", "plane"),
        ("fillet-m.step", "plane"),
        ("cylinder-m.step", "cylinder"),
        ("fillet-unsupported-m.step", "cylinder"),
        ("hole-split-m.step", "cylinder"),
    ],
)
def test_unsupported_and_failed_fillet_leave_geometry_and_setup_unchanged(
    client: TestClient, fixture: str, choose: str
) -> None:
    geometry = accepted(client, fixture)
    original = client.get(f"/api/v1/geometry/{geometry['id']}").json()
    face = next(
        f["id"]
        for f in geometry["faces"]
        if f["signature"]["surface_type"].endswith("GeomAbs_" + choose.capitalize())
    )
    edit = preview(client, geometry, face_id=face)
    assert edit["status"] == "failed" and edit["metadata"] is None, edit
    assert client.get(f"/api/v1/geometry/{geometry['id']}").json() == original
    assert client.get(f"/api/v1/projects/{geometry['project_id']}").json()["revision"] == 2
    response = client.post(
        f"/api/v1/geometry/{geometry['id']}/edit-commits",
        json={"preview_id": edit["id"], "reviewed": True},
        headers={"If-Match": '"2"'},
    )
    assert response.status_code == 409


def test_actual_cleaned_run_remains_viewable_after_undo_to_curved_source(
    client: TestClient,
) -> None:
    geometry = accepted(client)
    path = analysis(client, geometry)
    fixed = next(f["id"] for f in geometry["faces"] if f["signature"]["center_m"][0] == 0)
    loaded = next(f["id"] for f in geometry["faces"] if f["signature"]["center_m"][0] == 1)
    assign(client, path, geometry, "fixed", [fixed])
    assign(client, path, geometry, "pressure", [loaded], pressure=1000, units="m-N-Pa")
    edit = preview(client, geometry, path)
    applied = commit(client, geometry, edit)
    mesh = wait_job(client, submit(client, path)["id"])
    assert mesh["status"] == "succeeded", mesh
    run = wait_job(client, submit(client, path, mesh["id"])["id"])
    assert run["status"] == "succeeded", run
    route = f"/api/v1/runs/{run['id']}/results"
    original_result = client.get(route).json()
    original_deck = client.get(f"/api/v1/jobs/{run['id']}/artifacts/analysis.inp").content
    undo = client.post(f"/api/v1/geometry-edits/{edit['id']}/undo", headers={"If-Match": '"3"'})
    assert undo.status_code == 200, undo.text
    assert undo.json()["geometry"]["brep_sha256"] == geometry["brep_sha256"]
    assert client.get(route).json() == original_result
    assert original_result["geometry_revision_id"] == applied["geometry"]["id"]
    assert client.get(f"/api/v1/jobs/{run['id']}/artifacts/analysis.inp").content == original_deck
    response = client.post(
        path + "/runs",
        json={"mesh_job_id": mesh["id"]},
        headers={
            "If-Match": f'"{undo.json()["analysis"]["revision"]}"',
            "Idempotency-Key": str(uuid4()),
        },
    )
    assert response.status_code == 422
    assert client.get(route).json() == original_result


def test_real_preview_ownership_csrf_stale_commit_and_corrupt_artifacts(
    client: TestClient,
    application: FastAPI,
) -> None:
    geometry = accepted(client)
    edit = preview(client, geometry)
    assert edit["status"] == "ready", edit
    service = application.state.edit_service
    from app.domain.errors import DomainError

    with pytest.raises(DomainError) as inaccessible:
        service.repository.get(uuid4(), UUID(edit["id"]))
    assert inaccessible.value.status == 404
    route = f"/api/v1/geometry/{geometry['id']}/edit-commits"
    payload = {"preview_id": edit["id"], "reviewed": True}
    assert (
        client.post(
            route, json=payload, headers={"If-Match": '"2"', "X-CSRF-Token": "bad"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            route, json=payload | {"command": "shell"}, headers={"If-Match": '"2"'}
        ).status_code
        == 422
    )
    # Corruption cannot be committed or displayed; source geometry stays accessible.
    digest = edit["metadata"]["validation"]["artifacts"]["display-coarse.json"]["sha256"]
    blob = service.imports.storage.blob_path(UUID(geometry["project_id"]), digest)
    data = blob.read_bytes()
    blob.chmod(0o600)
    blob.write_bytes(b"corrupt")
    assert client.get(f"/api/v1/geometry-edits/{edit['id']}/display").status_code == 503
    assert client.post(route, json=payload, headers={"If-Match": '"2"'}).status_code == 503
    blob.write_bytes(data)
    blob.chmod(0o400)
    assert (
        client.patch(
            f"/api/v1/projects/{geometry['project_id']}",
            json={"name": "Changed"},
            headers={"If-Match": '"2"'},
        ).status_code
        == 200
    )
    assert client.post(route, json=payload, headers={"If-Match": '"3"'}).status_code == 409
    assert client.get(f"/api/v1/projects/{geometry['project_id']}/geometry").json()["total"] == 1
