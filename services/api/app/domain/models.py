"""T007 metadata contracts; no unvalidated engineering settings or executable inputs."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, JsonValue, model_validator

from app.domain.base import StrictModel

Name = Annotated[str, Field(min_length=1, max_length=200)]
Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
CatalogID = Annotated[str, Field(min_length=1, max_length=200)]


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


class CatalogVertex(StrictModel):
    id: CatalogID
    body_id: CatalogID
    point_m: tuple[float, float, float]
    face_ids: list[CatalogID]


class CatalogEdge(StrictModel):
    id: CatalogID
    body_id: CatalogID
    curve_type: str
    face_ids: list[CatalogID]
    vertex_ids: list[CatalogID]
    start_m: tuple[float, float, float] | None = None
    end_m: tuple[float, float, float] | None = None


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
    edges: list[CatalogEdge] = Field(default_factory=list, max_length=20000)
    vertices: list[CatalogVertex] = Field(default_factory=list, max_length=20000)
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
        vertices = {v.id for v in self.vertices}
        if len(vertices) != len(self.vertices) or len({e.id for e in self.edges}) != len(
            self.edges
        ):
            raise ValueError("Direction catalog identities must be unique")
        face_owners = {face.id: face.body_id for face in self.faces}
        vertex_owners = {vertex.id: vertex.body_id for vertex in self.vertices}
        direction_entities: list[CatalogVertex | CatalogEdge] = [*self.vertices, *self.edges]
        for entity in direction_entities:
            if entity.body_id not in bodies or not set(entity.face_ids) <= faces:
                raise ValueError("Direction catalog references must belong to this geometry")
            if any(face_owners[ref] != entity.body_id for ref in entity.face_ids):
                raise ValueError("Direction catalog cannot cross body ownership")
        for edge in self.edges:
            if not set(edge.vertex_ids) <= vertices:
                raise ValueError("Direction edge vertex reference does not resolve")
            if any(vertex_owners[ref] != edge.body_id for ref in edge.vertex_ids):
                raise ValueError("Direction edge cannot cross body vertex ownership")
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


class AnalysisRestore(StrictModel):
    target_revision: int = Field(ge=1)


class ConflictCopy(StrictModel):
    source_revision: int = Field(ge=1)
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
