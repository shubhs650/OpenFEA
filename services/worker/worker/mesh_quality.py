"""Full-domain C3D10 Jacobian certificates and dimensionless corner shape quality."""

import itertools
import math
import sys
from collections.abc import Sequence
from typing import Any

from worker.meshing import EDGES, Vec, add, cross, dot, norm, scale, sub

JACOBIAN_FLOOR = 1e-15  # Preserve ADR-011's dimensional m³ bound.
MEAN_RATIO_FLOOR = 0.05
MEAN_RATIO_WARNING = 0.2
MAX_SUBDIVISIONS = 3
GRADIENTS: tuple[Vec, ...] = ((-1, -1, -1), (1, 0, 0), (0, 1, 0), (0, 0, 1))
Matrix = tuple[Vec, Vec, Vec]  # columns
GROUPS: dict[tuple[int, ...], list[tuple[int, ...]]] = {}
for indices in itertools.product(range(4), repeat=3):
    GROUPS.setdefault(tuple(sorted(indices)), []).append(indices)


def jacobian(points: Sequence[Vec], barycentric: Sequence[float]) -> Matrix:
    if len(points) != 10 or len(barycentric) != 4:
        raise ValueError("C3D10 needs ten nodes and four barycentric coordinates")
    gradients = [scale(g, 4 * barycentric[i] - 1) for i, g in enumerate(GRADIENTS)]
    gradients += [
        scale(add(scale(GRADIENTS[a], barycentric[b]), scale(GRADIENTS[b], barycentric[a])), 4)
        for a, b in EDGES
    ]
    columns: list[Vec] = []
    # Translation-invariant accumulation prevents origin magnitude from polluting J.
    shifted = [sub(p, points[0]) for p in points]
    for axis in range(3):
        columns.append(
            tuple(
                math.fsum(p[k] * g[axis] for p, g in zip(shifted, gradients, strict=True))
                for k in range(3)
            )
        )  # type: ignore[arg-type]
    return (columns[0], columns[1], columns[2])


def determinant(matrix: Matrix) -> float:
    return dot(matrix[0], cross(matrix[1], matrix[2]))


def bernstein_bounds(matrices: Sequence[Matrix]) -> tuple[float, float]:
    # J is affine in barycentric coordinates. Its determinant is cubic. Each
    # degree-three tetrahedral Bernstein coefficient is the average determinant
    # of ordered column choices with that multiset of vertex indices.
    coefficients = [
        math.fsum(dot(matrices[i][0], cross(matrices[j][1], matrices[k][2])) for i, j, k in choices)
        / len(choices)
        for choices in GROUPS.values()
    ]
    magnitude = max(norm(column) for matrix in matrices for column in matrix)
    rounding = 128 * sys.float_info.epsilon * magnitude**3
    return min(coefficients) - rounding, max(coefficients) + rounding


def certify(matrices: Sequence[Matrix], depth: int = 0) -> tuple[float, float, bool]:
    lower, upper = bernstein_bounds(matrices)
    if lower > JACOBIAN_FLOOR:
        return lower, upper, True
    if depth == MAX_SUBDIVISIONS or upper <= JACOBIAN_FLOOR:
        return lower, upper, False
    center: Matrix = tuple(
        tuple(math.fsum(m[a][k] for m in matrices) / 4 for k in range(3)) for a in range(3)
    )  # type: ignore[assignment]
    children = [
        certify([center if i == replaced else m for i, m in enumerate(matrices)], depth + 1)
        for replaced in range(4)
    ]
    return min(c[0] for c in children), max(c[1] for c in children), all(c[2] for c in children)


def cell_quality(points: Sequence[Vec]) -> dict[str, float | bool | str]:
    if len(points) != 10 or not all(math.isfinite(v) for point in points for v in point):
        raise ValueError("Quality requires ten finite C3D10 node coordinates")
    matrices = [jacobian(points, [float(i == j) for i in range(4)]) for j in range(4)]
    lower, upper, positive = certify(matrices)
    corner_det = dot(
        sub(points[1], points[0]), cross(sub(points[2], points[0]), sub(points[3], points[0]))
    )
    edges_sq = math.fsum(
        norm(sub(points[a], points[b])) ** 2 for a, b in itertools.combinations(range(4), 2)
    )
    ratio = 12 * (corner_det / 2) ** (2 / 3) / edges_sq if corner_det > 0 and edges_sq > 0 else 0.0
    affine = all(
        norm(sub(points[i], scale(add(points[a], points[b]), 0.5))) <= 1e-9
        for i, (a, b) in enumerate(EDGES, 4)
    )
    accepted = positive and ratio >= MEAN_RATIO_FLOOR
    return {
        "jacobian_lower_m3": lower,
        "jacobian_upper_m3": upper,
        "mean_ratio": ratio,
        "accepted": accepted,
        "affine": affine,
        "reason": "passed" if accepted else "jacobian_unresolved" if not positive else "poor_shape",
    }


def mesh_quality(mesh: dict[str, Any]) -> dict[str, Any]:
    if not all(isinstance(mesh.get(key), dict) for key in ("nodes", "elements", "owners")):
        raise ValueError("Mesh nodes, elements and ownership must be maps")
    if any(not isinstance(p, (list, tuple)) or len(p) != 3 for p in mesh["nodes"].values()):
        raise ValueError("Mesh points must have three coordinates")
    nodes: dict[int, Vec] = {int(n): tuple(p) for n, p in mesh["nodes"].items()}
    if not mesh["elements"] or len(mesh["elements"]) > 3000 or len(nodes) > 30000:
        raise ValueError("Quality input exceeds the bounded mesh policy")
    owners = {int(e): b for e, b in mesh["owners"].items()}
    cells = []
    for identifier, connectivity in mesh["elements"].items():
        if len(connectivity) != 10 or len(set(connectivity)) != 10:
            raise ValueError("Quality requires distinct C3D10 connectivity")
        points = [nodes[n] for n in connectivity]
        metrics = cell_quality(points)
        cells.append(
            {
                "element_id": int(identifier),
                "body_id": owners[int(identifier)],
                "center_m": [math.fsum(p[a] for p in points[:4]) / 4 for a in range(3)],
                **metrics,
            }
        )
    return {
        "schema_version": 1,
        "accepted": all(c["accepted"] for c in cells),
        "minimum_jacobian_m3": min(c["jacobian_lower_m3"] for c in cells),
        "minimum_mean_ratio": min(c["mean_ratio"] for c in cells),
        "bad_elements": [c["element_id"] for c in cells if not c["accepted"]],
        "warning_elements": [
            c["element_id"] for c in cells if c["mean_ratio"] < MEAN_RATIO_WARNING
        ],
        "all_affine": all(c["affine"] for c in cells),
        "cells": cells,
        "policy": {
            "jacobian_floor_m3": JACOBIAN_FLOOR,
            "mean_ratio_floor": MEAN_RATIO_FLOOR,
            "mean_ratio_warning": MEAN_RATIO_WARNING,
            "subdivision_depth": MAX_SUBDIVISIONS,
            "method": "cubic tetrahedral Bernstein certificate with outward rounding margin",
        },
    }
