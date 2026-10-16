"""Cross-check portable physical values against retained source values and native references."""

import hashlib
import json
from typing import Any, cast
from uuid import UUID

from app.domain.archives import ArchiveAnalysis
from app.domain.directions import verify_direction
from app.domain.materials import CustomMaterial, custom_snapshot
from app.domain.units import Quantity, to_si


def review_hash(geometry_id: UUID, report: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            {"geometry_id": str(geometry_id), "report": report.model_dump(mode="json")},
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


def validate_physics(a: ArchiveAnalysis, geometries: dict[Any, Any]) -> None:
    for body in a.materials.assignments:
        material = body.material
        expected = custom_snapshot(
            CustomMaterial(
                kind="custom",
                units=material.source_units,
                values=material.source_values,
                provenance=material.provenance,
                confirmed=True,
            )
        )
        if expected.properties != material.properties:
            raise ValueError("Material source/SI properties disagree")
    mesh = a.mesh
    if mesh.global_size_m is not None and (
        mesh.source_units is None
        or mesh.source_global_size is None
        or to_si(mesh.source_global_size, mesh.source_units, "length") != mesh.global_size_m
    ):
        raise ValueError("Mesh size/source units disagree")
    for local in mesh.local_sizes:
        if to_si(local.source_size, local.source_units, "length") != local.size_m:
            raise ValueError("Local mesh size/source units disagree")
    for load in a.loads.assignments:
        units = load.source_units
        for source_name, target_name, dimension in [
            ("source_pressure", "pressure_pa", "stress"),
            ("source_displacement", "displacement_m", "length"),
            ("source_force", "force_n", "force"),
            ("source_acceleration", "acceleration_m_s2", "acceleration"),
        ]:
            source, target = getattr(load, source_name), getattr(load, target_name)
            if source is not None:
                if units is None:
                    raise ValueError("Load source units missing")
                expected_value = (
                    tuple(to_si(v, units, cast(Quantity, dimension)) for v in source)
                    if isinstance(source, tuple)
                    else to_si(source, units, cast(Quantity, dimension))
                )
                if expected_value != target:
                    raise ValueError("Load source/SI values disagree")
        if load.kind == "directional_force":
            if units is None or load.source_magnitude is None or load.direction is None:
                raise ValueError("Directed force source missing")
            magnitude = to_si(load.source_magnitude, units, "force")
            if tuple(v * magnitude for v in load.direction.vector) != load.force_n:
                raise ValueError("Directed force source/SI values disagree")
        if not load.review_direction:
            for direction in [
                *load.symmetry_directions.values(),
                *([load.direction] if load.direction else []),
            ]:
                if direction.geometry_revision_id not in geometries:
                    raise ValueError("Unknown direction geometry")
                verify_direction(geometries[direction.geometry_revision_id], direction)
    for bond in a.bonds.assignments:
        if review_hash(bond.geometry_revision_id, bond.review_report) != bond.review_sha256:
            raise ValueError("Saved bond review checksum mismatch")
