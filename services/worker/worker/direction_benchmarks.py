"""B06 predeclared continuum rotation references and actual native diagnostics."""

import json
import math
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

from worker.actions import external_balance
from worker.approval import require_benchmark_approval
from worker.benchmark import solve
from worker.calculix.results import Mesh, StressPoint, parse_dat
from worker.deck import generated_deck
from worker.deck_mesh import mesh_snapshot
from worker.directions import (
    IDENTITY,
    Basis,
    Constraint,
    compile_constraints,
    global_vector,
    local_vector,
    unit,
)
from worker.local_solve import result_mesh
from worker.meshing import Vec, add, cross, scale, sub, total_face_force
from worker.postprocess.tensors import von_mises
from worker.runtime import ROOT, sha256, synthetic_geometry, verified_tool


def placement(manifest: dict[str, Any], rotated: bool) -> tuple[Basis, Vec]:
    if not rotated:
        return IDENTITY, (0, 0, 0)
    ax, ay, az = map(math.radians, manifest["rotation_degrees_xyz"])
    cx, sx, cy, sy, cz, sz = (
        math.cos(ax),
        math.sin(ax),
        math.cos(ay),
        math.sin(ay),
        math.cos(az),
        math.sin(az),
    )
    rows = (
        (cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx),
        (sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx),
        (-sy, cy * sx, cy * cx),
    )
    return tuple(tuple(rows[i][j] for i in range(3)) for j in range(3)), tuple(
        manifest["translation_m"]
    )  # type: ignore[return-value]


def evaluate_rotation(
    manifest: dict[str, Any],
    rotated: bool,
    mesh: Mesh,
    dat: dict[str, Any],
    samples: list[StressPoint],
    equilibrium: dict[str, Any],
    *,
    driven: bool = False,
) -> dict[str, Any]:
    basis, translation = placement(manifest, rotated)
    force, young, poisson = (
        manifest["force_n"],
        manifest["material"]["E_pa"],
        manifest["material"]["nu"],
    )
    tolerance = manifest["tolerances"]
    stress = tuple(
        force * basis[0][i] * basis[0][j]
        for i, j in [(0, 0), (1, 1), (2, 2), (0, 1), (1, 2), (2, 0)]
    )
    displacement_errors, magnitude_errors, tensor_errors, invariant_errors = [], [], [], []
    displacements = {int(n): tuple(v) for n, v in dat["displacements_m"].items()}
    if set(displacements) != set(mesh.nodes) or len(samples) != 4 * len(mesh.elements):
        raise ValueError("B06 requires complete all-node/IP coverage")
    for n, point in mesh.nodes.items():
        x, y, z = local_vector(sub(point, translation), basis)
        local: Vec = (force / young * x, -poisson * force / young * y, -poisson * force / young * z)
        expected = global_vector(local, basis)
        actual = displacements[n]
        for a, b in zip(actual, expected, strict=True):
            error = abs(a - b)
            displacement_errors.append(error)
            if error > max(tolerance["displacement_absolute_m"], tolerance["relative"] * abs(b)):
                raise ValueError(f"B06 global displacement rotation failed at node {n}")
        magnitude_error = abs(math.hypot(*actual) - math.hypot(*local))
        magnitude_errors.append(magnitude_error)
        if magnitude_error > max(
            tolerance["displacement_absolute_m"], tolerance["relative"] * math.hypot(*local)
        ):
            raise ValueError("B06 displacement magnitude invariance failed")
    for sample in samples:
        for actual_component, expected_component in zip(sample.tensor_pa, stress, strict=True):
            error = abs(actual_component - expected_component)
            tensor_errors.append(error)
            if error > max(
                tolerance["stress_absolute_pa"], tolerance["relative"] * abs(expected_component)
            ):
                raise ValueError("B06 full global tensor rotation failed")
        error = abs(von_mises(sample.tensor_pa) - abs(force))
        invariant_errors.append(error)
        if error > max(tolerance["stress_absolute_pa"], tolerance["relative"] * abs(force)):
            raise ValueError("B06 von Mises invariance failed")
    expected_force = (0.0, 0.0, 0.0) if driven else scale(basis[0], -force)
    expected_moment = cross(add(global_vector((1, 0.5, 0.5), basis), translation), expected_force)
    force_error = max(
        abs(a - b) for a, b in zip(equilibrium["reaction_force_n"], expected_force, strict=True)
    )
    moment_error = max(
        abs(a - b) for a, b in zip(equilibrium["reaction_moment_nm"], expected_moment, strict=True)
    )
    if (
        force_error > tolerance["force_absolute_n"]
        or moment_error > tolerance["moment_absolute_nm"]
        or not equilibrium["passed"]
    ):
        raise ValueError("B06 constrained-span reaction force/moment failed")
    return {
        "placement": "rotated" if rotated else "identity",
        "rotation_basis": basis,
        "translation_m": translation,
        "max_displacement_error_m": max(displacement_errors),
        "max_displacement_magnitude_error_m": max(magnitude_errors),
        "max_tensor_error_pa": max(tensor_errors),
        "max_von_mises_error_pa": max(invariant_errors),
        "max_displacement_m": max(math.hypot(*v) for v in displacements.values()),
        "max_von_mises_pa": max(von_mises(s.tensor_pa) for s in samples),
        "reaction_force_error_n": force_error,
        "reaction_moment_error_nm": moment_error,
        "expected_global_stress_pa": stress,
        "equilibrium": equilibrium,
    }


def run_rotation(output: Path, development: bool = False) -> dict[str, Any]:
    manifest_path = ROOT / "tests/benchmarks/B06.json"
    manifest = json.loads(manifest_path.read_bytes())
    approved = require_benchmark_approval(manifest, development)
    output.mkdir(parents=True, exist_ok=True)
    runs = []
    for rotated in [False, True]:
        basis, translation = placement(manifest, rotated)
        for index, size in enumerate(manifest["mesh_sizes_m"], 1):
            directory = output / ("rotated" if rotated else "identity") / f"mesh{index}"
            inputs = directory / "inputs"
            inputs.mkdir(parents=True)
            synthetic_geometry(inputs, "rotated-box" if rotated else "box")
            catalog = json.loads((inputs / "catalog.json").read_bytes())
            mesh = mesh_snapshot(inputs, directory / "output", [size], curvature_elements=0)
            nodes = {int(n): tuple(p) for n, p in mesh["nodes"].items()}
            rows: dict[int, list[Constraint]] = {}
            loads: dict[int, Vec] = {}
            for face in catalog["faces"]:
                center = local_vector(sub(tuple(face["center"]), translation), basis)
                native = face["triangles"][0]
                normal = unit(
                    cross(
                        sub(tuple(native[1]), tuple(native[0])),
                        sub(tuple(native[2]), tuple(native[0])),
                    )
                )
                facets = mesh["boundary"][face["id"]]
                for axis in range(3):
                    if abs(center[axis]) < 1e-10:
                        for n in {n for f in facets for n in f["nodes"]}:
                            rows.setdefault(n, []).append((normal, 0))
                if abs(center[0] - 1) < 1e-10:
                    loads = total_face_force(
                        [tuple(f["nodes"]) for f in facets],
                        nodes,
                        scale(normal, manifest["force_n"]),
                    )
            supports, transforms = compile_constraints(rows)
            material = manifest["material"]
            deck = generated_deck(
                mesh,
                supports,
                loads,
                material["E_pa"],
                material["nu"],
                stress_coordinates=True,
                transforms=transforms,
            )
            solve(directory, deck)
            written = result_mesh(mesh, {b["id"]: "ISOTROPIC" for b in catalog["bodies"]})
            dat = parse_dat(directory / "analysis.dat", written)
            equilibrium, _ = external_balance(dat, written, mesh["boundary"], deck)
            measured = evaluate_rotation(
                manifest, rotated, written, dat, dat["samples"], equilibrium
            )
            runs.append(
                {
                    "mesh_size_m": size,
                    "nodes": len(mesh["nodes"]),
                    "elements": len(mesh["elements"]),
                    **measured,
                    "deck_sha256": sha256(directory / "analysis.inp"),
                    "mesh_sha256": sha256(directory / "output/mesh.json"),
                    "dat_sha256": sha256(directory / "analysis.dat"),
                }
            )
    # Placements are independently meshed: compare invariant extrema, not transient IDs.
    for index in range(2):
        a, b = runs[index], runs[index + 2]
        if (
            abs(a["max_displacement_m"] - b["max_displacement_m"])
            > manifest["tolerances"]["displacement_absolute_m"]
            or abs(a["max_von_mises_pa"] - b["max_von_mises_pa"])
            > manifest["tolerances"]["stress_absolute_pa"]
        ):
            raise ValueError("B06 invariant extrema disagree across placements")
    result = {
        "case": "B06",
        "status": "PASS" if approved else "DEVELOPMENT PASS; owner acceptance pending",
        "code_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "manifest_sha256": sha256(manifest_path),
        "reviewer_signoff": manifest["reviewer_signoff"],
        "platform": platform.platform(),
        "python": platform.python_version(),
        "ccx_version": "2.23",
        "gmsh_version": "4.15.2",
        "ocp_version": "8.0.1.1.0",
        "threads": 1,
        "ccx_sha256": sha256(verified_tool("ccx")),
        "runs": runs,
    }
    (output / "result.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    shutil.copyfile(manifest_path, output / "manifest.json")
    return result
