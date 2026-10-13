"""Bounded raw STEP upload and native inspection/confirmation endpoints."""

import hashlib
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, Query, Request, Response

from app.domain.errors import DomainError
from app.domain.import_service import ImportService
from app.domain.imports import (
    GeometryDisplay,
    GeometryImport,
    ImportConfirm,
    ImportCreate,
    Upload,
    UploadCreate,
)
from app.domain.models import GeometryRevision
from app.routes.projects import Owner, Revision, etag, router


def service(request: Request) -> ImportService:
    return request.app.state.import_service  # type: ignore[no-any-return]


Service = Annotated[ImportService, Depends(service)]


@router.post("/projects/{project_id}/geometry-uploads", response_model=Upload, status_code=201)
def create_upload(
    project_id: UUID, payload: UploadCreate, owner: Owner, service: Service
) -> Upload:
    return service.repository.create_upload(owner, project_id, payload)


@router.get("/geometry-uploads/{upload_id}", response_model=Upload)
def get_upload(upload_id: UUID, owner: Owner, service: Service) -> Upload:
    return service.repository.upload(owner, upload_id)


@router.put("/geometry-uploads/{upload_id}/content", response_model=Upload)
async def upload_content(
    upload_id: UUID, request: Request, owner: Owner, service: Service
) -> Upload:
    current = service.repository.upload(owner, upload_id)
    length = request.headers.get("content-length", "")
    if (
        not length.isascii()
        or not length.isdecimal()
        or len(length) > 10
        or int(length) != current.size_bytes
    ):
        raise DomainError(422, "upload_size", "Upload size must match its ticket")
    service.repository.transition_upload(owner, upload_id, "pending", "uploading")
    path = service.storage.directory("uploads", upload_id) / "source.step"
    size, digest = 0, hashlib.sha256()
    try:
        with path.open("xb") as output:
            async for chunk in request.stream():
                size += len(chunk)
                if size > current.size_bytes:
                    raise DomainError(413, "upload_size", "Upload exceeds its approved size")
                digest.update(chunk)
                output.write(chunk)
        if size != current.size_bytes or digest.hexdigest() != current.sha256:
            raise DomainError(
                422, "upload_checksum", "Upload was incomplete or its checksum did not match"
            )
        path.chmod(0o400)
        return service.repository.transition_upload(owner, upload_id, "uploading", "complete")
    except Exception:
        path.unlink(missing_ok=True)
        service.repository.transition_upload(owner, upload_id, "uploading", "failed")
        raise


@router.post(
    "/projects/{project_id}/geometry-imports", response_model=GeometryImport, status_code=201
)
def inspect_upload(
    project_id: UUID, payload: ImportCreate, revision: Revision, owner: Owner, service: Service
) -> GeometryImport:
    return service.inspect(owner, project_id, revision, payload)


@router.get("/geometry-imports/{import_id}", response_model=GeometryImport)
def get_inspection(import_id: UUID, owner: Owner, service: Service) -> GeometryImport:
    return service.repository.get_import(owner, import_id)


@router.post("/geometry-imports/{import_id}/confirm", response_model=GeometryRevision)
def confirm_import(
    import_id: UUID,
    payload: ImportConfirm,
    revision: Revision,
    owner: Owner,
    service: Service,
    response: Response,
) -> GeometryRevision:
    geometry = service.confirm(owner, import_id, revision)
    etag(response, service.repository.projects.get_project(owner, geometry.project_id).revision)
    return geometry


@router.get("/geometry/{geometry_id}/display", response_model=GeometryDisplay)
def get_display(
    geometry_id: UUID,
    owner: Owner,
    service: Service,
    lod: Annotated[Literal["coarse", "fine"], Query()] = "coarse",
) -> GeometryDisplay:
    return service.display(owner, geometry_id, lod)
