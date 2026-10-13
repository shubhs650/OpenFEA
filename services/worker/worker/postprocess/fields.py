"""Element-owned extrapolation and probing; never average across an interface."""

from dataclasses import replace
from typing import Any

from worker.calculix.results import A, B, Mesh, StressPoint
from worker.meshing import EDGES, Vec
from worker.postprocess.tensors import COMPONENTS, tensor


def element_nodes(points: list[StressPoint], mesh: Mesh) -> list[StressPoint]:
    mesh.validate()
    identity = mesh.identity()
    if any(
        p.provenance.get("mesh_sha256") != identity
        or tuple(p.provenance.get("components", ())) != COMPONENTS
        or p.provenance.get("frame") != "global_cartesian"
        or p.provenance.get("units") != "Pa"
        for p in points
    ):
        raise ValueError("Stress provenance disagrees with immutable mesh/frame/components")
    if len(points) != 4 * len(mesh.elements) or {p.element_id for p in points} != set(
        mesh.elements
    ):
        raise ValueError("Extrapolation needs four native integration tensors per C3D10")
    grouped: dict[int | None, list[StressPoint]] = {}
    for point in points:
        grouped.setdefault(point.element_id, []).append(point)
    output = []
    for eid, ns in sorted(mesh.elements.items()):
        local = {p.integration_point_id: p for p in grouped[eid]}
        if set(local) != {1, 2, 3, 4} or any(
            p.location != "integration_point" for p in local.values()
        ):
            raise ValueError("Extrapolation needs four native integration tensors per C3D10")
        if any(
            p.body_id != mesh.bodies[eid] or p.material_id != mesh.materials[eid]
            for p in local.values()
        ):
            raise ValueError("Stress ownership disagrees with frozen mesh")
        corners = [
            tensor(
                [
                    (local[i + 1].tensor_pa[k] - B * sum(p.tensor_pa[k] for p in local.values()))
                    / (A - B)
                    for k in range(6)
                ]
            )
            for i in range(4)
        ]
        values = corners + [
            tensor([(corners[a][k] + corners[b][k]) / 2 for k in range(6)]) for a, b in EDGES
        ]
        for n, value in zip(ns, values, strict=True):
            source = dict(local[1].provenance)
            source.update(
                {
                    "method": "linear_C3D10_extrapolation_from_native_DAT_IP",
                    "source_integration_points": [1, 2, 3, 4],
                    "source_lines": [local[i].provenance["line"] for i in range(1, 5)],
                    "warning": "Derived element-node values; not raw integration stresses",
                }
            )
            output.append(
                StressPoint(
                    "element_node",
                    eid,
                    None,
                    n,
                    mesh.bodies[eid],
                    mesh.materials[eid],
                    mesh.nodes[n],
                    value,
                    source,
                )
            )
    return output


def probe_element(
    points: list[StressPoint],
    mesh: Mesh,
    element: int,
    barycentric: tuple[float, float, float, float],
) -> StressPoint:
    if (
        element not in mesh.elements
        or abs(sum(barycentric) - 1) > 1e-12
        or any(v < 0 or v > 1 for v in barycentric)
    ):
        raise ValueError("Probe requires an element side and a position inside that tetrahedron")
    local = {
        p.node_id: p for p in points if p.element_id == element and p.location == "element_node"
    }
    ns = mesh.elements[element]
    if set(local) != set(ns):
        raise ValueError("Incomplete element-node probe field")
    value = tensor(
        [sum(barycentric[j] * local[ns[j]].tensor_pa[k] for j in range(4)) for k in range(6)]
    )
    p: Vec = (
        sum(barycentric[j] * mesh.nodes[ns[j]][0] for j in range(4)),
        sum(barycentric[j] * mesh.nodes[ns[j]][1] for j in range(4)),
        sum(barycentric[j] * mesh.nodes[ns[j]][2] for j in range(4)),
    )
    provenance: dict[str, Any] = dict(local[ns[0]].provenance)
    provenance.update(
        {
            "method": "element_owned_linear_stress_interpolation",
            "barycentric": barycentric,
            "warning": "Interpolated/extrapolated stress, not a raw IP sample",
        }
    )
    return replace(
        local[ns[0]],
        location="element_interpolated",
        node_id=None,
        position_m=p,
        tensor_pa=value,
        provenance=provenance,
    )
