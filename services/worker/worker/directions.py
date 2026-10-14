"""Global geometry bases and compatible per-node external constraint spans."""

import math
import sys
from dataclasses import dataclass

from worker.meshing import Vec, add, cross, dot, scale, sub

type Basis = tuple[Vec, Vec, Vec]
type Constraint = tuple[Vec, float]
IDENTITY: Basis = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
BASIS_TOLERANCE = 1e-10
ROUND_OFF = 64 * sys.float_info.epsilon
DIRECTION_POLICY = {
    "version": 1,
    "basis_tolerance": BASIS_TOLERANCE,
    "roundoff_ulps": 64,
    "edge_min_length_m": 1e-12,
    "one_transform_per_node": True,
    "output_frame": "global_cartesian",
}


def unit(vector: Vec) -> Vec:
    magnitude = math.hypot(*vector)
    if not all(map(math.isfinite, vector)) or not math.isfinite(magnitude) or magnitude == 0:
        raise ValueError("Direction is zero or nonfinite")
    return tuple(v / magnitude if v else 0.0 for v in vector)  # type: ignore[return-value]


def frame(primary: Vec, secondary: Vec | None = None) -> Basis:
    x = unit(primary)
    if secondary is None:
        secondary = IDENTITY[min(range(3), key=lambda a: abs(x[a]))]
    seed = unit(secondary)
    remaining = sub(seed, scale(x, dot(seed, x)))
    if math.hypot(*remaining) <= BASIS_TOLERANCE:
        raise ValueError("Singular direction basis")
    y = unit(remaining)
    z = unit(cross(x, y))
    basis = x, y, z
    if (
        max(
            abs(dot(a, b) - float(i == j)) for i, a in enumerate(basis) for j, b in enumerate(basis)
        )
        > BASIS_TOLERANCE
    ):
        raise ValueError("Direction basis is not orthonormal")
    if dot(cross(x, y), z) < 1 - BASIS_TOLERANCE:
        raise ValueError("Direction basis must be right handed")
    return basis


def global_vector(local: Vec, basis: Basis) -> Vec:
    return tuple(math.fsum(local[a] * basis[a][i] for a in range(3)) for i in range(3))  # type: ignore[return-value]


def local_vector(global_value: Vec, basis: Basis) -> Vec:
    return tuple(dot(global_value, axis) for axis in basis)  # type: ignore[return-value]


@dataclass(frozen=True)
class ConstraintFrame:
    basis: Basis
    values: dict[int, float]


def constraint_frame(rows: list[Constraint]) -> ConstraintFrame:
    """Reduce compatible rows only; refuse contradictory or ill-conditioned bases."""
    if not rows:
        return ConstraintFrame(IDENTITY, {})
    prepared: list[Constraint] = []
    for direction, value in rows:
        if not math.isfinite(value):
            raise ValueError("Nonfinite prescribed displacement")
        direction = unit(direction)
        for previous, prescribed in prepared:
            if math.hypot(*cross(direction, previous)) <= ROUND_OFF:
                sign = 1 if dot(direction, previous) > 0 else -1
                if value != sign * prescribed:
                    raise ValueError("Conflicting prescribed values along equivalent directions")
        prepared.append((direction, value))
    # Retain exact legacy global boundary semantics/deck bytes whenever possible.
    if all(direction in IDENTITY or scale(direction, -1) in IDENTITY for direction, _ in prepared):
        values: dict[int, float] = {}
        for direction, value in prepared:
            axis = next(i for i, v in enumerate(direction, 1) if v != 0)
            prescribed = value * direction[axis - 1]
            if axis in values and values[axis] != prescribed:
                raise ValueError("Conflicting global component values")
            values[axis] = prescribed
        return ConstraintFrame(IDENTITY, values)
    basis: list[Vec] = []
    values = {}
    tolerance = 64 * math.ulp(max(abs(value) for _, value in prepared))
    for direction, value in prepared:
        remaining, residual = direction, value
        for _ in range(2):
            for axis, q in enumerate(basis, 1):
                coefficient = dot(remaining, q)
                remaining = sub(remaining, scale(q, coefficient))
                residual -= coefficient * values[axis]
        magnitude = math.hypot(*remaining)
        if magnitude <= ROUND_OFF:
            if abs(residual) > tolerance:
                raise ValueError("Contradictory dependent directional constraints")
            continue
        if magnitude <= BASIS_TOLERANCE:
            raise ValueError("Ill-conditioned shared-node constraint basis")
        basis.append(unit(remaining))
        values[len(basis)] = residual / magnitude
        if not math.isfinite(values[len(basis)]):
            raise ValueError("Nonfinite reduced prescribed displacement")
    if len(basis) == 1:
        complete = frame(basis[0])
    elif len(basis) == 2:
        complete = (basis[0], basis[1], unit(cross(basis[0], basis[1])))
    else:
        if dot(cross(basis[0], basis[1]), basis[2]) < 0:
            basis[2] = scale(basis[2], -1)
            values[3] *= -1
        complete = (basis[0], basis[1], basis[2])
    return ConstraintFrame(complete, values)


def compile_constraints(
    rows: dict[int, list[Constraint]],
) -> tuple[dict[tuple[int, int], float], dict[int, Basis]]:
    supports: dict[tuple[int, int], float] = {}
    transforms: dict[int, Basis] = {}
    for node, constraints in sorted(rows.items()):
        resolved = constraint_frame(constraints)
        supports.update({(node, a): value for a, value in resolved.values.items()})
        if resolved.basis != IDENTITY:
            transforms[node] = resolved.basis
    return supports, transforms


def projected(value: Vec, directions: list[Vec]) -> Vec:
    result: Vec = (0, 0, 0)
    for direction in directions:
        result = add(result, scale(direction, dot(value, direction)))
    return result
