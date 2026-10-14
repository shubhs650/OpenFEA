"""Resolve native immutable direction sources; callers cannot submit arbitrary bases."""

import math
from typing import Literal, cast
from uuid import UUID

from app.domain.base import StrictModel
from app.domain.errors import DomainError
from app.domain.models import CatalogID, GeometryRevision
from worker.directions import Basis, frame, unit
from worker.meshing import Vec, scale, sub


class DirectionSelection(StrictModel):
    kind: Literal["plane_normal", "straight_edge", "cylinder_axis"]
    reference_id: CatalogID
    reverse: bool = False


class DirectionSnapshot(DirectionSelection):
    geometry_revision_id: UUID
    vector: Vec
    basis: Basis
    origin_m: Vec


class DirectionPreviewRequest(StrictModel):
    geometry_revision_id: UUID
    direction: DirectionSelection


def resolve_direction(
    geometry: GeometryRevision, selection: DirectionSelection
) -> DirectionSnapshot:
    try:
        if selection.kind == "straight_edge":
            edge = next((e for e in geometry.edges if e.id == selection.reference_id), None)
            if edge is None:
                raise ValueError(
                    "Select a native edge in this geometry; legacy catalogs require reimport"
                )
            if (
                not edge.curve_type.endswith("GeomAbs_Line")
                or edge.start_m is None
                or edge.end_m is None
            ):
                raise ValueError("Direction selection requires a straight native edge")
            vector = sub(edge.end_m, edge.start_m)
            if math.hypot(*vector) <= 1e-12:
                raise ValueError("Straight edge is too short for an unambiguous direction")
            origin = scale(tuple(a + b for a, b in zip(edge.start_m, edge.end_m, strict=True)), 0.5)  # type: ignore[arg-type]
        else:
            face = next((f for f in geometry.faces if f.id == selection.reference_id), None)
            if face is None:
                raise ValueError("Direction face must belong to this pinned geometry")
            required = "GeomAbs_Plane" if selection.kind == "plane_normal" else "GeomAbs_Cylinder"
            if not str(face.signature.get("surface_type", "")).endswith(required):
                raise ValueError("Select a planar normal or cylindrical axis of the declared type")
            field = "outward_normal" if selection.kind == "plane_normal" else "axis_direction"
            raw = face.signature.get(field)
            point = face.signature.get(
                "center_m" if selection.kind == "plane_normal" else "axis_point_m"
            )
            if (
                not isinstance(raw, (list, tuple))
                or len(raw) != 3
                or not isinstance(point, (list, tuple))
                or len(point) != 3
            ):
                raise ValueError("Reimport geometry to obtain the verified native direction")
            vector = cast(Vec, tuple(float(v) for v in raw))  # type: ignore[arg-type]
            origin = cast(Vec, tuple(float(v) for v in point))  # type: ignore[arg-type]
        if not all(map(math.isfinite, origin)):
            raise ValueError("Native direction origin is nonfinite")
        vector = scale(unit(vector), -1) if selection.reverse else unit(vector)
        basis = frame(vector)
        return DirectionSnapshot(
            **selection.model_dump(),
            geometry_revision_id=geometry.id,
            vector=vector,
            basis=basis,
            origin_m=origin,
        )
    except (ValueError, TypeError, OverflowError) as error:
        raise DomainError(422, "invalid_direction", str(error)) from None


def verify_direction(geometry: GeometryRevision, saved: DirectionSnapshot) -> None:
    if saved.geometry_revision_id != geometry.id:
        raise DomainError(422, "stale_direction", "Review the direction on the current geometry")
    current = resolve_direction(
        geometry,
        DirectionSelection.model_validate(
            {k: getattr(saved, k) for k in ("kind", "reference_id", "reverse")}
        ),
    )
    if current != saved:
        raise DomainError(
            422, "direction_mismatch", "Frozen direction differs from its native source"
        )
