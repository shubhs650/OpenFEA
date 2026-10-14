"""Revision-bound SI mesh sizes, disclosed recovery and conservative resource estimates."""

import math
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.domain.base import StrictModel
from app.domain.errors import DomainError
from app.domain.imports import GeometryDisplay
from app.domain.models import CatalogID, GeometryRevision
from app.domain.units import PresetID, to_si


class LocalSizeInput(StrictModel):
    kind: Literal["body", "face"]
    entity_id: CatalogID
    size: float = Field(gt=0, strict=True)


class MeshControls(StrictModel):
    units: PresetID
    global_size: float | None = Field(default=None, gt=0, strict=True)
    local_sizes: list[LocalSizeInput] = Field(default_factory=list, max_length=100)
    curvature_elements: int = Field(default=16, ge=0, le=64, strict=True)
    recovery_enabled: bool = Field(default=False, strict=True)


class LocalSize(StrictModel):
    kind: Literal["body", "face"]
    entity_id: CatalogID
    size_m: float = Field(gt=0)
    source_size: float = Field(gt=0)
    source_units: PresetID


class MeshSetup(StrictModel):
    schema_version: Literal[1] = 1
    geometry_revision_id: UUID | None = None
    global_size_m: float | None = Field(default=None, gt=0)
    source_global_size: float | None = None
    source_units: PresetID | None = None
    local_sizes: list[LocalSize] = Field(default_factory=list, max_length=100)
    curvature_elements: int = 16
    recovery_enabled: bool = False


class MeshState(StrictModel):
    analysis_id: UUID
    analysis_revision: int
    geometry_revision_id: UUID | None
    setup: MeshSetup
    resolved_body_sizes_m: list[float]
    estimated_elements_upper: int
    estimated_nodes_upper: int
    estimated_dofs_upper: int
    limits: dict[str, int]
    blockers: list[str]
    warnings: list[str]
    coarsening_proposal_m: float | None
    estimate_basis: str


def normalize(geometry: GeometryRevision, controls: MeshControls) -> MeshSetup:
    if controls.curvature_elements not in (0, *range(8, 65)):
        raise DomainError(
            422, "invalid_curvature", "Curvature uses 0 (disabled) or 8–64 elements per full circle"
        )

    def size_m(value: float) -> float:
        converted = to_si(value, controls.units, "length")
        if converted < 1e-9:
            raise DomainError(422, "mesh_size_too_small", "Mesh size must be at least 1e-9 m")
        return converted

    bodies, faces = {b.id for b in geometry.bodies}, {f.id for f in geometry.faces}
    seen = set()
    local = []
    for item in controls.local_sizes:
        if (
            item.entity_id not in (bodies if item.kind == "body" else faces)
            or (item.kind, item.entity_id) in seen
        ):
            raise DomainError(
                422,
                "invalid_mesh_selection",
                "Mesh controls need unique body/face references from this geometry",
            )
        seen.add((item.kind, item.entity_id))
        local.append(
            LocalSize(
                kind=item.kind,
                entity_id=item.entity_id,
                size_m=size_m(item.size),
                source_size=item.size,
                source_units=controls.units,
            )
        )
    return MeshSetup(
        geometry_revision_id=geometry.id,
        global_size_m=size_m(controls.global_size) if controls.global_size else None,
        source_global_size=controls.global_size,
        source_units=controls.units,
        local_sizes=sorted(local, key=lambda x: (x.kind, x.entity_id)),
        curvature_elements=controls.curvature_elements,
        recovery_enabled=controls.recovery_enabled,
    )


def sizing(
    geometry: GeometryRevision, display: GeometryDisplay, setup: MeshSetup
) -> tuple[list[float], dict[str, float], list[str]]:
    blockers = []
    if setup.local_sizes and setup.geometry_revision_id != geometry.id:
        blockers.append(
            "Mesh local selections belong to a changed geometry. Review/remove controls: "
            + ", ".join(s.entity_id for s in setup.local_sizes)
        )
    sizes = [
        setup.global_size_m or max(b.bounds_m[a + 3] - b.bounds_m[a] for a in range(3)) / 2
        for b in display.bodies
    ]
    face_sizes = {}
    for item in setup.local_sizes:
        if setup.geometry_revision_id != geometry.id:
            continue
        if item.kind == "body":
            index = next((i for i, b in enumerate(display.bodies) if b.id == item.entity_id), None)
            if index is None:
                blockers.append(f"Unresolved mesh body: {item.entity_id}")
            else:
                sizes[index] = min(sizes[index], item.size_m)
        else:
            face = next((f for f in geometry.faces if f.id == item.entity_id), None)
            if face is None:
                blockers.append(f"Unresolved mesh face: {item.entity_id}")
            else:
                face_sizes[item.entity_id] = item.size_m
    for ref, size in face_sizes.items():
        body = next(f.body_id for f in geometry.faces if f.id == ref)
        index = next(i for i, b in enumerate(display.bodies) if b.id == body)
        if size > sizes[index]:
            blockers.append(f"Local face size must refine its body size: {ref}")
    if any(not math.isfinite(h) or h < 1e-9 for h in (*sizes, *face_sizes.values())):
        blockers.append("Mesh sizes must be finite and at least 1e-9 m.")
    return sizes, face_sizes, blockers


def estimate(
    analysis_id: UUID,
    revision: int,
    geometry: GeometryRevision,
    display: GeometryDisplay,
    setup: MeshSetup,
) -> MeshState:
    sizes, face_sizes, blockers = sizing(geometry, display, setup)
    upper = 0
    proposal = None
    for body, size in zip(display.bodies, sizes, strict=True):
        local = [
            h
            for ref, h in face_sizes.items()
            if next(f.body_id for f in geometry.faces if f.id == ref) == body.id
        ]
        minimum = min(size, *local) if local else size
        if setup.curvature_elements and any(
            f.body_id == body.id
            and str(f.signature.get("surface_type", "")).endswith("GeomAbs_Cylinder")
            for f in geometry.faces
        ):
            extent = min(body.bounds_m[a + 3] - body.bounds_m[a] for a in range(3))
            minimum = min(minimum, math.pi * extent / setup.curvature_elements)
        # Conservative regular-cell count at the finest requested size over the whole body.
        # This is a planning bound, not a memory/runtime calibration or capacity guarantee.
        log_count = math.log(12) + math.log(body.volume_m3) - 3 * math.log(max(minimum, 1e-100))
        count = 10**9 if log_count >= math.log(10**9) else max(1, math.ceil(math.exp(log_count)))
        upper += count
        if count > 3000:
            proposal = max(
                proposal or 0, (12 * sum(b.volume_m3 for b in display.bodies) / 2400) ** (1 / 3)
            )
    if upper > 3000:
        blockers.append(
            f"Conservative mesh estimate {upper} exceeds the 3,000-element local cap. "
            "Explicitly accept a coarser size and review finer overrides."
        )
        proposal = proposal or (12 * sum(b.volume_m3 for b in display.bodies) / 2400) ** (1 / 3)
    return MeshState(
        analysis_id=analysis_id,
        analysis_revision=revision,
        geometry_revision_id=geometry.id,
        setup=setup,
        resolved_body_sizes_m=sizes,
        estimated_elements_upper=upper,
        estimated_nodes_upper=10 * upper,
        estimated_dofs_upper=30 * upper,
        limits={
            "elements": 3000,
            "nodes": 30000,
            "native_wall_seconds": 60,
            "job_wall_seconds": 180,
            "rss_mib": 1536,
            "scratch_mib": 192,
            "max_attempts": 3 if setup.recovery_enabled else 1,
        },
        blockers=blockers,
        warnings=[
            "Count estimate uses the finest size over the whole body; "
            "actual meshing can still exceed the cap.",
            "No universal bytes-per-element RAM promise; "
            "sampled RSS/scratch and wall guards remain enforced.",
            "Local sizes refine: the smallest applicable global/body/face size wins.",
        ],
        coarsening_proposal_m=proposal,
        estimate_basis="12 × CAD volume / minimum requested size³; "
        "planning only; native caps authoritative",
    )
