"""B08 development experiment: ideal displacement continuity across an explicit void."""

import copy
import json
import platform
import re
import subprocess
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, cast

from worker.approval import require_benchmark_approval
from worker.benchmark import solve
from worker.bond_fixture import (
    build_fixture,
    coordinate_audit,
    interface_refs,
    setup_axial,
    tie_deck,
)
from worker.calculix.bonds import (
    mesh_hash,
    prepare_bond,
    solver_uncovered_nodes,
    tie_residual,
    typed_mesh,
)
from worker.calculix.mortar import mortar_bond
from worker.calculix.results import parse_dat
from worker.meshing import Vec, add, norm, resultant
from worker.runtime import ROOT, sha256, verified_tool


def run_b08(output: Path, development: bool = False) -> dict[str, Any]:
    manifest_path = ROOT / "tests/benchmarks/B08.json"
    manifest = json.loads(manifest_path.read_text())
    approved = require_benchmark_approval(manifest, development)
    if output.exists():
        raise ValueError("B08 requires a fresh output directory")
    output.mkdir(parents=True)
    mesh, catalog = build_fixture(output / "geometry", gap_probe=True)
    original_hash = mesh_hash(mesh)
    master, slave = interface_refs(catalog, gap=True)
    gap = manifest["gap_m"]
    supports, loads = setup_axial(mesh, catalog)
    typed = typed_mesh(mesh)
    cases = {}
    for name, m, s in (("left_master", master, slave), ("right_master", slave, master)):
        # Integrate on projected interface planes only. Physical mesh is never altered.
        integration = copy.deepcopy(mesh)
        selected_body = next(f["body"] for f in catalog["faces"] if f["id"] == s)
        selected_nodes = {
            n for e, ns in typed.elements.items() if typed.bodies[e] == selected_body for n in ns
        }
        translation = -gap if s == slave else gap
        for n in selected_nodes:
            p = typed.nodes[n]
            integration["nodes"][str(n)] = [p[0] + translation, p[1], p[2]]
        planned = prepare_bond(integration, catalog, m, s, {n for n, _ in supports})
        planned, coupling = mortar_bond(integration, planned)
        bond = replace(
            planned,
            mesh_sha256=original_hash,
            projections=tuple(replace(p, distance_m=gap) for p in planned.projections),
        )
        directory = output / name
        directory.mkdir()
        deck = (
            "** B08 explicit 10 micrometre physical gap; ideal displacement continuity\n"
            "** No coordinate adjustment\n" + tie_deck(mesh, supports, loads, bond)
        )
        u, _, rf = solve(directory, deck)
        log = (directory / "solver.log").read_text()
        if "*WARNING" in log or solver_uncovered_nodes(directory):
            raise ValueError("B08 solver warning or uncovered node")
        expected_equations = 3 * len(typed.nodes) - len(supports) - 3 * len(bond.slave_nodes)
        equations = re.search(r"number of equations\s*:?\s*(\d+)", log, re.I)
        if not equations or int(equations[1]) != expected_equations:
            raise ValueError("B08 native equation coverage mismatch")
        tol = manifest["tolerances"]
        u_error = s_error = 0.0
        for n, p in typed.nodes.items():
            x = p[0] - gap if p[0] > 1 else p[0]
            expected = (1e6 / 210e9 * x, -0.3e6 / 210e9 * p[1], -0.3e6 / 210e9 * p[2])
            for actual, target in zip(u[n], expected, strict=True):
                u_error = max(u_error, abs(actual - target))
                if abs(actual - target) > max(
                    tol["displacement_absolute_m"], tol["displacement_relative"] * abs(target)
                ):
                    raise ValueError("B08 all-node analytical displacement failed")
        parsed = parse_dat(directory / "analysis.dat", typed)
        for point in parsed["samples"]:
            for actual, target in zip(point.tensor_pa, (1e6, 0, 0, 0, 0, 0), strict=True):
                s_error = max(s_error, abs(actual - target))
                if abs(actual - target) > max(
                    tol["stress_absolute_pa"], tol["stress_relative"] * abs(target)
                ):
                    raise ValueError("B08 all-IP stress failed")
        reactions: dict[int, Vec] = {
            n: cast(
                Vec,
                tuple(
                    rf[n][k] - loads.get(n, (0, 0, 0))[k] if (n, k + 1) in supports else 0.0
                    for k in range(3)
                ),
            )
            for n in typed.nodes
        }
        reaction_f, reaction_m = resultant(reactions, typed.nodes)
        applied_f, applied_m = resultant(loads, typed.nodes)
        force, moment = norm(add(reaction_f, applied_f)), norm(add(reaction_m, applied_m))
        if force > max(tol["force_absolute_n"], tol["equilibrium_relative"] * 1e6) or moment > max(
            tol["moment_absolute_nm"], tol["equilibrium_relative"] * 2e6
        ):
            raise ValueError("B08 external force/moment balance failed")
        residual = tie_residual(bond, u)
        if residual > tol["tie_residual_absolute_m"]:
            raise ValueError("B08 displacement continuity failed")
        audit = coordinate_audit(directory / "coordinate-audit", deck, mesh)
        if audit["max_solver_adjustment_m"] > tol["solver_adjustment_absolute_m"]:
            raise ValueError("B08 solver adjusted geometry")
        if mesh_hash(mesh) != original_hash:
            raise ValueError("B08 source mesh mutated")
        (directory / "bond.json").write_text(json.dumps(asdict(bond), indent=2) + "\n")
        cases[name] = {
            "intended_slave_nodes": len(bond.slave_nodes),
            "equations": expected_equations,
            "uncovered_nodes": [],
            "max_displacement_error_m": u_error,
            "max_stress_error_pa": s_error,
            "max_tie_residual_m": residual,
            "force_residual_n": force,
            "moment_residual_nm": moment,
            "coordinate_audit": audit,
            "coupling": coupling,
            "artifacts": {p.name: sha256(p) for p in directory.iterdir() if p.is_file()},
        }
    result = {
        "case": "B08",
        "status": "PASS" if approved else "DEVELOPMENT PASS; engineering review pending",
        "manifest_sha256": sha256(manifest_path),
        "code_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "ccx_sha256": sha256(verified_tool("ccx")),
        "gmsh_version": mesh["gmsh_version"],
        "ocp_version": catalog["ocp_version"],
        "threads": 1,
        "gap_m": gap,
        "source_mesh_sha256": original_hash,
        "cases": cases,
    }
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
