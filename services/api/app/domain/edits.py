"""Bounded cleanup previews and explicit revision/assignment review contracts."""

from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.domain.base import StrictModel
from app.domain.models import Analysis, CatalogID, GeometryMetadata, GeometryRevision, Project


class EditCreate(StrictModel):
    operation: Literal["remove_feature"]
    face_id: CatalogID
    analysis_id: UUID | None = None
    analysis_revision: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def paired_analysis(self) -> "EditCreate":
        if (self.analysis_id is None) != (self.analysis_revision is None):
            raise ValueError("Analysis identity and revision are required together")
        return self


class FaceMapping(StrictModel):
    source_face_id: CatalogID
    target_face_id: CatalogID | None
    status: Literal["unchanged", "removed", "changed_or_ambiguous"]


class EditPreview(StrictModel):
    feature: Literal["hole", "fillet"]
    original_volume_m3: float
    preview_volume_m3: float
    volume_delta_m3: float
    expected_delta_m3: float
    mappings: list[FaceMapping]


class GeometryEdit(StrictModel):
    id: UUID
    project_id: UUID
    project_revision: int
    source_geometry_id: UUID
    request: EditCreate
    status: Literal["ready", "failed", "committed", "undone"]
    metadata: GeometryMetadata | None = None
    preview: EditPreview | None = None
    error: str | None = None
    result_geometry_id: UUID | None = None
    result_analysis_revision: int | None = None
    result_project_revision: int | None = None


class EditCommit(StrictModel):
    preview_id: UUID
    reviewed: Literal[True]


class EditResult(StrictModel):
    project: Project
    geometry: GeometryRevision
    analysis: Analysis | None


class ReselectFaces(StrictModel):
    geometry_revision_id: UUID
    face_ids: list[CatalogID] = Field(min_length=1, max_length=200)
    reviewed: Literal[True]
    combine_confirmed: bool = False


class ReselectBodies(StrictModel):
    geometry_revision_id: UUID
    body_ids: list[CatalogID] = Field(min_length=1, max_length=10)
    reviewed: Literal[True]
    combine_confirmed: bool = False
