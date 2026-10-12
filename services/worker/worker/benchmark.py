"""Small analytical development cases; release acceptance requires owner sign-off."""

import json
import math
import platform
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from worker.deck import generated_deck
from worker.meshing import Vec, add, norm, resultant, scale, total_face_force
from worker.runtime import (
    ROOT,
    quadratic_mesh,
    sha256,
    solve_generated,
    synthetic_geometry,
    verified_tool,
)


def dat_rows(text: str, heading: str, columns: int) -> list[list[float]]:
    # Deliberately limited to a single static step in these generated test decks.
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if line.strip().startswith(heading)]
    if len(starts) != 1:
        raise ValueError(f"Expected one {heading} section")
    rows: list[list[float]] = []
    for line in lines[starts[0] + 1 :]:
        parts = line.split()
        if not parts:
            if rows:
                break
            continue
        if not parts[0].isdigit() or len(parts) != columns:
            raise ValueError(f"Malformed {heading} row")
        row = [float(v) for v in parts]
        if not all(math.isfinite(v) for v in row):
            raise ValueError("Nonfinite solver output")
        rows.append(row)
    if not rows:
        raise ValueError(f"Empty {heading} output")
    return rows


def solve(directory: Path, deck: str) -> tuple[dict[int, Vec], list[list[float]], dict[int, Vec]]:
    (directory / "analysis.inp").write_text(deck)
    result = solve_generated(directory)
    (directory / "solver.log").write_text(result.stdout + result.stderr)
    if "*ERROR" in result.stdout + result.stderr or "Job finished" not in result.stdout:
        raise ValueError("CCX did not finish without errors")
    equations = re.search(r"number of equations\s*:?\s*(\d+)", result.stdout, re.I)
    if not equations or int(equations[1]) == 0:
        raise ValueError("Reference must solve actual free equations")
    raw = (directory / "analysis.dat").read_text()
    displacement = {int(r[0]): (r[1], r[2], r[3]) for r in dat_rows(raw, "displacements", 4)}
    forces = {int(r[0]): (r[1], r[2], r[3]) for r in dat_rows(raw, "forces", 4)}
    return displacement, dat_rows(raw, "stresses", 8), forces


def run_case(case: str, output: Path, development: bool = False) -> dict[str, Any]:
    if case == "B07":
        from worker.bond_fixture import run_b07

        return run_b07(output, development)
    if case == "B09":
        from worker.stress_fixture import run_b09

        return run_b09(output, development)
    if case not in ("B01", "B02"):
        raise ValueError("Only B01/B02 are implemented; later benchmarks remain unrun")
    manifest_path = ROOT / f"tests/benchmarks/{case}.json"
    manifest = json.loads(manifest_path.read_text())
    approved = not manifest["reviewer_signoff"].startswith("PENDING")
    if not approved and not development:
        raise ValueError(
            "Engineering-owner manifest sign-off pending; use DEVELOPMENT=1 for diagnostics"
        )
    output.mkdir(parents=True, exist_ok=True)
    runs = []
    for index, size in enumerate(manifest["mesh_sizes_m"]):
        directory = output / f"mesh{index + 1}"
        directory.mkdir(exist_ok=True)
        synthetic_geometry(directory, "box")
        quadratic_mesh(directory, size, 1000 * index)
        mesh = json.loads((directory / "mesh.json").read_text())
        catalog = json.loads((directory / "catalog.json").read_text())
        nodes: dict[int, Vec] = {int(n): tuple(p) for n, p in mesh["nodes"].items()}
        supports: dict[tuple[int, int], float] = {}
        loads: dict[int, Vec] = {}
        material = manifest["material"]
        young, poisson = material["E_pa"], material["nu"]
        if case == "B01":
            gradient = manifest["displacement_gradient"]
            expected = {
                n: tuple(sum(gradient[k][j] * p[j] for j in range(3)) for k in range(3))
                for n, p in nodes.items()
            }
            boundary_nodes = {
                n for values in mesh["boundary"].values() for face in values for n in face["nodes"]
            }
            supports = {(n, k + 1): expected[n][k] for n in boundary_nodes for k in range(3)}
            if len(boundary_nodes) == len(nodes):
                raise ValueError("Patch mesh has no free interior nodes")
        else:
            strain = manifest["total_force_n"][0] / young
            expected = {
                n: (strain * p[0], -poisson * strain * p[1], -poisson * strain * p[2])
                for n, p in nodes.items()
            }
            supports = {(n, 1): 0 for n, p in nodes.items() if abs(p[0]) < 1e-9}
            origin = next(n for n, p in nodes.items() if norm(p) < 1e-9)
            edge = next(n for n, p in nodes.items() if norm((p[0], p[1] - 1, p[2])) < 1e-9)
            supports.update({(origin, 2): 0, (origin, 3): 0, (edge, 3): 0})
            ref = next(f["id"] for f in catalog["faces"] if abs(f["center"][0] - 1) < 1e-9)
            loads = total_face_force(
                [tuple(f["nodes"]) for f in mesh["boundary"][ref]],
                nodes,
                tuple(manifest["total_force_n"]),
            )
        deck = generated_deck(mesh, supports, loads, young, poisson)
        if deck != generated_deck(mesh, supports, loads, young, poisson):
            raise ValueError("Nondeterministic deck")
        displacement, stresses, forces = solve(directory, deck)
        if set(displacement) != set(nodes) or set(forces) != set(nodes):
            raise ValueError("Solver omitted nodes")
        element_ids = {int(n) for n in mesh["elements"]}
        if {(int(r[0]), int(r[1])) for r in stresses} != {
            (e, ip) for e in element_ids for ip in range(1, 5)
        }:
            raise ValueError("Solver omitted/duplicated integration points")
        tolerance = manifest["tolerances"]
        displacement_error = max(
            abs(displacement[n][k] - expected[n][k]) for n in nodes for k in range(3)
        )
        stress_error = max(
            abs(r[k + 2] - manifest["expected_stress_ccx_pa"][k])
            for r in stresses
            for k in range(6)
        )
        for n in nodes:
            for k in range(3):
                if abs(displacement[n][k] - expected[n][k]) > max(
                    tolerance["displacement_absolute_m"],
                    tolerance["relative"] * abs(expected[n][k]),
                ):
                    raise ValueError("Analytical displacement tolerance failed")
        for row in stresses:
            for k, reference in enumerate(manifest["expected_stress_ccx_pa"]):
                if abs(row[k + 2] - reference) > max(
                    tolerance["stress_absolute_pa"], tolerance["relative"] * abs(reference)
                ):
                    raise ValueError("Analytical stress tolerance failed")
        # RF is reaction + CLOAD. Recover reactions rather than labelling RF as reaction.
        reactions = {n: add(forces[n], scale(loads.get(n, (0, 0, 0)), -1)) for n in nodes}
        applied_f, applied_m = resultant(loads, nodes)
        reaction_f, reaction_m = resultant(reactions, nodes)
        residual_f = norm(add(applied_f, reaction_f))
        residual_m = norm(add(applied_m, reaction_m))
        force_reference = sum(norm(f) for f in (loads or forces).values())
        moment_reference = force_reference  # explicit 1 m characteristic cube length
        if residual_f > max(
            tolerance["force_absolute_n"], tolerance["equilibrium_relative"] * force_reference
        ):
            raise ValueError("Force balance failed")
        if residual_m > max(
            tolerance["moment_absolute_nm"], tolerance["equilibrium_relative"] * moment_reference
        ):
            raise ValueError("Moment balance failed")
        runs.append(
            {
                "size_m": size,
                "nodes": len(nodes),
                "elements": len(element_ids),
                "max_displacement_error_m": displacement_error,
                "max_stress_error_pa": stress_error,
                "force_residual_n": residual_f,
                "moment_residual_nm": residual_m,
                "applied_force_n": applied_f,
                "reaction_force_n": reaction_f,
                "geometry_revision": mesh["revision"],
                "deck_sha256": sha256(directory / "analysis.inp"),
                "mesh_sha256": sha256(directory / "mesh.json"),
                "dat_sha256": sha256(directory / "analysis.dat"),
            }
        )
    result = {
        "case": case,
        "code_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "manifest_sha256": sha256(manifest_path),
        "reviewer_signoff": manifest["reviewer_signoff"],
        "status": "PASS" if approved else "DEVELOPMENT PASS; owner acceptance pending",
        "platform": platform.platform(),
        "python": platform.python_version(),
        "ccx_version": "2.23",
        "ccx_sha256": sha256(verified_tool("ccx")),
        "gmsh_version": mesh["gmsh_version"],
        "gmsh_build_info": mesh["build_info"],
        "ocp_version": catalog["ocp_version"],
        "occt_cad_version": "8.0.1",
        "threads": 1,
        "parser_scope": "single-step synthetic DAT; raw xx,yy,zz,xy,xz,yz; no averaging",
        "runs": runs,
    }
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    shutil.copy2(manifest_path, output / "manifest.json")
    return result
