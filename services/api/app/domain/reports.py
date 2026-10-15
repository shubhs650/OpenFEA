"""Immutable, renderer-independent report facts and validated saved view definitions."""

import math
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, JsonValue, model_validator

from app.domain.base import StrictModel
from app.domain.comparisons import ComparisonRequest, ResultComparison
from app.domain.jobs import JobInput
from app.domain.models import Hash
from app.domain.results import AssumptionNote, FieldKey, ResultIdentity, SectionRequest, Vector
from app.domain.units import PRESETS, PresetID


class ReportCamera(StrictModel):
    # Coordinates use the result viewport's model-centred metre frame.
    position: Vector
    focal: Vector
    up: Vector
    parallel: bool
    parallel_scale: float = Field(gt=0, le=1e12)
    angle: float = Field(ge=1, le=120)

    @model_validator(mode="after")
    def basis(self) -> "ReportCamera":
        direction = [b - a for a, b in zip(self.position, self.focal, strict=True)]
        cross = [
            direction[1] * self.up[2] - direction[2] * self.up[1],
            direction[2] * self.up[0] - direction[0] * self.up[2],
            direction[0] * self.up[1] - direction[1] * self.up[0],
        ]
        if not all(math.isfinite(v) for v in (*direction, *cross)) or math.hypot(*cross) < 1e-20:
            raise ValueError("Camera needs a finite nondegenerate basis")
        if max(abs(v) for v in (*self.position, *self.focal, *self.up)) > 1e12:
            raise ValueError("Camera coordinates exceed report bounds")
        return self


class ReportViewDefinition(StrictModel):
    field: FieldKey
    smoothed: bool = False
    deformation_scale: float = Field(ge=0, le=1e6)
    range_si: tuple[float, float]
    visible_body_ids: list[str] = Field(min_length=1, max_length=10)
    camera: ReportCamera
    section: SectionRequest | None = None

    @model_validator(mode="after")
    def range_valid(self) -> "ReportViewDefinition":
        low, high = self.range_si
        if not math.isfinite(high - low):
            raise ValueError("Contour span must be finite")
        if low > high or (self.field in ("displacement", "von_mises") and low < 0):
            raise ValueError("Invalid contour range")
        if len(set(self.visible_body_ids)) != len(self.visible_body_ids):
            raise ValueError("Duplicate visible bodies")
        return self


class ReportRequest(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    units: PresetID
    views: list[ReportViewDefinition] = Field(min_length=1, max_length=4)
    user_conclusion: str = Field(default="", max_length=4000)
    comparison: ComparisonRequest | None = None

    @model_validator(mode="after")
    def finite_display_limits(self) -> "ReportRequest":
        preset = PRESETS[self.units]
        for view in self.views:
            displacement = view.field in ("displacement", "ux", "uy", "uz")
            factor = (preset.length if displacement else preset.stress).to_si
            if not all(math.isfinite(v / factor) for v in view.range_si):
                raise ValueError("Contour limits must be finite in report units")
        return self


class ReportTable(StrictModel):
    title: str
    columns: list[str]
    rows: list[list[str]]


class ReportFigure(StrictModel):
    caption: str
    svg: str  # Trusted generator output only; never accepted from an HTTP request.


class ReportModel(StrictModel):
    schema_version: Literal[1] = 1
    id: UUID
    created_at: datetime
    project_id: UUID
    project_name: str
    run_finished_at: datetime
    request: ReportRequest
    source: ResultIdentity
    frozen_input: JobInput
    generator: dict[str, str]
    run_summary: dict[str, JsonValue]
    mesh_summary: dict[str, JsonValue]
    tables: list[ReportTable]
    figures: list[ReportFigure]
    warnings: list[str]
    assumptions: list[AssumptionNote]
    comparison: ResultComparison | None
    limitations: list[str]


class ReportRecord(StrictModel):
    id: UUID
    job_id: UUID
    project_id: UUID
    created_at: datetime
    title: str
    model_sha256: Hash
    html_sha256: Hash
    pdf_sha256: Hash
    renderer: dict[str, str]
