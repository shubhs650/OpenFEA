"""Saved connection review is separate from mesh-dependent solver admission."""

from typing import Any
from uuid import UUID

from pydantic import Field

from app.domain.base import StrictModel
from app.domain.errors import DomainError
from app.domain.models import CatalogID, Hash, Name

COINCIDENCE_M = 1e-8
MAX_GAP_M = 1e-5
POLICY = "planar-unit-complete-b08-v1"


class BondPair(StrictModel):
    master_face_id: CatalogID
    slave_face_id: CatalogID
    gap_m: float = Field(ge=0)
    normal_dot: float
    overlap_area_m2: float = Field(gt=0)
    master_coverage: float
    slave_coverage: float
    master_normal: tuple[float, float, float]
    slave_normal: tuple[float, float, float]
    master_center_m: tuple[float, float, float]
    slave_center_m: tuple[float, float, float]
    eligible: bool
    blocker: str | None = None


class BodyOverlap(StrictModel):
    body_ids: list[CatalogID]
    volume_m3: float = Field(gt=0)


class BondReport(StrictModel):
    policy: dict[str, Any]
    pairs: list[BondPair]
    overlaps: list[BodyOverlap]
    runtime: dict[str, Any]


class BondRequest(StrictModel):
    geometry_revision_id: UUID
    name: Name
    master_face_id: CatalogID
    slave_face_id: CatalogID
    gap_tolerance_m: float = Field(ge=0, le=MAX_GAP_M)
    gap_approved: bool = False
    assumptions_confirmed: bool


class BondAssignment(BondRequest):
    id: UUID
    pair: BondPair
    review_report: BondReport
    review_sha256: Hash
    policy: str = POLICY


class BondSetup(StrictModel):
    assignments: list[BondAssignment] = Field(default_factory=list, max_length=10)


class BondState(StrictModel):
    analysis_id: UUID
    analysis_revision: int
    geometry_revision_id: UUID | None
    setup: BondSetup
    review_required: list[UUID]
    solve_blockers: list[str]


class BondCandidates(StrictModel):
    analysis_id: UUID
    analysis_revision: int
    geometry_revision_id: UUID
    report_sha256: Hash
    report: BondReport
    coincidence_m: float = COINCIDENCE_M
    max_gap_m: float = MAX_GAP_M
    policy: str = POLICY


def validate_pair(payload: BondRequest, pair: BondPair) -> None:
    if not payload.assumptions_confirmed:
        raise DomainError(422, "bond_review_required", "Confirm the experimental bond assumptions")
    if not pair.eligible:
        raise DomainError(422, "unsupported_bond", pair.blocker or "Unsupported pair")
    if pair.gap_m > COINCIDENCE_M and (
        not payload.gap_approved or payload.gap_tolerance_m + 1e-12 < pair.gap_m
    ):
        raise DomainError(
            422,
            "gap_approval_required",
            "Explicitly approve a tolerance covering the measured physical gap",
        )


class AssemblyComponent(StrictModel):
    body_ids: list[CatalogID]
    support_rank: int = Field(ge=0, le=6)


class AssemblyPreflight(StrictModel):
    components: list[AssemblyComponent] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    mesh_checked: bool = False
    stability_proven: bool = False
    expected_free_equations: int | None = None
    intended_slave_nodes: int = 0
