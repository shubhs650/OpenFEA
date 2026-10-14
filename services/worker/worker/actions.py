"""Written affine C3D10 actions and external constrained-component equilibrium."""

import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from worker.calculix.results import Mesh
from worker.meshing import (
    GMSH_TO_CCX,
    Vec,
    add,
    convert_tetra,
    cross,
    dot,
    resultant,
    scale,
    sub,
    surface_integral,
)

RELATIVE_BALANCE = 0.005
FORCE_ABSOLUTE_N = 1e-6
MOMENT_ABSOLUTE_NM = 1e-6
RIGID_RANK_THRESHOLD = 1e-10
EQUILIBRIUM_POLICY = {
    "version": 1,
    "relative": RELATIVE_BALANCE,
    "force_absolute_n": FORCE_ABSOLUTE_N,
    "moment_absolute_nm": MOMENT_ABSOLUTE_NM,
}


def constrain(supports: dict[tuple[int, int], float], node: int, axis: int, value: float) -> None:
    if axis not in (1, 2, 3) or not math.isfinite(value):
        raise ValueError("Constraint requires a finite global translation component")
    key = node, axis
    if key in supports and supports[key] != value:
        raise ValueError(f"Conflicting prescribed values at node {node}, global component {axis}")
    supports[key] = value


def rigid_rank(rows: Iterable[tuple[Vec, int]], origin: Vec, extent: float) -> int:
    """Necessary rigid-motion coverage; positions normalized before rank decisions."""
    if not math.isfinite(extent) or extent <= 0:
        raise ValueError("Invalid support reference extent")
    basis: list[list[float]] = []
    for point, axis in rows:
        x, y, z = scale(sub(point, origin), 1 / extent)
        rotations = ((0, z, -y), (-z, 0, x), (y, -x, 0))
        row = [float(k == axis) for k in (1, 2, 3)] + list(rotations[axis - 1])
        # Reorthogonalize to prevent accumulated cancellation from inflating rank.
        for _ in range(2):
            for unit in basis:
                projection = math.fsum(a * b for a, b in zip(row, unit, strict=True))
                row = [a - projection * b for a, b in zip(row, unit, strict=True)]
        magnitude = math.hypot(*row)
        if magnitude > RIGID_RANK_THRESHOLD:
            basis.append([v / magnitude for v in row])
            if len(basis) == 6:
                break
    return len(basis)


def gravity_forces(
    nodes: dict[int, Vec],
    elements: dict[int, tuple[int, ...]],
    accelerations: dict[int, Vec],
    densities: dict[int, float],
) -> dict[int, Vec]:
    """Exact constant-volume load integration; negative corner weights are retained."""
    loads: dict[int, Vec] = {}
    if set(accelerations) != set(densities) or not set(accelerations) <= set(elements):
        raise ValueError("Gravity element/density coverage disagrees")
    for eid, acceleration in accelerations.items():
        ns = elements[eid]
        convert_tetra([ns[i] for i in GMSH_TO_CCX], nodes)
        p = [nodes[n] for n in ns[:4]]
        volume = dot(sub(p[1], p[0]), cross(sub(p[2], p[0]), sub(p[3], p[0]))) / 6
        density = densities[eid]
        if density <= 0 or not math.isfinite(density) or not all(map(math.isfinite, acceleration)):
            raise ValueError("Gravity requires finite acceleration and positive density")
        for index, n in enumerate(ns):
            force = scale(acceleration, density * volume * (-1 / 20 if index < 4 else 1 / 5))
            loads[n] = add(loads.get(n, (0, 0, 0)), force)
    return loads


@dataclass(frozen=True)
class WrittenActions:
    supports: dict[tuple[int, int], float]
    applied: dict[int, Vec]
    force_scale_n: float
    moment_scale_nm: float


def deck_actions(deck: str, mesh: Mesh, boundary: dict[str, Any]) -> WrittenActions:
    """Read verified internally generated decks, never an uploaded executable input."""
    supports: dict[tuple[int, int], float] = {}
    applied: dict[int, Vec] = {}
    sets: dict[str, set[int]] = {}
    sections: dict[str, str] = {}
    densities: dict[str, float] = {}
    pressure_rows: list[tuple[int, int, float]] = []
    gravity_rows: list[tuple[str, Vec]] = []
    faces = {(f["element"], f["face"]): f for fs in boundary.values() for f in fs}
    mode, material, elset = "", "", ""
    for line in deck.splitlines():
        if line.startswith("**") or not line.strip():
            continue
        if line.startswith("*"):
            fields = line.upper().split(",")
            mode = fields[0]
            options = dict(part.split("=", 1) for part in fields[1:] if "=" in part)
            if mode == "*ELEMENT":
                sets[options["ELSET"]] = set(mesh.elements)
            elif mode == "*ELSET":
                elset = options["ELSET"]
                sets.setdefault(elset, set())
            elif mode == "*MATERIAL":
                material = options["NAME"]
            elif mode == "*SOLID SECTION":
                sections[options["ELSET"]] = options["MATERIAL"]
            continue
        row = [v.strip() for v in line.split(",")]
        if mode == "*BOUNDARY":
            n, first, last = map(int, row[:3])
            if n not in mesh.nodes or not 1 <= first <= last <= 3:
                raise ValueError("Invalid written global boundary")
            for axis in range(first, last + 1):
                constrain(supports, n, axis, float(row[3]))
        elif mode == "*ELSET":
            values = {int(v) for v in row if v}
            if not values <= set(mesh.elements):
                raise ValueError("Invalid element set")
            sets[elset].update(values)
        elif mode == "*DENSITY":
            density = float(row[0])
            if not material or not math.isfinite(density) or density <= 0:
                raise ValueError("Invalid written density")
            if material in densities and densities[material] != density:
                raise ValueError("Multiple density definitions")
            densities[material] = density
        elif mode == "*CLOAD":
            n, axis, value = int(row[0]), int(row[1]), float(row[2])
            if n not in mesh.nodes or axis not in (1, 2, 3) or not math.isfinite(value):
                raise ValueError("Invalid written nodal force")
            force: Vec = tuple(value if a == axis else 0.0 for a in (1, 2, 3))  # type: ignore[assignment]
            applied[n] = add(applied.get(n, (0, 0, 0)), force)
        elif mode == "*DLOAD":
            value = float(row[2])
            if not math.isfinite(value):
                raise ValueError("Invalid distributed load")
            if row[1] == "GRAV":
                direction: Vec = (float(row[3]), float(row[4]), float(row[5]))
                if (
                    value <= 0
                    or not all(map(math.isfinite, direction))
                    or abs(math.hypot(*direction) - 1) > 1e-12
                ):
                    raise ValueError("Gravity requires a positive magnitude and unit direction")
                gravity_rows.append((row[0], scale(direction, value)))
            elif row[1].startswith("P"):
                pressure_rows.append((int(row[0]), int(row[1][1:]), value))
            else:
                raise ValueError("Unsupported written distributed load")
    if not supports:
        raise ValueError("Missing external constraints")
    force_scale = math.fsum(math.hypot(*v) for v in applied.values())
    moment_scale = math.fsum(math.hypot(*cross(mesh.nodes[n], v)) for n, v in applied.items())
    for eid, face_number, pressure in pressure_rows:
        face = faces[(eid, face_number)]
        integrated = surface_integral([mesh.nodes[n] for n in face["nodes"]], pressure=pressure)[2]
        part = dict(zip(face["nodes"], integrated, strict=True))
        force, moment = resultant(part, mesh.nodes)
        force_scale += math.hypot(*force)
        moment_scale += math.hypot(*moment)
        for n, vector in part.items():
            applied[n] = add(applied.get(n, (0, 0, 0)), vector)
    element_densities: dict[int, float] = {}
    accelerations: dict[int, Vec] = {}
    for target, acceleration in gravity_rows:
        selected = {int(target)} if target.isdigit() else sets[target]
        for eid in selected:
            material_names = {m for name, m in sections.items() if eid in sets[name]}
            if len(material_names) != 1:
                raise ValueError("Gravity material ownership is ambiguous")
            element_densities[eid] = densities[next(iter(material_names))]
            accelerations[eid] = add(accelerations.get(eid, (0, 0, 0)), acceleration)
    if accelerations:
        body_loads = gravity_forces(mesh.nodes, mesh.elements, accelerations, element_densities)
        # Physical gravity resultant per independent body; consistent negative
        # corner forces must not inflate the mass-load reference magnitude.
        for body in set(mesh.bodies.values()):
            ids = {
                e: ns
                for e, ns in mesh.elements.items()
                if mesh.bodies[e] == body and e in accelerations
            }
            local = gravity_forces(
                mesh.nodes,
                ids,
                {e: accelerations[e] for e in ids},
                {e: element_densities[e] for e in ids},
            )
            force, moment = resultant(local, mesh.nodes)
            force_scale += math.hypot(*force)
            moment_scale += math.hypot(*moment)
        for n, vector in body_loads.items():
            applied[n] = add(applied.get(n, (0, 0, 0)), vector)
    return WrittenActions(supports, applied, force_scale, moment_scale)


def balance_check(
    residual: Vec, reference: float, absolute: float, relative: float = RELATIVE_BALANCE
) -> dict[str, Any]:
    magnitude = math.hypot(*residual)
    if (
        not all(map(math.isfinite, (*residual, reference, absolute, relative)))
        or reference < 0
        or absolute <= 0
        or relative <= 0
    ):
        raise ValueError("Nonfinite equilibrium")
    absolute_mode = reference * relative <= absolute
    tolerance = max(absolute, reference * relative)
    return {
        "residual": residual,
        "residual_norm": magnitude,
        "reference": reference,
        "relative_residual": None if absolute_mode else magnitude / reference,
        "criterion": "absolute" if absolute_mode else "relative",
        "absolute_tolerance": absolute,
        "relative_tolerance": relative,
        "tolerance": tolerance,
        "passed": magnitude <= tolerance,
    }


def external_balance(
    dat: dict[str, Any],
    mesh: Mesh,
    boundary: dict[str, Any],
    deck: str,
    reference: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    actions = deck_actions(deck, mesh, boundary)
    forces = {int(n): tuple(v) for n, v in dat["external_forces_n"].items()}
    displacements = {int(n): tuple(v) for n, v in dat["displacements_m"].items()}
    if set(forces) != set(mesh.nodes) or set(displacements) != set(mesh.nodes):
        raise ValueError("Incomplete external force/displacement output")
    if any(
        len(v) != 3 or not all(map(math.isfinite, v))
        for v in (*forces.values(), *displacements.values())
    ):
        raise ValueError("Nonfinite or invalid native force/displacement vector")
    for (n, axis), value in actions.supports.items():
        if abs(displacements[n][axis - 1] - value) > max(1e-12, 1e-6 * abs(value)):
            raise ValueError("Output violates the written prescribed displacement")
    constrained_nodes = {n for n, _ in actions.supports}
    reactions: dict[int, Vec] = {
        n: tuple(
            forces[n][a - 1] - actions.applied.get(n, (0, 0, 0))[a - 1]
            if (n, a) in actions.supports
            else 0.0
            for a in (1, 2, 3)
        )  # type: ignore[misc]
        for n in constrained_nodes
    }
    prescribed_scale = math.fsum(
        abs(reactions[n][a - 1]) for (n, a), value in actions.supports.items() if value != 0
    )
    applied_force, applied_moment = resultant(actions.applied, mesh.nodes)
    reaction_force, reaction_moment = resultant(reactions, mesh.nodes)
    if reference is not None:
        if not reference["resultant_complete"]:
            raise ValueError("Incomplete frozen load reference")
        if any(
            abs(a - b) > 1e-8
            for actual, expected in (
                (applied_force, reference["total_force_n"]),
                (applied_moment, reference["total_moment_nm"]),
            )
            for a, b in zip(actual, expected, strict=True)
        ):
            raise ValueError("Written applied actions disagree with the frozen CAD reference")
        force_scale = reference["force_scale_n"]
        moment_scale = reference["moment_scale_nm"]
        extent = reference["characteristic_length_m"]
    else:
        force_scale, moment_scale = actions.force_scale_n, actions.moment_scale_nm
        extent = max(
            max(p[a] for p in mesh.nodes.values()) - min(p[a] for p in mesh.nodes.values())
            for a in range(3)
        )
    force_scale += prescribed_scale
    moment_scale = max(moment_scale, force_scale * extent)
    policy = (reference or {}).get("equilibrium_policy", EQUILIBRIUM_POLICY)
    if policy["version"] != 1:
        raise ValueError("Unsupported frozen equilibrium policy")
    force_check = balance_check(
        add(applied_force, reaction_force),
        force_scale,
        policy["force_absolute_n"],
        policy["relative"],
    )
    moment_check = balance_check(
        add(applied_moment, reaction_moment),
        moment_scale,
        policy["moment_absolute_nm"],
        policy["relative"],
    )
    by_body = []
    for body in sorted(set(mesh.bodies.values())):
        owned = {n for e, ns in mesh.elements.items() if mesh.bodies[e] == body for n in ns}
        supported = owned & constrained_nodes
        force, moment = resultant({n: reactions[n] for n in supported}, mesh.nodes)
        by_body.append(
            {
                "body_id": body,
                "node_count": len(supported),
                "constrained_dof_count": sum(n in owned for n, _ in actions.supports),
                "force_n": force,
                "moment_nm": moment,
            }
        )
    return {
        "passed": force_check["passed"] and moment_check["passed"],
        "applied_force_n": applied_force,
        "applied_moment_nm": applied_moment,
        "reaction_force_n": reaction_force,
        "reaction_moment_nm": reaction_moment,
        "moment_origin_m": (0, 0, 0),
        "characteristic_length_m": extent,
        "prescribed_actuator_reference_n": prescribed_scale,
        "force": force_check,
        "moment": moment_check,
        "method": "Frozen physical load magnitudes plus nonzero prescribed-component actuator "
        "reactions; moments about global origin; external constrained components only; "
        "internal ties/MPC/free-node RF excluded",
    }, by_body
