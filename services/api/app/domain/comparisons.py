"""Bounded immutable two-run physical-sample comparison and export contract."""

from typing import Literal
from uuid import UUID

from pydantic import Field, FiniteFloat

from app.domain.base import StrictModel
from app.domain.models import Hash
from app.domain.results import (
    AssumptionNote,
    FieldKey,
    InspectionVertex,
    ResultIdentity,
    ResultSample,
    Vector,
)


class ComparisonPoint(StrictModel):
    label: str = Field(min_length=1, max_length=100)
    body_id: str = Field(min_length=1, max_length=200)
    point_m: Vector
    reference_element_id: int = Field(gt=0)
    compared_element_id: int = Field(gt=0)


class ComparisonRequest(StrictModel):
    compared_run_id: UUID
    field: FieldKey
    smoothed: bool = False
    points: list[ComparisonPoint] = Field(min_length=1, max_length=8)


class ValueChange(StrictModel):
    reference: FiniteFloat
    compared: FiniteFloat
    signed_change: FiniteFloat
    absolute_change: FiniteFloat
    relative_change: FiniteFloat | None


class ComparisonRow(StrictModel):
    sample: ComparisonPoint
    reference: InspectionVertex
    compared: InspectionVertex
    change: ValueChange


class ComparisonRun(StrictModel):
    source: ResultIdentity
    elements: int
    nodes: int
    warnings: list[str]
    assumptions: list[AssumptionNote]
    raw_peak: ResultSample


class ResultComparison(StrictModel):
    schema_version: Literal[1] = 1
    processor: str
    sample_location: Literal["element_interpolated"] = "element_interpolated"
    tensor_components: tuple[
        Literal["xx"], Literal["yy"], Literal["zz"], Literal["xy"], Literal["yz"], Literal["zx"]
    ] = ("xx", "yy", "zz", "xy", "yz", "zx")
    principal_order: Literal["s1 >= s2 >= s3 (algebraic)"] = "s1 >= s2 >= s3 (algebraic)"
    physics_sha256: Hash
    field: FieldKey
    smoothed: bool
    unit: Literal["m", "Pa"]
    frame: Literal["global_cartesian"]
    reference_floor: FiniteFloat
    method: str
    convergence_claim: Literal[False] = False
    reference: ComparisonRun
    compared: ComparisonRun
    rows: list[ComparisonRow]
    raw_peak_change: ValueChange
    warnings: list[str]
