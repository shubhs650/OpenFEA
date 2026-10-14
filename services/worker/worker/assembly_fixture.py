"""B11: actual unstable native diagnostics remain failures, never valid solutions."""

import json
import subprocess
from pathlib import Path
from typing import Any

from worker.approval import require_benchmark_approval
from worker.bond_fixture import build_fixture, interface_refs, setup_axial
from worker.calculix.assembly import components, mesh_supports, support_rank
from worker.calculix.bonds import prepare_bond, typed_mesh
from worker.calculix.results import parse_dat
from worker.deck import generated_deck
from worker.local_solve import SolverSingularity, check_numerical_log
from worker.runtime import ROOT, NativeOperationError, sha256, solve_generated, verified_tool


def run_b11(output: Path, development: bool = False) -> dict[str, Any]:
    path = ROOT / "tests/benchmarks/B11.json"
    manifest = json.loads(path.read_text())
    approved = require_benchmark_approval(manifest, development)
    if output.exists():
        raise ValueError("B11 requires a fresh output directory")
    output.mkdir(parents=True)
    mesh, catalog = build_fixture(output / "geometry")
    typed = typed_mesh(mesh)
    supports, loads = setup_axial(mesh, catalog)
    bodies = [b["id"] for b in catalog["bodies"]]
    try:
        mesh_supports(mesh, components(bodies, []), supports, {})
    except ValueError as error:
        detached = str(error)
    else:
        raise ValueError("Detached body incorrectly passed")
    ux = {(n, a): v for (n, a), v in supports.items() if a == 1}
    try:
        mesh_supports(mesh, [bodies], ux, {})
    except ValueError as error:
        underconstrained = str(error)
    else:
        raise ValueError("Rank-deficient connected body incorrectly passed")
    try:
        components(bodies, [(bodies[0], bodies[1]), (bodies[1], bodies[0])])
    except ValueError as error:
        redundant = str(error)
    else:
        raise ValueError("Redundant cycle incorrectly passed")
    master, slave = interface_refs(catalog)
    constrained = {n for f in mesh["boundary"][slave] for n in f["nodes"]}
    try:
        prepare_bond(mesh, catalog, master, slave, constrained)
    except ValueError as error:
        conflict = str(error)
    else:
        raise ValueError("Slave SPC conflict incorrectly passed")
    # A finite translation is a true zero-strain mode without an external support.
    finite_mode = {str(n): [1.0, 2.0, 3.0] for n in typed.nodes}
    if support_rank([], list(typed.nodes.values())) != 0:
        raise ValueError("Finite rigid translation was misclassified as supported")
    diagnostic = output / "native"
    diagnostic.mkdir()
    deck = generated_deck(mesh, supports, loads, 210e9, 0.3, stress_coordinates=True)
    if "*SPRING" in deck or "*TIE" in deck or "*EQUATION" in deck:
        raise ValueError("Diagnostic unexpectedly stabilizes or ties the detached body")
    (diagnostic / "analysis.inp").write_text(deck)
    try:
        completed = solve_generated(diagnostic)
    except NativeOperationError as error:
        completed = error.result
    transcript = completed.stdout + completed.stderr
    (diagnostic / "solver.log").write_text(transcript)
    try:
        check_numerical_log(transcript)
        native_message = None
    except SolverSingularity as error:
        native_message = str(error)
    finite_native = None
    parse_error = None
    if (diagnostic / "analysis.dat").exists():
        try:
            parsed = parse_dat(diagnostic / "analysis.dat", typed)
            finite_native = max(abs(v) for u in parsed["displacements_m"].values() for v in u)
        except ValueError as error:
            parse_error = str(error)
    result = {
        "case": "B11",
        "status": "PASS" if approved else "DEVELOPMENT PASS; engineering review pending",
        "code_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "manifest_sha256": sha256(path),
        "ccx_sha256": sha256(verified_tool("ccx")),
        "detached_refusal": detached,
        "underconstrained_refusal": underconstrained,
        "redundant_refusal": redundant,
        "slave_spc_refusal": conflict,
        "finite_rigid_mode": {
            "displacement_m": [1.0, 2.0, 3.0],
            "support_rank": 0,
            "node_count": len(finite_mode),
            "credited_as_result": False,
        },
        "native": {
            "returncode": completed.returncode,
            "finish_marker": "Job finished" in transcript,
            "singularity_message": native_message,
            "max_finite_native_displacement_m": finite_native,
            "raw_parse_error": parse_error,
            "credited_as_result": False,
            "refusal": detached,
            "artifacts": {p.name: sha256(p) for p in diagnostic.iterdir() if p.is_file()},
        },
        "weak_springs": False,
        "stability_proven": False,
        "threads": 1,
    }
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
