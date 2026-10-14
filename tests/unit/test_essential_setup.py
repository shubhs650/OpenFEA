"""SI/source quantities, density availability, immutable revisions and owner-bound targets."""

from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.domain.loads import LoadRequest, normalized
from app.domain.units import PRESETS, PresetID
from tests.unit import test_materials as material_tests
from tests.unit.test_face_loads import fixture
from tests.unit.test_materials import custom

application = material_tests.application
client = material_tests.client


def gravity(geometry: dict[str, Any], **values: Any) -> dict[str, Any]:
    return {
        "assignment": {
            "kind": "gravity",
            "name": "Acceleration",
            "geometry_revision_id": geometry["id"],
            "body_ids": ["body", "body"],
            "units": "m-N-Pa",
            "acceleration": [0, 0, -9.80665],
            **values,
        }
    }


@pytest.mark.parametrize("preset", list(PRESETS))
def test_acceleration_displacement_source_si_round_trips_and_zero_component(
    preset: PresetID,
) -> None:
    units = PRESETS[preset]
    selection = {"geometry_revision_id": str(uuid4()), "name": "Reference", "units": preset}
    acceleration = (1.0, -9.80665, 2.0)
    source = [v / units.acceleration.to_si for v in acceleration]
    g = normalized(
        uuid4(),
        LoadRequest.model_validate(
            {
                "assignment": selection
                | {"kind": "gravity", "body_ids": ["b", "b"], "acceleration": source}
            }
        ),
    )
    assert g.acceleration_m_s2 == pytest.approx(acceleration, rel=1e-12)
    assert (
        g.source_acceleration == tuple(source) and g.source_units == preset and g.body_ids == ["b"]
    )
    for value in (0.0, -0.001):
        request = LoadRequest.model_validate(
            {
                "assignment": selection
                | {
                    "kind": "displacement",
                    "face_ids": ["f", "f"],
                    "axis": "z",
                    "displacement": value / units.length.to_si,
                }
            }
        )
        u = normalized(uuid4(), request)
        assert u.displacement_m == pytest.approx(value, rel=1e-12, abs=1e-15)
        assert u.source_displacement == value / units.length.to_si and u.face_ids == ["f"]


def test_missing_density_withholds_whole_gravity_weight_and_confirmed_material_restores_it(
    client: TestClient,
    application: FastAPI,
) -> None:
    path, geometry = fixture(client, application, centroid=True)
    response = client.post(path + "/loads", json=gravity(geometry), headers={"If-Match": '"1"'})
    assert response.status_code == 200, response.text
    state = response.json()
    assert not state["resultant_complete"] and state["previews"] == []
    assert any("weight is unavailable" in x for x in state["blockers"])
    assert state["markers"][0]["direction"] == [0, 0, -1]
    material = custom()
    assert (
        client.put(path + "/materials/body", json=material, headers={"If-Match": '"2"'}).status_code
        == 200
    )
    saved = client.get(path + "/loads").json()
    assert saved["resultant_complete"] and saved["previews"][0]["mass_kg"] == pytest.approx(
        7850, abs=1e-10
    )
    assert saved["total_force_n"] == pytest.approx([0, 0, -76982.2025], abs=1e-8)
    assert saved["total_moment_nm"] == pytest.approx([-38491.10125, 38491.10125, 0], abs=1e-8)
    assert saved["setup"]["assignments"] == state["setup"]["assignments"]


def test_legacy_without_native_centroid_refuses_gravity_without_creating_revision(
    client: TestClient,
    application: FastAPI,
) -> None:
    path, geometry = fixture(client, application)
    response = client.post(path + "/loads", json=gravity(geometry), headers={"If-Match": '"1"'})
    assert response.status_code == 422 and response.json()["code"] == "gravity_centroid_unavailable"
    assert client.get(path).json()["revision"] == 1


def test_overlapping_body_acceleration_needs_explicit_permission_and_preserves_resultant_scale(
    client: TestClient,
    application: FastAPI,
) -> None:
    path, geometry = fixture(client, application, centroid=True)
    assert (
        client.put(path + "/materials/body", json=custom(), headers={"If-Match": '"1"'}).status_code
        == 200
    )
    assert (
        client.post(
            path + "/loads", json=gravity(geometry), headers={"If-Match": '"2"'}
        ).status_code
        == 200
    )
    response = client.post(
        path + "/loads",
        json=gravity(geometry, acceleration=[0, 0, 9.80665]),
        headers={"If-Match": '"3"'},
    )
    assert response.status_code == 409 and response.json()["code"] == "load_overlap"
    combined = client.post(
        path + "/loads",
        json=gravity(geometry, acceleration=[0, 0, 9.80665], combine_confirmed=True),
        headers={"If-Match": '"3"'},
    )
    assert combined.status_code == 200, combined.text
    state = combined.json()
    assert state["total_force_n"] == pytest.approx([0, 0, 0], abs=1e-10)
    assert state["force_scale_n"] == pytest.approx(2 * 76982.2025, abs=1e-8)
    assert any("explicitly combined" in x for x in state["warnings"])


def test_prescribed_duplicate_and_conflicting_component_guards_keep_head_unchanged(
    client: TestClient,
    application: FastAPI,
) -> None:
    path, geometry = fixture(client, application)
    item = {
        "assignment": {
            "kind": "displacement",
            "name": "x support",
            "geometry_revision_id": geometry["id"],
            "face_ids": ["small"],
            "units": "m-N-Pa",
            "axis": "x",
            "displacement": 0,
        }
    }
    for revision in (1, 2):
        assert (
            client.post(
                path + "/loads", json=item, headers={"If-Match": f'"{revision}"'}
            ).status_code
            == 200
        )
    item["assignment"]["displacement"] = 0.01
    response = client.post(path + "/loads", json=item, headers={"If-Match": '"3"'})
    assert response.status_code == 422 and response.json()["code"] == "conflicting_constraints"
    assert client.get(path).json()["revision"] == 3


@pytest.mark.parametrize("fault", ["body", "zero", "bool", "raw_deck", "axis"])
def test_bad_body_component_inputs_and_executable_fields_fail_closed(
    client: TestClient,
    application: FastAPI,
    fault: str,
) -> None:
    path, geometry = fixture(client, application, centroid=True)
    item = gravity(geometry)
    if fault == "body":
        item["assignment"]["body_ids"] = ["foreign"]
    elif fault == "zero":
        item["assignment"]["acceleration"] = [0, 0, 0]
    elif fault == "bool":
        item["assignment"]["acceleration"] = [True, 0, 0]
    elif fault == "raw_deck":
        item["assignment"]["command"] = "*INCLUDE"
    else:
        item = {
            "assignment": {
                "kind": "displacement",
                "name": "unsupported",
                "geometry_revision_id": geometry["id"],
                "face_ids": ["small"],
                "units": "m-N-Pa",
                "axis": "normal",
                "displacement": 0,
            }
        }
    assert client.post(path + "/loads", json=item, headers={"If-Match": '"1"'}).status_code == 422
    assert client.get(path).json()["revision"] == 1


def test_gravity_component_owner_csrf_revision_and_immutable_unit_carry_forward(
    client: TestClient,
    application: FastAPI,
) -> None:
    path, geometry = fixture(client, application, centroid=True)
    item = gravity(geometry)
    assert client.post(path + "/loads", json=item).status_code == 428
    assert (
        client.post(
            path + "/loads", json=item, headers={"If-Match": '"1"', "X-CSRF-Token": "bad"}
        ).status_code
        == 403
    )
    saved = client.post(path + "/loads", json=item, headers={"If-Match": '"1"'}).json()["setup"]
    assert client.post(path + "/loads", json=item, headers={"If-Match": '"1"'}).status_code == 409
    assert (
        client.patch(
            path + "/display-units", json={"preset": "inch-lbf-psi"}, headers={"If-Match": '"2"'}
        ).status_code
        == 200
    )
    assert client.get(path + "/loads").json()["setup"] == saved
    store = application.state.repository
    with store.write() as connection:
        with pytest.raises(IntegrityError, match="immutable"):
            connection.exec_driver_sql("UPDATE analysis_load_setups SET setup_json='{}'")
        foreign = str(uuid4())
        connection.exec_driver_sql("INSERT INTO users VALUES (?,NULL,'test')", (foreign,))
        connection.exec_driver_sql(
            "UPDATE projects SET owner_id=? WHERE id=?", (foreign, geometry["project_id"])
        )
    assert client.get(path + "/loads").status_code == 404
    assert client.post(path + "/loads", json=item, headers={"If-Match": '"3"'}).status_code == 404
