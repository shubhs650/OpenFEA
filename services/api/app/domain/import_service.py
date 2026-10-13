"""Real upload inspection and confirmation; no mesh/solve/job placeholders."""

import fcntl
from typing import Any
from uuid import UUID

from app.domain.errors import DomainError
from app.domain.imports import GeometryDisplay, GeometryImport, ImportCreate, ImportInspection
from app.domain.models import GeometryMetadata, GeometryRevision
from app.persistence.imports import ImportRepository
from app.storage.geometry import GeometryStorage
from worker.step_import import ImportSandboxError, inspect_step


def validate_display(data: bytes, metadata: GeometryMetadata) -> GeometryDisplay:
    display = GeometryDisplay.model_validate_json(data)
    if display.brep_sha256 != metadata.brep_sha256:
        raise ValueError("Stale display revision")
    if {b.id for b in display.bodies} != {b.id for b in metadata.bodies}:
        raise ValueError("Display body identities differ")
    catalog = {f.id: f.body_id for f in metadata.faces}
    if len(display.faces) != len(catalog) or {f.id: f.body_id for f in display.faces} != catalog:
        raise ValueError("Display face identities differ")
    for face in display.faces:
        if (
            not face.points_m
            or not face.triangles
            or any(
                min(t) < 0 or max(t) >= len(face.points_m) or len(set(t)) != 3
                for t in face.triangles
            )
        ):
            raise ValueError("Invalid display connectivity")
    return display


class ImportService:
    def __init__(self, repository: ImportRepository, storage: GeometryStorage) -> None:
        self.repository, self.storage = repository, storage

    def inspect(
        self, owner: UUID, project: UUID, expected: int, payload: ImportCreate
    ) -> GeometryImport:
        # An OS lock serializes real parser processes across API threads/processes.
        with (self.storage.root / "native-import.lock").open("a+b") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise DomainError(
                    429,
                    "import_busy",
                    "Another geometry import is processing; try when it finishes",
                ) from None
            current = self.repository.create_import(owner, project, expected, payload)
            upload = self.repository.upload(owner, payload.upload_id)
            source = self.storage.directory("uploads", upload.id) / "source.step"
            output = self.storage.directory("imports", current.id) / "output"
            try:
                self.storage.read_fixed(source, upload.sha256)
                preview = inspect_step(source, output, payload.source_length_unit)
                if preview.get("status") not in ("ready", "needs_units", "failed"):
                    raise ValueError("Invalid inspection state")
                if preview["status"] == "failed":
                    return self.repository.finish(
                        owner,
                        current.id,
                        "failed",
                        None,
                        preview["error_code"],
                        preview["error_message"],
                    )
                preview["inspection"] = ImportInspection.model_validate(
                    preview["inspection"]
                ).model_dump(mode="json")
                if preview["status"] == "ready":
                    metadata = GeometryMetadata.model_validate(preview["metadata"])
                    if metadata.source_sha256 != upload.sha256:
                        raise ValueError("Source hash differs")
                    artifacts = metadata.validation["artifacts"]
                    if not isinstance(artifacts, dict):
                        raise ValueError("Invalid artifact manifest")
                    allowed = {
                        "geometry.brep",
                        "display-coarse.json",
                        "display-fine.json",
                        *(f"body{i}.brep" for i in range(1, len(metadata.bodies) + 1)),
                    }
                    if set(artifacts) != allowed:
                        raise ValueError("Invalid artifact names")
                    for name, item in artifacts.items():
                        if not isinstance(item, dict):
                            raise ValueError("Invalid artifact hash")
                        digest = item.get("sha256")
                        if not isinstance(digest, str):
                            raise ValueError("Invalid artifact hash")
                        path = output / name
                        data = self.storage.read_fixed(path, digest)
                        if len(data) != item["size_bytes"]:
                            raise ValueError("Invalid artifact size")
                        if name.startswith("display-"):
                            validate_display(data, metadata)
                        self.storage.save(project, path, digest)
                    self.storage.save(project, source, upload.sha256)
                    artifacts["source.step"] = {
                        "sha256": upload.sha256,
                        "size_bytes": upload.size_bytes,
                    }
                    preview["metadata"] = metadata.model_dump(mode="json")
                    # Retain the source descriptor in the serialized metadata too.
                    preview["metadata"]["validation"]["artifacts"]["source.step"] = artifacts[
                        "source.step"
                    ]
                return self.repository.finish(owner, current.id, preview["status"], preview)
            except ImportSandboxError as failure:
                return self.repository.finish(
                    owner, current.id, "failed", None, "import_failed", str(failure)
                )
            except DomainError:
                self.repository.finish(
                    owner,
                    current.id,
                    "failed",
                    None,
                    "artifact_integrity",
                    "Uploaded bytes are unavailable or corrupted",
                )
                raise
            except (ValueError, KeyError, TypeError):
                return self.repository.finish(
                    owner,
                    current.id,
                    "failed",
                    None,
                    "invalid_native_output",
                    "CAD inspection outputs failed validation",
                )

    def confirm(self, owner: UUID, identifier: UUID, expected: int) -> GeometryRevision:
        current = self.repository.get_import(owner, identifier)
        preview = self.repository.preview(owner, identifier)
        if current.status not in ("ready", "committed"):
            raise DomainError(
                409, "import_not_ready", "Complete the geometry inspection before accepting"
            )
        self.verify_artifacts(current.project_id, preview["metadata"])
        return self.repository.commit(owner, identifier, expected)

    def verify_artifacts(self, project: UUID, fields: dict[str, Any]) -> None:
        artifacts = fields["validation"]["artifacts"]
        for descriptor in artifacts.values():
            self.storage.read(project, descriptor["sha256"])

    def display(self, owner: UUID, geometry: UUID, lod: str) -> GeometryDisplay:
        metadata = self.repository.projects.get_geometry(owner, geometry)
        fields = metadata.model_dump(mode="json")
        if "artifacts" not in fields["validation"]:
            raise DomainError(
                409, "display_unavailable", "This geometry has no verified display artifacts"
            )
        descriptor = fields["validation"]["artifacts"][f"display-{lod}.json"]
        return validate_display(
            self.storage.read(metadata.project_id, descriptor["sha256"]), metadata
        )
