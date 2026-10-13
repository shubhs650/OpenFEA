"""Real isolated CAD previews, verified artifacts, owned publication and undo."""

import fcntl
from uuid import UUID, uuid4

from app.domain.edits import EditCreate, EditPreview, EditResult, GeometryEdit
from app.domain.errors import DomainError, stale_revision
from app.domain.import_service import ImportService, validate_display
from app.domain.imports import GeometryDisplay
from app.domain.models import GeometryMetadata
from app.persistence.edits import EditRepository
from worker.step_import import ImportSandboxError, inspect_step


class EditService:
    def __init__(self, imports: ImportService) -> None:
        self.imports = imports
        self.repository = EditRepository(imports.repository.projects)

    def preview(
        self, owner: UUID, source_id: UUID, expected: int, payload: EditCreate
    ) -> GeometryEdit:
        projects, storage = self.repository.projects, self.imports.storage
        source = projects.get_geometry(owner, source_id)
        project = projects.get_project(owner, source.project_id)
        if project.revision != expected:
            raise stale_revision()
        if payload.face_id not in {f.id for f in source.faces}:
            raise DomainError(
                422, "invalid_face", "Select a face from the displayed immutable geometry"
            )
        if payload.analysis_id:
            analysis = projects.get_analysis(owner, payload.analysis_id)
            if (
                analysis.project_id != source.project_id
                or analysis.geometry_revision_id != source.id
            ):
                raise DomainError(
                    422, "invalid_analysis", "Select an analysis pinned to this geometry"
                )
            if analysis.revision != payload.analysis_revision:
                raise stale_revision()
        edit = GeometryEdit(
            id=uuid4(),
            project_id=project.id,
            project_revision=expected,
            source_geometry_id=source.id,
            request=payload,
            status="failed",
        )
        with (storage.root / "native-import.lock").open("a+b") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise DomainError(
                    429, "geometry_busy", "Another native geometry/mesh operation is processing"
                ) from None
            self.imports.verify_artifacts(project.id, source.model_dump(mode="json"))
            directory = storage.directory("edits", edit.id)
            metadata_path = directory / "source.json"
            metadata_path.write_text(source.model_dump_json())
            metadata_path.chmod(0o400)
            try:
                result = inspect_step(
                    storage.blob_path(project.id, source.brep_sha256),
                    directory / "output",
                    edit=(metadata_path, payload.face_id),
                )
                if result.get("status") != "ready":
                    edit = edit.model_copy(
                        update={
                            "error": result.get(
                                "error_message", "Cleanup failed; original geometry retained"
                            )
                        }
                    )
                else:
                    metadata = GeometryMetadata.model_validate(result["metadata"])
                    if (
                        metadata.source_sha256 != source.source_sha256
                        or metadata.brep_sha256 == source.brep_sha256
                    ):
                        raise ValueError("Invalid source/change identity")
                    metadata = metadata.model_copy(update={"units": source.units.model_copy()})
                    metadata.validation["unit_origin"] = source.validation.get("unit_origin")
                    artifacts = metadata.validation["artifacts"]
                    if not isinstance(artifacts, dict) or set(artifacts) != {
                        "geometry.brep",
                        "body1.brep",
                        "display-coarse.json",
                        "display-fine.json",
                    }:
                        raise ValueError("Invalid preview artifact manifest")
                    for name, descriptor in artifacts.items():
                        if not isinstance(descriptor, dict) or not isinstance(
                            descriptor.get("sha256"), str
                        ):
                            raise ValueError("Invalid preview artifact hash")
                        digest = descriptor["sha256"]
                        if not isinstance(digest, str):
                            raise ValueError("Invalid artifact identity")
                        path = directory / "output" / name
                        data = storage.read_fixed(path, digest)
                        if len(data) != descriptor["size_bytes"]:
                            raise ValueError("Invalid preview artifact size")
                        if name.startswith("display-"):
                            validate_display(data, metadata)
                        storage.save(project.id, path, digest)
                    source_artifacts = source.model_dump(mode="json")["validation"]["artifacts"]
                    artifacts["source.step"] = source_artifacts["source.step"]
                    edit = edit.model_copy(
                        update={
                            "metadata": metadata,
                            "preview": EditPreview.model_validate(result["edit"]),
                            "status": "ready",
                        }
                    )
            except ImportSandboxError:
                edit = edit.model_copy(
                    update={
                        "error": "Isolated cleanup failed or exceeded its processing budget; "
                        "original retained"
                    }
                )
            except (ValueError, KeyError, TypeError):
                edit = edit.model_copy(
                    update={"error": "Cleanup outputs failed verification; original retained"}
                )
            finally:
                self.imports.verify_artifacts(project.id, source.model_dump(mode="json"))
        # Recheck owner/tombstone and both captured revisions after native completion.
        return self.repository.save(owner, edit)

    def display(self, owner: UUID, identifier: UUID, lod: str) -> GeometryDisplay:
        edit = self.repository.get(owner, identifier)
        if edit.metadata is None or edit.status == "failed":
            raise DomainError(
                409, "preview_unavailable", "No successful cleanup preview is available"
            )
        descriptor = edit.metadata.model_dump(mode="json")["validation"]["artifacts"][
            f"display-{lod}.json"
        ]
        assert isinstance(descriptor, dict) and isinstance(descriptor["sha256"], str)
        result = validate_display(
            self.imports.storage.read(edit.project_id, descriptor["sha256"]), edit.metadata
        )
        self.repository.get(owner, identifier)
        return result

    def commit(self, owner: UUID, identifier: UUID, source: UUID, expected: int) -> EditResult:
        edit = self.repository.get(owner, identifier)
        if edit.metadata:
            self.imports.verify_artifacts(edit.project_id, edit.metadata.model_dump(mode="json"))
        return self.repository.commit(owner, identifier, source, expected)

    def undo(self, owner: UUID, identifier: UUID, expected: int) -> EditResult:
        edit = self.repository.get(owner, identifier)
        source = self.repository.projects.get_geometry(owner, edit.source_geometry_id)
        self.imports.verify_artifacts(edit.project_id, source.model_dump(mode="json"))
        return self.repository.undo(owner, identifier, expected)
