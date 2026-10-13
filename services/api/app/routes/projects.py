"""Real local CRUD; geometry import and engineering editing are later slices."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request, Response

from app.auth.local import COOKIE, current_owner, expected_revision
from app.domain.models import (
    Analysis,
    AnalysisCreate,
    AnalysisPage,
    AnalysisPatch,
    ErrorResponse,
    GeometryPage,
    GeometryRevision,
    LocalSession,
    Project,
    ProjectCreate,
    ProjectPage,
)
from app.persistence.repository import Repository

router = APIRouter(
    prefix="/api/v1",
    responses={
        status: {"model": ErrorResponse}
        for status in (401, 403, 404, 409, 411, 413, 422, 428, 429, 503)
    },
)
Owner = Annotated[UUID, Depends(current_owner)]
Revision = Annotated[int, Depends(expected_revision)]
Offset = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=100)]


def repository(request: Request) -> Repository:
    return request.app.state.repository  # type: ignore[no-any-return]


Store = Annotated[Repository, Depends(repository)]


def etag(response: Response, revision: int) -> None:
    response.headers["ETag"] = f'"{revision}"'


@router.get("/session", response_model=LocalSession)
def session(request: Request, response: Response) -> LocalSession:
    response.set_cookie(
        COOKIE,
        request.app.state.session_token,
        httponly=True,
        samesite="strict",
        path="/api/v1",
        secure=False,
    )
    return LocalSession(owner_id=request.app.state.owner, csrf_token=request.app.state.csrf_token)


@router.post("/projects", response_model=Project, status_code=201)
def create_project(
    payload: ProjectCreate, owner: Owner, store: Store, response: Response
) -> Project:
    result = store.create_project(owner, payload)
    etag(response, result.revision)
    response.headers["Location"] = f"/api/v1/projects/{result.id}"
    return result


@router.get("/projects", response_model=ProjectPage)
def list_projects(owner: Owner, store: Store, offset: Offset = 0, limit: Limit = 50) -> ProjectPage:
    return store.list_projects(owner, offset, limit)


@router.get("/projects/{project_id}", response_model=Project)
def get_project(project_id: UUID, owner: Owner, store: Store, response: Response) -> Project:
    result = store.get_project(owner, project_id)
    etag(response, result.revision)
    return result


@router.patch("/projects/{project_id}", response_model=Project)
def edit_project(
    project_id: UUID,
    payload: ProjectCreate,
    revision: Revision,
    owner: Owner,
    store: Store,
    response: Response,
) -> Project:
    result = store.edit_project(owner, project_id, revision, payload)
    assert result is not None
    etag(response, result.revision)
    return result


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: UUID, revision: Revision, owner: Owner, store: Store) -> Response:
    store.edit_project(owner, project_id, revision, None)
    return Response(status_code=204)


@router.get("/projects/{project_id}/geometry", response_model=GeometryPage)
def list_geometry(
    project_id: UUID, owner: Owner, store: Store, offset: Offset = 0, limit: Limit = 50
) -> GeometryPage:
    return store.list_geometry(owner, project_id, offset, limit)


@router.get("/geometry/{geometry_id}", response_model=GeometryRevision)
def get_geometry(geometry_id: UUID, owner: Owner, store: Store) -> GeometryRevision:
    return store.get_geometry(owner, geometry_id)


@router.post("/projects/{project_id}/analyses", response_model=Analysis, status_code=201)
def create_analysis(
    project_id: UUID,
    payload: AnalysisCreate,
    revision: Revision,
    owner: Owner,
    store: Store,
    response: Response,
) -> Analysis:
    result = store.create_analysis(owner, project_id, revision, payload)
    etag(response, result.revision)
    response.headers["Location"] = f"/api/v1/analyses/{result.id}"
    return result


@router.get("/projects/{project_id}/analyses", response_model=AnalysisPage)
def list_analyses(
    project_id: UUID, owner: Owner, store: Store, offset: Offset = 0, limit: Limit = 50
) -> AnalysisPage:
    return store.list_analyses(owner, project_id, offset, limit)


@router.get("/analyses/{analysis_id}", response_model=Analysis)
def get_analysis(analysis_id: UUID, owner: Owner, store: Store, response: Response) -> Analysis:
    result = store.get_analysis(owner, analysis_id)
    etag(response, result.revision)
    return result


@router.patch("/analyses/{analysis_id}", response_model=Analysis)
def edit_analysis(
    analysis_id: UUID,
    payload: AnalysisPatch,
    revision: Revision,
    owner: Owner,
    store: Store,
    response: Response,
) -> Analysis:
    result = store.edit_analysis(owner, analysis_id, revision, payload)
    etag(response, result.revision)
    return result


@router.get("/analyses/{analysis_id}/revisions/{revision}", response_model=Analysis)
def get_analysis_revision(
    analysis_id: UUID,
    revision: Annotated[int, Path(ge=1)],
    owner: Owner,
    store: Store,
    response: Response,
) -> Analysis:
    result = store.get_analysis(owner, analysis_id, revision)
    etag(response, result.revision)
    return result
