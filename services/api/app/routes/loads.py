"""Owned, revision-guarded face loads and immutable downloadable generated inputs."""

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, Path, Request, Response
from pydantic import Field

from app.domain.base import StrictModel
from app.domain.deck_service import DeckService
from app.domain.directions import DirectionSelection, DirectionSnapshot, resolve_direction
from app.domain.errors import DomainError, stale_revision
from app.domain.loads import (
    DeckExport,
    LoadRequest,
    LoadSetup,
    LoadState,
    load_state,
    normalized,
    validate_assignment,
)
from app.routes.projects import Owner, Revision, Store, etag, router


def service(request: Request) -> DeckService:
    return request.app.state.deck_service  # type: ignore[no-any-return]


Service = Annotated[DeckService, Depends(service)]


@router.get("/analyses/{analysis_id}/loads", response_model=LoadState)
def get_loads(analysis_id: UUID, owner: Owner, service: Service, response: Response) -> LoadState:
    result = service.state(owner, analysis_id)
    etag(response, result.analysis_revision)
    return result


@router.get("/analyses/{analysis_id}/revisions/{revision}/loads", response_model=LoadState)
def history(
    analysis_id: UUID,
    revision: Annotated[int, Path(ge=1)],
    owner: Owner,
    service: Service,
    response: Response,
) -> LoadState:
    result = service.state(owner, analysis_id, revision)
    etag(response, result.analysis_revision)
    return result


@router.post("/analyses/{analysis_id}/loads", response_model=LoadState)
def assign(
    analysis_id: UUID,
    payload: LoadRequest,
    revision: Revision,
    owner: Owner,
    store: Store,
    service: Service,
    response: Response,
) -> LoadState:
    # Preview before persistence rejects degenerate/nonfinite direction and moments.
    current, geometry, materials, setup = store.load_inputs(owner, analysis_id)
    if current.revision != revision:
        raise stale_revision()
    if geometry is None:
        raise DomainError(409, "geometry_required", "Accept geometry first")
    item = normalized(uuid4(), payload, geometry)
    validate_assignment(geometry, setup, item)
    if len(setup.assignments) >= 50:
        raise DomainError(422, "load_limit", "At most 50 face assignments are supported")
    load_state(
        current,
        geometry,
        materials,
        LoadSetup(assignments=[*setup.assignments, item]),
        service.imports.display(owner, geometry.id, "coarse"),
        store.bond_state(owner, analysis_id, revision).setup,
    )
    store.edit_loads(owner, analysis_id, revision, item)
    return get_loads(analysis_id, owner, service, response)


@router.delete("/analyses/{analysis_id}/loads/{assignment_id}", response_model=LoadState)
def remove(
    analysis_id: UUID,
    assignment_id: UUID,
    revision: Revision,
    owner: Owner,
    store: Store,
    service: Service,
    response: Response,
) -> LoadState:
    store.edit_loads(owner, analysis_id, revision, None, assignment_id)
    return get_loads(analysis_id, owner, service, response)


@router.post("/analyses/{analysis_id}/deck-exports", response_model=DeckExport, status_code=201)
def export(analysis_id: UUID, revision: Revision, owner: Owner, service: Service) -> DeckExport:
    return service.generate(owner, analysis_id, revision)


@router.get("/analyses/{analysis_id}/deck-exports", response_model=list[DeckExport])
def exports(analysis_id: UUID, owner: Owner, store: Store) -> list[DeckExport]:
    return store.list_exports(owner, analysis_id)


@router.get("/deck-exports/{export_id}", response_model=DeckExport)
def metadata(export_id: UUID, owner: Owner, store: Store) -> DeckExport:
    return store.export(owner, export_id)[0]


@router.get("/deck-exports/{export_id}/input", response_class=Response)
def download(export_id: UUID, owner: Owner, service: Service) -> Response:
    return Response(
        service.artifact(owner, export_id, "input"),
        media_type="text/plain",
        headers={"Content-Disposition": 'attachment; filename="analysis.inp"'},
    )


@router.get("/deck-exports/{export_id}/snapshot", response_class=Response)
def snapshot(export_id: UUID, owner: Owner, service: Service) -> Response:
    return Response(
        service.artifact(owner, export_id, "snapshot"),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="snapshot.json"'},
    )


class DirectionPreviewBatch(StrictModel):
    geometry_revision_id: UUID
    directions: list[DirectionSelection] = Field(min_length=1, max_length=200)


@router.post("/analyses/{analysis_id}/direction-previews", response_model=list[DirectionSnapshot])
def direction_previews(
    analysis_id: UUID,
    payload: DirectionPreviewBatch,
    revision: Revision,
    owner: Owner,
    store: Store,
    response: Response,
) -> list[DirectionSnapshot]:
    analysis, geometry, _, _ = store.load_inputs(owner, analysis_id)
    if analysis.revision != revision:
        raise stale_revision()
    if geometry is None or geometry.id != payload.geometry_revision_id:
        raise DomainError(422, "stale_direction", "Choose the analysis's pinned geometry")
    values = [resolve_direction(geometry, selection) for selection in payload.directions]
    # Read-only: no analysis row, job, native subprocess or physical load is created.
    etag(response, revision)
    return values
