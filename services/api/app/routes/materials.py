"""Owner/revision-guarded material editing against pinned immutable body identities."""

from typing import Annotated
from uuid import UUID

from fastapi import Path, Response

from app.domain.materials import (
    SAMPLES,
    DisplayUnitsPatch,
    MaterialAssignment,
    MaterialExample,
    MaterialState,
    snapshot_for,
)
from app.domain.units import PRESETS, UnitPreset
from app.routes.projects import Owner, Revision, Store, etag, router

Body = Annotated[str, Path(min_length=1, max_length=200)]


@router.get("/unit-presets", response_model=list[UnitPreset])
def unit_presets(owner: Owner) -> list[UnitPreset]:
    return list(PRESETS.values())


@router.get("/material-library", response_model=list[MaterialExample])
def material_library(owner: Owner) -> list[MaterialExample]:
    return [
        MaterialExample.model_validate(
            sample.model_dump(exclude={"schema_version", "kind", "confirmed"})
        )
        for sample in SAMPLES.values()
    ]


@router.get("/analyses/{analysis_id}/materials", response_model=MaterialState)
def get_materials(
    analysis_id: UUID, owner: Owner, store: Store, response: Response
) -> MaterialState:
    result = store.get_material_state(owner, analysis_id)
    etag(response, result.analysis_revision)
    return result


@router.get("/analyses/{analysis_id}/revisions/{revision}/materials", response_model=MaterialState)
def historical_materials(
    analysis_id: UUID,
    revision: Annotated[int, Path(ge=1)],
    owner: Owner,
    store: Store,
    response: Response,
) -> MaterialState:
    result = store.get_material_state(owner, analysis_id, revision)
    etag(response, result.analysis_revision)
    return result


@router.patch("/analyses/{analysis_id}/display-units", response_model=MaterialState)
def set_display_units(
    analysis_id: UUID,
    payload: DisplayUnitsPatch,
    revision: Revision,
    owner: Owner,
    store: Store,
    response: Response,
) -> MaterialState:
    result = store.edit_material_setup(owner, analysis_id, revision, display_units=payload.preset)
    etag(response, result.analysis_revision)
    return result


@router.put("/analyses/{analysis_id}/materials/{body_id}", response_model=MaterialState)
def assign_material(
    analysis_id: UUID,
    body_id: Body,
    payload: MaterialAssignment,
    revision: Revision,
    owner: Owner,
    store: Store,
    response: Response,
) -> MaterialState:
    result = store.edit_material_setup(
        owner, analysis_id, revision, body=body_id, material=snapshot_for(payload.material)
    )
    etag(response, result.analysis_revision)
    return result


@router.delete("/analyses/{analysis_id}/materials/{body_id}", response_model=MaterialState)
def remove_material(
    analysis_id: UUID,
    body_id: Body,
    revision: Revision,
    owner: Owner,
    store: Store,
    response: Response,
) -> MaterialState:
    result = store.edit_material_setup(owner, analysis_id, revision, body=body_id)
    etag(response, result.analysis_revision)
    return result
