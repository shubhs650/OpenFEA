"""Bounded STEP import and immutable display contracts."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from app.domain.base import StrictModel
from app.domain.models import Hash

MAX_UPLOAD_BYTES = 16 * 1024 * 1024
LengthUnit = Literal["m", "mm", "inch"]
Vector = tuple[float, float, float]
Bounds = tuple[float, float, float, float, float, float]


class UploadCreate(StrictModel):
    size_bytes: Annotated[int, Field(gt=0, le=MAX_UPLOAD_BYTES)]
    sha256: Hash


class Upload(UploadCreate):
    id: UUID
    project_id: UUID
    status: Literal["pending", "uploading", "complete", "failed"]
    created_at: datetime


class ImportCreate(StrictModel):
    upload_id: UUID
    source_length_unit: LengthUnit | None = None


class ImportConfirm(StrictModel):
    dimensions_confirmed: Literal[True]


class BodyDisplay(StrictModel):
    id: str
    volume_m3: float
    bounds_m: Bounds
    center_m: Vector | None = None


class FaceDisplay(StrictModel):
    id: str
    body_id: str
    points_m: list[Vector]
    triangles: list[tuple[int, int, int]]


class GeometryDisplay(StrictModel):
    schema_version: Literal[1] = 1
    brep_sha256: Hash
    lod: Literal["coarse", "fine"]
    bodies: list[BodyDisplay]
    faces: list[FaceDisplay]


class ImportInspection(StrictModel):
    source_length_unit: LengthUnit | None
    unit_origin: Literal["step_metadata", "explicit_missing_metadata"] | None
    detected_length_units: list[str]
    bounds_m: Bounds | None = None
    body_count: int = 0
    face_count: int = 0
    coarse_triangles: int = 0
    fine_triangles: int = 0
    warnings: list[str] = Field(default_factory=list)


class GeometryImport(StrictModel):
    id: UUID
    project_id: UUID
    upload_id: UUID
    project_revision: int
    status: Literal["processing", "needs_units", "ready", "failed", "committed"]
    inspection: ImportInspection | None = None
    geometry_revision_id: UUID | None = None
    error_code: str | None = None
    error_message: str | None = None
