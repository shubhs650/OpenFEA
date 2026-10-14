"""Revision-bound, canonical fixed/pressure/total-force assignments and previews."""

import math
from typing import Annotated, Any, Literal, cast
from uuid import UUID

from pydantic import Field, model_validator

from app.domain.base import StrictModel
from app.domain.errors import DomainError
from app.domain.imports import GeometryDisplay
from app.domain.materials import MaterialSetup
from app.domain.mesh import MeshSetup
from app.domain.models import Analysis, CatalogID, GeometryRevision, Hash, Name
from app.domain.units import PresetID, to_si
from worker.actions import rigid_rank
from worker.meshing import Vec, add, cross, norm, scale, sub

Number = Annotated[float, Field(strict=True)]
Vector = tuple[Number, Number, Number]


class FaceInput(StrictModel):
    geometry_revision_id: UUID
    face_ids: list[CatalogID] = Field(min_length=1, max_length=200)
    name: Name


class FixedInput(FaceInput):
    kind: Literal["fixed"]


class DisplacementInput(FaceInput):
    kind: Literal["displacement"]
    units: PresetID
    axis: Literal["x", "y", "z"]
    displacement: Number


class GravityInput(StrictModel):
    kind: Literal["gravity"]
    geometry_revision_id: UUID
    body_ids: list[CatalogID] = Field(min_length=1, max_length=10)
    name: Name
    units: PresetID
    acceleration: Vector
    combine_confirmed: bool = False

    @model_validator(mode="after")
    def nonzero(self) -> "GravityInput":
        if not any(self.acceleration):
            raise ValueError("Gravity acceleration must be nonzero")
        return self


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
    assignment: Annotated[
        FixedInput | PressureInput | ForceInput | DisplacementInput | GravityInput,
        Field(discriminator="kind"),
    ]


class LoadAssignment(StrictModel):
    id: UUID
    name: Name
    kind: Literal["fixed", "pressure", "force", "displacement", "gravity"]
    geometry_revision_id: UUID
    face_ids: list[CatalogID] = Field(default_factory=list)
    body_ids: list[CatalogID] = Field(default_factory=list)
    axis: Literal["x", "y", "z"] | None = None
    displacement_m: float | None = None
    acceleration_m_s2: Vec | None = None
    pressure_pa: float | None = None
    force_n: Vec | None = None
    source_units: PresetID | None = None
    source_pressure: float | None = None
    source_force: Vec | None = None
    source_displacement: float | None = None
    source_acceleration: Vec | None = None
    combine_confirmed: bool = False
    review_faces: list[CatalogID] = Field(default_factory=list)
    review_bodies: list[CatalogID] = Field(default_factory=list)

    @model_validator(mode="after")
    def targets(self) -> "LoadAssignment":
        if self.kind == "gravity":
            if (
                not self.body_ids
                or self.face_ids
                or not self.acceleration_m_s2
                or not any(self.acceleration_m_s2)
            ):
                raise ValueError("Gravity needs complete bodies and nonzero acceleration")
        elif self.body_ids or self.review_bodies or not self.face_ids:
            raise ValueError("Face assignments need complete face selections")
        if self.kind == "displacement" and (self.axis is None or self.displacement_m is None):
            raise ValueError("Prescribed displacement requires one global component")
        return self


class LoadSetup(StrictModel):
    schema_version: Literal[1] = 1
    assignments: list[LoadAssignment] = Field(default_factory=list, max_length=50)


class LoadMarker(StrictModel):
    assignment_id: UUID
    face_id: str
    body_id: str
    kind: Literal["fixed", "pressure", "force", "displacement", "gravity"]
    position_m: Vec
    direction: Vec
    tip_on_face: bool = False


class LoadPreview(StrictModel):
    assignment_id: UUID
    area_m2: float
    force_n: Vec
    moment_nm: Vec
    force_scale_n: float = 0
    moment_scale_nm: float = 0
    mass_kg: float | None = None


class LoadState(StrictModel):
    analysis_id: UUID
    analysis_revision: int
    geometry_revision_id: UUID | None
    setup: LoadSetup
    previews: list[LoadPreview]
    markers: list[LoadMarker]
    total_force_n: Vec
    total_moment_nm: Vec
    force_scale_n: float = 0
    moment_scale_nm: float = 0
    characteristic_length_m: float = 0
    resultant_complete: bool = True
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
    )
    try:
        if isinstance(item, GravityInput):
            fields.update(
                body_ids=sorted(set(item.body_ids)),
                acceleration_m_s2=tuple(
                    to_si(v, item.units, "acceleration") for v in item.acceleration
                ),
                source_units=item.units,
                source_acceleration=item.acceleration,
                combine_confirmed=item.combine_confirmed,
            )
            return LoadAssignment.model_validate(fields)
        fields["face_ids"] = sorted(set(item.face_ids))
        if isinstance(item, DisplacementInput):
            displacement = to_si(item.displacement, item.units, "length")
            if item.displacement != 0 and displacement == 0:
                raise ValueError("Nonzero displacement underflows in SI")
            fields.update(
                axis=item.axis,
                displacement_m=displacement,
                source_displacement=item.displacement,
                source_units=item.units,
            )
            return LoadAssignment.model_validate(fields)
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


def support_components(assignment: LoadAssignment) -> dict[int, float]:
    if assignment.kind == "fixed":
        return {1: 0, 2: 0, 3: 0}
    if assignment.kind == "displacement":
        assert assignment.axis is not None and assignment.displacement_m is not None
        return {"xyz".index(assignment.axis) + 1: assignment.displacement_m}
    return {}


def validate_assignment(geometry: GeometryRevision, setup: LoadSetup, item: LoadAssignment) -> None:
    if geometry.id != item.geometry_revision_id:
        raise DomainError(
            422, "stale_geometry", "The selection belongs to another geometry revision"
        )
    if item.kind == "gravity":
        if not set(item.body_ids) <= {b.id for b in geometry.bodies}:
            raise DomainError(422, "invalid_body", "Gravity bodies must belong to this geometry")
        if (
            any(
                old.id != item.id
                and old.kind == "gravity"
                and not old.review_bodies
                and set(old.body_ids) & set(item.body_ids)
                for old in setup.assignments
            )
            and not item.combine_confirmed
        ):
            raise DomainError(
                409,
                "load_overlap",
                "Body accelerations overlap. Review and explicitly confirm their combination",
            )
        return
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
        and old.kind in ("pressure", "force")
        and item.kind in ("pressure", "force")
        and set(old.face_ids) & set(item.face_ids)
        for old in setup.assignments
    )
    if overlaps and not item.combine_confirmed:
        raise DomainError(
            409,
            "load_overlap",
            "Loads overlap on a face. Review and explicitly confirm their combination",
        )

    incoming = support_components(item)
    if incoming:
        touching = set(item.face_ids) | {
            n for f in geometry.faces if f.id in item.face_ids for n in f.neighbors
        }
        for old in setup.assignments:
            if old.id == item.id or old.review_faces or not touching.intersection(old.face_ids):
                continue
            previous = support_components(old)
            if any(
                axis in previous and previous[axis] != value for axis, value in incoming.items()
            ):
                raise DomainError(
                    422,
                    "conflicting_constraints",
                    "Shared faces/edges prescribe different values for one global component",
                )


def load_state(
    analysis: Analysis,
    geometry: GeometryRevision | None,
    materials: MaterialSetup,
    setup: LoadSetup,
    display: GeometryDisplay | None,
) -> LoadState:
    previews: list[LoadPreview] = []
    markers: list[LoadMarker] = []
    warnings: list[str] = []
    blockers: list[str] = []
    total_force: Vec = (0, 0, 0)
    total_moment: Vec = (0, 0, 0)
    complete = True
    length = 0.0
    if geometry is None:
        blockers.append("Accept geometry and create a geometry-pinned analysis.")
    else:
        assigned = {a.body_id: a.material.properties for a in materials.assignments}
        body_display = {b.id: b for b in display.bodies} if display else {}
        face_display = {f.id: f for f in display.faces} if display else {}
        if body_display:
            length = max(
                max(b.bounds_m[a + 3] for b in body_display.values())
                - min(b.bounds_m[a] for b in body_display.values())
                for a in range(3)
            )
        for index, body in enumerate(geometry.bodies, 1):
            if body.id not in assigned:
                blockers.append(f"Body {index} needs a confirmed material.")
            rows: list[tuple[Vec, int]] = []
            for item in setup.assignments:
                if item.kind not in ("fixed", "displacement") or item.review_faces:
                    continue
                axes = (1, 2, 3) if item.kind == "fixed" else ("xyz".index(item.axis or "x") + 1,)
                for ref in item.face_ids:
                    face = face_display.get(ref)
                    if face and face.body_id == body.id:
                        rows.extend((point, axis) for point in face.points_m for axis in axes)
            native = body_display.get(body.id)
            rank = (
                rigid_rank(
                    rows,
                    (native.bounds_m[0], native.bounds_m[1], native.bounds_m[2]),
                    max(native.bounds_m[a + 3] - native.bounds_m[a] for a in range(3)),
                )
                if native
                else 0
            )
            if rank < 6:
                blockers.append(
                    f"Body {index} needs a fixed face or sufficient global component supports "
                    f"(rigid-motion rank {rank}/6)."
                )
        if not any(
            a.kind in ("pressure", "force", "gravity")
            or (a.kind == "displacement" and a.displacement_m != 0)
            for a in setup.assignments
        ):
            blockers.append(
                "Add a nonzero pressure, total force, gravity or prescribed displacement."
            )
        for item in setup.assignments:
            if item.review_faces or item.review_bodies:
                complete = False
                targets = item.review_faces or item.review_bodies
                target_kind = "bodies" if item.kind == "gravity" else "faces"
                blockers.append(
                    f"{item.name}: geometry changed. Reselect the intended {target_kind} "
                    "before meshing: " + ", ".join(targets)
                )
                continue
            # Existing overlapping assignments were already explicitly reviewed;
            # reads validate their references without demanding approval again.
            validate_assignment(geometry, LoadSetup(), item)
            resultant: Vec = (0, 0, 0)
            moment: Vec = (0, 0, 0)
            force_scale = moment_scale = area = 0.0
            mass: float | None = None
            if item.kind == "gravity":
                assert item.acceleration_m_s2 is not None
                acceleration = item.acceleration_m_s2
                magnitude = math.hypot(*acceleration)
                mass = 0.0
                unknown = False
                for body_id in item.body_ids:
                    body_native = body_display.get(body_id)
                    if body_native is None or body_native.center_m is None:
                        raise DomainError(
                            422,
                            "gravity_centroid_unavailable",
                            "Reimport geometry to obtain native body centres of mass "
                            "before gravity.",
                        )
                    markers.append(
                        LoadMarker(
                            assignment_id=item.id,
                            face_id="",
                            body_id=body_id,
                            kind="gravity",
                            position_m=body_native.center_m,
                            direction=cast(
                                Vec, tuple(v / magnitude if v else 0.0 for v in acceleration)
                            ),
                        )
                    )
                    properties = assigned.get(body_id)
                    density = properties.density_kg_m3 if properties else None
                    if density is None:
                        blockers.append(
                            f"{item.name}: body {body_id} needs positive density for gravity; "
                            "weight is unavailable."
                        )
                        unknown = True
                        continue
                    weight = scale(acceleration, density * body_native.volume_m3)
                    torque = cross(body_native.center_m, weight)
                    mass += density * body_native.volume_m3
                    resultant = add(resultant, weight)
                    moment = add(moment, torque)
                    force_scale += math.hypot(*weight)
                    moment_scale += math.hypot(*torque)
                if unknown:
                    complete = False
                    continue  # Withhold the whole assignment; no fabricated zero/partial weight.
            else:
                metrics = [face_metrics(geometry, f) for f in item.face_ids]
                area = sum(m[0] for m in metrics)
                for face_id, (face_area, center, body_id) in zip(
                    item.face_ids, metrics, strict=True
                ):
                    vector: Vec = (0, 0, 0)
                    if item.kind == "pressure":
                        assert display is not None and item.pressure_pa is not None
                        vector = scale(
                            outward_normal(display, face_id, geometry),
                            -item.pressure_pa * face_area,
                        )
                    elif item.kind == "force":
                        assert item.force_n is not None
                        vector = scale(item.force_n, face_area / area)
                    magnitude = math.hypot(*vector)
                    if not math.isfinite(magnitude) or (
                        item.kind in ("pressure", "force") and magnitude == 0
                    ):
                        raise DomainError(
                            422, "invalid_load", "Load preview must be finite and nonzero"
                        )
                    direction: Vec = (
                        cast(Vec, tuple(v / magnitude if v else 0.0 for v in vector))
                        if magnitude
                        else (0, 0, 0)
                    )
                    if item.kind == "displacement":
                        assert item.axis is not None and item.displacement_m is not None
                        direction = cast(
                            Vec,
                            tuple(
                                (-1.0 if item.displacement_m < 0 else 1.0)
                                if a == "xyz".index(item.axis)
                                else 0.0
                                for a in range(3)
                            ),
                        )
                    markers.append(
                        LoadMarker(
                            assignment_id=item.id,
                            face_id=face_id,
                            body_id=body_id,
                            kind=item.kind,
                            tip_on_face=item.kind == "pressure" and (item.pressure_pa or 0) > 0,
                            position_m=center,
                            direction=direction,
                        )
                    )
                    resultant = add(resultant, vector)
                    torque = cross(center, vector)
                    moment = add(moment, torque)
                    force_scale += math.hypot(*vector)
                    moment_scale += math.hypot(*torque)
            if not all(
                math.isfinite(v)
                for v in (area, force_scale, moment_scale, mass or 0, *resultant, *moment)
            ):
                raise DomainError(
                    422, "invalid_load", "Load resultant, mass and moment must be finite"
                )
            previews.append(
                LoadPreview(
                    assignment_id=item.id,
                    area_m2=area,
                    force_n=resultant,
                    moment_nm=moment,
                    force_scale_n=force_scale,
                    moment_scale_nm=moment_scale,
                    mass_kg=mass,
                )
            )
            total_force = add(total_force, resultant)
            total_moment = add(total_moment, moment)
            if item.combine_confirmed:
                warnings.append(
                    f"{item.name}: overlapping loads explicitly combined; signed resultants add."
                )
    force_reference = math.fsum(p.force_scale_n for p in previews)
    moment_reference = max(math.fsum(p.moment_scale_nm for p in previews), force_reference * length)
    if not all(
        math.isfinite(v) for v in (*total_force, *total_moment, force_reference, moment_reference)
    ):
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
        force_scale_n=force_reference,
        moment_scale_nm=moment_reference,
        characteristic_length_m=length,
        resultant_complete=complete,
        blockers=blockers,
        warnings=warnings,
    )
