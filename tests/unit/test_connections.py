"""Immutable reviewed setup, explicit physical tolerance and backward-compatible history."""

from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.domain.connections import BondAssignment, BondPair, BondReport, BondRequest, validate_pair
from app.domain.errors import DomainError
from tests.unit import test_face_loads as loads
from worker.gap_fixture import run_b08

application = loads.application
client = loads.client


def pair(gap: float = 1e-5) -> BondPair:
    return BondPair(
        master_face_id="master",
        slave_face_id="slave",
        gap_m=gap,
        normal_dot=-1,
        overlap_area_m2=1,
        master_coverage=1,
        slave_coverage=1,
        master_normal=(1, 0, 0),
        slave_normal=(-1, 0, 0),
        master_center_m=(1, 0.5, 0.5),
        slave_center_m=(1 + gap, 0.5, 0.5),
        eligible=True,
    )


def payload(geometry_id: UUID) -> dict[str, Any]:
    return dict(
        geometry_revision_id=geometry_id,
        name="Explicit gap",
        master_face_id="master",
        slave_face_id="slave",
        gap_tolerance_m=1e-5,
        gap_approved=True,
        assumptions_confirmed=True,
    )


@pytest.mark.parametrize(
    "change", [{"gap_approved": False}, {"gap_tolerance_m": 0}, {"assumptions_confirmed": False}]
)
def test_physical_gap_needs_independent_tolerance_and_review(change: dict[str, Any]) -> None:
    value = BondRequest(**{**payload(uuid4()), **change})
    with pytest.raises(DomainError):
        validate_pair(value, pair())
    validate_pair(BondRequest(**payload(uuid4())), pair())


@pytest.mark.parametrize("tolerance", [1e-4, -1, float("nan"), float("inf")])
def test_unbounded_or_nonfinite_gap_refused(tolerance: float) -> None:
    with pytest.raises(ValidationError):
        BondRequest(**{**payload(uuid4()), "gap_tolerance_m": tolerance})


def test_coincidence_still_requires_review_and_partial_pair_cannot_approve() -> None:
    value = BondRequest(**{**payload(uuid4()), "gap_tolerance_m": 0, "gap_approved": False})
    validate_pair(value, pair(0))
    with pytest.raises(DomainError, match="Partial"):
        validate_pair(
            value, pair(0).model_copy(update={"eligible": False, "blocker": "Partial coverage"})
        )


def test_saved_bonds_carry_through_edits_restore_and_independent_copy(
    client: TestClient, application: FastAPI
) -> None:
    path, geometry = loads.fixture(client, application)
    store, owner = application.state.repository, application.state.owner
    identifier = UUID(path.split("/")[-1])
    report = BondReport(
        pairs=[pair()], overlaps=[], runtime={"test_only": True}, policy={"synthetic": True}
    )
    item = BondAssignment(
        **payload(UUID(geometry["id"])),
        id=uuid4(),
        pair=pair(),
        review_report=report,
        review_sha256="a" * 64,
    )
    store.edit_bonds(owner, identifier, 1, item)
    original = client.get(path + "/bonds").json()["setup"]
    assert (
        client.patch(path, json={"name": "Another tab"}, headers={"If-Match": '"2"'}).status_code
        == 200
    )
    assert client.get(path + "/bonds").json()["setup"] == original
    assert (
        client.delete(path + "/bonds/" + str(item.id), headers={"If-Match": '"3"'}).status_code
        == 200
    )
    assert (
        client.post(
            path + "/restores", json={"target_revision": 2}, headers={"If-Match": '"4"'}
        ).status_code
        == 200
    )
    assert client.get(path + "/bonds").json()["setup"] == original
    copy = client.post(
        path + "/duplicates",
        json={"source_revision": 2, "name": "Copy bonds"},
        headers={"If-Match": '"5"'},
    ).json()
    assert client.get(f"/api/v1/analyses/{copy['id']}/bonds").json()["setup"] == original
    assert client.get(path + "/revisions/1/bonds").json()["setup"]["assignments"] == []
    with pytest.raises(IntegrityError), store.write() as connection:
        connection.execute(
            text("UPDATE analysis_bond_setups SET setup_json='{}' WHERE analysis_id=:id"),
            {"id": str(identifier)},
        )
    # Simulate the trusted geometry-change publication path: saved references stay
    # auditable, but cannot be approved for a different pinned geometry.
    from app.domain.models import AnalysisCreate
    from app.persistence.repository import now

    with store.write() as connection:
        store._insert_analysis_revision(
            connection,
            UUID(copy["id"]),
            UUID(copy["project_id"]),
            2,
            AnalysisCreate(name="Geometry changed"),
            now(),
        )
        connection.execute(
            text("UPDATE analyses SET head_revision=2 WHERE id=:id"), {"id": copy["id"]}
        )
    invalid = store.bond_state(owner, UUID(copy["id"]))
    assert invalid.review_required == [item.id]
    assert invalid.setup.model_dump(mode="json") == original
    assert "changed geometry" in invalid.solve_blockers[0]


def test_unsigned_b08_stops_before_native_execution(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="review pending"):
        run_b08(tmp_path / "absent")
    assert not (tmp_path / "absent").exists()


def test_legacy_mesh_schema_upgrade_preserves_setup_and_empty_bonds(tmp_path: Path) -> None:
    from app.domain.models import AnalysisCreate, ProjectCreate
    from app.persistence.database import Database
    from app.persistence.repository import Repository

    database = Database(tmp_path / "legacy.sqlite3")
    database.migrate("0007_mesh_setups")
    store = Repository(database)
    owner = store.local_owner()
    project = store.create_project(owner, ProjectCreate(name="Legacy project"))
    analysis = store.create_analysis(owner, project.id, 1, AnalysisCreate(name="Legacy setup"))
    database.migrate()
    assert store.get_analysis(owner, analysis.id) == analysis
    assert store.bond_state(owner, analysis.id).setup.assignments == []
    database.close()
