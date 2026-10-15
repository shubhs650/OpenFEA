"""Explicit archive and diagnostic preview/download; bounded raw ZIP import."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request, Response
from starlette.concurrency import run_in_threadpool

from app.domain.archive_service import ArchiveService
from app.domain.archives import (
    MAX_ARCHIVE,
    ArchiveOptions,
    BundleRecord,
    DiagnosticOptions,
    ImportedArchive,
)
from app.domain.errors import DomainError
from app.routes.projects import Owner, router


def service(request: Request) -> ArchiveService:
    return request.app.state.archive_service  # type: ignore[no-any-return]


Service = Annotated[ArchiveService, Depends(service)]


@router.post("/projects/{project_id}/exports", response_model=BundleRecord, status_code=201)
def export(
    project_id: UUID, payload: ArchiveOptions, owner: Owner, service: Service
) -> BundleRecord:
    return service.export(owner, project_id, payload)


@router.post(
    "/projects/{project_id}/diagnostic-previews", response_model=BundleRecord, status_code=201
)
def diagnostic(
    project_id: UUID, payload: DiagnosticOptions, owner: Owner, service: Service
) -> BundleRecord:
    return service.diagnostics(owner, project_id, payload)


@router.get("/portable-bundles/{bundle_id}", response_model=BundleRecord)
def bundle(bundle_id: UUID, owner: Owner, service: Service) -> BundleRecord:
    return service.bundle(owner, bundle_id)


def attachment(raw: bytes, filename: str, media_type: str) -> Response:
    return Response(
        raw,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox; default-src 'none'",
        },
    )


@router.get("/portable-bundles/{bundle_id}/zip", response_class=Response)
def download(bundle_id: UUID, owner: Owner, service: Service) -> Response:
    return attachment(
        service.download(owner, bundle_id), f"bundle-{bundle_id}.zip", "application/zip"
    )


@router.post("/archive-imports", response_model=ImportedArchive, status_code=201)
async def import_archive(request: Request, owner: Owner, service: Service) -> ImportedArchive:
    if request.headers.get("content-type", "").split(";")[0] != "application/zip":
        raise DomainError(422, "archive_type", "Upload a project archive as application/zip")
    with service.bundle_slot("archive-upload.lock"):
        chunks = bytearray()
        async for chunk in request.stream():
            if len(chunks) + len(chunk) > MAX_ARCHIVE:
                raise DomainError(413, "archive_size", "Archive exceeds 64 MiB")
            chunks.extend(chunk)
        if len(chunks) != int(request.headers["content-length"]):
            raise DomainError(422, "archive_size", "Archive size does not match")
        return await run_in_threadpool(service.import_archive, owner, bytes(chunks))


@router.get("/archive-imports/{import_id}", response_model=ImportedArchive)
def imported(import_id: UUID, owner: Owner, service: Service) -> ImportedArchive:
    return service.imported(owner, import_id)


@router.get("/projects/{project_id}/archive-imports", response_model=list[ImportedArchive])
def imports(project_id: UUID, owner: Owner, service: Service) -> list[ImportedArchive]:
    from sqlalchemy import text

    with service.projects.database.engine.connect() as connection, connection.begin():
        service.projects._project(connection, owner, project_id)
        return [
            ImportedArchive.model_validate_json(raw)
            for raw in connection.execute(
                text("SELECT record_json FROM archive_imports WHERE project_id=:id"),
                {"id": str(project_id)},
            ).scalars()
        ]


@router.get("/archive-imports/{import_id}/history/{item_id}/{filename}", response_class=Response)
def history(
    import_id: UUID, item_id: UUID, filename: str, owner: Owner, service: Service
) -> Response:
    # Filename never becomes a filesystem path; only an exact descriptor key lookup.
    return attachment(
        service.history_file(owner, import_id, item_id, filename),
        f"historical-{item_id}.bin",
        "application/octet-stream",
    )
