"""SI core result views explicitly separating raw extrema and derived contours."""

from typing import Literal
from uuid import UUID

from pydantic import Field, FiniteFloat, model_validator

from app.domain.base import StrictModel
from app.domain.models import Hash

Vector = tuple[FiniteFloat, FiniteFloat, FiniteFloat]
Tensor = tuple[FiniteFloat, FiniteFloat, FiniteFloat, FiniteFloat, FiniteFloat, FiniteFloat]
FieldKey = Literal[
    "displacement",
    "ux",
    "uy",
    "uz",
    "von_mises",
    "sxx",
    "syy",
    "szz",
    "sxy",
    "syz",
    "szx",
    "s1",
    "s2",
    "s3",
]


class StressValues(StrictModel):
    tensor_pa: Tensor
    principal_pa: Vector
    von_mises_pa: FiniteFloat


class ResultVertex(StrictModel):
    node_id: int
    element_id: int
    body_id: str
    material_id: str
    face_id: str
    position_m: Vector
    displacement_m: Vector
    von_mises_pa: FiniteFloat
    stress: StressValues
    smoothed_stress: StressValues
    smoothed_contributions: int


class ResultSample(StrictModel):
    value: FiniteFloat
    location: Literal["node", "integration_point"]
    position_m: Vector
    node_id: int | None
    element_id: int | None
    integration_point_id: int | None
    body_id: str | None
    material_id: str | None


class ResultExtrema(StrictModel):
    minimum: ResultSample
    maximum: ResultSample


class ResultField(StrictModel):
    key: FieldKey
    label: str
    unit: Literal["m", "Pa"]
    raw_location: Literal["node", "integration_point"]
    extrema: ResultExtrema


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
    fields: list[ResultField]
    frame: Literal["global_cartesian"]
    tensor_components: tuple[
        Literal["xx"], Literal["yy"], Literal["zz"], Literal["xy"], Literal["yz"], Literal["zx"]
    ]
    principal_order: Literal["s1 >= s2 >= s3 (algebraic)"]
    smoothing_method: str
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


class ResultIdentity(StrictModel):
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


class ResultView(ResultIdentity):
    data: ResultData


class ProbeRequest(StrictModel):
    element_id: int = Field(gt=0)
    point_m: Vector


class SectionRequest(StrictModel):
    point_m: Vector
    normal: Vector

    @model_validator(mode="after")
    def nonzero_normal(self) -> "SectionRequest":
        if max(abs(v) for v in self.normal) == 0:
            raise ValueError("A section normal must be nonzero")
        return self


class InspectionVertex(StrictModel):
    element_id: int
    body_id: str
    material_id: str
    position_m: Vector
    barycentric: tuple[FiniteFloat, FiniteFloat, FiniteFloat, FiniteFloat]
    displacement_m: Vector
    stress: StressValues
    smoothed_stress: StressValues


class ResultInspection(ResultIdentity):
    frame: Literal["global_cartesian"]
    tensor_components: tuple[
        Literal["xx"], Literal["yy"], Literal["zz"], Literal["xy"], Literal["yz"], Literal["zx"]
    ]
    principal_order: Literal["s1 >= s2 >= s3 (algebraic)"]
    kind: Literal["probe", "section"]
    processor: str
    location: Literal["element_interpolated"]
    method: str
    point_m: Vector
    normal: Vector | None
    vertices: list[InspectionVertex]
    triangles: list[tuple[int, int, int]]
