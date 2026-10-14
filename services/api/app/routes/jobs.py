"""Asynchronous owned local mesh/solve submission, status, cancel and downloads."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, Header, Request, Response

from app.domain.connections import AssemblyPreflight
from app.domain.errors import DomainError
from app.domain.jobs import JobEvent, LocalJob, MeshCandidates, MeshPreview, MeshRequest, RunRequest
from app.domain.results import ProbeRequest, ResultInspection, ResultView, SectionRequest
from app.jobs.service import JobService
from app.routes.projects import Owner, Revision, router


def service(request: Request) -> JobService:
    return request.app.state.job_service  # type: ignore[no-any-return]


def key(value: Annotated[str | None, Header(alias="Idempotency-Key")] = None) -> UUID:
    if value is None:
        raise DomainError(
            428, "idempotency_required", "A request key is required to prevent duplicate jobs"
        )
    try:
        return UUID(value)
    except ValueError:
        raise DomainError(422, "invalid_idempotency", "The request key must be a UUID") from None


Service = Annotated[JobService, Depends(service)]
Key = Annotated[UUID, Depends(key)]
Filename = Literal[
    "snapshot.json",
    "mesh.json",
    "analysis.inp",
    "mesh.log",
    "solver.log",
    "analysis.dat",
    "analysis.frd",
    "resources.json",
    "results.json",
    "recovery.json",
    "assembly.json",
    "mesh-attempt-1.log",
    "mesh-attempt-2.log",
    "mesh-attempt-3.log",
    "mesh-attempt-1-resources.json",
    "mesh-attempt-2-resources.json",
    "mesh-attempt-3-resources.json",
]


@router.post("/analyses/{analysis_id}/mesh-jobs", response_model=LocalJob, status_code=202)
def mesh(
    analysis_id: UUID,
    payload: MeshRequest,
    revision: Revision,
    key: Key,
    owner: Owner,
    service: Service,
    response: Response,
) -> LocalJob:
    result = service.admit(owner, analysis_id, revision, key)
    response.headers["Location"] = f"/api/v1/jobs/{result.id}"
    return result


@router.post("/analyses/{analysis_id}/runs", response_model=LocalJob, status_code=202)
def run(
    analysis_id: UUID,
    payload: RunRequest,
    revision: Revision,
    key: Key,
    owner: Owner,
    service: Service,
    response: Response,
) -> LocalJob:
    result = service.admit(owner, analysis_id, revision, key, payload.mesh_job_id)
    response.headers["Location"] = f"/api/v1/jobs/{result.id}"
    return result


@router.get("/analyses/{analysis_id}/jobs", response_model=list[LocalJob])
def jobs(analysis_id: UUID, owner: Owner, service: Service) -> list[LocalJob]:
    return service.repository.list_jobs(owner, analysis_id)


@router.get("/analyses/{analysis_id}/compatible-meshes", response_model=MeshCandidates)
def compatible_meshes(analysis_id: UUID, owner: Owner, service: Service) -> MeshCandidates:
    return service.mesh_candidates(owner, analysis_id)


@router.get("/jobs/{job_id}", response_model=LocalJob)
def job(job_id: UUID, owner: Owner, service: Service) -> LocalJob:
    return service.repository.get(owner, job_id)


@router.get("/jobs/{job_id}/events", response_model=list[JobEvent])
def events(job_id: UUID, owner: Owner, service: Service) -> list[JobEvent]:
    return service.repository.get(owner, job_id).events


@router.post("/jobs/{job_id}/cancel", response_model=LocalJob)
def cancel(job_id: UUID, owner: Owner, service: Service) -> LocalJob:
    return service.repository.cancel(owner, job_id)


@router.get("/jobs/{job_id}/artifacts/{filename}", response_class=Response)
def artifact(job_id: UUID, filename: Filename, owner: Owner, service: Service) -> Response:
    data, media = service.artifact(owner, job_id, filename)
    return Response(
        data,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/jobs/{job_id}/mesh-display", response_model=MeshPreview)
def preview(job_id: UUID, owner: Owner, service: Service) -> MeshPreview:
    return service.mesh_preview(owner, job_id)


@router.get("/local-worker", response_model=dict[str, str])
def worker(owner: Owner, request: Request) -> dict[str, str]:
    return {"state": request.app.state.local_worker.state}


@router.get("/runs/{job_id}/results", response_model=ResultView)
def results(job_id: UUID, owner: Owner, service: Service) -> ResultView:
    return service.result_view(owner, job_id)


@router.post("/analyses/{analysis_id}/assembly-preflight", response_model=AssemblyPreflight)
def assembly_preflight(
    analysis_id: UUID, payload: RunRequest, revision: Revision, owner: Owner, service: Service
) -> AssemblyPreflight:
    return service.assembly_preflight(owner, analysis_id, revision, payload.mesh_job_id)


@router.post("/runs/{job_id}/probes", response_model=ResultInspection)
def probe(job_id: UUID, payload: ProbeRequest, owner: Owner, service: Service) -> ResultInspection:
    return service.result_inspection(owner, job_id, payload)


@router.post("/runs/{job_id}/sections", response_model=ResultInspection)
def section(
    job_id: UUID, payload: SectionRequest, owner: Owner, service: Service
) -> ResultInspection:
    return service.result_inspection(owner, job_id, payload)
