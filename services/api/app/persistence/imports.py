"""Owned import lifecycle; geometry promotion and revision update commit atomically."""

import json
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Connection, text

from app.domain.errors import DomainError, not_found, stale_revision
from app.domain.imports import GeometryImport, ImportCreate, Upload, UploadCreate
from app.domain.models import GeometryMetadata, GeometryRevision
from app.persistence.repository import Repository, now


class ImportRepository:
    def __init__(self, projects: Repository) -> None:
        self.projects = projects

    def create_upload(self, owner: UUID, project: UUID, payload: UploadCreate) -> Upload:
        identifier = uuid4()
        with self.projects.write() as connection:
            self.projects._project(connection, owner, project)
            connection.execute(
                text(
                    "INSERT INTO geometry_uploads VALUES (:id,:project,:size,:hash,'pending',:time)"
                ),
                {
                    "id": str(identifier),
                    "project": str(project),
                    "size": payload.size_bytes,
                    "hash": payload.sha256,
                    "time": now(),
                },
            )
            return self._upload(connection, owner, identifier)

    def _upload(self, connection: Connection, owner: UUID, identifier: UUID) -> Upload:
        row = (
            connection.execute(
                text("""SELECT u.* FROM geometry_uploads u JOIN projects p ON p.id=u.project_id
            WHERE u.id=:id AND p.owner_id=:owner AND p.deleted_at IS NULL"""),
                {"id": str(identifier), "owner": str(owner)},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise not_found()
        return Upload.model_validate(dict(row))

    def upload(self, owner: UUID, identifier: UUID) -> Upload:
        with self.projects.database.engine.connect() as connection:
            return self._upload(connection, owner, identifier)

    def transition_upload(self, owner: UUID, identifier: UUID, before: str, after: str) -> Upload:
        with self.projects.write() as connection:
            current = self._upload(connection, owner, identifier)
            if current.status != before:
                raise DomainError(409, "upload_state", "This upload is already used or unavailable")
            connection.execute(
                text("UPDATE geometry_uploads SET status=:status WHERE id=:id"),
                {"status": after, "id": str(identifier)},
            )
            return self._upload(connection, owner, identifier)

    def create_import(
        self, owner: UUID, project: UUID, expected: int, payload: ImportCreate
    ) -> GeometryImport:
        identifier = uuid4()
        with self.projects.write() as connection:
            current = self.projects._project(connection, owner, project)
            if current.revision != expected:
                raise stale_revision()
            upload = self._upload(connection, owner, payload.upload_id)
            if upload.project_id != project:
                raise not_found()
            if upload.status != "complete":
                raise DomainError(
                    409, "upload_incomplete", "Complete a verified upload before importing"
                )
            connection.execute(
                text("""INSERT INTO geometry_imports
                (id,project_id,upload_id,project_revision,status,source_unit,created_at)
                VALUES (:id,:project,:upload,:revision,'processing',:unit,:time)"""),
                {
                    "id": str(identifier),
                    "project": str(project),
                    "upload": str(upload.id),
                    "revision": expected,
                    "unit": payload.source_length_unit,
                    "time": now(),
                },
            )
            return self._import(connection, owner, identifier)

    def _import(self, connection: Connection, owner: UUID, identifier: UUID) -> GeometryImport:
        row = (
            connection.execute(
                text("""SELECT i.* FROM geometry_imports i JOIN projects p ON p.id=i.project_id
            WHERE i.id=:id AND p.owner_id=:owner AND p.deleted_at IS NULL"""),
                {"id": str(identifier), "owner": str(owner)},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise not_found()
        fields = dict(row)
        raw = fields.pop("preview_json")
        preview = json.loads(raw) if raw else None
        fields.pop("source_unit")
        fields.pop("created_at")
        fields["inspection"] = preview["inspection"] if preview else None
        return GeometryImport.model_validate(fields)

    def get_import(self, owner: UUID, identifier: UUID) -> GeometryImport:
        with self.projects.database.engine.connect() as connection:
            return self._import(connection, owner, identifier)

    def finish(
        self,
        owner: UUID,
        identifier: UUID,
        status: str,
        preview: dict[str, Any] | None,
        code: str | None = None,
        message: str | None = None,
    ) -> GeometryImport:
        with self.projects.write() as connection:
            current = self._import(connection, owner, identifier)
            if current.status != "processing":
                raise DomainError(409, "import_state", "This import is no longer processing")
            connection.execute(
                text("""UPDATE geometry_imports SET status=:status, preview_json=:preview,
                error_code=:code, error_message=:message WHERE id=:id"""),
                {
                    "id": str(identifier),
                    "status": status,
                    "preview": json.dumps(preview, allow_nan=False) if preview else None,
                    "code": code,
                    "message": message,
                },
            )
            return self._import(connection, owner, identifier)

    def preview(self, owner: UUID, identifier: UUID) -> dict[str, Any]:
        with self.projects.database.engine.connect() as connection:
            self._import(connection, owner, identifier)
            raw = connection.execute(
                text("SELECT preview_json FROM geometry_imports WHERE id=:id"),
                {"id": str(identifier)},
            ).scalar_one()
            if raw is None:
                raise DomainError(409, "preview_unavailable", "No validated preview is available")
            return json.loads(raw)  # type: ignore[no-any-return]

    def commit(self, owner: UUID, identifier: UUID, expected: int) -> GeometryRevision:
        with self.projects.write() as connection:
            current = self._import(connection, owner, identifier)
            if current.status == "committed":
                assert current.geometry_revision_id is not None
                return self.projects._geometry(connection, owner, current.geometry_revision_id)
            project = self.projects._project(connection, owner, current.project_id)
            if project.revision != expected or current.project_revision != expected:
                raise stale_revision()
            if current.status != "ready":
                raise DomainError(
                    409, "import_not_ready", "Inspect units and geometry before confirming"
                )
            raw = connection.execute(
                text("SELECT preview_json FROM geometry_imports WHERE id=:id"),
                {"id": str(identifier)},
            ).scalar_one()
            metadata = GeometryMetadata.model_validate(json.loads(raw)["metadata"])
            geometry_id = uuid4()
            connection.execute(
                text("INSERT INTO geometry_revisions VALUES (:id,:project,NULL,:metadata,:time)"),
                {
                    "id": str(geometry_id),
                    "project": str(project.id),
                    "time": now(),
                    "metadata": metadata.model_dump_json(),
                },
            )
            connection.execute(
                text("UPDATE projects SET revision=revision+1,updated_at=:time WHERE id=:id"),
                {"time": now(), "id": str(project.id)},
            )
            connection.execute(
                text(
                    "UPDATE geometry_imports SET status='committed',geometry_revision_id=:geometry "
                    "WHERE id=:id"
                ),
                {"id": str(identifier), "geometry": str(geometry_id)},
            )
            return self.projects._geometry(connection, owner, geometry_id)

    def interrupt_incomplete(self) -> None:
        # Startup never retries native parsing; the sandbox dies with its API parent.
        with self.projects.write() as connection:
            connection.execute(
                text("UPDATE geometry_uploads SET status='failed' WHERE status='uploading'")
            )
            connection.execute(
                text("""UPDATE geometry_imports SET status='failed',
                error_code='interrupted',error_message='Import interrupted; start a new inspection'
                WHERE status='processing'""")
            )
