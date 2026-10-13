"""Real revision/ownership/SI/geometry invalidation behavior with synthetic metadata."""

from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.persistence.database import Database
from app.persistence.repository import Repository
from tests.unit import test_face_loads as loads
from tests.unit.test_materials import custom

application = loads.application
client = loads.client


def setup(client: TestClient, application: FastAPI) -> tuple[str, dict[str, Any]]:
    # Existing synthetic CAD display fixture is genuine metadata-only evidence.
    return loads.fixture(client, application)


def test_saved_sizes_remain_si_across_units_material_and_name_revisions(
    client: TestClient,
    application: FastAPI,
) -> None:
    path, geometry = setup(client, application)
    data = {
        "units": "mm-N-MPa",
        "global_size": 500.0,
        "local_sizes": [{"kind": "body", "entity_id": "body", "size": 250.0}],
        "curvature_elements": 16,
        "recovery_enabled": True,
    }
    first = client.put(path + "/mesh-controls", json=data, headers={"If-Match": '"1"'})
    assert first.status_code == 200, first.text
    original = first.json()["setup"]
    assert original["global_size_m"] == 0.5 and original["local_sizes"][0]["size_m"] == 0.25
    assert original["local_sizes"][0]["source_size"] == 250
    for revision, preset in ((2, "inch-lbf-psi"), (3, "m-N-Pa"), (4, "mm-N-MPa")):
        response = client.patch(
            path + "/display-units", json={"preset": preset}, headers={"If-Match": f'"{revision}"'}
        )
        assert response.status_code == 200
        assert client.get(path + "/mesh-controls").json()["setup"] == original
    assert (
        client.put(path + "/materials/body", json=custom(), headers={"If-Match": '"5"'}).status_code
        == 200
    )
    assert (
        client.patch(path, json={"name": "Renamed"}, headers={"If-Match": '"6"'}).status_code == 200
    )
    assert client.get(path + "/mesh-controls").json()["setup"] == original
    with application.state.repository.write() as connection:
        with pytest.raises(IntegrityError, match="immutable"):
            connection.exec_driver_sql("UPDATE analysis_mesh_setups SET setup_json='{}'")


@pytest.mark.parametrize(
    "changes",
    [
        {"global_size": 0},
        {"global_size": -1},
        {"global_size": True},
        {"curvature_elements": True},
        {"curvature_elements": 7},
        {"curvature_elements": 65},
        {"command": "gmsh"},
        {"local_sizes": [{"kind": "face", "entity_id": "stale", "size": 1.0}]},
        {
            "local_sizes": [
                {"kind": "face", "entity_id": "small", "size": 0.1},
                {"kind": "face", "entity_id": "small", "size": 0.1},
            ]
        },
    ],
)
def test_invalid_controls_do_not_append_revisions(
    client: TestClient, application: FastAPI, changes: dict[str, Any]
) -> None:
    path, geometry = setup(client, application)
    result = client.put(
        path + "/mesh-controls",
        json={"units": "m-N-Pa", "global_size": 0.5} | changes,
        headers={"If-Match": '"1"'},
    )
    assert result.status_code == 422, result.text
    assert client.get(path).json()["revision"] == 1


def test_preview_does_not_save_and_owner_csrf_stale_guards_apply(
    client: TestClient, application: FastAPI
) -> None:
    path, geometry = setup(client, application)
    before = client.get(path + "/mesh-controls").json()
    payload = {"units": "m-N-Pa", "global_size": 0.01}
    preview = client.post(
        path + "/mesh-controls/preview", json=payload, headers={"If-Match": '"1"'}
    )
    assert preview.status_code == 200 and preview.json()["coarsening_proposal_m"]
    assert client.get(path + "/mesh-controls").json() == before
    assert (
        client.put(path + "/mesh-controls", json=payload, headers={"If-Match": '"2"'}).status_code
        == 409
    )
    assert (
        client.put(
            path + "/mesh-controls",
            json=payload,
            headers={"If-Match": '"1"', "X-CSRF-Token": "bad"},
        ).status_code
        == 403
    )
    from app.domain.errors import DomainError

    with pytest.raises(DomainError) as foreign:
        application.state.repository.mesh_setup(uuid4(), UUID(path.split("/")[-1]))
    assert foreign.value.status == 404


def test_populated_legacy_migration_defaults_and_reversal_preserve_geometry(tmp_path: Path) -> None:
    database = Database(tmp_path / "legacy.sqlite3")
    database.migrate("0006_geometry_edits")
    store = Repository(database)
    owner = store.local_owner()
    from app.domain.models import ProjectCreate

    project = store.create_project(owner, ProjectCreate(name="Before mesh settings"))
    database.migrate()
    assert store.get_project(owner, project.id) == project
    database.migrate("0006_geometry_edits", downgrade=True)
    assert store.get_project(owner, project.id) == project
    database.migrate()
    assert store.get_project(owner, project.id) == project
