"""Authoritative bounded affine-volume inspection; no exterior clipping or side merging."""

import math
from typing import Any

from worker.meshing import EDGES, Vec, cross, dot, sub
from worker.postprocess.fields import SMOOTHING_METHOD, smooth_nodes
from worker.postprocess.tensors import COMPONENTS, principal, tensor, von_mises
from worker.postprocess.view import vector, volume_fields

INSPECTION_VERSION = "affine-c3d10-volume-inspection-v1"
METHOD = (
    "Physical reference coordinates in the retained volume mesh; explicit element side. "
    "Displacement uses all ten quadratic C3D10 shape functions. Unaveraged stress uses "
    "linear interpolation of native four-IP extrapolated corner tensors. Smoothed stress "
    "uses ten-node quadratic interpolation of body/material-partitioned nodal tensors; "
    "invariants follow interpolation. Not a raw node/IP value. "
    "Sections intersect affine tetrahedron volumes and sample polygon corners, edge midsides "
    "and the interior centroid; rendering uses linear display triangles. "
    "No exterior-only clipping. "
    "Curved/non-midpoint volume geometry is refused. " + SMOOTHING_METHOD
)
# Roundoff-only admission in reference coordinates; no geometry movement or snapping.
BARYCENTRIC_ROUNDOFF = 1e-12


def inspect_volume(
    raw: dict[str, Any],
    raw_mesh: dict[str, Any],
    materials: dict[str, dict[str, Any]],
    point: Vec,
    element: int | None = None,
    normal: Vec | None = None,
) -> dict[str, Any]:
    mesh, derived = volume_fields(raw, raw_mesh, materials)
    fields = {(p.element_id, p.node_id): p.tensor_pa for p in derived}
    smoothed = {(p.element_id, p.node_id): p.tensor_pa for p in smooth_nodes(derived, mesh)}
    displacement = {int(n): vector(v) for n, v in raw["dat"]["displacements_m"].items()}
    if set(displacement) != set(mesh.nodes):
        raise ValueError("Incomplete displacement volume")
    point = vector(list(point))

    def interpolate(e: int, bary: list[float]) -> dict[str, Any]:
        ns = mesh.elements[e]
        shape = [b * (2 * b - 1) for b in bary] + [4 * bary[a] * bary[b] for a, b in EDGES]

        def stress(
            values: dict[tuple[int | None, int | None], Any], weights: list[float]
        ) -> dict[str, Any]:
            t = tensor(
                [
                    math.fsum(
                        w * values[e, n][k]
                        for n, w in zip(ns[: len(weights)], weights, strict=True)
                    )
                    for k in range(6)
                ]
            )
            return {"tensor_pa": t, "principal_pa": principal(t), "von_mises_pa": von_mises(t)}

        return {
            "element_id": e,
            "body_id": mesh.bodies[e],
            "material_id": mesh.materials[e],
            "barycentric": bary,
            "position_m": [
                math.fsum(bary[j] * mesh.nodes[ns[j]][k] for j in range(4)) for k in range(3)
            ],
            "displacement_m": [
                math.fsum(shape[j] * displacement[ns[j]][k] for j in range(10)) for k in range(3)
            ],
            "stress": stress(fields, bary),
            "smoothed_stress": stress(smoothed, shape),
        }

    vertices: list[dict[str, Any]] = []
    triangles: list[tuple[int, int, int]] = []
    if element is not None:
        if element not in mesh.elements:
            raise ValueError("Select an existing element side")
        corners = [mesh.nodes[n] for n in mesh.elements[element][:4]]
        a, b, c = (sub(corners[i], corners[0]) for i in (1, 2, 3))
        d = sub(point, corners[0])
        determinant = dot(a, cross(b, c))
        bary = [
            dot(d, cross(b, c)) / determinant,
            dot(a, cross(d, c)) / determinant,
            dot(a, cross(b, d)) / determinant,
        ]
        bary.insert(0, 1 - math.fsum(bary))
        if any(
            not math.isfinite(v) or v < -BARYCENTRIC_ROUNDOFF or v > 1 + BARYCENTRIC_ROUNDOFF
            for v in bary
        ):
            raise ValueError("The physical probe point is outside the selected element side")
        vertices.append(interpolate(element, bary))
    else:
        if normal is None:
            raise ValueError("A volume section requires a normal")
        # Normalize without overflow/underflow; magnitude is not a physical distance.
        largest = max(abs(v) for v in vector(list(normal)))
        if largest == 0:
            raise ValueError("A section normal must be nonzero")
        scaled = [v / largest for v in normal]
        length = math.hypot(*scaled)
        normal = vector([v / length for v in scaled])
        axis = min(range(3), key=lambda k: abs(normal[k]))
        tangent = cross(normal, vector([1 if k == axis else 0 for k in range(3)]))
        second = cross(normal, tangent)
        for e, ns in sorted(mesh.elements.items()):
            corners = [mesh.nodes[n] for n in ns[:4]]
            distances = [dot(sub(p, point), normal) for p in corners]
            if not all(math.isfinite(d) for d in distances):
                raise ValueError("Section coordinate arithmetic is not finite")
            polygon = [
                [1.0 if j == i else 0.0 for j in range(4)]
                for i, d in enumerate(distances)
                if d == 0
            ]
            for i, j in EDGES:
                if (distances[i] < 0 < distances[j]) or (distances[j] < 0 < distances[i]):
                    t = abs(distances[i]) / (abs(distances[i]) + abs(distances[j]))
                    bary = [0.0] * 4
                    bary[i], bary[j] = 1 - t, t
                    polygon.append(bary)
            if len(polygon) < 3:
                continue  # Tangency at a point/edge has zero section area.
            positions = [
                vector([sum(b[j] * corners[j][k] for j in range(4)) for k in range(3)])
                for b in polygon
            ]
            center = vector([sum(p[k] for p in positions) / len(positions) for k in range(3)])
            polygon = [
                b
                for _, b in sorted(
                    zip(
                        [
                            math.atan2(dot(sub(p, center), second), dot(sub(p, center), tangent))
                            for p in positions
                        ],
                        polygon,
                        strict=True,
                    )
                )
            ]
            count = len(polygon)
            barys = (
                polygon
                + [
                    [(polygon[j][k] + polygon[(j + 1) % count][k]) / 2 for k in range(4)]
                    for j in range(count)
                ]
                + [[math.fsum(b[k] for b in polygon) / count for k in range(4)]]
            )
            offset = len(vertices)
            vertices.extend(interpolate(e, b) for b in barys)
            for j in range(count):
                triangles.extend(
                    (
                        (offset + 2 * count, offset + j, offset + count + j),
                        (offset + 2 * count, offset + count + j, offset + (j + 1) % count),
                    )
                )
    return {
        "frame": "global_cartesian",
        "tensor_components": COMPONENTS,
        "principal_order": "s1 >= s2 >= s3 (algebraic)",
        "kind": "probe" if element is not None else "section",
        "processor": INSPECTION_VERSION,
        "location": "element_interpolated",
        "method": METHOD,
        "point_m": point,
        "normal": normal,
        "vertices": vertices,
        "triangles": triangles,
    }
