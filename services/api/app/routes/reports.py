"""Private report history, immutable shared model, preview and PDF downloads."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, Request, Response

from app.domain.report_service import ReportService
from app.domain.reports import ReportRecord, ReportRequest
from app.routes.projects import Owner, router
from worker.reports.html import CSP


def service(request: Request) -> ReportService:
    return request.app.state.report_service  # type: ignore[no-any-return]


Service = Annotated[ReportService, Depends(service)]


@router.post("/runs/{job_id}/reports", response_model=ReportRecord, status_code=201)
def create(job_id: UUID, payload: ReportRequest, owner: Owner, service: Service) -> ReportRecord:
    return service.create(owner, job_id, payload)


@router.get("/runs/{job_id}/reports", response_model=list[ReportRecord])
def reports(job_id: UUID, owner: Owner, service: Service) -> list[ReportRecord]:
    return service.list(owner, job_id)


@router.get("/reports/{report_id}", response_model=ReportRecord)
def report(report_id: UUID, owner: Owner, service: Service) -> ReportRecord:
    return service.get(owner, report_id)


@router.get("/reports/{report_id}/{kind}", response_class=Response)
def artifact(
    report_id: UUID, kind: Literal["model", "html", "pdf"], owner: Owner, service: Service
) -> Response:
    data = service.artifact(owner, report_id, kind)
    media, extension = {
        "model": ("application/json", "json"),
        "html": ("text/html", "html"),
        "pdf": ("application/pdf", "pdf"),
    }[kind]
    return Response(
        data,
        media_type=media,
        headers={
            "Content-Disposition": f"{'inline' if kind == 'html' else 'attachment'}; "
            f'filename="report-{report_id}.{extension}"',
            "Content-Security-Policy": CSP + "; sandbox",
        },
    )
