"""Real read-only CAD intersections through owned persistent HTTP connection review."""

from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from tests.native import test_step_import as step_tests
from tests.native.test_step_import import import_fixture

application = step_tests.application
client = step_tests.client


def analysis(client: TestClient, fixture: str = "bond-gap-m.step") -> tuple[str, dict[str, Any]]:
    project, preview = import_fixture(client, fixture)
    assert preview["status"] == "ready", preview
    response = client.post(
        f"/api/v1/geometry-imports/{preview['id']}/confirm",
        json={"dimensions_confirmed": True},
        headers={"If-Match": '"1"'},
    )
    assert response.status_code == 200, response.text
    geometry = response.json()
    response = client.post(
        f"/api/v1/projects/{project}/analyses",
        json={"name": "Reviewed assembly", "geometry_revision_id": geometry["id"]},
        headers={"If-Match": '"2"'},
    )
    assert response.status_code == 201, response.text
    return f"/api/v1/analyses/{response.json()['id']}", geometry


def inspect(client: TestClient, path: str) -> dict[str, Any]:
    response = client.post(
        path + "/bond-candidates", headers={"If-Match": f'"{client.get(path).json()["revision"]}"'}
    )
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


def request(geometry: dict[str, Any], pair: dict[str, Any]) -> dict[str, Any]:
    return {
        "geometry_revision_id": geometry["id"],
        "name": "Reviewed gap",
        "master_face_id": pair["master_face_id"],
        "slave_face_id": pair["slave_face_id"],
        "gap_tolerance_m": 1e-5,
        "gap_approved": True,
        "assumptions_confirmed": True,
    }


def test_gap_approval_is_explicit_remeasured_revisioned_and_copied(client: TestClient) -> None:
    path, geometry = analysis(client)
    original = client.get(path + "/bonds").json()
    report = inspect(client, path)
    assert original["setup"]["assignments"] == []
    assert client.get(path).json()["revision"] == 1  # Detection is read-only.
    assert len(report["report"]["pairs"]) == 1
    pair = report["report"]["pairs"][0]
    assert pair["gap_m"] == pytest.approx(1e-5, abs=1e-12)
    assert pair["overlap_area_m2"] == pytest.approx(1, abs=1e-12)
    assert pair["normal_dot"] == pytest.approx(-1)
    assert report["report"]["runtime"]["network_disabled"]
    payload = request(geometry, pair)
    for update, error in (
        ({"gap_approved": False}, "gap_approval_required"),
        ({"gap_tolerance_m": 0}, "gap_approval_required"),
        ({"assumptions_confirmed": False}, "bond_review_required"),
        ({"geometry_revision_id": str(uuid4())}, "stale_bond"),
    ):
        response = client.post(
            path + "/bonds", json={**payload, **update}, headers={"If-Match": '"1"'}
        )
        assert response.status_code == 422 and response.json()["code"] == error, response.text
    payload["master_face_id"], payload["slave_face_id"] = (
        payload["slave_face_id"],
        payload["master_face_id"],
    )
    response = client.post(path + "/bonds", json=payload, headers={"If-Match": '"1"'})
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["analysis_revision"] == 2
    item = saved["setup"]["assignments"][0]
    assert item["pair"]["master_face_id"] == payload["master_face_id"]
    assert client.get(path + "/revisions/1/bonds").json() == original
    assert (
        client.post(path + "/bonds", json=payload, headers={"If-Match": '"1"'}).status_code == 409
    )
    assert (
        client.post(path + "/bonds", json=payload, headers={"If-Match": '"2"'}).json()["code"]
        == "bond_conflict"
    )
    copy = client.post(
        path + "/duplicates",
        json={"name": "Independent bonds", "source_revision": 2},
        headers={"If-Match": '"2"'},
    ).json()
    copy_path = f"/api/v1/analyses/{copy['id']}"
    assert client.get(copy_path + "/bonds").json()["setup"] == saved["setup"]
    # A reviewed pair must never silently solve as two independent bodies.
    response = client.post(path + "/deck-exports", headers={"If-Match": '"2"'})
    assert response.status_code == 422 and response.json()["code"] == "setup_incomplete", (
        response.text
    )
    assert (
        client.post(
            path + "/bonds", json=payload, headers={"If-Match": '"2"', "X-CSRF-Token": "invalid"}
        ).status_code
        == 403
    )
    response = client.delete(path + "/bonds/" + item["id"], headers={"If-Match": '"2"'})
    assert response.status_code == 200 and response.json()["setup"]["assignments"] == []
    assert client.get(copy_path + "/bonds").json()["setup"] == saved["setup"]
    assert client.get(path + "/revisions/2/bonds").json()["setup"] == saved["setup"]


@pytest.mark.parametrize(
    ("fixture", "kind"),
    [
        ("bond-zero-m.step", "zero"),
        ("bond-curved-boundary-m.step", "curved-boundary"),
        ("bond-partial-m.step", "partial"),
        ("bond-excess-m.step", "excess"),
        ("bond-unrelated-m.step", "unrelated"),
        ("bond-overlap-m.step", "overlap"),
    ],
)
def test_native_candidate_geometry_and_overlap_admission(
    client: TestClient, fixture: str, kind: str
) -> None:
    path, geometry = analysis(client, fixture)
    report = inspect(client, path)["report"]
    if kind == "overlap":
        assert report["overlaps"][0]["volume_m3"] == pytest.approx(0.001, abs=1e-12)
        response = client.post(
            path + "/mesh-jobs",
            json={},
            headers={"If-Match": '"1"', "Idempotency-Key": str(uuid4())},
        )
        assert response.status_code == 422 and response.json()["code"] == "body_overlap", (
            response.text
        )
    elif kind == "unrelated":
        assert report["pairs"] == []
        response = client.post(
            path + "/bonds",
            json=request(
                geometry,
                {
                    "master_face_id": geometry["faces"][0]["id"],
                    "slave_face_id": geometry["faces"][6]["id"],
                },
            ),
            headers={"If-Match": '"1"'},
        )
        assert response.status_code == 422
    else:
        pair = report["pairs"][0]
        assert pair["eligible"] is (kind == "zero")
        if kind == "partial":
            assert pair["overlap_area_m2"] == pytest.approx(0.5, abs=1e-12)
        response = client.post(
            path + "/bonds", json=request(geometry, pair), headers={"If-Match": '"1"'}
        )
        assert response.status_code == (200 if kind == "zero" else 422), response.text


def test_native_review_guards_owner_head_and_artifact_integrity(client: TestClient) -> None:
    path, geometry = analysis(client)
    assert client.post(path + "/bond-candidates", headers={"If-Match": '"2"'}).status_code == 409
    from app.domain.errors import DomainError

    service = client.app.state.connection_service  # type: ignore[attr-defined]
    with pytest.raises(DomainError) as error:
        service.candidates(uuid4(), UUID(path.split("/")[-1]), 1)
    assert error.value.status == 404
    storage = service.imports.storage
    blob = storage.blob_path(UUID(geometry["project_id"]), geometry["brep_sha256"])
    blob.chmod(0o600)  # Explicit corruption diagnostic of otherwise immutable storage.
    blob.write_bytes(b"corrupt")
    assert client.post(path + "/bond-candidates", headers={"If-Match": '"1"'}).status_code == 503


def test_b08_real_gap_coverage_adjustment_and_analytical_response(tmp_path: Any) -> None:
    import shutil

    from worker.gap_fixture import run_b08
    from worker.runtime import ROOT

    output = tmp_path / "B08"
    result = run_b08(output, development=True)
    assert result["status"].startswith("DEVELOPMENT PASS")
    assert result["gap_m"] == 1e-5
    for case in result["cases"].values():
        assert case["intended_slave_nodes"] in (37, 65)
        assert case["uncovered_nodes"] == []
        assert case["coordinate_audit"]["max_solver_adjustment_m"] == 0
    shutil.copytree(output, ROOT / ".local/native/validation/T019/B08", dirs_exist_ok=True)


@pytest.mark.parametrize("change", ["head", "tombstone"])
def test_native_review_rechecks_after_actual_processing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    import app.domain.connection_service as connection_module
    from app.domain.models import AnalysisPatch

    path, geometry = analysis(client)
    service = client.app.state.connection_service  # type: ignore[attr-defined]
    owner = client.app.state.owner  # type: ignore[attr-defined]
    from worker.step_import import inspect_step

    original = inspect_step

    def inspect_and_change(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = original(*args, **kwargs)
        if change == "head":
            service.repository.edit_analysis(
                owner, UUID(path.split("/")[-1]), 1, AnalysisPatch(name="Other tab")
            )
        else:
            service.repository.edit_project(owner, UUID(geometry["project_id"]), 2, None)
        return result

    monkeypatch.setattr(connection_module, "inspect_step", inspect_and_change)
    response = client.post(path + "/bond-candidates", headers={"If-Match": '"1"'})
    assert response.status_code == (409 if change == "head" else 404), response.text
