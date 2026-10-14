"""Guarded candidate measurement and explicit persistent connection approval."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Path, Request, Response

from app.domain.connection_service import ConnectionService
from app.domain.connections import BondCandidates, BondRequest, BondState
from app.routes.projects import Owner, Revision, Store, etag, router


def service(request: Request) -> ConnectionService:
    return request.app.state.connection_service  # type: ignore[no-any-return]


Service = Annotated[ConnectionService, Depends(service)]


@router.get("/analyses/{analysis_id}/bonds", response_model=BondState)
def state(analysis_id: UUID, owner: Owner, store: Store, response: Response) -> BondState:
    result = store.bond_state(owner, analysis_id)
    etag(response, result.analysis_revision)
    return result


@router.get("/analyses/{analysis_id}/revisions/{revision}/bonds", response_model=BondState)
def history(
    analysis_id: UUID, revision: Annotated[int, Path(ge=1)], owner: Owner, store: Store
) -> BondState:
    return store.bond_state(owner, analysis_id, revision)


@router.post("/analyses/{analysis_id}/bond-candidates", response_model=BondCandidates)
def candidates(
    analysis_id: UUID, revision: Revision, owner: Owner, service: Service
) -> BondCandidates:
    return service.candidates(owner, analysis_id, revision)


@router.post("/analyses/{analysis_id}/bonds", response_model=BondState)
def approve(
    analysis_id: UUID,
    payload: BondRequest,
    revision: Revision,
    owner: Owner,
    service: Service,
    response: Response,
) -> BondState:
    result = service.approve(owner, analysis_id, revision, payload)
    etag(response, result.analysis_revision)
    return result


@router.delete("/analyses/{analysis_id}/bonds/{bond_id}", response_model=BondState)
def remove(
    analysis_id: UUID,
    bond_id: UUID,
    revision: Revision,
    owner: Owner,
    store: Store,
    response: Response,
) -> BondState:
    result = store.edit_bonds(owner, analysis_id, revision, remove=bond_id)
    etag(response, result.analysis_revision)
    return result
