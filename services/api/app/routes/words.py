"""Owned immutable Word conversion and downloads for existing PDF report models."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request, Response

from app.domain.word_service import WordService
from app.domain.words import WordExport, WordRequest
from app.routes.projects import Owner, router


def service(request: Request) -> WordService:
    return request.app.state.word_service  # type: ignore[no-any-return]


Service = Annotated[WordService, Depends(service)]


@router.post("/reports/{report_id}/exports/word", response_model=WordExport, status_code=201)
def create(report_id: UUID, payload: WordRequest, owner: Owner, service: Service) -> WordExport:
    return service.create(owner, report_id)


@router.get("/reports/{report_id}/exports/word", response_model=list[WordExport])
def exports(report_id: UUID, owner: Owner, service: Service) -> list[WordExport]:
    return service.list(owner, report_id)


@router.get("/word-exports/{export_id}", response_model=WordExport)
def export(export_id: UUID, owner: Owner, service: Service) -> WordExport:
    return service.get(owner, export_id)


@router.get("/word-exports/{export_id}/docx", response_class=Response)
def artifact(export_id: UUID, owner: Owner, service: Service) -> Response:
    return Response(
        service.artifact(owner, export_id),
        media_type=("application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        headers={"Content-Disposition": f'attachment; filename="report-{export_id}.docx"'},
    )
