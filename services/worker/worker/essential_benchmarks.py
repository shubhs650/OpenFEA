"""Predeclared B03/B04/B05 analytical references, never engineering-owner approval."""

import json
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
from worker.local_solve import result_mesh
from worker.meshing import Vec, total_face_force
from worker.runtime import ROOT, sha256, synthetic_geometry, verified_tool


def evaluate(
    manifest: dict[str, Any],
    mesh: Mesh,
    boundary: dict[str, Any],
    dat: dict[str, Any],
    samples: list[StressPoint],
    equilibrium: dict[str, Any],
    tip_ref: str | None = None,
) -> dict[str, Any]:
    case, material, tolerance = manifest["id"], manifest["material"], manifest["tolerances"]
    young, poisson = material["E_pa"], material["nu"]
    displacement = {int(n): tuple(v) for n, v in dat["displacements_m"].items()}
    stress_errors: list[float] = []
    displacement_errors: list[float] = []
    if case == "B03":
        assert tip_ref is not None
        # Affine tri6's exact area weights are zero at corners and A/3 at midsides.
        from worker.meshing import surface_integral

        area = weighted = 0.0
        for face in boundary[tip_ref]:
            face_area = surface_integral([mesh.nodes[n] for n in face["nodes"]])[0]
            area += face_area
            weighted += face_area * sum(displacement[n][1] for n in face["nodes"][3:]) / 3
        tip = weighted / area
        expected = manifest["expected_tip_uy_m"]
        displacement_errors.append(abs(tip - expected))
        if abs(tip - expected) > max(
            tolerance["displacement_absolute_m"], tolerance["displacement_relative"] * abs(expected)
        ):
            raise ValueError(
                f"B03 Euler–Bernoulli tip criterion failed: actual {tip}, reference {expected}"
            )
        for point in samples:
            x, y, z = point.position_m
            if 0.25 <= x <= 0.75 and abs(y - 0.05) >= 0.02 and 0.02 <= z <= 0.08:
                reference = (1 - x) * (y - 0.05) / (0.1 * 0.1**3 / 12)
                error = abs(point.tensor_pa[0] - reference)
                stress_errors.append(error)
                if error > max(
                    tolerance["stress_absolute_pa"], tolerance["stress_relative"] * abs(reference)
                ):
                    raise ValueError(
                        f"B03 declared interior bending sample failed at {point.position_m}"
                    )
        if len(stress_errors) < 4:
            raise ValueError("B03 lacks predeclared interior stress samples")
        expected_force, expected_moment = (0.0, 1.0, 0.0), (-0.05, 0.0, 1.0)
        result: dict[str, Any] = {
            "tip_mean_uy_m": tip,
            "expected_tip_mean_uy_m": expected,
            "tip_relative_error": abs(tip - expected) / abs(expected),
            "interior_stress_sample_count": len(stress_errors),
        }
    else:
        weight = manifest.get("expected_weight_n", 0)
        for n, (x, y, z) in mesh.nodes.items():
            if case == "B04":
                strain = -manifest["pressure_pa"] * (1 - 2 * poisson) / young
                reference_vector = (strain * x, strain * y, strain * z)
            else:
                reference_vector = (0.0, 0.0, -weight * (z - z * z / 2) / young)
            for actual, reference in zip(displacement[n], reference_vector, strict=True):
                error = abs(actual - reference)
                displacement_errors.append(error)
                if error > max(
                    tolerance["displacement_absolute_m"], tolerance["relative"] * abs(reference)
                ):
                    raise ValueError(f"{case} exact continuum displacement failed")
        for point in samples:
            reference_tensor = (
                (-1000.0, -1000.0, -1000.0, 0.0, 0.0, 0.0)
                if case == "B04"
                else (0.0, 0.0, -weight * (1 - point.position_m[2]), 0.0, 0.0, 0.0)
            )
            for actual, reference in zip(point.tensor_pa, reference_tensor, strict=True):
                error = abs(actual - reference)
                stress_errors.append(error)
                if error > max(
                    tolerance["stress_absolute_pa"], tolerance["relative"] * abs(reference)
                ):
                    raise ValueError(f"{case} exact continuum stress failed")
        expected_force = (1000.0, 1000.0, 1000.0) if case == "B04" else (0.0, 0.0, weight)
        expected_moment = (0.0, 0.0, 0.0) if case == "B04" else (weight / 2, -weight / 2, 0.0)
        result = {}
    force_error = max(
        abs(a - b) for a, b in zip(equilibrium["reaction_force_n"], expected_force, strict=True)
    )
    moment_error = max(
        abs(a - b) for a, b in zip(equilibrium["reaction_moment_nm"], expected_moment, strict=True)
    )
    if (
        force_error > tolerance["force_absolute_n"]
        or moment_error > tolerance["moment_absolute_nm"]
    ):
        raise ValueError(f"{case} analytical reaction force/moment failed")
    if not equilibrium["passed"]:
        raise ValueError(f"{case} external equilibrium failed")
    return result | {
        "max_displacement_error_m": max(displacement_errors),
        "max_stress_error_pa": max(stress_errors),
        "reaction_force_error_n": force_error,
        "reaction_moment_error_nm": moment_error,
        "equilibrium": equilibrium,
    }


def run_essential(case: str, output: Path, development: bool = False) -> dict[str, Any]:
    manifest_path = ROOT / f"tests/benchmarks/{case}.json"
    manifest = json.loads(manifest_path.read_bytes())
    approved = require_benchmark_approval(manifest, development)
    output.mkdir(parents=True, exist_ok=True)
    runs = []
    for index, size in enumerate(manifest["mesh_sizes_m"], 1):
        directory = output / f"mesh{index}"
        inputs = directory / "inputs"
        inputs.mkdir(parents=True, exist_ok=True)
        synthetic_geometry(inputs, "beam" if case == "B03" else "box")
        catalog = json.loads((inputs / "catalog.json").read_bytes())
        mesh = mesh_snapshot(inputs, directory / "output", [size], curvature_elements=0)
        nodes: dict[int, Vec] = {int(n): tuple(p) for n, p in mesh["nodes"].items()}
        supports: dict[tuple[int, int], float] = {}
        loads: dict[int, Vec] = {}
        pressure_rows: list[tuple[int, int, float]] = []
        gravity: dict[str, Vec] = {}
        density: dict[str, float] = {}
        tip_ref = None
        for face in catalog["faces"]:
            center = face["center"]
            refs = mesh["boundary"][face["id"]]
            ns = {n for f in refs for n in f["nodes"]}
            if case == "B03":
                if abs(center[0]) < 1e-10:
                    supports.update({(n, a): 0.0 for n in ns for a in (1, 2, 3)})
                elif abs(center[0] - 1) < 1e-10:
                    tip_ref = face["id"]
                    loads = total_face_force([tuple(f["nodes"]) for f in refs], nodes, (0, -1, 0))
            elif case == "B04":
                for a in range(3):
                    if abs(center[a]) < 1e-10:
                        supports.update({(n, a + 1): 0.0 for n in ns})
                    elif abs(center[a] - 1) < 1e-10:
                        pressure_rows.extend((f["element"], f["face"], 1000.0) for f in refs)
            elif abs(center[2]) < 1e-10:
                supports.update({(n, a): 0.0 for n in ns for a in (1, 2, 3)})
        material = manifest["material"]
        if case == "B05":
            density = {"M1": material["density_kg_m3"]}
            gravity = {"M1": tuple(manifest["acceleration_m_s2"])}
        deck = generated_deck(
            mesh,
            supports,
            loads,
            0,
            0,
            materials={"M1": (material["E_pa"], material["nu"])},
            element_materials={int(e): "M1" for e in mesh["elements"]},
            densities=density,
            gravities=gravity,
            pressures=pressure_rows,
            stress_coordinates=True,
        )
        solve(directory, deck)
        written = result_mesh(mesh, {b["id"]: "M1" for b in catalog["bodies"]})
        dat = parse_dat(directory / "analysis.dat", written)
        equilibrium, _ = external_balance(dat, written, mesh["boundary"], deck)
        measurements = evaluate(
            manifest, written, mesh["boundary"], dat, dat["samples"], equilibrium, tip_ref
        )
        runs.append(
            {
                "mesh_size_m": size,
                "nodes": len(mesh["nodes"]),
                "elements": len(mesh["elements"]),
                **measurements,
                "deck_sha256": sha256(directory / "analysis.inp"),
                "mesh_sha256": sha256(directory / "output/mesh.json"),
                "dat_sha256": sha256(directory / "analysis.dat"),
            }
        )
    result = {
        "case": case,
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
