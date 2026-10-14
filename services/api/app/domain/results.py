"""SI core result views explicitly separating raw extrema and derived contours."""

from typing import Literal
from uuid import UUID

from pydantic import FiniteFloat

from app.domain.base import StrictModel
from app.domain.models import Hash

Vector = tuple[FiniteFloat, FiniteFloat, FiniteFloat]


class ResultVertex(StrictModel):
    node_id: int
    element_id: int
    body_id: str
    material_id: str
    face_id: str
    position_m: Vector
    displacement_m: Vector
    von_mises_pa: FiniteFloat


class ResultSample(StrictModel):
    value: FiniteFloat
    location: Literal["node", "integration_point"]
    position_m: Vector
    node_id: int | None
    element_id: int | None
    integration_point_id: int | None
    body_id: str | None


class ResultExtrema(StrictModel):
    minimum: ResultSample
    maximum: ResultSample


class YieldFactor(StrictModel):
    body_id: str
    material_id: str
    material_name: str
    yield_strength_pa: FiniteFloat | None
    state: Literal["finite", "unavailable", "unbounded"]
    minimum: FiniteFloat | None
    critical_sample: ResultSample


class BodyReaction(StrictModel):
    body_id: str
    node_count: int
    constrained_dof_count: int
    force_n: Vector
    moment_nm: Vector


class BalanceCheck(StrictModel):
    residual: Vector
    residual_norm: FiniteFloat
    reference: FiniteFloat
    relative_residual: FiniteFloat | None
    criterion: Literal["absolute", "relative"]
    absolute_tolerance: FiniteFloat
    relative_tolerance: FiniteFloat
    tolerance: FiniteFloat
    passed: bool


class EquilibriumData(StrictModel):
    passed: bool
    applied_force_n: Vector
    applied_moment_nm: Vector
    reaction_force_n: Vector
    reaction_moment_nm: Vector
    moment_origin_m: Vector
    characteristic_length_m: FiniteFloat
    prescribed_actuator_reference_n: FiniteFloat
    force: BalanceCheck
    moment: BalanceCheck
    method: str


class ResultData(StrictModel):
    processor: str
    vertices: list[ResultVertex]
    triangles: list[tuple[int, int, int]]
    displacement: ResultExtrema
    von_mises: ResultExtrema
    yield_factors: list[YieldFactor]
    zero_stress_pa: FiniteFloat
    reactions: list[BodyReaction]
    reaction_force_n: Vector
    reaction_moment_nm: Vector
    moment_origin_m: Vector
    reaction_method: str
    equilibrium: EquilibriumData
    warnings: list[str]
    stress_method: str
    extrema_method: str


class ResultView(StrictModel):
    schema_version: Literal[1] = 1
    job_id: UUID
    analysis_id: UUID
    analysis_revision: int
    geometry_revision_id: UUID
    input_sha256: Hash
    results_sha256: Hash
    mesh_sha256: Hash
    deck_sha256: Hash
    dat_sha256: Hash
    processor_sources: dict[str, Hash]
    data: ResultData
