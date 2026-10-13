"""Consistent planar quadratic-face mortar equations, solved by real CCX."""

import math
from dataclasses import replace
from typing import Any

from worker.calculix.bonds import Bond, Projection, barycentric, mesh_hash, typed_mesh
from worker.meshing import QUADRATURE, Vec, cross, dot, norm, scale, sub

Point2 = tuple[float, float]


def side(a: Point2, b: Point2, p: Point2) -> float:
    return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])


def intersection(subject: list[Point2], clip: list[Point2]) -> list[Point2]:
    if side(*subject) < 0:
        subject = list(reversed(subject))
    if side(*clip) < 0:
        clip = list(reversed(clip))
    polygon = subject
    for i, a in enumerate(clip):
        b = clip[(i + 1) % 3]
        previous = polygon
        polygon = []
        if not previous:
            break
        p = previous[-1]
        dp = side(a, b, p)
        for q in previous:
            dq = side(a, b, q)
            if (dp >= 0) != (dq >= 0):
                fraction = dp / (dp - dq)
                polygon.append((p[0] + fraction * (q[0] - p[0]), p[1] + fraction * (q[1] - p[1])))
            if dq >= 0:
                polygon.append(q)
            p, dp = q, dq
    return polygon


def basis(p: Point2, corners: list[Point2]) -> tuple[float, ...]:
    bary = barycentric((p[0], p[1], 0.0), [(x, y, 0.0) for x, y in corners])
    if bary is None:
        raise ValueError("Overlap quadrature point outside selected interface triangle")
    t, r, s = bary
    return (t * (2 * t - 1), r * (2 * r - 1), s * (2 * s - 1), 4 * t * r, 4 * r * s, 4 * s * t)


def coupling(
    nodes: dict[int, Vec], slave_faces: list[tuple[int, ...]], master_faces: list[tuple[int, ...]]
) -> tuple[tuple[int, ...], tuple[int, ...], list[list[float]], list[list[float]], float]:
    slaves = tuple(sorted({n for face in slave_faces for n in face}))
    masters = tuple(sorted({n for face in master_faces for n in face}))
    origin = nodes[master_faces[0][0]]
    axis = sub(nodes[master_faces[0][1]], origin)
    axis = scale(axis, 1 / norm(axis))
    normal = cross(axis, sub(nodes[master_faces[0][2]], origin))
    normal = scale(normal, 1 / norm(normal))
    vertical = cross(normal, axis)
    flat = {n: (dot(sub(p, origin), axis), dot(sub(p, origin), vertical)) for n, p in nodes.items()}
    si, mi = {n: i for i, n in enumerate(slaves)}, {n: i for i, n in enumerate(masters)}
    mass = [[0.0] * len(slaves) for _ in slaves]
    cross_mass = [[0.0] * len(masters) for _ in slaves]
    area = 0.0
    for sf in slave_faces:
        sc = [flat[n] for n in sf[:3]]
        for mf in master_faces:
            mc = [flat[n] for n in mf[:3]]
            polygon = intersection(sc, mc)
            for k in range(1, len(polygon) - 1):
                a, b, c = polygon[0], polygon[k], polygon[k + 1]
                determinant = abs(side(a, b, c))
                if determinant <= 1e-20:
                    continue
                for r, s, weight in QUADRATURE:
                    p = (
                        a[0] + r * (b[0] - a[0]) + s * (c[0] - a[0]),
                        a[1] + r * (b[1] - a[1]) + s * (c[1] - a[1]),
                    )
                    ns, nm = basis(p, sc), basis(p, mc)
                    measure = determinant * weight
                    area += measure
                    for i, n in enumerate(sf):
                        for j, m in enumerate(sf):
                            mass[si[n]][si[m]] += measure * ns[i] * ns[j]
                        for j, m in enumerate(mf):
                            cross_mass[si[n]][mi[m]] += measure * ns[i] * nm[j]
    return slaves, masters, mass, cross_mass, area


def solve_mass(mass: list[list[float]], coupled: list[list[float]]) -> list[list[float]]:
    # Cholesky of the positive definite slave trace mass; no stabilizing diagonal.
    n = len(mass)
    lower = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            value = mass[i][j] - sum(lower[i][k] * lower[j][k] for k in range(j))
            if i == j:
                if value <= 1e-14:
                    raise ValueError("Uncovered/singular slave trace mass; no stabilization")
                lower[i][j] = math.sqrt(value)
            else:
                lower[i][j] = value / lower[j][j]
    solution = [[0.0] * len(coupled[0]) for _ in range(n)]
    for column in range(len(coupled[0])):
        temp = [0.0] * n
        for i in range(n):
            temp[i] = (coupled[i][column] - sum(lower[i][k] * temp[k] for k in range(i))) / lower[
                i
            ][i]
        for i in reversed(range(n)):
            solution[i][column] = (
                temp[i] - sum(lower[k][i] * solution[k][column] for k in range(i + 1, n))
            ) / lower[i][i]
    return solution


def mortar_bond(mesh: dict[str, Any], bond: Bond) -> tuple[Bond, dict[str, Any]]:
    if bond.revision != mesh["revision"] or bond.mesh_sha256 != mesh_hash(mesh):
        raise ValueError("Stale mortar bond snapshot")
    typed = typed_mesh(mesh)
    if any(
        len({n for p in mesh["boundary"][ref] for n in p["nodes"]}) > 65
        for ref in (bond.master_ref, bond.slave_ref)
    ):
        raise ValueError(
            "M0 experimental mortar supports at most 65 trace nodes per side; "
            "larger interfaces unvalidated"
        )
    slaves, masters, mass, coupled, area = coupling(
        typed.nodes,
        [tuple(p["nodes"]) for p in mesh["boundary"][bond.slave_ref]],
        [tuple(p["nodes"]) for p in mesh["boundary"][bond.master_ref]],
    )
    # Unit-square synthetic patch only; no implicit extrapolation across gaps/edges.
    if abs(area - 1.0) > 1e-10:
        raise ValueError("Quadrature overlap does not cover the full unit interface")
    projection = solve_mass(mass, coupled)
    error = 0.0
    for i, n in enumerate(slaves):
        error = max(error, abs(sum(projection[i]) - 1))
        for k in range(3):
            error = max(
                error,
                abs(
                    sum(projection[i][j] * typed.nodes[m][k] for j, m in enumerate(masters))
                    - typed.nodes[n][k]
                ),
            )
    if error > 1e-10:
        raise ValueError("Mortar coupling does not preserve affine displacement fields")
    # Virtual-work transfer of uniform traction: P^T*M_s*1 = C^T*1.
    slave_force = [sum(row) for row in mass]
    master_force = [sum(coupled[i][j] for i in range(len(slaves))) for j in range(len(masters))]
    transfer_error = max(
        abs(sum(projection[i][j] * slave_force[i] for i in range(len(slaves))) - master_force[j])
        for j in range(len(masters))
    )
    if transfer_error > 1e-10:
        raise ValueError("Mortar virtual-work transfer fails constant traction")
    planned = tuple(
        Projection(n, masters, tuple(row), 0.0) for n, row in zip(slaves, projection, strict=True)
    )
    output = replace(bond, formulation="mortar_equation", projections=planned)
    return output, {
        "overlap_area_m2": area,
        "slave_trace_dofs": len(slaves),
        "master_trace_dofs": len(masters),
        "affine_reproduction_error": error,
        "uniform_traction_transfer_error": transfer_error,
        "quadrature": "degree-five Dunavant over exact planar triangle intersections",
        "matrix": "M_slave*P=C; Cholesky, no regularization",
        "equation_rows": 3 * len(slaves),
    }
