"""Owned mesh controls, optimistic edits and an explicit coarsening planning preview."""

from uuid import UUID

from fastapi import Response

from app.domain.errors import DomainError, stale_revision
from app.domain.mesh import MeshControls, MeshSetup, MeshState, estimate, normalize, sizing
from app.routes.imports import Service as Imports
from app.routes.projects import Owner, Revision, Store, etag, router


def state(
    analysis_id: UUID, owner: UUID, store: Store, imports: Imports, setup: MeshSetup | None = None
) -> MeshState:
    analysis, geometry, saved = store.mesh_setup(owner, analysis_id)
    if geometry is None:
        raise DomainError(409, "geometry_required", "Accept geometry before configuring a mesh")
    return estimate(
        analysis_id,
        analysis.revision,
        geometry,
        imports.display(owner, geometry.id, "coarse"),
        setup or saved,
    )


@router.get("/analyses/{analysis_id}/mesh-controls", response_model=MeshState)
def get(
    analysis_id: UUID, owner: Owner, store: Store, imports: Imports, response: Response
) -> MeshState:
    result = state(analysis_id, owner, store, imports)
    etag(response, result.analysis_revision)
    return result


@router.post("/analyses/{analysis_id}/mesh-controls/preview", response_model=MeshState)
def preview(
    analysis_id: UUID,
    payload: MeshControls,
    revision: Revision,
    owner: Owner,
    store: Store,
    imports: Imports,
) -> MeshState:
    analysis, geometry, _ = store.mesh_setup(owner, analysis_id)
    if analysis.revision != revision:
        raise stale_revision()
    if geometry is None:
        raise DomainError(409, "geometry_required", "Accept geometry first")
    return state(analysis_id, owner, store, imports, normalize(geometry, payload))


@router.put("/analyses/{analysis_id}/mesh-controls", response_model=MeshState)
def save(
    analysis_id: UUID,
    payload: MeshControls,
    revision: Revision,
    owner: Owner,
    store: Store,
    imports: Imports,
    response: Response,
) -> MeshState:
    analysis, geometry, _ = store.mesh_setup(owner, analysis_id)
    if analysis.revision != revision:
        raise stale_revision()
    if geometry is None:
        raise DomainError(409, "geometry_required", "Accept geometry first")
    setup = normalize(geometry, payload)
    _, _, invalid = sizing(geometry, imports.display(owner, geometry.id, "coarse"), setup)
    if invalid:
        raise DomainError(422, "invalid_mesh_controls", " ".join(invalid))
    proposed = state(analysis_id, owner, store, imports, setup)
    if proposed.blockers and proposed.coarsening_proposal_m is None:
        raise DomainError(422, "invalid_mesh_controls", " ".join(proposed.blockers))
    # Oversize intentional settings may be saved, but admission refuses them.
    store.edit_mesh_setup(owner, analysis_id, revision, setup)
    return get(analysis_id, owner, store, imports, response)
