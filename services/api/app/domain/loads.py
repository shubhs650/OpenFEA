"""Revision-bound, canonical fixed/pressure/total-force assignments and previews."""

import math
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.domain.base import StrictModel
from app.domain.errors import DomainError
from app.domain.imports import GeometryDisplay
from app.domain.materials import MaterialSetup
from app.domain.mesh import MeshSetup
from app.domain.models import Analysis, CatalogID, GeometryRevision, Hash, Name
from app.domain.units import PresetID, to_si
from worker.meshing import Vec, add, cross, norm, scale, sub

Number = Annotated[float, Field(strict=True)]
Vector = tuple[Number, Number, Number]


class FaceInput(StrictModel):
    geometry_revision_id: UUID
    face_ids: list[CatalogID] = Field(min_length=1, max_length=200)
    name: Name


class FixedInput(FaceInput):
    kind: Literal["fixed"]


class PressureInput(FaceInput):
    kind: Literal["pressure"]
    units: PresetID
    pressure: Number
    combine_confirmed: bool = False

    @model_validator(mode="after")
    def nonzero(self) -> "PressureInput":
        if self.pressure == 0:
            raise ValueError("Pressure must be nonzero")
        return self


class ForceInput(FaceInput):
    kind: Literal["force"]
    units: PresetID
    force: Vector
    combine_confirmed: bool = False

    @model_validator(mode="after")
    def nonzero(self) -> "ForceInput":
        if not any(self.force):
            raise ValueError("Total force must be nonzero")
        return self


class LoadRequest(StrictModel):
    assignment: Annotated[FixedInput | PressureInput | ForceInput, Field(discriminator="kind")]


class LoadAssignment(StrictModel):
    id: UUID
    name: Name
    kind: Literal["fixed", "pressure", "force"]
    geometry_revision_id: UUID
    face_ids: list[CatalogID]
    pressure_pa: float | None = None
    force_n: Vec | None = None
    source_units: PresetID | None = None
    source_pressure: float | None = None
    source_force: Vec | None = None
    combine_confirmed: bool = False
    review_faces: list[CatalogID] = Field(default_factory=list)


class LoadSetup(StrictModel):
    schema_version: Literal[1] = 1
    assignments: list[LoadAssignment] = Field(default_factory=list, max_length=50)


class LoadMarker(StrictModel):
    assignment_id: UUID
    face_id: str
    body_id: str
    kind: Literal["fixed", "pressure", "force"]
    position_m: Vec
    direction: Vec
    tip_on_face: bool = False


class LoadPreview(StrictModel):
    assignment_id: UUID
    area_m2: float
    force_n: Vec
    moment_nm: Vec


class LoadState(StrictModel):
    analysis_id: UUID
    analysis_revision: int
    geometry_revision_id: UUID | None
    setup: LoadSetup
    previews: list[LoadPreview]
    markers: list[LoadMarker]
    total_force_n: Vec
    total_moment_nm: Vec
    blockers: list[str]
    warnings: list[str]


class DeckSnapshot(StrictModel):
    schema_version: Literal[1] = 1
    analysis: Analysis
    geometry: GeometryRevision
    materials: MaterialSetup
    loads: LoadSetup
    mesh_setup: MeshSetup = Field(default_factory=MeshSetup)


class DeckExport(StrictModel):
    id: UUID
    analysis_id: UUID
    analysis_revision: int
    geometry_revision_id: UUID
    snapshot_sha256: Hash
    deck_sha256: Hash
    mesh_sha256: Hash
    summary: dict[str, float | int | str | list[str]]


def normalized(identifier: UUID, request: LoadRequest) -> LoadAssignment:
    item = request.assignment
    fields: dict[str, Any] = dict(
        id=identifier,
        name=item.name,
        kind=item.kind,
        geometry_revision_id=item.geometry_revision_id,
        face_ids=sorted(set(item.face_ids)),
    )
    try:
        if isinstance(item, PressureInput):
            fields.update(
                pressure_pa=to_si(item.pressure, item.units, "stress"),
                source_units=item.units,
                source_pressure=item.pressure,
                combine_confirmed=item.combine_confirmed,
            )
            return LoadAssignment.model_validate(fields)
        if isinstance(item, ForceInput):
            force = tuple(to_si(v, item.units, "force") for v in item.force)
            fields.update(
                force_n=force,
                source_units=item.units,
                source_force=item.force,
                combine_confirmed=item.combine_confirmed,
            )
            return LoadAssignment.model_validate(fields)
        return LoadAssignment.model_validate(fields)
    except ValueError:
        raise DomainError(422, "invalid_load", "Load must be finite in canonical SI") from None


def face_metrics(geometry: GeometryRevision, face_id: str) -> tuple[float, Vec, str]:
    face = next((f for f in geometry.faces if f.id == face_id), None)
    if face is None:
        raise DomainError(422, "invalid_face", "Select faces from this analysis geometry revision")
    try:
        area = float(face.signature["area_m2"])  # type: ignore[arg-type]
        center = tuple(float(v) for v in face.signature["center_m"])  # type: ignore[union-attr,arg-type]
        if area <= 0 or len(center) != 3 or not all(math.isfinite(v) for v in (area, *center)):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise DomainError(
            422, "invalid_face", "The selected face has no valid native area/centroid"
        ) from None
    return area, (center[0], center[1], center[2]), face.body_id


def outward_normal(display: GeometryDisplay, face_id: str, geometry: GeometryRevision) -> Vec:
    face = next(f for f in display.faces if f.id == face_id)
    vectors = [
        cross(
            sub(face.points_m[t[1]], face.points_m[t[0]]),
            sub(face.points_m[t[2]], face.points_m[t[0]]),
        )
        for t in face.triangles
    ]
    normal = next((scale(v, 1 / norm(v)) for v in vectors if norm(v) > 1e-15), None)
    if normal is None or any(
        norm(sub(scale(v, 1 / norm(v)), normal)) > 1e-10 for v in vectors if norm(v) > 1e-15
    ):
        raise DomainError(
            422, "unsupported_pressure_face", "Basic pressure requires a valid planar face"
        )
    catalog = next(f for f in geometry.faces if f.id == face_id)
    declared = catalog.signature.get("outward_normal")
    if (
        not isinstance(declared, list)
        or len(declared) != 3
        or not all(isinstance(v, (int, float)) for v in declared)
    ):
        raise DomainError(
            422,
            "normal_unavailable",
            "Reimport geometry to obtain verified native pressure normals",
        )
    native = (float(declared[0]), float(declared[1]), float(declared[2]))  # type: ignore[arg-type]
    if norm(sub(normal, native)) > 1e-10:
        raise DomainError(
            422, "normal_mismatch", "Display orientation differs from the native face normal"
        )
    return normal


def validate_assignment(geometry: GeometryRevision, setup: LoadSetup, item: LoadAssignment) -> None:
    if geometry.id != item.geometry_revision_id:
        raise DomainError(
            422, "stale_geometry", "The selection belongs to another geometry revision"
        )
    for face_id in item.face_ids:
        face_metrics(geometry, face_id)
        face = next(f for f in geometry.faces if f.id == face_id)
        if item.kind == "pressure" and not str(face.signature.get("surface_type", "")).endswith(
            "GeomAbs_Plane"
        ):
            raise DomainError(
                422,
                "unsupported_pressure_face",
                "Basic pressure currently supports planar faces only",
            )
    overlaps = any(
        not old.review_faces
        and old.id != item.id
        and old.kind != "fixed"
        and item.kind != "fixed"
        and set(old.face_ids) & set(item.face_ids)
        for old in setup.assignments
    )
    if overlaps and not item.combine_confirmed:
        raise DomainError(
            409,
            "load_overlap",
            "Loads overlap on a face. Review and explicitly confirm their combination",
        )


def load_state(
    analysis: Analysis,
    geometry: GeometryRevision | None,
    materials: MaterialSetup,
    setup: LoadSetup,
    display: GeometryDisplay | None,
) -> LoadState:
    previews, markers, warnings, blockers = [], [], [], []
    total_force: Vec = (0, 0, 0)
    total_moment: Vec = (0, 0, 0)
    if geometry is None:
        blockers.append("Accept geometry and create a geometry-pinned analysis.")
    else:
        assigned = {a.body_id for a in materials.assignments}
        fixed = {
            f
            for a in setup.assignments
            if a.kind == "fixed" and not a.review_faces
            for f in a.face_ids
        }
        for index, body in enumerate(geometry.bodies, 1):
            if body.id not in assigned:
                blockers.append(f"Body {index} needs a confirmed material.")
            if not any(f.body_id == body.id and f.id in fixed for f in geometry.faces):
                blockers.append(f"Body {index} needs a fixed face in this independent-body slice.")
        if not any(a.kind != "fixed" for a in setup.assignments):
            blockers.append("Add a nonzero pressure or total force.")
        for item in setup.assignments:
            if item.review_faces:
                blockers.append(
                    f"{item.name}: geometry changed. Reselect the intended faces before meshing: "
                    + ", ".join(item.review_faces)
                )
                continue
            if item.geometry_revision_id != geometry.id:
                raise DomainError(
                    422, "stale_geometry", "Saved assignment belongs to another geometry revision"
                )
            metrics = [face_metrics(geometry, f) for f in item.face_ids]
            area = sum(m[0] for m in metrics)
            resultant: Vec = (0, 0, 0)
            moment: Vec = (0, 0, 0)
            for face_id, (face_area, center, body_id) in zip(item.face_ids, metrics, strict=True):
                vector: Vec = (0, 0, 0)
                if item.kind == "pressure":
                    assert display is not None and item.pressure_pa is not None
                    vector = scale(
                        outward_normal(display, face_id, geometry), -item.pressure_pa * face_area
                    )
                elif item.kind == "force":
                    assert item.force_n is not None
                    vector = scale(item.force_n, face_area / area)
                length = math.hypot(*vector)
                if not math.isfinite(length) or (item.kind != "fixed" and length == 0):
                    raise DomainError(
                        422, "invalid_load", "Load preview must be finite and nonzero"
                    )
                markers.append(
                    LoadMarker(
                        assignment_id=item.id,
                        face_id=face_id,
                        body_id=body_id,
                        kind=item.kind,
                        tip_on_face=item.kind == "pressure" and (item.pressure_pa or 0) > 0,
                        position_m=center,
                        direction=(
                            vector[0] / length if vector[0] else 0.0,
                            vector[1] / length if vector[1] else 0.0,
                            vector[2] / length if vector[2] else 0.0,
                        )
                        if length
                        else (0, 0, 0),
                    )
                )
                resultant = add(resultant, vector)
                moment = add(moment, cross(center, vector))
            if not all(math.isfinite(v) for v in (area, *resultant, *moment)):
                raise DomainError(422, "invalid_load", "Load resultant and moment must be finite")
            previews.append(
                LoadPreview(
                    assignment_id=item.id, area_m2=area, force_n=resultant, moment_nm=moment
                )
            )
            total_force = add(total_force, resultant)
            total_moment = add(total_moment, moment)
            if item.combine_confirmed:
                warnings.append(
                    f"{item.name}: overlapping loads explicitly combined; signed resultants add."
                )
            if item.kind != "fixed" and set(item.face_ids) & fixed:
                warnings.append(
                    f"{item.name}: loading a fixed face needs review; "
                    "force export may be blocked on fixed degrees of freedom."
                )
    if not all(math.isfinite(v) for v in (*total_force, *total_moment)):
        raise DomainError(422, "invalid_load", "Load resultant and moment must be finite")
    return LoadState(
        analysis_id=analysis.id,
        analysis_revision=analysis.revision,
        geometry_revision_id=analysis.geometry_revision_id,
        setup=setup,
        previews=previews,
        markers=markers,
        total_force_n=total_force,
        total_moment_nm=total_moment,
        blockers=blockers,
        warnings=warnings,
    )
