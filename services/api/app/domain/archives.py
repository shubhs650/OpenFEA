"""Strict portable data contracts. Historical files never enter the executable job queue."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.domain.base import StrictModel
from app.domain.connections import BondSetup
from app.domain.loads import LoadSetup
from app.domain.materials import MaterialSetup
from app.domain.mesh import MeshSetup
from app.domain.models import Analysis, GeometryRevision, Hash, Name, Project

MAX_ARCHIVE = 64 * 1024**2
MAX_EXPANDED = 128 * 1024**2
MAX_FILES = 512


class ArchiveOptions(StrictModel):
    include_outputs: bool = Field(default=False, strict=True)


class DiagnosticOptions(StrictModel):
    include_geometry: bool = Field(default=False, strict=True)
    include_results: bool = Field(default=False, strict=True)


class ArchiveAnalysis(StrictModel):
    analysis: Analysis
    materials: MaterialSetup
    loads: LoadSetup
    mesh: MeshSetup
    bonds: BondSetup


class HistoricalItem(StrictModel):
    id: UUID
    kind: Literal["job", "report", "word"]
    analysis_id: UUID
    geometry_revision_id: UUID
    source_id: UUID
    related_ids: list[UUID] = Field(default_factory=list, max_length=10)
    files: dict[str, Hash] = Field(default_factory=dict, max_length=64)
    omitted: dict[str, Literal["not_selected", "unavailable"]] = Field(default_factory=dict)


class PortableProject(StrictModel):
    schema_version: Literal[1] = 1
    name: Name
    source_project_id: UUID
    geometries: list[GeometryRevision] = Field(default_factory=list, max_length=8)
    analyses: list[ArchiveAnalysis] = Field(default_factory=list, max_length=256)
    history: list[HistoricalItem] = Field(default_factory=list, max_length=100)


class FileEntry(StrictModel):
    sha256: Hash
    size_bytes: int = Field(ge=0, le=32 * 1024**2)


class ArchiveManifest(StrictModel):
    schema_version: Literal[1] = 1
    kind: Literal["project", "diagnostic"]
    created_at: datetime
    files: dict[str, FileEntry] = Field(max_length=MAX_FILES)
    tools: dict[str, str] = Field(max_length=20)
    omitted: list[str] = Field(default_factory=list, max_length=2000)
    labels: dict[str, str] = Field(default_factory=dict, max_length=MAX_FILES)
    required_migrations: list[str] = Field(default_factory=list, max_length=0)


class BundleRecord(StrictModel):
    id: UUID
    project_id: UUID
    kind: Literal["project", "diagnostic"]
    created_at: datetime
    sha256: Hash
    size_bytes: int
    manifest: ArchiveManifest
    notice: str


class ImportedArchive(StrictModel):
    id: UUID
    project: Project
    archive_sha256: Hash
    id_map: dict[str, UUID]
    history: list[HistoricalItem]
    notice: str = (
        "Imported historical files are read-only, untrusted provenance, never executable. "
        "CAD derivatives are rebuilt; flagged geometry directions require review. "
        "Re-solve uses current tools and a new run."
    )
