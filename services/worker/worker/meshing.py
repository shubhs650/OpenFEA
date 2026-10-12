"""Verified affine C3D10 export and quadratic surface integration (SI)."""

import math
from collections.abc import Iterable, Sequence

Vec = tuple[float, float, float]
# Gmsh type 11 edges: 12,23,31,14,34,24; CCX: 12,23,31,14,24,34.
GMSH_TO_CCX = (0, 1, 2, 3, 4, 5, 6, 7, 9, 8)
EDGES = ((0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3))
# Outward-oriented corners followed by their three midsides; CCX face numbers.
FACES = ((0, 2, 1, 6, 5, 4), (0, 1, 3, 4, 8, 7), (1, 2, 3, 5, 9, 8), (2, 0, 3, 6, 7, 9))


def add(a: Vec, b: Vec) -> Vec:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def scale(a: Vec, factor: float) -> Vec:
    return (a[0] * factor, a[1] * factor, a[2] * factor)


def cross(a: Vec, b: Vec) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def dot(a: Vec, b: Vec) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def norm(a: Vec) -> float:
    return math.sqrt(dot(a, a))


def convert_tetra(tags: Sequence[int], nodes: dict[int, Vec]) -> tuple[int, ...]:
    if len(tags) != 10 or len(set(tags)) != 10:
        raise ValueError("Expected ten distinct Gmsh tetra10 nodes")
    ordered = tuple(tags[i] for i in GMSH_TO_CCX)
    points = [nodes[n] for n in ordered]
    if not all(math.isfinite(x) for p in points for x in p):
        raise ValueError("Nonfinite tetra coordinates")
    midpoint_errors = []
    for index, (a, b) in enumerate(EDGES, 4):
        error = norm(sub(points[index], scale(add(points[a], points[b]), 0.5)))
        midpoint_errors.append(error)
        if error > 1e-9:
            raise ValueError("Curved/non-midpoint C3D10 is outside the affine validation scope")
    determinant = dot(
        sub(points[1], points[0]), cross(sub(points[2], points[0]), sub(points[3], points[0]))
    )
    # x=sum(L_i*x_i)+sum(4*L_i*L_j*delta_ij). Each derivative of
    # 4*L_i*L_j is bounded by 4 throughout the reference tetrahedron.
    # Multilinearity + Hadamard's inequality bounds the determinant error
    # everywhere, even for thin elements whose rounding error matters.
    lengths = [norm(sub(points[i], points[0])) for i in (1, 2, 3)]
    variation = 4 * sum(midpoint_errors)
    error_bound = (
        variation * (lengths[0] * lengths[1] + lengths[0] * lengths[2] + lengths[1] * lengths[2])
        + variation**2 * sum(lengths)
        + variation**3
    )
    if (
        not math.isfinite(determinant)
        or not math.isfinite(error_bound)
        or determinant - error_bound <= 1e-15
    ):
        raise ValueError("Nonpositive or degenerate quadratic Jacobian")
    return ordered


def face_nodes(element: Sequence[int], face: int) -> tuple[int, ...]:
    if not 1 <= face <= 4:
        raise ValueError("CCX face must be 1..4")
    return tuple(element[i] for i in FACES[face - 1])


# Degree-five Dunavant quadrature; weights sum to reference triangle area 1/2.
QUADRATURE = (
    (1 / 3, 1 / 3, 0.1125),
    (0.470142064105115, 0.470142064105115, 0.066197076394253),
    (0.059715871789770, 0.470142064105115, 0.066197076394253),
    (0.470142064105115, 0.059715871789770, 0.066197076394253),
    (0.101286507323456, 0.101286507323456, 0.062969590272414),
    (0.797426985353087, 0.101286507323456, 0.062969590272414),
    (0.101286507323456, 0.797426985353087, 0.062969590272414),
)


def surface_integral(
    points: Sequence[Vec], traction: Vec | None = None, pressure: float = 0
) -> tuple[float, Vec, list[Vec]]:
    """Isoparametric tri6 quadrature; positive pressure is inward."""
    if len(points) != 6 or not all(math.isfinite(x) for p in points for x in p):
        raise ValueError("Expected six finite quadratic-face coordinates")
    if not math.isfinite(pressure) or (traction and not all(map(math.isfinite, traction))):
        raise ValueError("Nonfinite load")
    area = 0.0
    centroid_integral: Vec = (0, 0, 0)
    loads: list[Vec] = [(0, 0, 0) for _ in points]
    for r, s, weight in QUADRATURE:
        t = 1 - r - s
        shape = (t * (2 * t - 1), r * (2 * r - 1), s * (2 * s - 1), 4 * t * r, 4 * r * s, 4 * s * t)
        dr = (1 - 4 * t, 4 * r - 1, 0, 4 * (t - r), 4 * s, -4 * s)
        ds = (1 - 4 * t, 0, 4 * s - 1, -4 * r, 4 * r, 4 * (t - s))
        x: Vec = (0, 0, 0)
        xr: Vec = (0, 0, 0)
        xs: Vec = (0, 0, 0)
        for i, point in enumerate(points):
            x = add(x, scale(point, shape[i]))
            xr = add(xr, scale(point, dr[i]))
            xs = add(xs, scale(point, ds[i]))
        normal = cross(xr, xs)
        jac = norm(normal)
        if jac <= 1e-15:
            raise ValueError("Zero-area quadratic face")
        area += weight * jac
        centroid_integral = add(centroid_integral, scale(x, weight * jac))
        density = add(scale(traction or (0, 0, 0), jac), scale(normal, -pressure))
        for i in range(6):
            loads[i] = add(loads[i], scale(density, weight * shape[i]))
    return area, scale(centroid_integral, 1 / area), loads


def total_face_force(
    faces: Iterable[tuple[int, ...]], nodes: dict[int, Vec], total: Vec
) -> dict[int, Vec]:
    # Repeated/overlapping selections count once; the force is over the whole set.
    unique = {tuple(sorted(face)): face for face in faces}
    if not unique:
        raise ValueError("Empty face selection")
    area = sum(surface_integral([nodes[n] for n in f])[0] for f in unique.values())
    traction = scale(total, 1 / area)
    result: dict[int, Vec] = {}
    for face in sorted(unique.values()):
        loads = surface_integral([nodes[n] for n in face], traction)[2]
        for n, force in zip(face, loads, strict=True):
            result[n] = add(result.get(n, (0, 0, 0)), force)
    return result


def resultant(loads: dict[int, Vec], nodes: dict[int, Vec]) -> tuple[Vec, Vec]:
    force: Vec = (0, 0, 0)
    moment: Vec = (0, 0, 0)
    for n, value in loads.items():
        force = add(force, value)
        moment = add(moment, cross(nodes[n], value))
    return force, moment
