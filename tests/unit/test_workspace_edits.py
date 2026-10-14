"""Append-only undo/conflict recovery of complete owned historical setup."""

from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.domain.errors import DomainError
from app.domain.models import AnalysisCreate
from tests.unit import test_face_loads as loads
from tests.unit.test_materials import custom

application = loads.application
client = loads.client


def configured(client: TestClient, application: FastAPI) -> str:
    path, geometry = loads.fixture(client, application)
    assert (
        client.put(path + "/materials/body", json=custom(), headers={"If-Match": '"1"'}).status_code
        == 200
    )
    assert (
        client.post(
            path + "/loads", json=loads.payload(geometry), headers={"If-Match": '"2"'}
        ).status_code
        == 200
    )
    assert (
        client.put(
            path + "/mesh-controls",
            json={
                "units": "m-N-Pa",
                "global_size": 0.5,
                "curvature_elements": 16,
                "recovery_enabled": True,
            },
            headers={"If-Match": '"3"'},
        ).status_code
        == 200
    )
    return path


def test_undo_restores_all_snapshots_without_rewriting_history(
    client: TestClient, application: FastAPI
) -> None:
    path = configured(client, application)
    original = {
        key: client.get(path + "/" + key).json()["setup"]
        for key in ("materials", "loads", "mesh-controls")
    }
    assert (
        client.patch(
            path + "/display-units", json={"preset": "inch-lbf-psi"}, headers={"If-Match": '"4"'}
        ).status_code
        == 200
    )
    response = client.post(
        path + "/restores", json={"target_revision": 4}, headers={"If-Match": '"5"'}
    )
    assert response.status_code == 200, response.text
    assert response.json()["revision"] == 6 and response.headers["etag"] == '"6"'
    for key, snapshot in original.items():
        assert client.get(path + "/" + key).json()["setup"] == snapshot
    assert client.get(path + "/revisions/5").json()["revision"] == 5
    # Multiple command undo uses the newly appended head, not the old revision number.
    assert (
        client.post(
            path + "/restores", json={"target_revision": 1}, headers={"If-Match": '"6"'}
        ).status_code
        == 200
    )
    assert client.get(path + "/materials").json()["setup"]["assignments"] == []
    assert client.get(path + "/loads").json()["setup"]["assignments"] == []
    assert client.get(path + "/mesh-controls").json()["setup"]["global_size_m"] is None


def test_conflict_copy_uses_observed_setup_and_replays_validated_edit(
    client: TestClient, application: FastAPI
) -> None:
    path = configured(client, application)
    original = {
        key: client.get(path + "/" + key).json()["setup"]
        for key in ("materials", "loads", "mesh-controls")
    }
    assert (
        client.patch(path, json={"name": "Other tab"}, headers={"If-Match": '"4"'}).status_code
        == 200
    )
    assert client.patch(path, json={"name": "Mine"}, headers={"If-Match": '"4"'}).status_code == 409
    response = client.post(
        path + "/conflict-copies",
        json={"source_revision": 4, "name": "Recovered"},
        headers={"If-Match": '"5"'},
    )
    assert response.status_code == 201, response.text
    copy = "/api/v1/analyses/" + response.json()["id"]
    for key, snapshot in original.items():
        assert client.get(copy + "/" + key).json()["setup"] == snapshot
    assert client.patch(copy, json={"name": "Mine"}, headers={"If-Match": '"1"'}).status_code == 200
    assert client.get(path).json()["name"] == "Other tab"
    assert client.get(copy).json()["name"] == "Mine"
    assert client.get(copy + "/jobs").json() == []


@pytest.mark.parametrize(
    "suffix,payload",
    [
        ("restores", {"target_revision": 1}),
        ("conflict-copies", {"source_revision": 1, "name": "Copy"}),
    ],
)
def test_recovery_requires_csrf_head_owner_and_live_project(
    client: TestClient, application: FastAPI, suffix: str, payload: dict[str, object]
) -> None:
    path = configured(client, application)
    assert client.post(path + "/" + suffix, json=payload).status_code == 428
    assert (
        client.post(path + "/" + suffix, json=payload, headers={"If-Match": '"1"'}).status_code
        == 409
    )
    assert (
        client.post(
            path + "/" + suffix, json=payload, headers={"If-Match": '"4"', "X-CSRF-Token": "bad"}
        ).status_code
        == 403
    )
    store = application.state.repository
    identifier = UUID(path.rsplit("/", 1)[1])
    with pytest.raises(DomainError) as failure:
        if suffix == "restores":
            store.restore_analysis(uuid4(), identifier, 4, 1)
        else:
            store.conflict_copy(uuid4(), identifier, 4, 1, "Copy")
    assert failure.value.status == 404
    project = store.get_analysis(application.state.owner, identifier).project_id
    store.edit_project(application.state.owner, project, 2, None)
    assert (
        client.post(path + "/" + suffix, json=payload, headers={"If-Match": '"4"'}).status_code
        == 404
    )


def test_restore_refuses_cross_geometry_and_conflict_copy_requires_old_revision(
    client: TestClient, application: FastAPI
) -> None:
    path = configured(client, application)
    assert (
        client.post(
            path + "/restores", json={"target_revision": 4}, headers={"If-Match": '"4"'}
        ).status_code
        == 409
    )
    assert (
        client.post(
            path + "/conflict-copies",
            json={"source_revision": 4, "name": "Copy"},
            headers={"If-Match": '"4"'},
        ).status_code
        == 409
    )
    assert (
        client.post(
            path + "/restores", json={"target_revision": 99}, headers={"If-Match": '"4"'}
        ).status_code
        == 404
    )
    store = application.state.repository
    identifier = UUID(path.rsplit("/", 1)[1])
    a = store.get_analysis(application.state.owner, identifier)
    with store.write() as connection:
        store._insert_analysis_revision(
            connection,
            identifier,
            a.project_id,
            5,
            AnalysisCreate(name="Changed geometry", geometry_revision_id=None),
            a.updated_at.isoformat(),
        )
        connection.exec_driver_sql(
            "UPDATE analyses SET head_revision=5 WHERE id=?", (str(identifier),)
        )
    assert (
        client.post(
            path + "/restores", json={"target_revision": 4}, headers={"If-Match": '"5"'}
        ).status_code
        == 409
    )


def test_concurrent_restore_has_one_winner(client: TestClient, application: FastAPI) -> None:
    path = configured(client, application)
    store, owner = application.state.repository, application.state.owner
    identifier = UUID(path.rsplit("/", 1)[1])

    def restore() -> int:
        try:
            return int(store.restore_analysis(owner, identifier, 4, 1).revision)
        except DomainError as error:
            return error.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: restore(), range(2))) == [5, 409]
