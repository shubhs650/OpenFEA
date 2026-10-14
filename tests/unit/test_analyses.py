"""Independent trusted setup copies, optimistic ownership and exact mesh contract hashes."""

from concurrent.futures import ThreadPoolExecutor
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.domain.errors import DomainError
from app.domain.loads import DeckSnapshot
from app.domain.mesh import LocalSize
from app.domain.mesh_reuse import compatibility_hash
from app.domain.models import AnalysisPatch
from tests.unit import test_face_loads as loads
from tests.unit.test_materials import custom
from tests.unit.test_workspace_edits import configured

application = loads.application
client = loads.client


def test_duplicate_complete_setup_then_edit_is_independent(
    client: TestClient, application: FastAPI
) -> None:
    path = configured(client, application)
    original = {
        key: client.get(path + "/" + key).json()["setup"]
        for key in ("materials", "loads", "mesh-controls")
    }
    copy = client.post(
        path + "/duplicates",
        json={"source_revision": 4, "name": "Independent variant"},
        headers={"If-Match": '"4"'},
    )
    assert copy.status_code == 201, copy.text
    assert copy.headers["etag"] == '"1"'
    duplicate = "/api/v1/analyses/" + copy.json()["id"]
    for key, setup in original.items():
        assert client.get(duplicate + "/" + key).json()["setup"] == setup
    assert client.get(duplicate + "/jobs").json() == []
    assert client.get(duplicate + "/deck-exports").json() == []
    assert client.get(path).json()["revision"] == 4
    change = custom()
    change["material"]["values"]["young_modulus"] = 100000
    assert (
        client.put(
            duplicate + "/materials/body", json=change, headers={"If-Match": '"1"'}
        ).status_code
        == 200
    )
    assignment = original["loads"]["assignments"][0]["id"]
    assert (
        client.delete(duplicate + "/loads/" + assignment, headers={"If-Match": '"2"'}).status_code
        == 200
    )
    assert (
        client.put(
            duplicate + "/mesh-controls",
            json={"units": "m-N-Pa", "global_size": 0.4},
            headers={"If-Match": '"3"'},
        ).status_code
        == 200
    )
    for key, setup in original.items():
        assert client.get(path + "/" + key).json()["setup"] == setup
    assert client.get(duplicate + "/revisions/1/materials").json()["setup"] == original["materials"]


def test_duplicate_historical_revision_retains_its_exact_geometry_and_units(
    client: TestClient, application: FastAPI
) -> None:
    path = configured(client, application)
    initial = client.get(path + "/revisions/1").json()
    assert (
        client.patch(
            path + "/display-units", json={"preset": "inch-lbf-psi"}, headers={"If-Match": '"4"'}
        ).status_code
        == 200
    )
    copy = client.post(
        path + "/duplicates",
        json={"source_revision": 1, "name": "Initial setup"},
        headers={"If-Match": '"5"'},
    )
    assert copy.status_code == 201
    duplicate = "/api/v1/analyses/" + copy.json()["id"]
    assert copy.json()["geometry_revision_id"] == initial["geometry_revision_id"]
    assert client.get(duplicate + "/materials").json()["setup"]["display_units"] == "mm-N-MPa"
    assert client.get(duplicate + "/loads").json()["setup"]["assignments"] == []
    assert client.get(duplicate + "/mesh-controls").json()["setup"]["global_size_m"] is None


@pytest.mark.parametrize("revision", [0, -1, 100])
def test_bad_or_missing_source_does_not_create_copy(
    client: TestClient, application: FastAPI, revision: int
) -> None:
    path = configured(client, application)
    project = client.get(path).json()["project_id"]
    response = client.post(
        path + "/duplicates",
        json={"source_revision": revision, "name": "Rejected"},
        headers={"If-Match": '"4"'},
    )
    assert response.status_code == (404 if revision == 100 else 422)
    assert client.get(f"/api/v1/projects/{project}/analyses").json()["total"] == 1


def test_duplicate_owner_tombstone_csrf_and_stale_head(
    client: TestClient, application: FastAPI
) -> None:
    path = configured(client, application)
    payload = {"source_revision": 4, "name": "Copy"}
    assert client.post(path + "/duplicates", json=payload).status_code == 428
    assert (
        client.post(path + "/duplicates", json=payload, headers={"If-Match": '"3"'}).status_code
        == 409
    )
    assert (
        client.post(
            path + "/duplicates", json=payload, headers={"If-Match": '"4"', "X-CSRF-Token": "bad"}
        ).status_code
        == 403
    )
    store = application.state.repository
    identifier = UUID(path.rsplit("/", 1)[1])
    with pytest.raises(DomainError) as failure:
        store.duplicate_analysis(uuid4(), identifier, 4, 4, "Unauthorized")
    assert failure.value.status == 404
    project = store.get_analysis(application.state.owner, identifier).project_id
    store.edit_project(application.state.owner, project, 2, None)
    assert (
        client.post(path + "/duplicates", json=payload, headers={"If-Match": '"4"'}).status_code
        == 404
    )


def test_concurrent_copies_are_distinct_and_source_never_changes(
    client: TestClient, application: FastAPI
) -> None:
    path = configured(client, application)
    store, owner = application.state.repository, application.state.owner
    identifier = UUID(path.rsplit("/", 1)[1])

    def copy(index: int) -> str:
        return str(store.duplicate_analysis(owner, identifier, 4, 4, f"Copy {index}").id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        identifiers = list(pool.map(copy, range(2)))
    assert len(set(identifiers)) == 2
    assert store.get_analysis(owner, identifier).revision == 4
    store.edit_analysis(owner, identifier, 4, AnalysisPatch(name="Other tab"))
    with pytest.raises(DomainError) as failure:
        store.duplicate_analysis(owner, identifier, 4, 4, "Stale copy")
    assert failure.value.status == 409


def snapshot(client: TestClient, application: FastAPI) -> DeckSnapshot:
    path = configured(client, application)
    store = application.state.repository
    identifier = UUID(path.rsplit("/", 1)[1])
    analysis, geometry, materials, load_setup = store.load_inputs(
        application.state.owner, identifier
    )
    assert geometry is not None
    return DeckSnapshot(
        analysis=analysis,
        geometry=geometry,
        materials=materials,
        loads=load_setup,
        mesh_setup=store.mesh_setup(application.state.owner, identifier)[2],
    )


def test_mesh_hash_excludes_analysis_material_load_and_display_recovery_edits(
    client: TestClient, application: FastAPI
) -> None:
    original = snapshot(client, application)
    changed = original.model_copy(
        update={
            "analysis": original.analysis.model_copy(
                update={"id": uuid4(), "name": "Variant", "revision": 9}
            ),
            "materials": original.materials.model_copy(
                update={"display_units": "inch-lbf-psi", "assignments": []}
            ),
            "loads": original.loads.model_copy(update={"assignments": []}),
            "mesh_setup": original.mesh_setup.model_copy(update={"recovery_enabled": False}),
        }
    )
    assert compatibility_hash(changed, {"source": "fixed"}) == compatibility_hash(
        original, {"source": "fixed"}
    )


@pytest.mark.parametrize("change", ["geometry", "catalog", "size", "local", "curvature", "policy"])
def test_mesh_hash_changes_for_every_physical_identity(
    client: TestClient, application: FastAPI, change: str
) -> None:
    original = snapshot(client, application)
    changed, policy = original, {"source": "fixed"}
    if change == "geometry":
        changed = original.model_copy(
            update={"geometry": original.geometry.model_copy(update={"id": uuid4()})}
        )
    elif change == "catalog":
        changed = original.model_copy(
            update={"geometry": original.geometry.model_copy(update={"faces": []})}
        )
    elif change in {"size", "local", "curvature"}:
        update: dict[str, Any] = (
            {"global_size_m": 0.5000000000000001}
            if change == "size"
            else {"local_sizes": []}
            if change == "local"
            else {"curvature_elements": 8}
        )
        if change == "local":
            update = {
                "local_sizes": [
                    LocalSize(
                        kind="body",
                        entity_id="body",
                        size_m=0.25,
                        source_size=250,
                        source_units="mm-N-MPa",
                    )
                ]
            }
        changed = original.model_copy(
            update={"mesh_setup": original.mesh_setup.model_copy(update=update)}
        )
    else:
        policy = {"source": "changed"}
    assert compatibility_hash(changed, policy) != compatibility_hash(original, {"source": "fixed"})


def test_mesh_choices_report_missing_native_contract_as_unavailable(
    client: TestClient, application: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = configured(client, application)

    def unavailable() -> dict[str, Any]:
        raise RuntimeError("Controlled missing native tool contract")

    monkeypatch.setattr(application.state.job_service, "policy", unavailable)
    response = client.get(path + "/compatible-meshes")
    assert response.status_code == 503
    assert response.json()["code"] == "native_unavailable"
