"""T007 metadata contracts; no unvalidated engineering settings or executable inputs."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

Name = Annotated[str, Field(min_length=1, max_length=200)]
Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
CatalogID = Annotated[str, Field(min_length=1, max_length=200)]


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, frozen=True, allow_inf_nan=False
    )


class ErrorResponse(StrictModel):
    code: str
    message: str
    field_errors: dict[str, str] = Field(default_factory=dict)
    retryable: bool = False
    request_id: str


class ProjectCreate(StrictModel):
    name: Name


class Project(StrictModel):
    id: UUID
    owner_id: UUID
    name: Name
    revision: int
    created_at: datetime
    updated_at: datetime


class ProjectPage(StrictModel):
    items: list[Project]
    total: int
    offset: int
    limit: int


class CatalogBody(StrictModel):
    id: CatalogID


class CatalogFace(StrictModel):
    id: CatalogID
    body_id: CatalogID
    signature: dict[str, JsonValue]
    neighbors: list[CatalogID] = Field(default_factory=list)


class UnitsDecision(StrictModel):
    source_length_unit: Literal["m", "mm", "inch"]
    canonical_length_unit: Literal["m"] = "m"
    confirmed: Literal[True]


class GeometryMetadata(StrictModel):
    """Only the trusted CAD adapter may register metadata after validating its bytes."""

    source_sha256: Hash
    brep_sha256: Hash
    units: UnitsDecision
    bodies: list[CatalogBody] = Field(min_length=1)
    faces: list[CatalogFace] = Field(min_length=1)
    edit_recipe: dict[str, JsonValue] = Field(default_factory=dict)
    validation: dict[str, JsonValue]

    @model_validator(mode="after")
    def catalog_consistent(self) -> "GeometryMetadata":
        bodies = {body.id for body in self.bodies}
        faces = {face.id for face in self.faces}
        if len(bodies) != len(self.bodies) or len(faces) != len(self.faces):
            raise ValueError("Catalog identities must be unique")
        for face in self.faces:
            if face.body_id not in bodies or not set(face.neighbors) <= faces:
                raise ValueError("Catalog references must resolve in this geometry revision")
        return self


class GeometryRevision(GeometryMetadata):
    id: UUID
    project_id: UUID
    parent_id: UUID | None
    created_at: datetime


class GeometryPage(StrictModel):
    items: list[GeometryRevision]
    total: int
    offset: int
    limit: int


class AnalysisCreate(StrictModel):
    name: Name
    geometry_revision_id: UUID | None = None


class AnalysisPatch(StrictModel):
    name: Name


class Analysis(AnalysisCreate):
    id: UUID
    project_id: UUID
    revision: int
    status: Literal["draft"] = "draft"
    created_at: datetime
    updated_at: datetime


class AnalysisPage(StrictModel):
    items: list[Analysis]
    total: int
    offset: int
    limit: int


class LocalSession(StrictModel):
    owner_id: UUID
    mode: Literal["local"] = "local"
    csrf_token: str
