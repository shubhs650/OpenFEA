"""Independent preview math, request guards, revision and immutable artifact contracts."""

import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.domain.errors import DomainError
from app.domain.imports import GeometryDisplay
from app.domain.loads import LoadRequest, LoadSetup, load_state, normalized
from app.domain.models import AnalysisCreate, GeometryMetadata, ProjectCreate
from app.persistence.database import Database
from app.persistence.repository import Repository
from tests.unit import test_materials as material_tests
from worker.deck import generated_deck

application = material_tests.application
client = material_tests.client


def fixture(
    client: TestClient, application: FastAPI, *, centroid: bool = False
) -> tuple[str, dict[str, Any]]:
    store = application.state.repository
    owner = application.state.owner
    project = store.create_project(owner, ProjectCreate(name="Synthetic load math"))
    display = GeometryDisplay.model_validate(
        {
            "brep_sha256": "b" * 64,
            "lod": "coarse",
            "bodies": [
                {
                    "id": "body",
                    "volume_m3": 1,
                    "bounds_m": [0, 0, 0, 1, 1, 1],
                    **({"center_m": [0.5, 0.5, 0.5]} if centroid else {}),
                }
            ],
            "faces": [
                {
                    "id": "small",
                    "body_id": "body",
                    "points_m": [[0, 0, 1], [1, 0, 1], [0, 1, 1]],
                    "triangles": [[0, 1, 2]],
                },
                {
                    "id": "large",
                    "body_id": "body",
                    "points_m": [[1, 0, 0], [1, 2, 0], [1, 0, 2]],
                    "triangles": [[0, 1, 2]],
                },
            ],
        }
    )
    raw = display.model_dump_json().encode()
    digest = hashlib.sha256(raw).hexdigest()
    path = application.state.import_service.storage.blob_path(project.id, digest)
    path.write_bytes(raw)
    geometry = store.register_geometry(
        owner,
        project.id,
        1,
        GeometryMetadata.model_validate(
            {
                "source_sha256": "a" * 64,
                "brep_sha256": "b" * 64,
                "units": {"source_length_unit": "m", "confirmed": True},
                "bodies": [{"id": "body"}],
                "faces": [
                    {
                        "id": "small",
                        "body_id": "body",
                        "signature": {
                            "area_m2": 0.5,
                            "center_m": [1 / 3, 1 / 3, 1],
                            "surface_type": "GeomAbs_Plane",
                            "outward_normal": [0, 0, 1],
                        },
                    },
                    {
                        "id": "large",
                        "body_id": "body",
                        "signature": {
                            "area_m2": 2,
                            "center_m": [1, 2 / 3, 2 / 3],
                            "surface_type": "GeomAbs_Plane",
                            "outward_normal": [1, 0, 0],
                        },
                    },
                ],
                "validation": {
                    "artifacts": {
                        "display-coarse.json": {"sha256": digest, "size_bytes": len(raw)}
                    },
                    "synthetic_math_only": True,
                },
            }
        ),
    )
    analysis = store.create_analysis(
        owner, project.id, 2, AnalysisCreate(name="Loads", geometry_revision_id=geometry.id)
    )
    return f"/api/v1/analyses/{analysis.id}", geometry.model_dump(mode="json")


def payload(geometry: dict[str, Any], kind: str = "force", **values: Any) -> dict[str, Any]:
    return {
        "assignment": {
            "kind": kind,
            "name": "Reference",
            "geometry_revision_id": geometry["id"],
            "face_ids": ["small", "large", "small"],
            **({"units": "m-N-Pa", "force": [10, -5, 2]} if kind == "force" else {}),
            **values,
        }
    }


def test_unequal_areas_force_and_origin_moment_are_independent_of_duplicates(
    client: TestClient, application: FastAPI
) -> None:
    path, geometry = fixture(client, application)
    response = client.post(path + "/loads", json=payload(geometry), headers={"If-Match": '"1"'})
    assert response.status_code == 200, response.text
    state = response.json()
    assert state["total_force_n"] == pytest.approx([10, -5, 2], abs=1e-12)
    # Weighted CAD centroid = (13/15, 3/5, 11/15); c x F.
    assert state["total_moment_nm"] == pytest.approx([73 / 15, 28 / 5, -31 / 3], abs=1e-12)
    assert state["previews"][0]["area_m2"] == 2.5
    assert state["setup"]["assignments"][0]["face_ids"] == ["large", "small"]
    assert client.get(path + "/revisions/1/loads").json()["setup"]["assignments"] == []
    saved = state["setup"]
    assert (
        client.patch(
            path + "/display-units", json={"preset": "inch-lbf-psi"}, headers={"If-Match": '"2"'}
        ).status_code
        == 200
    )
    assert (
        client.patch(path, json={"name": "Renamed"}, headers={"If-Match": '"3"'}).status_code == 200
    )
    assert (
        client.put(
            path + "/materials/body", json=material_tests.custom(), headers={"If-Match": '"4"'}
        ).status_code
        == 200
    )
    assert client.get(path + "/loads").json()["setup"] == saved
    assert client.get(path + "/revisions/2/loads").json() == state
    with application.state.repository.write() as connection:
        for command in (
            "UPDATE analysis_load_setups SET setup_json='{}'",
            "DELETE FROM analysis_load_setups",
        ):
            with pytest.raises(IntegrityError, match="immutable"):
                connection.exec_driver_sql(command)


def test_overlap_requires_confirmation_and_signed_resultant_adds(
    client: TestClient, application: FastAPI
) -> None:
    path, geometry = fixture(client, application)
    first = client.post(
        path + "/loads",
        json=payload(geometry, "pressure", face_ids=["small"], units="mm-N-MPa", pressure=2),
        headers={"If-Match": '"1"'},
    )
    assert first.status_code == 200, first.text
    assert first.json()["total_force_n"] == [0, 0, -1e6]
    request = payload(geometry, "pressure", face_ids=["small"], units="m-N-Pa", pressure=-2e6)
    rejected = client.post(path + "/loads", json=request, headers={"If-Match": '"2"'})
    assert rejected.status_code == 409 and rejected.json()["code"] == "load_overlap"
    assert client.get(path).json()["revision"] == 2
    request["assignment"]["combine_confirmed"] = True
    result = client.post(path + "/loads", json=request, headers={"If-Match": '"2"'})
    assert result.status_code == 200, result.text
    assert result.json()["total_force_n"] == [0, 0, 0]
    assert result.json()["warnings"]


@pytest.mark.parametrize(
    "changes",
    [
        {"force": [0, 0, 0]},
        {"force": [True, 0, 0]},
        {"force": ["1", 0, 0]},
        {"force": [1, 2]},
        {"force": [1.7e308, 1.7e308, 1.7e308]},
        {"face_ids": []},
        {"face_ids": ["foreign"]},
        {"geometry_revision_id": str(uuid4())},
        {"remote_moment": [1, 2, 3]},
        {"units": "unknown"},
    ],
)
def test_invalid_loads_do_not_append_revisions(
    client: TestClient, application: FastAPI, changes: dict[str, Any]
) -> None:
    path, geometry = fixture(client, application)
    result = client.post(
        path + "/loads", json=payload(geometry, **changes), headers={"If-Match": '"1"'}
    )
    assert result.status_code == 422, result.text
    assert client.get(path).json()["revision"] == 1


def test_owner_csrf_stale_geometry_and_tombstone_guards(
    client: TestClient, application: FastAPI
) -> None:
    path, geometry = fixture(client, application)
    request = payload(geometry)
    assert client.post(path + "/loads", json=request).status_code == 428
    assert (
        client.post(
            path + "/loads", json=request, headers={"If-Match": '"1"', "X-CSRF-Token": "wrong"}
        ).status_code
        == 403
    )
    assert (
        client.post(path + "/loads", json=request, headers={"If-Match": '"1"'}).status_code == 200
    )
    assert (
        client.post(path + "/loads", json=request, headers={"If-Match": '"1"'}).json()["code"]
        == "stale_revision"
    )
    store = application.state.repository
    owner = uuid4()
    with store.write() as connection:
        connection.exec_driver_sql("INSERT INTO users VALUES (?,NULL,'test')", (str(owner),))
    project = store.create_project(owner, ProjectCreate(name="Other"))
    other = store.create_analysis(owner, project.id, 1, AnalysisCreate(name="Other"))
    other_path = f"/api/v1/analyses/{other.id}"
    for suffix in ("/loads", "/revisions/1/loads", "/deck-exports"):
        assert client.get(other_path + suffix).status_code == 404
    assert client.post(other_path + "/deck-exports", headers={"If-Match": '"1"'}).status_code == 404
    assert (
        client.delete(
            f"/api/v1/projects/{geometry['project_id']}", headers={"If-Match": '"2"'}
        ).status_code
        == 204
    )
    assert client.get(path + "/loads").status_code == 404
    assert client.post(path + "/deck-exports", headers={"If-Match": '"2"'}).status_code == 404


def test_imperial_force_canonical_and_pressure_zero_refused() -> None:
    geometry = str(uuid4())
    item = normalized(
        uuid4(),
        LoadRequest.model_validate(
            {
                "assignment": {
                    "kind": "force",
                    "name": "Imperial",
                    "geometry_revision_id": geometry,
                    "face_ids": ["a", "a"],
                    "units": "inch-lbf-psi",
                    "force": [1, 0, 0],
                }
            }
        ),
    )
    assert item.force_n == (4.4482216152605, 0, 0)
    assert item.source_force == (1, 0, 0) and item.face_ids == ["a"]
    with pytest.raises(ValueError):
        LoadRequest.model_validate(
            {
                "assignment": {
                    "kind": "pressure",
                    "name": "zero",
                    "geometry_revision_id": geometry,
                    "face_ids": ["a"],
                    "units": "m-N-Pa",
                    "pressure": 0,
                }
            }
        )


def test_full_reference_deck_bytes_and_large_material_sets() -> None:
    from tests.unit.test_quadratic import POINTS

    mesh = {
        "nodes": POINTS,
        "elements": {"1": list(range(1, 11))},
        "boundary": {"face-a": [{"element": 1, "face": 1}], "face-b": [{"element": 1, "face": 3}]},
    }
    deck = generated_deck(
        mesh,
        {(1, 1): 0, (1, 2): 0, (1, 3): 0},
        {4: (1, -2, 3)},
        0,
        0,
        materials={"M1": (210e9, 0.3)},
        element_materials={1: "M1"},
        pressures=[(1, 3, 7), (1, 1, -2)],
    )
    expected = Path("tests/fixtures/decks/face-loads.inp").read_text()
    assert deck == expected
    mesh["elements"] = {str(i): list(range(1, 11)) for i in range(1, 34)}
    large = generated_deck(
        mesh,
        {(1, 1): 0},
        {},
        0,
        0,
        materials={"M1": (210e9, 0.3)},
        element_materials={i: "M1" for i in range(1, 34)},
    )
    section = large.split("*ELSET,ELSET=M1\n")[1].split("*MATERIAL")[0]
    assert [len(line.split(",")) for line in section.strip().splitlines()] == [16, 16, 1]


@pytest.mark.parametrize("mode", ["legacy_missing", "wrong_direction"])
def test_pressure_refuses_missing_or_mismatched_native_normals(
    client: TestClient, application: FastAPI, mode: str
) -> None:
    path, fields = fixture(client, application)
    analysis, geometry, materials, _ = application.state.repository.load_inputs(
        application.state.owner, UUID(path.split("/")[-1])
    )
    assert geometry is not None
    display = application.state.import_service.display(
        application.state.owner, geometry.id, "coarse"
    )
    request = LoadRequest.model_validate(
        payload(fields, "pressure", face_ids=["small"], units="m-N-Pa", pressure=10)
    )
    assignment = normalized(uuid4(), request)
    faces = []
    for face in geometry.faces:
        signature = dict(face.signature)
        if face.id == "small":
            if mode == "legacy_missing":
                signature.pop("outward_normal")
            else:
                signature["outward_normal"] = [0, 0, -1]
        faces.append(face.model_copy(update={"signature": signature}))
    changed = geometry.model_copy(update={"faces": faces})
    with pytest.raises(DomainError) as error:
        load_state(analysis, changed, materials, LoadSetup(assignments=[assignment]), display)
    assert error.value.code == (
        "normal_unavailable" if mode == "legacy_missing" else "normal_mismatch"
    )


def test_tiny_finite_force_keeps_a_finite_unit_direction(
    client: TestClient, application: FastAPI
) -> None:
    path, geometry = fixture(client, application)
    response = client.post(
        path + "/loads",
        json=payload(geometry, force=[1e-320, 0, 0], face_ids=["small"]),
        headers={"If-Match": '"1"'},
    )
    assert response.status_code == 200, response.text
    assert response.json()["markers"][0]["direction"] == [1, 0, 0]
    assert response.json()["total_force_n"] == [1e-320, 0, 0]


def test_competing_load_and_unit_writes_have_one_winner(
    client: TestClient, application: FastAPI
) -> None:
    path, geometry = fixture(client, application)
    store = application.state.repository
    owner = application.state.owner
    identifier = UUID(path.split("/")[-1])
    assignment = normalized(uuid4(), LoadRequest.model_validate(payload(geometry)))

    def save(load: bool) -> str:
        try:
            if load:
                store.edit_loads(owner, identifier, 1, assignment)
            else:
                store.edit_material_setup(owner, identifier, 1, display_units="m-N-Pa")
            return "saved"
        except DomainError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(save, [True, False])) == ["saved", "stale_revision"]
    assert client.get(path).json()["revision"] == 2


def test_legacy_load_migration_preserves_history_and_reverses(tmp_path: Path) -> None:
    database = Database(tmp_path / "legacy.sqlite3")
    try:
        database.migrate("0003_analysis_materials")
        store = Repository(database)
        owner = store.local_owner()
        project = store.create_project(owner, ProjectCreate(name="Legacy"))
        identifier = uuid4()
        with store.write() as connection:
            connection.exec_driver_sql(
                "INSERT INTO analyses VALUES (?,?,1,'2026-10-13','2026-10-13')",
                (str(identifier), str(project.id)),
            )
            connection.exec_driver_sql(
                "INSERT INTO analysis_revisions VALUES (?,?,1,'Legacy',NULL,'2026-10-13')",
                (str(identifier), str(project.id)),
            )
        database.migrate()
        assert store.load_inputs(owner, identifier)[3] == LoadSetup()
        store.edit_material_setup(owner, identifier, 1, display_units="m-N-Pa")
        assert store.load_inputs(owner, identifier)[3] == LoadSetup()
        database.migrate("0003_analysis_materials", downgrade=True)
        database.migrate()
        assert store.get_analysis(owner, identifier).revision == 2
        assert store.get_analysis(owner, identifier, 1).name == "Legacy"
        with database.engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA integrity_check").scalar_one() == "ok"
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    finally:
        database.close()
