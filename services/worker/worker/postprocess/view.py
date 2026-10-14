"""Bounded, element-owned derivatives of verified immutable local solve outputs."""

import math
from typing import Any

from worker.actions import external_balance
from worker.calculix.results import Mesh, StressPoint
from worker.meshing import Vec
from worker.postprocess.fields import SMOOTHING_METHOD, element_nodes, smooth_nodes
from worker.postprocess.tensors import COMPONENTS, principal, tensor, von_mises

VIEW_VERSION = "affine-c3d10-assumptions-v5"
ZERO_STRESS_PA = 1e-6  # Absolute display convention; never a finite safety factor.


def volume_fields(
    raw: dict[str, Any], raw_mesh: dict[str, Any], materials: dict[str, dict[str, Any]]
) -> tuple[Mesh, list[StressPoint]]:
    if (
        raw.get("schema_version") != 1
        or raw.get("components") != list(COMPONENTS)
        or raw.get("frame") != "global_cartesian"
        or raw.get("stress_location") != "integration_point"
        or raw.get("units") != {"displacement": "m", "stress": "Pa", "force": "N"}
        or raw_mesh.get("units") != "m"
        or not 1 <= len(raw_mesh["elements"]) <= 3000
        or len(raw_mesh["nodes"]) > 30000
    ):
        raise ValueError("Unsupported result contract")
    # Match the coordinates actually written to CCX, as in the strict raw parser.
    mesh = Mesh(
        {int(n): vector([float(f"{v:.12e}") for v in p]) for n, p in raw_mesh["nodes"].items()},
        {int(e): tuple(ns) for e, ns in raw_mesh["elements"].items()},
        {int(e): b for e, b in raw_mesh["owners"].items()},
        {int(e): materials[b]["material_id"] for e, b in raw_mesh["owners"].items()},
        raw_mesh["revision"],
    )
    mesh.validate()
    if raw["result_mesh_sha256"] != mesh.identity() or set(mesh.bodies.values()) != set(materials):
        raise ValueError("Stale result mesh/material ownership")
    points = [StressPoint(**p) for p in raw["integration_points"]]
    if any(p.provenance.get("source_sha256") != raw["dat"]["source_sha256"] for p in points):
        raise ValueError("Raw stress source identity disagrees")
    return mesh, element_nodes(points, mesh)


def build_view(
    raw: dict[str, Any],
    raw_mesh: dict[str, Any],
    materials: dict[str, dict[str, Any]],
    deck: str,
    reference: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mesh, derived = volume_fields(raw, raw_mesh, materials)
    points = [StressPoint(**p) for p in raw["integration_points"]]

    def stress_values(point: StressPoint) -> dict[str, Any]:
        t = tensor(point.tensor_pa)
        return {"tensor_pa": t, "principal_pa": principal(t), "von_mises_pa": von_mises(t)}

    fields = {(p.element_id, p.node_id): stress_values(p) for p in derived}
    smoothed = {(p.element_id, p.node_id): p for p in smooth_nodes(derived, mesh)}
    smooth_values = {key: stress_values(p) for key, p in smoothed.items()}
    displacements = {int(n): vector(v) for n, v in raw["dat"]["displacements_m"].items()}
    forces = {int(n): vector(v) for n, v in raw["dat"]["external_forces_n"].items()}
    if set(displacements) != set(mesh.nodes) or set(forces) != set(mesh.nodes):
        raise ValueError("Incomplete nodal output")
    vertices: list[dict[str, Any]] = []
    triangles = []
    # Each boundary face keeps its own element side. No shared-node averaging.
    for face_id, faces in sorted(raw_mesh["boundary"].items()):
        for face in faces:
            eid, ns = face["element"], face["nodes"]
            if len(ns) != 6 or not set(ns).issubset(mesh.elements[eid]):
                raise ValueError("Invalid quadratic result boundary")
            offset = len(vertices)
            for n in ns:
                vertices.append(
                    {
                        "node_id": n,
                        "element_id": eid,
                        "body_id": mesh.bodies[eid],
                        "material_id": mesh.materials[eid],
                        "face_id": face_id,
                        "position_m": mesh.nodes[n],
                        "displacement_m": displacements[n],
                        "von_mises_pa": fields[(eid, n)]["von_mises_pa"],
                        "stress": fields[(eid, n)],
                        "smoothed_stress": smooth_values[(eid, n)],
                        "smoothed_contributions": smoothed[(eid, n)].provenance[
                            "contributing_elements"
                        ],
                    }
                )
            triangles.extend(
                [
                    tuple(offset + i for i in tri)
                    for tri in ((0, 3, 5), (3, 1, 4), (5, 4, 2), (3, 4, 5))
                ]
            )
    if not triangles:
        raise ValueError("Missing result surface")
    displacement_samples = [
        sample(math.hypot(*displacements[n]), "node", mesh.nodes[n], node=n)
        for n in sorted(mesh.nodes)
    ]
    stress_samples = [
        sample(
            von_mises(tensor(p.tensor_pa)),
            "integration_point",
            p.position_m,
            element=p.element_id,
            ip=p.integration_point_id,
            body=p.body_id,
            material=p.material_id,
        )
        for p in points
    ]
    field_definitions = [
        {
            "key": "displacement",
            "label": "Displacement magnitude",
            "unit": "m",
            "raw_location": "node",
            "extrema": extrema(displacement_samples),
        },
        {
            "key": "von_mises",
            "label": "Von Mises stress",
            "unit": "Pa",
            "raw_location": "integration_point",
            "extrema": extrema(stress_samples),
        },
    ]
    for axis, key in enumerate(("ux", "uy", "uz")):
        field_definitions.append(
            {
                "key": key,
                "label": f"Displacement {key}",
                "unit": "m",
                "raw_location": "node",
                "extrema": extrema(
                    [
                        sample(displacements[n][axis], "node", mesh.nodes[n], node=n)
                        for n in sorted(mesh.nodes)
                    ]
                ),
            }
        )
    raw_values = [(p, stress_values(p)) for p in points]
    for key, label, source, index in [
        *((f"s{c}", f"Stress σ{c}", "tensor_pa", i) for i, c in enumerate(COMPONENTS)),
        *((f"s{i + 1}", f"Principal stress σ{i + 1}", "principal_pa", i) for i in range(3)),
    ]:
        field_definitions.append(
            {
                "key": key,
                "label": label,
                "unit": "Pa",
                "raw_location": "integration_point",
                "extrema": extrema(
                    [
                        sample(
                            values[source][index],
                            "integration_point",
                            p.position_m,
                            element=p.element_id,
                            ip=p.integration_point_id,
                            body=p.body_id,
                            material=p.material_id,
                        )
                        for p, values in raw_values
                    ]
                ),
            }
        )
    equilibrium, reactions = external_balance(
        raw["dat"], mesh, raw_mesh["boundary"], deck, reference
    )
    if not equilibrium["passed"]:
        raise ValueError("External force/moment equilibrium failed")
    factors = []
    warnings = list(raw["warnings"])
    assumptions: list[dict[str, Any]] = [
        {
            "code": "stress_singularity",
            "body_id": None,
            "triggered": None,
            "metric": None,
            "threshold": None,
            "message": "Peaks near supports, reentrant corners or idealized load/bond edges may "
            "increase with refinement. No automatic singularity detection is claimed. Compare "
            "fixed physical locations away from these regions; a lower smoothed peak is not "
            "evidence of convergence or a design allowable.",
        }
    ]
    for body, material in sorted(materials.items()):
        owned_nodes = {n for e, ns in mesh.elements.items() if mesh.bodies[e] == body for n in ns}
        body_samples = [s for s in stress_samples if s["body_id"] == body]
        peak = max(body_samples, key=lambda s: s["value"])
        strength = material["yield_strength_pa"]
        state = (
            "unavailable"
            if strength is None
            else "unbounded"
            if peak["value"] <= ZERO_STRESS_PA
            else "finite"
        )
        factor = strength / peak["value"] if state == "finite" else None
        factors.append(
            {
                "body_id": body,
                "material_id": material["material_id"],
                "material_name": material["name"],
                "yield_strength_pa": strength,
                "state": state,
                "minimum": factor,
                "critical_sample": peak,
            }
        )
        if factor is not None and factor < 1:
            warnings.append(
                f"Body {body}: stress exceeds the supplied yield strength; "
                "linear elasticity does not model plastic deformation."
            )
        extent = max(
            max(mesh.nodes[n][a] for n in owned_nodes) - min(mesh.nodes[n][a] for n in owned_nodes)
            for a in range(3)
        )
        ratio = max(math.hypot(*displacements[n]) for n in owned_nodes) / extent
        if ratio > 0.01:
            warnings.append(
                f"Body {body}: maximum displacement exceeds 1% of its largest "
                f"extent ({ratio:.3g}); review the small-deformation assumption. "
                "This heuristic cannot certify validity."
            )
        assumptions.extend(
            [
                {
                    "code": "yielding",
                    "body_id": body,
                    "triggered": None
                    if state in ("unavailable", "unbounded")
                    else peak["value"] > strength,
                    "metric": peak["value"],
                    "threshold": strength,
                    "message": "Compare raw integration-point von Mises with the frozen supplied"
                    " ductile yield. "
                    "Yield exceedance does not model plastic deformation; missing "
                    "yield cannot establish a factor. "
                    "No fatigue, brittle failure, buckling or code check is implied.",
                },
                {
                    "code": "small_deformation",
                    "body_id": body,
                    "triggered": ratio > 0.01,
                    "metric": ratio,
                    "threshold": 0.01,
                    "message": "Maximum native displacement / largest body extent is a 1% "
                    "screening heuristic. "
                    "Exceedance requires review of small-deformation linear "
                    "elasticity. Passing this heuristic "
                    "does not bound local strain/rotation or certify validity; "
                    "display exaggeration is irrelevant.",
                },
            ]
        )
    force, moment = equilibrium["reaction_force_n"], equilibrium["reaction_moment_nm"]
    view = {
        "processor": VIEW_VERSION,
        "assumptions": assumptions,
        "fields": field_definitions,
        "frame": "global_cartesian",
        "tensor_components": COMPONENTS,
        "principal_order": "s1 >= s2 >= s3 (algebraic)",
        "smoothing_method": SMOOTHING_METHOD,
        "vertices": vertices,
        "triangles": triangles,
        "displacement": extrema(displacement_samples),
        "von_mises": extrema(stress_samples),
        "yield_factors": factors,
        "zero_stress_pa": ZERO_STRESS_PA,
        "reactions": reactions,
        "equilibrium": equilibrium,
        "reaction_force_n": force,
        "reaction_moment_nm": moment,
        "moment_origin_m": (0, 0, 0),
        "reaction_method": "DAT RF minus written equivalent CLOAD/pressure/consistent gravity, "
        "constrained global components only; unique nodes/DOFs per body; internal ties excluded",
        "warnings": list(dict.fromkeys(warnings)),
        "stress_method": "linear_C3D10_extrapolation_from_native_DAT_IP; element-owned "
        "tensors, then invariants; default unaveraged, "
        "optional body/material-partitioned smoothing",
        "extrema_method": "Displacement: all native DAT nodes; von Mises/yield factor: "
        "all raw DAT integration points, including interior",
    }
    # Infinity/NaN cannot leak into JSON, even after derived arithmetic.
    import json

    json.dumps(view, allow_nan=False)
    return view


def vector(value: list[float]) -> Vec:
    if len(value) != 3 or not all(math.isfinite(v) for v in value):
        raise ValueError("Expected three finite vector components")
    return (value[0], value[1], value[2])


def sample(
    value: float,
    location: str,
    position: Vec,
    *,
    node: int | None = None,
    element: int | None = None,
    ip: int | None = None,
    body: str | None = None,
    material: str | None = None,
) -> dict[str, Any]:
    return {
        "value": value,
        "location": location,
        "position_m": position,
        "node_id": node,
        "element_id": element,
        "integration_point_id": ip,
        "body_id": body,
        "material_id": material,
    }


def extrema(samples: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "minimum": min(samples, key=lambda s: s["value"]),
        "maximum": max(samples, key=lambda s: s["value"]),
    }
