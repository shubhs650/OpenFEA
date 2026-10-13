"""Independent dimensional references and real immutable/owned material API paths."""

import math
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.domain.materials import (
    LIBRARY_VERSION,
    SAMPLES,
    DisplayUnitsPatch,
    SampleMaterial,
    snapshot_for,
)
from app.domain.models import AnalysisCreate, GeometryMetadata, ProjectCreate
from app.domain.units import PRESETS, PresetID, from_si, to_si
from app.main import create_app
from app.persistence.database import Database
from app.persistence.repository import Repository


@pytest.fixture
def application(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    for key, value in {
        "FEA_ENV": "test",
        "FEA_AUTH_MODE": "local",
        "FEA_BIND_HOST": "127.0.0.1",
        "FEA_DATA_ROOT": str(tmp_path),
    }.items():
        monkeypatch.setenv(key, value)
    return create_app()


@pytest.fixture
def client(application: FastAPI) -> Iterator[TestClient]:
    with TestClient(application, base_url="http://127.0.0.1", client=("127.0.0.1", 55000)) as api:
        api.headers["X-CSRF-Token"] = api.get("/api/v1/session").json()["csrf_token"]
        yield api


def metadata(body: str = "body-1", digest: str = "b") -> GeometryMetadata:
    return GeometryMetadata.model_validate(
        {
            "source_sha256": "a" * 64,
            "brep_sha256": digest * 64,
            "units": {"source_length_unit": "m", "confirmed": True},
            "bodies": [{"id": body}],
            "faces": [{"id": "face", "body_id": body, "signature": {}}],
            "validation": {"synthetic_metadata_only": True},
        }
    )


def analysis_fixture(client: TestClient, application: FastAPI) -> tuple[dict[str, Any], str]:
    project = client.post("/api/v1/projects", json={"name": "Material fixture"}).json()
    store = application.state.repository
    geometry = store.register_geometry(application.state.owner, UUID(project["id"]), 1, metadata())
    created = client.post(
        f"/api/v1/projects/{project['id']}/analyses",
        json={"name": "Original", "geometry_revision_id": str(geometry.id)},
        headers={"If-Match": '"2"'},
    )
    assert created.status_code == 201, created.text
    return project, f"/api/v1/analyses/{created.json()['id']}"


def custom() -> dict[str, Any]:
    return {
        "material": {
            "kind": "custom",
            "units": "mm-N-MPa",
            "confirmed": True,
            "values": {
                "young_modulus": 210000,
                "poisson_ratio": 0.3,
                "density": 7.85e-9,
                "yield_strength": 250,
            },
            "provenance": {
                "name": "Synthetic steel",
                "grade": "Test only",
                "condition": "Analytical fixture",
                "temperature_note": "Room-temperature fixture",
                "sources": [{"title": "Independent test definition"}],
                "assumptions": "Synthetic isotropic reference; no certified allowable.",
            },
        }
    }


@pytest.mark.parametrize("preset", list(PRESETS))
def test_dimensional_round_trips_and_known_references(preset: PresetID) -> None:
    # Independent SI/engineering relationships; comparisons never reuse rounded display text.
    for value, quantity in [
        (210e9, "stress"),
        (7850, "density"),
        (-9.80665, "acceleration"),
        (0.0254, "length"),
        (4.4482216152605, "force"),
    ]:
        shown = from_si(value, preset, quantity)  # type: ignore[arg-type]
        assert to_si(shown, preset, quantity) == pytest.approx(value, rel=2e-16, abs=1e-15)  # type: ignore[arg-type]
    if preset == "mm-N-MPa":
        assert from_si(210e9, preset, "stress") == 210000
        assert from_si(7850, preset, "density") == 7.85e-9
        assert from_si(-9.80665, preset, "acceleration") == -9806.65
    elif preset == "inch-lbf-psi":
        assert to_si(1, preset, "length") == 0.0254
        assert to_si(1, preset, "force") == 4.4482216152605
        assert to_si(1, preset, "stress") == pytest.approx(6894.757293168361, rel=2e-16)
        # rho*g*volume returns the same force after independent dimensions cancel.
        rho = from_si(7850, preset, "density")
        gravity = from_si(9.80665, preset, "acceleration")
        volume = (1 / 0.0254) ** 3
        assert rho * gravity * volume * 4.4482216152605 == pytest.approx(7850 * 9.80665, rel=5e-16)


def test_library_and_presets_require_session_and_show_source_limits(application: FastAPI) -> None:
    with TestClient(application, base_url="http://127.0.0.1", client=("127.0.0.1", 55000)) as api:
        assert api.get("/api/v1/material-library").status_code == 401
        assert api.get("/api/v1/unit-presets").status_code == 401
        api.get("/api/v1/session")
        library = api.get("/api/v1/material-library").json()
        assert len(library) == 2
        assert all("confirmed" not in item for item in library)
        assert all("assumption" in item["provenance"]["assumptions"] for item in library)
        assert all(
            item["provenance"]["sources"][0]["url"].startswith("https://") for item in library
        )
        assert library[1]["properties"]["yield_strength_pa"] is None
        assert {item["id"] for item in api.get("/api/v1/unit-presets").json()} == set(PRESETS)


def test_material_snapshots_unit_only_edits_history_and_name_edits(
    client: TestClient, application: FastAPI
) -> None:
    project, path = analysis_fixture(client, application)
    initial = client.get(path + "/materials").json()
    assert not initial["bodies"][0]["material_assigned"]
    assigned = client.put(path + "/materials/body-1", json=custom(), headers={"If-Match": '"1"'})
    assert assigned.status_code == 200, assigned.text
    assert assigned.headers["etag"] == '"2"'
    snapshot = assigned.json()["setup"]["assignments"][0]["material"]
    assert snapshot["properties"] == pytest.approx(
        {
            "young_modulus_pa": 210e9,
            "poisson_ratio": 0.3,
            "density_kg_m3": 7850,
            "yield_strength_pa": 250e6,
        },
        rel=2e-16,
        abs=1e-15,
    )
    revision = 2
    for preset in ["inch-lbf-psi", "m-N-Pa", "mm-N-MPa"] * 5:
        result = client.patch(
            path + "/display-units", json={"preset": preset}, headers={"If-Match": f'"{revision}"'}
        )
        assert result.status_code == 200, result.text
        revision += 1
        assert result.json()["setup"]["assignments"][0]["material"] == snapshot
    renamed = client.patch(path, json={"name": "Renamed"}, headers={"If-Match": f'"{revision}"'})
    assert renamed.status_code == 200
    revision += 1
    assert client.get(path + "/materials").json()["setup"]["assignments"][0]["material"] == snapshot
    assert client.get(path + "/revisions/1/materials").json() == initial
    assert client.get(path + "/revisions/2/materials").json() == assigned.json()
    assert client.get(f"/api/v1/projects/{project['id']}").json()["revision"] == 2
    removed = client.delete(path + "/materials/body-1", headers={"If-Match": f'"{revision}"'})
    assert removed.status_code == 200 and removed.json()["setup"]["assignments"] == []
    assert client.get(path + "/revisions/2/materials").json() == assigned.json()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("young_modulus", 0),
        ("young_modulus", -1),
        ("young_modulus", True),
        ("young_modulus", "NaN"),
        ("young_modulus", 1e308),
        ("poisson_ratio", -0.01),
        ("poisson_ratio", 0.450001),
        ("poisson_ratio", 0.5),
        ("poisson_ratio", "Infinity"),
        ("density", 0),
        ("density", -1),
        ("yield_strength", 0),
    ],
)
def test_invalid_or_unvalidated_materials_cannot_append_revisions(
    client: TestClient, application: FastAPI, field: str, value: Any
) -> None:
    _, path = analysis_fixture(client, application)
    payload = custom()
    payload["material"]["values"][field] = value
    result = client.put(path + "/materials/body-1", json=payload, headers={"If-Match": '"1"'})
    assert result.status_code == 422, result.text
    assert client.get(path).json()["revision"] == 1
    assert client.get(path + "/materials").json()["setup"]["assignments"] == []


def test_confirmation_provenance_and_density_yield_prerequisites(
    client: TestClient, application: FastAPI
) -> None:
    _, path = analysis_fixture(client, application)
    payload = custom()
    payload["material"]["confirmed"] = False
    assert (
        client.put(
            path + "/materials/body-1", json=payload, headers={"If-Match": '"1"'}
        ).status_code
        == 422
    )
    payload["material"]["confirmed"] = True
    payload["material"]["provenance"]["sources"] = []
    assert (
        client.put(
            path + "/materials/body-1", json=payload, headers={"If-Match": '"1"'}
        ).status_code
        == 422
    )
    payload = custom()
    payload["material"]["values"].update(density=None, yield_strength=None, poisson_ratio=0.45)
    result = client.put(path + "/materials/body-1", json=payload, headers={"If-Match": '"1"'})
    assert result.status_code == 200, result.text
    status = result.json()["bodies"][0]
    assert (
        status["material_assigned"]
        and not status["gravity_available"]
        and not status["yield_factor_available"]
    )
    assert len(status["warnings"]) == 3


def test_saved_samples_are_independent_of_library_edits(
    client: TestClient, application: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, path = analysis_fixture(client, application)
    request = {
        "material": {
            "kind": "sample",
            "sample_id": "al-6061-t6-rod",
            "library_version": LIBRARY_VERSION,
            "confirmed": True,
        }
    }
    original = client.put(
        path + "/materials/body-1", json=request, headers={"If-Match": '"1"'}
    ).json()
    previous = SAMPLES["al-6061-t6-rod"]
    changed = previous.model_copy(
        update={
            "properties": previous.properties.model_copy(update={"young_modulus_pa": 100e9}),
            "library_version": "test-edit",
        },
        deep=True,
    )
    monkeypatch.setitem(SAMPLES, "al-6061-t6-rod", changed)
    assert client.get(path + "/materials").json() == original
    assert client.get(path + "/revisions/2/materials").json() == original
    rejected = client.put(path + "/materials/body-1", json=request, headers={"If-Match": '"2"'})
    assert rejected.status_code == 409 and rejected.json()["code"] == "material_library_changed"
    assert client.get(path + "/materials").json() == original
    request["material"]["library_version"] = "test-edit"
    updated = client.put(
        path + "/materials/body-1", json=request, headers={"If-Match": '"2"'}
    ).json()
    assert updated["setup"]["assignments"][0]["material"]["properties"]["young_modulus_pa"] == 100e9
    assert client.get(path + "/revisions/2/materials").json() == original


def test_owner_body_revision_csrf_and_tombstone_guards(
    client: TestClient, application: FastAPI
) -> None:
    project, path = analysis_fixture(client, application)
    assert (
        client.put(
            path + "/materials/foreign-body", json=custom(), headers={"If-Match": '"1"'}
        ).status_code
        == 422
    )
    assert client.put(path + "/materials/body-1", json=custom()).status_code == 428
    assert (
        client.put(
            path + "/materials/body-1",
            json=custom(),
            headers={"If-Match": '"1"', "X-CSRF-Token": "wrong"},
        ).status_code
        == 403
    )
    assert (
        client.put(
            path + "/materials/body-1", json=custom(), headers={"If-Match": '"1"'}
        ).status_code
        == 200
    )
    assert (
        client.patch(
            path + "/display-units", json={"preset": "m-N-Pa"}, headers={"If-Match": '"1"'}
        ).status_code
        == 409
    )
    store: Repository = application.state.repository
    with store.write() as connection:
        foreign = uuid4()
        connection.execute(
            text("INSERT INTO users VALUES (:id, NULL, 'test')"), {"id": str(foreign)}
        )
    other = store.create_project(foreign, ProjectCreate(name="Other"))
    other_analysis = store.create_analysis(foreign, other.id, 1, AnalysisCreate(name="Other"))
    other_path = f"/api/v1/analyses/{other_analysis.id}"
    for suffix in ("/materials", "/revisions/1/materials"):
        assert client.get(other_path + suffix).status_code == 404
    assert (
        client.put(
            other_path + "/materials/body-1", json=custom(), headers={"If-Match": '"1"'}
        ).status_code
        == 404
    )
    assert (
        client.patch(
            other_path + "/display-units", json={"preset": "m-N-Pa"}, headers={"If-Match": '"1"'}
        ).status_code
        == 404
    )
    assert (
        client.delete(f"/api/v1/projects/{project['id']}", headers={"If-Match": '"2"'}).status_code
        == 204
    )
    assert client.get(path + "/materials").status_code == 404
    assert client.get(path + "/revisions/2/materials").status_code == 404
    assert client.delete(path + "/materials/body-1", headers={"If-Match": '"2"'}).status_code == 404


def test_geometry_pinning_and_analysis_independence(
    client: TestClient, application: FastAPI
) -> None:
    project, path = analysis_fixture(client, application)
    assert (
        client.put(
            path + "/materials/body-1", json=custom(), headers={"If-Match": '"1"'}
        ).status_code
        == 200
    )
    store: Repository = application.state.repository
    owner = application.state.owner
    geometry = store.register_geometry(owner, UUID(project["id"]), 2, metadata("new-body", "c"))
    second = store.create_analysis(
        owner,
        UUID(project["id"]),
        3,
        AnalysisCreate(name="Independent", geometry_revision_id=geometry.id),
    )
    assert (
        client.get(f"/api/v1/analyses/{second.id}/materials").json()["setup"]["assignments"] == []
    )
    assert (
        client.put(
            path + "/materials/new-body", json=custom(), headers={"If-Match": '"2"'}
        ).status_code
        == 422
    )
    assert client.get(path + "/materials").json()["geometry_revision_id"] != str(geometry.id)
    empty = store.create_analysis(owner, UUID(project["id"]), 3, AnalysisCreate(name="No geometry"))
    assert (
        client.put(
            f"/api/v1/analyses/{empty.id}/materials/body-1",
            json=custom(),
            headers={"If-Match": '"1"'},
        ).status_code
        == 409
    )


def test_competing_unit_and_material_writes_have_one_winner(
    client: TestClient, application: FastAPI
) -> None:
    _, path = analysis_fixture(client, application)
    store: Repository = application.state.repository
    identifier = UUID(path.split("/")[-1])
    snapshot = snapshot_for(
        SampleMaterial(
            kind="sample",
            sample_id="stainless-304",
            library_version=LIBRARY_VERSION,
            confirmed=True,
        )
    )

    def save(unit_only: bool) -> str:
        from app.domain.errors import DomainError

        try:
            store.edit_material_setup(
                application.state.owner,
                identifier,
                1,
                **(
                    {"display_units": "m-N-Pa"}
                    if unit_only
                    else {"body": "body-1", "material": snapshot}
                ),
            )
            return "saved"
        except DomainError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(save, [True, False]))
    assert sorted(outcomes) == ["saved", "stale_revision"]
    assert client.get(path).json()["revision"] == 2


def test_material_migration_preserves_old_revisions_and_reverses(tmp_path: Path) -> None:
    database = Database(tmp_path / "migration.sqlite3")
    try:
        database.migrate("0002_step_imports")
        store = Repository(database)
        owner = store.local_owner()
        project = store.create_project(owner, ProjectCreate(name="Before materials"))
        geometry = store.register_geometry(owner, project.id, 1, metadata())
        identifier = uuid4()
        parameters = {
            "id": str(identifier),
            "project": str(project.id),
            "geometry": str(geometry.id),
            "time": "2026-10-13T00:00:00+00:00",
        }
        with store.write() as connection:
            connection.execute(
                text("INSERT INTO analyses VALUES (:id,:project,1,:time,:time)"),
                parameters,
            )
            connection.execute(
                text(
                    "INSERT INTO analysis_revisions VALUES "
                    "(:id,:project,1,'Legacy',:geometry,:time)"
                ),
                parameters,
            )
        database.migrate()
        assert store.get_material_state(owner, identifier).setup.assignments == []
        snapshot = snapshot_for(
            SampleMaterial(
                kind="sample",
                sample_id="stainless-304",
                library_version=LIBRARY_VERSION,
                confirmed=True,
            )
        )
        state = store.edit_material_setup(owner, identifier, 1, body="body-1", material=snapshot)
        assert state.analysis_revision == 2
        with store.write() as connection:
            for command in (
                "UPDATE analysis_material_setups SET setup_json='{}'",
                "DELETE FROM analysis_material_setups",
            ):
                with pytest.raises(IntegrityError, match="immutable material setup"):
                    connection.exec_driver_sql(command)
        assert store.get_material_state(owner, identifier).setup.assignments[0].material == snapshot
        database.migrate("0002_step_imports", downgrade=True)
        database.migrate()
        assert store.get_analysis(owner, identifier).revision == 2
        assert store.get_analysis(owner, identifier, 1).name == "Legacy"
        assert store.get_material_state(owner, identifier).setup.assignments == []
        with database.engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA integrity_check").scalar_one() == "ok"
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    finally:
        database.close()


def test_nonfinite_conversion_refuses_without_clamping() -> None:
    for value in (math.inf, -math.inf, math.nan):
        with pytest.raises(ValueError, match="finite"):
            to_si(value, "mm-N-MPa", "stress")
        with pytest.raises(ValueError, match="finite"):
            from_si(value, "mm-N-MPa", "stress")
    assert DisplayUnitsPatch(preset="m-N-Pa").preset == "m-N-Pa"
