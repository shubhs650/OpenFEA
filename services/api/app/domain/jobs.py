"""Local durable job DTOs and immutable run inputs; no hosted billing policy."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, JsonValue

from app.domain.base import StrictModel
from app.domain.imports import GeometryDisplay
from app.domain.loads import DeckSnapshot
from app.domain.models import Hash

Status = Literal[
    "queued", "running", "cancelling", "cancelled", "succeeded", "failed", "interrupted"
]
Stage = Literal["queued", "meshing", "solving", "validating", "finished"]
TERMINAL = {"cancelled", "succeeded", "failed", "interrupted"}


class MeshRequest(StrictModel):
    pass


class RunRequest(StrictModel):
    mesh_job_id: UUID


class MeshSource(StrictModel):
    job_id: UUID
    sha256: Hash


class JobInput(StrictModel):
    schema_version: Literal[1] = 1
    kind: Literal["mesh", "solve"]
    snapshot: DeckSnapshot
    display: GeometryDisplay
    policy: dict[str, JsonValue]
    mesh: MeshSource | None = None
    deck_sha256: Hash | None = None


class Artifact(StrictModel):
    sha256: Hash
    size_bytes: int = Field(ge=0, le=32 * 1024**2)
    media_type: Literal["application/json", "text/plain"]


class JobEvent(StrictModel):
    sequence: int
    status: Status
    stage: Stage
    at: datetime
    reason_code: str | None


class LocalJob(StrictModel):
    id: UUID
    analysis_id: UUID
    project_id: UUID
    analysis_revision: int
    geometry_revision_id: UUID
    kind: Literal["mesh", "solve"]
    mesh_job_id: UUID | None
    input_sha256: Hash
    status: Status
    stage: Stage
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    heartbeat_at: datetime | None
    cancel_requested: bool
    reason_code: str | None
    reason_message: str | None
    summary: dict[str, JsonValue]
    artifacts: dict[str, Artifact]
    events: list[JobEvent]


class MeshPreview(StrictModel):
    job_id: UUID
    analysis_id: UUID
    geometry_revision_id: UUID
    nodes: int
    elements: int
    display: GeometryDisplay
