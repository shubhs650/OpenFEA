"""Frozen T028 references: published comparisons, never invented external runs."""

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
from worker.calculix.results import parse_dat
from worker.deck import generated_deck
from worker.local_solve import check_numerical_log, result_mesh
from worker.meshing import Vec, cross, dot, sub, surface_integral, total_face_force
from worker.postprocess.fields import element_nodes, probe_element
from worker.postprocess.tensors import von_mises
from worker.runtime import NATIVE, ROOT, execute, sha256, verified_tool


def reference_displacement(case: str, p: Vec) -> Vec:
    x, y, z = p
    if case == "B12":
        return tuple(0.0005 * (x + y + z + v) for v in p)  # type: ignore[return-value]
    q, nu = 7800 * 9.81 / 2e11, 0.3
    return -nu * q * x * z, -nu * q * y * z, q * (z * z + nu * (x * x + y * y) - 9) / 2


def compare(actual: float, expected: float, relative: float, absolute: float) -> float:
    if not math.isfinite(actual) or abs(actual - expected) > max(
        absolute, relative * abs(expected)
    ):
        raise ValueError(f"Predeclared reference failed: actual={actual}, expected={expected}")
    return abs(actual - expected)


def run_reference(case: str, output: Path, development: bool = False) -> dict[str, Any]:
    path = ROOT / f"tests/benchmarks/{case}.json"
    manifest = json.loads(path.read_bytes())
    approved = require_benchmark_approval(manifest, development)
    # Fresh destinations retain failures instead of overwriting earlier evidence.
    output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(path, output / "manifest.json")
    runs = []
    tolerance = manifest["tolerances"]
    for index, size in enumerate(manifest["mesh_sizes_m"], 1):
        directory = output / f"mesh{index}"
        directory.mkdir()
        generated = execute(
            [
                str(NATIVE / "venvs/mesh/bin/python"),
                "-I",
                str(ROOT / "services/worker/worker/meshing_native/references.py"),
                case,
                str(size),
            ],
            directory,
        )
        (directory / "mesh.log").write_text(generated.stdout + generated.stderr)
        raw = json.loads((directory / "mesh.json").read_bytes())
        mesh = result_mesh(raw, {"reference": "M1"})
        nodes = mesh.nodes
        supports: dict[tuple[int, int], float] = {}
        loads: dict[int, Vec] = {}
        tip = []
        material = manifest["material"]
        for faces in raw["boundary"].values():
            ns = {n for f in faces for n in f["nodes"]}
            if case == "B12":
                supports.update(
                    {
                        (n, a + 1): reference_displacement(case, nodes[n])[a]
                        for n in ns
                        for a in range(3)
                    }
                )
            elif case == "B13":
                for axis in (0, 1):
                    if all(abs(nodes[n][axis]) < 1e-10 for n in ns):
                        supports.update({(n, axis + 1): 0 for n in ns})
                if all(abs(nodes[n][2] - 3) < 1e-10 for n in ns):
                    loads = total_face_force(
                        [tuple(f["nodes"]) for f in faces], nodes, (0, 0, 229554 * 0.25)
                    )
            else:
                axis, root, end, force = (
                    (2, 0.06, 0.08, (0, 0, -10))
                    if case == "B10"
                    else (1, 0, 0.254, (0, 44482.216152605, 0))
                )
                if all(abs(nodes[n][axis] - root) < 1e-10 for n in ns):
                    supports.update({(n, a): 0 for n in ns for a in (1, 2, 3)})
                end_axis = 0 if case == "B10" else 1
                if all(abs(nodes[n][end_axis] - end) < 1e-10 for n in ns):
                    tip = faces
                    loads = total_face_force([tuple(f["nodes"]) for f in faces], nodes, force)
        if case == "B13":
            anchor = next(
                n
                for n, p in nodes.items()
                if max(abs(p[k] - v) for k, v in enumerate((0, 0, 3))) < 1e-10
            )
            supports[anchor, 3] = 0
        deck = generated_deck(
            raw,
            supports,
            loads,
            0,
            0,
            materials={"M1": (material["E_pa"], material["nu"])},
            element_materials={e: "M1" for e in mesh.elements},
            densities={"M1": 7800} if case == "B13" else None,
            gravities={"M1": (0, 0, -9.81)} if case == "B13" else None,
            stress_coordinates=True,
        )
        solve(directory, deck)
        check_numerical_log((directory / "solver.log").read_text())
        dat = parse_dat(directory / "analysis.dat", mesh)
        equilibrium, _ = external_balance(dat, mesh, raw["boundary"], deck)
        if not equilibrium["passed"]:
            raise ValueError("External force/moment equilibrium failed")
        displacement = {int(n): tuple(v) for n, v in dat["displacements_m"].items()}
        measurements: dict[str, Any] = {}
        if case in ("B12", "B13"):
            de = [
                compare(
                    displacement[n][a],
                    reference_displacement(case, p)[a],
                    tolerance["relative"],
                    tolerance["displacement_absolute_m"],
                )
                for n, p in nodes.items()
                for a in range(3)
            ]
            se: list[float] = []
            for p in dat["samples"]:
                expected = (
                    manifest["expected_tensor_pa"]
                    if case == "B12"
                    else (0, 0, 7800 * 9.81 * p.position_m[2], 0, 0, 0)
                )
                se.extend(
                    compare(a, b, tolerance["relative"], tolerance["stress_absolute_pa"])
                    for a, b in zip(p.tensor_pa, expected, strict=True)
                )
            measurements.update(
                max_displacement_error_m=max(de),
                max_stress_error_pa=max(se),
                stress_samples=len(dat["samples"]),
            )
            if case == "B13":
                bottom = next(n for n, p in nodes.items() if max(map(abs, p)) < 1e-10)
                compare(
                    displacement[bottom][2],
                    manifest["published_B_uz_m"],
                    tolerance["relative"],
                    tolerance["displacement_absolute_m"],
                )
                measurements["published_B_uz_m"] = displacement[bottom][2]
        else:
            component = 2 if case == "B10" else 1
            areas = [surface_integral([nodes[n] for n in f["nodes"]])[0] for f in tip]
            mean = sum(
                area * sum(displacement[n][component] for n in f["nodes"][3:]) / 3
                for area, f in zip(areas, tip, strict=True)
            ) / sum(areas)
            measurements["tip_mean_m"] = mean
            if case == "B14":
                samples = [
                    p.tensor_pa[1]
                    for p in dat["samples"]
                    if abs(p.position_m[1] - 0.127) <= 0.00508
                    and max(abs(p.position_m[k]) for k in (0, 2)) <= 0.00635
                ]
                if len(samples) < 4:
                    raise ValueError("Missing predeclared interior samples")
                stress = sum(samples) / len(samples)
                compare(
                    mean,
                    manifest["expected_tip_uy_m"],
                    tolerance["tip_relative"],
                    tolerance["displacement_absolute_m"],
                )
                compare(
                    stress,
                    manifest["expected_syy_pa"],
                    tolerance["stress_relative"],
                    tolerance["stress_absolute_pa"],
                )
                measurements.update(
                    stress_mean_pa=stress,
                    stress_range_pa=[min(samples), max(samples)],
                    stress_samples=len(samples),
                    tip_relative_error=abs(mean / manifest["expected_tip_uy_m"] - 1),
                    stress_relative_error=abs(stress / manifest["expected_syy_pa"] - 1),
                    published_solid45_tip_difference_m=mean
                    - manifest["published_solid45_tip_uy_m"],
                    published_solid45_stress_difference_pa=stress
                    - manifest["published_solid45_syy_pa"],
                )
            else:
                point = tuple(manifest["samples"]["stress_point_m"])
                derived = element_nodes(dat["samples"], mesh)
                for e, element in sorted(mesh.elements.items()):
                    a, b, c = (sub(nodes[element[i]], nodes[element[0]]) for i in (1, 2, 3))
                    d = sub(point, nodes[element[0]])
                    det = dot(a, cross(b, c))
                    bary = (
                        dot(d, cross(b, c)) / det,
                        dot(a, cross(d, c)) / det,
                        dot(a, cross(b, d)) / det,
                    )
                    weights = (1 - sum(bary), *bary)
                    if min(weights) >= 0 and max(weights) <= 1:
                        sample = probe_element(derived, mesh, e, weights)
                        measurements.update(
                            stress_von_mises_pa=von_mises(sample.tensor_pa),
                            stress_element=e,
                            stress_barycentric=weights,
                        )
                        break
                else:
                    raise ValueError("Fixed interior physical point is outside mesh")
        runs.append(
            {
                "mesh_size_m": size,
                "nodes": len(nodes),
                "elements": len(mesh.elements),
                **measurements,
                "equilibrium": equilibrium,
                **{
                    name + "_sha256": sha256(directory / name)
                    for name in (
                        "source.brep",
                        "mesh.json",
                        "analysis.inp",
                        "analysis.dat",
                        "solver.log",
                    )
                },
            }
        )
        (output / "progress.json").write_text(json.dumps(runs, indent=2, allow_nan=False) + "\n")
    if case == "B10":
        previous, final = runs[-2:]
        compare(
            final["tip_mean_m"],
            previous["tip_mean_m"],
            tolerance["tip_change_relative"],
            tolerance["displacement_absolute_m"],
        )
        compare(
            final["stress_von_mises_pa"],
            previous["stress_von_mises_pa"],
            tolerance["stress_change_relative"],
            tolerance["stress_absolute_pa"],
        )
    result = {
        "case": case,
        "status": "PASS" if approved else "DEVELOPMENT PASS; owner acceptance pending",
        "runs": runs,
        "code_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "manifest_sha256": sha256(path),
        "reviewer_signoff": manifest["reviewer_signoff"],
        "platform": platform.platform(),
        "python": platform.python_version(),
        "ccx_version": "2.23",
        "gmsh_version": "4.15.2",
        "threads": 1,
        "ccx_sha256": sha256(verified_tool("ccx")),
        "solver_backend": "CalculiX 2.23",
        "code_aster_executed": False,
        "ansys_executed": False,
    }
    (output / "result.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    return result
