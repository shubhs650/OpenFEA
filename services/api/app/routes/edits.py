"""Owned preview/apply/undo and explicit face-assignment reselection."""

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import Depends, Query, Request, Response

from app.domain.directions import DirectionPreviewRequest, DirectionSelection, resolve_direction
from app.domain.edit_service import EditService
from app.domain.edits import (
    EditCommit,
    EditCreate,
    EditResult,
    GeometryEdit,
    ReselectBodies,
    ReselectFaces,
)
from app.domain.errors import DomainError, not_found, stale_revision
from app.domain.imports import GeometryDisplay
from app.domain.loads import LoadAssignment, LoadSetup, LoadState, load_state, validate_assignment
from app.routes.loads import Service as DeckService
from app.routes.loads import get_loads
from app.routes.projects import Owner, Revision, Store, etag, router


def service(request: Request) -> EditService:
    return request.app.state.edit_service  # type: ignore[no-any-return]


Service = Annotated[EditService, Depends(service)]


@router.post("/geometry/{geometry_id}/edits", response_model=GeometryEdit, status_code=201)
def preview(
    geometry_id: UUID, payload: EditCreate, revision: Revision, owner: Owner, service: Service
) -> GeometryEdit:
    return service.preview(owner, geometry_id, revision, payload)


@router.get("/geometry-edits/{edit_id}", response_model=GeometryEdit)
def get(edit_id: UUID, owner: Owner, service: Service) -> GeometryEdit:
    return service.repository.get(owner, edit_id)


@router.get("/geometry-edits/{edit_id}/display", response_model=GeometryDisplay)
def display(
    edit_id: UUID,
    owner: Owner,
    service: Service,
    lod: Annotated[Literal["coarse", "fine"], Query()] = "coarse",
) -> GeometryDisplay:
    return service.display(owner, edit_id, lod)


@router.post("/geometry/{geometry_id}/edit-commits", response_model=EditResult)
def commit(
    geometry_id: UUID,
    payload: EditCommit,
    revision: Revision,
    owner: Owner,
    service: Service,
    response: Response,
) -> EditResult:
    result = service.commit(owner, payload.preview_id, geometry_id, revision)
    etag(response, result.project.revision)
    return result


@router.post("/geometry-edits/{edit_id}/undo", response_model=EditResult)
def undo(
    edit_id: UUID, revision: Revision, owner: Owner, service: Service, response: Response
) -> EditResult:
    result = service.undo(owner, edit_id, revision)
    etag(response, result.project.revision)
    return result


@router.put("/analyses/{analysis_id}/loads/{assignment_id}/faces", response_model=LoadState)
def reselect(
    analysis_id: UUID,
    assignment_id: UUID,
    payload: ReselectFaces,
    revision: Revision,
    owner: Owner,
    store: Store,
    service: DeckService,
    response: Response,
) -> LoadState:
    analysis, geometry, materials, setup = store.load_inputs(owner, analysis_id)
    if analysis.revision != revision:
        raise stale_revision()
    old = next((a for a in setup.assignments if a.id == assignment_id), None)
    if old is None:
        raise not_found()
    if not old.review_faces or geometry is None:
        raise DomainError(
            409, "review_unavailable", "This assignment does not need geometry review"
        )
    # Retain magnitude, sign, global direction and all source quantities exactly.
    fields = old.model_dump() | {
        "geometry_revision_id": payload.geometry_revision_id,
        "face_ids": sorted(set(payload.face_ids)),
        "review_faces": [],
        "combine_confirmed": payload.combine_confirmed,
    }
    if old.kind == "symmetry":
        fields.update(
            symmetry_directions={
                ref: resolve_direction(
                    geometry, DirectionSelection(kind="plane_normal", reference_id=ref)
                )
                for ref in fields["face_ids"]
            },
            review_direction=False,
        )
    item = LoadAssignment.model_validate(fields)
    validate_assignment(geometry, setup, item)
    load_state(
        analysis,
        geometry,
        materials,
        LoadSetup(assignments=[a for a in setup.assignments if a.id != old.id] + [item]),
        service.imports.display(owner, geometry.id, "coarse"),
    )
    store.edit_loads(owner, analysis_id, revision, item)
    return get_loads(analysis_id, owner, service, response)


@router.put("/analyses/{analysis_id}/loads/{assignment_id}/bodies", response_model=LoadState)
def reselect_bodies(
    analysis_id: UUID,
    assignment_id: UUID,
    payload: ReselectBodies,
    revision: Revision,
    owner: Owner,
    store: Store,
    service: DeckService,
    response: Response,
) -> LoadState:
    analysis, geometry, materials, setup = store.load_inputs(owner, analysis_id)
    if analysis.revision != revision:
        raise stale_revision()
    old = next((a for a in setup.assignments if a.id == assignment_id), None)
    if old is None:
        raise not_found()
    if old.kind != "gravity" or not old.review_bodies or geometry is None:
        raise DomainError(
            409, "review_unavailable", "This gravity assignment does not need body review"
        )
    item = LoadAssignment.model_validate(
        old.model_dump()
        | {
            "geometry_revision_id": payload.geometry_revision_id,
            "body_ids": sorted(set(payload.body_ids)),
            "review_bodies": [],
            "combine_confirmed": payload.combine_confirmed,
        }
    )
    validate_assignment(geometry, setup, item)
    load_state(
        analysis,
        geometry,
        materials,
        LoadSetup(assignments=[a for a in setup.assignments if a.id != old.id] + [item]),
        service.imports.display(owner, geometry.id, "coarse"),
    )
    store.edit_loads(owner, analysis_id, revision, item)
    return get_loads(analysis_id, owner, service, response)


class ReselectDirection(DirectionPreviewRequest):
    reviewed: Literal[True]


@router.put("/analyses/{analysis_id}/loads/{assignment_id}/direction", response_model=LoadState)
def reselect_direction(
    analysis_id: UUID,
    assignment_id: UUID,
    payload: ReselectDirection,
    revision: Revision,
    owner: Owner,
    store: Store,
    service: DeckService,
    response: Response,
) -> LoadState:
    analysis, geometry, materials, setup = store.load_inputs(owner, analysis_id)
    if analysis.revision != revision:
        raise stale_revision()
    old = next((a for a in setup.assignments if a.id == assignment_id), None)
    if old is None:
        raise not_found()
    if not old.review_direction or old.direction is None or old.review_faces or geometry is None:
        raise DomainError(
            409, "review_unavailable", "Review target faces first, then reselect this direction"
        )
    if geometry.id != payload.geometry_revision_id:
        raise DomainError(422, "stale_direction", "Select the current pinned geometry")
    direction = resolve_direction(geometry, payload.direction)
    fields: dict[str, Any] = {
        "geometry_revision_id": geometry.id,
        "direction": direction,
        "review_direction": False,
    }
    if old.kind == "directional_force":
        assert old.source_magnitude is not None and old.source_units is not None
        from app.domain.units import to_si
        from worker.meshing import scale

        fields["force_n"] = scale(
            direction.vector, to_si(old.source_magnitude, old.source_units, "force")
        )
    item = LoadAssignment.model_validate(old.model_dump() | fields)
    validate_assignment(geometry, setup, item)
    load_state(
        analysis,
        geometry,
        materials,
        LoadSetup(assignments=[a for a in setup.assignments if a.id != old.id] + [item]),
        service.imports.display(owner, geometry.id, "coarse"),
    )
    store.edit_loads(owner, analysis_id, revision, item)
    return get_loads(analysis_id, owner, service, response)
