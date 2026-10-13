"""B07 independently meshed zero-gap tie versus real monolithic reference."""

import json
import platform
import re
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any

from worker.approval import require_benchmark_approval
from worker.benchmark import solve
from worker.calculix.bonds import (
    Bond,
    binary_frd_coordinates,
    bond_keywords,
    prepare_bond,
    require_supported_bodies,
    solver_uncovered_nodes,
    tie_residual,
    typed_mesh,
)
from worker.calculix.mortar import mortar_bond
from worker.calculix.results import parse_dat
from worker.deck import generated_deck
from worker.meshing import Vec, add, cross, dot, norm, resultant, sub, total_face_force
from worker.postprocess.fields import element_nodes, probe_element
from worker.runtime import (
    ROOT,
    NativeOperationError,
    quadratic_mesh,
    sha256,
    solve_generated,
    synthetic_geometry,
    verified_tool,
)


def build_fixture(
    directory: Path, bonded: bool = True, gap_probe: bool = False
) -> tuple[dict[str, Any], dict[str, Any]]:
    directory.mkdir(parents=True, exist_ok=True)
    synthetic_geometry(directory, "gap-probe" if gap_probe else "bonded" if bonded else "long-box")
    quadratic_mesh(directory, 0.4, 3000, body_sizes=(0.6, 0.4) if bonded else None)
    return json.loads((directory / "mesh.json").read_text()), json.loads(
        (directory / "catalog.json").read_text()
    )


def setup_axial(
    mesh: dict[str, Any], catalog: dict[str, Any]
) -> tuple[dict[tuple[int, int], float], dict[int, Vec]]:
    nodes = typed_mesh(mesh).nodes
    supports = {(n, 1): 0.0 for n, p in nodes.items() if abs(p[0]) < 1e-9}
    origin = next(n for n, p in nodes.items() if norm(p) < 1e-9)
    edge = next(n for n, p in nodes.items() if norm(sub(p, (0, 1, 0))) < 1e-9)
    supports.update({(origin, 2): 0.0, (origin, 3): 0.0, (edge, 3): 0.0})
    far = max(p[0] for p in nodes.values())
    loaded = next(f["id"] for f in catalog["faces"] if abs(f["center"][0] - far) < 1e-9)
    loads = total_face_force(
        [tuple(f["nodes"]) for f in mesh["boundary"][loaded]], nodes, (1e6, 0, 0)
    )
    return supports, loads


def interface_refs(catalog: dict[str, Any], gap: bool = False) -> tuple[str, str]:
    left = catalog["bodies"][0]["id"]
    right = catalog["bodies"][1]["id"]
    master = next(
        f["id"] for f in catalog["faces"] if f["body"] == left and abs(f["center"][0] - 1) < 1e-9
    )
    slave = next(
        f["id"]
        for f in catalog["faces"]
        if f["body"] == right and abs(f["center"][0] - (1.00001 if gap else 1)) < 1e-9
    )
    return master, slave


def tie_deck(
    mesh: dict[str, Any],
    supports: dict[tuple[int, int], float],
    loads: dict[int, Vec],
    bond: Bond | None,
) -> str:
    if bond:
        require_supported_bodies(mesh, [bond], {n for n, _axis in supports})
    else:
        require_supported_bodies(mesh, [], {n for n, _axis in supports})
    deck = generated_deck(mesh, supports, loads, 210e9, 0.3, stress_coordinates=True)
    if bond:
        # Model-definition keywords before material/step; never raw uploaded input.
        deck = deck.replace(
            "*MATERIAL,NAME=ISOTROPIC", bond_keywords(bond) + "*MATERIAL,NAME=ISOTROPIC", 1
        )
    return deck


def coordinate_audit(directory: Path, deck: str, mesh: dict[str, Any]) -> dict[str, Any]:
    # The last output card selects binary FRD geometry, written as native doubles.
    directory.mkdir(parents=True, exist_ok=True)
    audit_deck = deck.replace("*END STEP", "*NODE OUTPUT\nU\n*END STEP")
    (directory / "analysis.inp").write_text(audit_deck)
    completed = solve_generated(directory)
    (directory / "solver.log").write_text(completed.stdout + completed.stderr)
    if "*ERROR" in completed.stdout + completed.stderr or "Job finished" not in completed.stdout:
        raise ValueError("Native coordinate audit failed")
    nodes = typed_mesh(mesh).nodes
    actual = binary_frd_coordinates(directory / "analysis.frd", set(nodes))
    # Compare against emitted finite-precision deck coordinates, not rounded ASCII FRD.
    expected = {n: tuple(float(f"{v:.12e}") for v in p) for n, p in nodes.items()}
    changes = {n: norm(sub(actual[n], (p[0], p[1], p[2]))) for n, p in expected.items()}
    result = {
        "max_solver_adjustment_m": max(changes.values()),
        "changed_nodes_gt_1e12_m": [n for n, value in changes.items() if value > 1e-12],
        "coordinate_precision": "native binary FRD doubles; little-endian x86_64 geometry only",
        "source_sha256": sha256(directory / "analysis.frd"),
        "deck_sha256": sha256(directory / "analysis.inp"),
    }
    (directory / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def point_probe(mesh: dict[str, Any], samples: list[Any], position: Vec) -> dict[str, Any]:
    typed = typed_mesh(mesh)
    derived = element_nodes(samples, typed)
    for eid, ns in sorted(typed.elements.items()):
        origin = typed.nodes[ns[0]]
        a, b, c = [sub(typed.nodes[ns[i]], origin) for i in (1, 2, 3)]
        p = sub(position, origin)
        determinant = dot(a, cross(b, c))
        r, s, t = (
            dot(p, cross(b, c)) / determinant,
            dot(a, cross(p, c)) / determinant,
            dot(a, cross(b, p)) / determinant,
        )
        bary = (1 - r - s - t, r, s, t)
        if min(bary) >= -1e-12 and max(bary) <= 1 + 1e-12:
            values = [max(0.0, min(1.0, v)) for v in bary]  # numerical boundary rounding only
            total = sum(values)
            sample = probe_element(
                derived,
                typed,
                eid,
                (values[0] / total, values[1] / total, values[2] / total, values[3] / total),
            )
            return asdict(sample)
    raise ValueError("No validated element contains the declared physical probe")


def evaluate(
    directory: Path,
    mesh: dict[str, Any],
    catalog: dict[str, Any],
    bond: Bond | None,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    supports, loads = setup_axial(mesh, catalog)
    deck = tie_deck(mesh, supports, loads, bond)
    displacement, _raw_stresses, forces = solve(directory, deck)
    log = (directory / "solver.log").read_text()
    if "*WARNING" in log:
        raise ValueError("Solver warning must be reviewed before crediting a bonded solve")
    uncovered = solver_uncovered_nodes(directory)
    if uncovered:
        raise ValueError(f"Native solver did not tie all intended nodes: {uncovered}")
    typed = typed_mesh(mesh)
    parsed = parse_dat(directory / "analysis.dat", typed)
    samples = parsed["samples"]
    tolerance = manifest["tolerances"]
    displacement_error = 0.0
    stress_error = 0.0
    for n, p in typed.nodes.items():
        expected = (1e6 * p[0] / 210e9, -0.3 * 1e6 * p[1] / 210e9, -0.3 * 1e6 * p[2] / 210e9)
        for actual, target in zip(displacement[n], expected, strict=True):
            displacement_error = max(displacement_error, abs(actual - target))
            if abs(actual - target) > max(
                tolerance["displacement_absolute_m"],
                tolerance["displacement_relative"] * abs(target),
            ):
                raise ValueError("B07 analytical displacement tolerance failed")
    for sample in samples:
        for actual, target in zip(
            sample.tensor_pa, manifest["expected_canonical_stress_pa"], strict=True
        ):
            stress_error = max(stress_error, abs(actual - target))
            if abs(actual - target) > max(
                tolerance["stress_absolute_pa"], tolerance["stress_relative"] * abs(target)
            ):
                raise ValueError("B07 raw integration stress tolerance failed")
    # Only SPC DOFs are external reactions. Tie MPC forces remain internal.
    reactions = {
        n: tuple(
            forces[n][k] - loads.get(n, (0, 0, 0))[k] if (n, k + 1) in supports else 0.0
            for k in range(3)
        )
        for n in typed.nodes
    }
    reaction_f, reaction_m = resultant(
        {n: (v[0], v[1], v[2]) for n, v in reactions.items()}, typed.nodes
    )
    applied_f, applied_m = resultant(loads, typed.nodes)
    force_residual = norm(add(reaction_f, applied_f))
    moment_residual = norm(add(reaction_m, applied_m))
    if force_residual > max(tolerance["force_absolute_n"], tolerance["equilibrium_relative"] * 1e6):
        raise ValueError("B07 external reaction force balance failed")
    if moment_residual > max(
        tolerance["moment_absolute_nm"], tolerance["equilibrium_relative"] * 1e6 * 2
    ):
        raise ValueError("B07 external reaction moment balance failed")
    equations = re.search(r"number of equations\s*:?\s*(\d+)", log, re.I)
    expected_equations = (
        3 * len(typed.nodes) - len(supports) - (3 * len(bond.slave_nodes) if bond else 0)
    )
    if not equations or int(equations[1]) != expected_equations:
        raise ValueError("Native free-equation count does not account for every intended tie DOF")
    audit = coordinate_audit(directory / "coordinate-audit", deck, mesh)
    if audit["max_solver_adjustment_m"] > tolerance["solver_adjustment_absolute_m"]:
        raise ValueError("Solver changed geometry despite ADJUST=NO")
    residual = tie_residual(bond, displacement) if bond else 0.0
    if residual > tolerance["tie_residual_absolute_m"]:
        raise ValueError("Native displacements do not satisfy quadratic tie interpolation")
    end = [n for n, p in typed.nodes.items() if abs(p[0] - 2) < 1e-9]
    probes = [point_probe(mesh, samples, p) for p in ((0.5, 0.25, 0.25), (1.5, 0.25, 0.25))]
    result = {
        "nodes": len(typed.nodes),
        "elements": len(typed.elements),
        "body_count": len(set(typed.bodies.values())),
        "body_nodes": {
            body: len(
                {n for e, ns in typed.elements.items() if typed.bodies[e] == body for n in ns}
            )
            for body in sorted(set(typed.bodies.values()))
        },
        "equations": int(equations[1]),
        "expected_equations": expected_equations,
        "intended_slave_nodes": len(bond.slave_nodes) if bond else 0,
        "solver_uncovered_nodes": uncovered,
        "max_tie_residual_m": residual,
        "max_displacement_error_m": displacement_error,
        "max_stress_error_pa": stress_error,
        "mean_end_ux_m": sum(displacement[n][0] for n in end) / len(end),
        "external_reaction_force_n": reaction_f,
        "force_residual_n": force_residual,
        "moment_residual_nm": moment_residual,
        "coordinate_audit": audit,
        "probes": probes,
        "geometry_revision": mesh["revision"],
        "mesh_sha256": sha256(directory / "mesh.json"),
        "deck_sha256": sha256(directory / "analysis.inp"),
        "dat_sha256": sha256(directory / "analysis.dat"),
        "frd_sha256": sha256(directory / "analysis.frd"),
        "solver_log_sha256": sha256(directory / "solver.log"),
    }
    (directory / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def run_b07(output: Path, development: bool = False) -> dict[str, Any]:
    manifest_path = ROOT / "tests/benchmarks/B07-mortar.json"
    manifest = json.loads(manifest_path.read_text())
    approved = require_benchmark_approval(manifest, development)
    output.mkdir(parents=True, exist_ok=True)
    reference_dir = output / "monolithic"
    reference_mesh, reference_catalog = build_fixture(reference_dir, bonded=False)
    reference = evaluate(reference_dir, reference_mesh, reference_catalog, None, manifest)
    geometry_dir = output / "geometry"
    mesh, catalog = build_fixture(geometry_dir)
    left, right = interface_refs(catalog)
    supports, _loads = setup_axial(mesh, catalog)
    results = {}
    for name, master, slave in (("left_master", left, right), ("right_master", right, left)):
        directory = output / name
        directory.mkdir(exist_ok=True)
        bond = prepare_bond(mesh, catalog, master, slave, {n for n, _ in supports})
        bond, coupling_report = mortar_bond(mesh, bond)
        (directory / "bond.json").write_text(json.dumps(asdict(bond), indent=2) + "\n")
        for file in ("mesh.json", "catalog.json"):
            shutil.copy2(geometry_dir / file, directory / file)
        result = evaluate(directory, mesh, catalog, bond, manifest)
        result["coupling"] = coupling_report
        error = abs(result["mean_end_ux_m"] - reference["mean_end_ux_m"]) / abs(
            reference["mean_end_ux_m"]
        )
        if error > manifest["tolerances"]["displacement_relative"]:
            raise ValueError("Bonded versus monolithic displacement failed")
        for probe, reference_probe in zip(result["probes"], reference["probes"], strict=True):
            for a, b in zip(probe["tensor_pa"], reference_probe["tensor_pa"], strict=True):
                if abs(a - b) > max(
                    manifest["tolerances"]["stress_absolute_pa"],
                    manifest["tolerances"]["stress_relative"] * abs(b),
                ):
                    raise ValueError("Bonded versus monolithic physical stress probe failed")
        result["relative_end_displacement_difference_to_monolithic"] = error
        results[name] = result
    summary = {
        "case": "B07",
        "status": "PASS" if approved else "DEVELOPMENT PASS; engineering review pending",
        "code_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "manifest_sha256": sha256(manifest_path),
        "reviewer_signoff": manifest["reviewer_signoff"],
        "ccx_version": "2.23",
        "ccx_sha256": sha256(verified_tool("ccx")),
        "threads": 1,
        "gmsh_version": mesh["gmsh_version"],
        "gmsh_build_info": mesh["build_info"],
        "ocp_version": catalog["ocp_version"],
        "platform": platform.platform(),
        "python": platform.python_version(),
        "reference": reference,
        "bonded_cases": results,
    }
    (output / "result.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def native_diagnostics(output: Path) -> dict[str, Any]:
    """Controlled rejected native *TIE/rank/adjustment experiments, not enabled features."""
    from dataclasses import replace

    from worker.calculix.bonds import UnresolvedBond, mesh_hash

    output.mkdir(parents=True, exist_ok=True)
    mesh, catalog = build_fixture(output / "geometry")
    supports, loads = setup_axial(mesh, catalog)
    master, slave = interface_refs(catalog)
    native = prepare_bond(mesh, catalog, master, slave, {n for n, _ in supports})
    candidate = output / "native-tie"
    candidate.mkdir(exist_ok=True)
    native_deck = tie_deck(mesh, supports, loads, native)
    u, stress, _forces = solve(candidate, native_deck)
    max_error = max(abs(row[k + 2] - ([1e6, 0, 0, 0, 0, 0][k])) for row in stress for k in range(6))
    if max_error <= 5e4:
        raise ValueError(
            "Unexpected native candidate behavior; re-review frozen rejection evidence"
        )
    audit = coordinate_audit(candidate / "coordinate-audit", native_deck, mesh)
    results = {
        "native_tie_candidate": {
            "status": "REJECTED under unchanged B07 revision-1 patch criteria",
            "max_stress_error_pa": max_error,
            "intended_slave_nodes": len(native.slave_nodes),
            "uncovered_nodes": solver_uncovered_nodes(candidate),
            "max_kinematic_residual_m": tie_residual(native, u),
            "coordinate_audit": audit,
        }
    }
    # Demonstrate native missing coverage even though the normal preflight blocks it.
    partial = output / "partial-master"
    partial.mkdir(exist_ok=True)
    broken = replace(native, master_faces=native.master_faces[:1])
    deck = generated_deck(mesh, supports, loads, 210e9, 0.3, stress_coordinates=True)
    deck = deck.replace(
        "*MATERIAL,NAME=ISOTROPIC", bond_keywords(broken) + "*MATERIAL,NAME=ISOTROPIC", 1
    )
    (partial / "analysis.inp").write_text(deck)
    try:
        completed = solve_generated(partial)
    except NativeOperationError as error:
        completed = error.result
    (partial / "solver.log").write_text(completed.stdout + completed.stderr)
    missing = solver_uncovered_nodes(partial)
    if not missing or not set(missing).issubset(set(native.slave_nodes)):
        raise ValueError("Native missing-coverage diagnostic produced no valid warning nodes")
    results["partial_master"] = {
        "status": "EXPECTED REJECTION; incomplete native tie coverage",
        "uncovered_nodes": missing,
        "solver_exit_code": completed.returncode,
    }
    # Both the graph preflight and the actual bare native response are retained.
    untied = output / "untied"
    untied.mkdir(exist_ok=True)
    try:
        require_supported_bodies(mesh, [], {n for n, _ in supports})
    except UnresolvedBond as error:
        graph_failure = str(error)
    else:
        raise ValueError("Detached body was not rejected before solve")
    deck = generated_deck(mesh, supports, loads, 210e9, 0.3, stress_coordinates=True)
    (untied / "analysis.inp").write_text(deck)
    try:
        completed = solve_generated(untied)
    except NativeOperationError as error:
        completed = error.result
    (untied / "solver.log").write_text(completed.stdout + completed.stderr)
    results["untied"] = {
        "status": "EXPECTED REJECTION; detached rigid body, no stabilization",
        "preflight_diagnosis": graph_failure,
        "solver_exit_code": completed.returncode,
        "native_job_finished": "Job finished" in completed.stdout,
        "native_error_reported": "*ERROR" in completed.stdout + completed.stderr,
    }
    if (untied / "analysis.dat").is_file():
        from worker.benchmark import dat_rows

        displacements = dat_rows((untied / "analysis.dat").read_text(), "displacements", 4)
        maximum = max(abs(v) for row in displacements for v in row[1:])
        results["untied"]["max_native_displacement_m"] = maximum
    # Gap remains rejected by the supported path. Only measure keyword side effects.
    gap_mesh, gap_catalog = build_fixture(output / "gap-geometry", gap_probe=True)
    gap_supports, gap_loads = setup_axial(gap_mesh, gap_catalog)
    gap_master, gap_slave = interface_refs(gap_catalog, gap=True)
    try:
        prepare_bond(gap_mesh, gap_catalog, gap_master, gap_slave)
    except UnresolvedBond as error:
        gap_failure = str(error)
    else:
        raise ValueError("Unapproved physical gap was accepted")
    raw = Bond(
        gap_mesh["revision"],
        mesh_hash(gap_mesh),
        gap_master,
        gap_slave,
        gap_catalog["bodies"][0]["id"],
        gap_catalog["bodies"][1]["id"],
        tuple(sorted((p["element"], p["face"]) for p in gap_mesh["boundary"][gap_master])),
        tuple(sorted({n for p in gap_mesh["boundary"][gap_slave] for n in p["nodes"]})),
        (),
    )
    gap_deck = generated_deck(
        gap_mesh, gap_supports, gap_loads, 210e9, 0.3, stress_coordinates=True
    )
    keywords = bond_keywords(raw).replace(
        "POSITION TOLERANCE=1.000000000000e-08", "POSITION TOLERANCE=1.000000000000e-04"
    )
    gap_deck = gap_deck.replace(
        "*MATERIAL,NAME=ISOTROPIC", keywords + "*MATERIAL,NAME=ISOTROPIC", 1
    )
    gap_audits = {}
    for mode in ("default_adjust", "adjust_no"):
        deck = gap_deck.replace(",ADJUST=NO", "") if mode == "default_adjust" else gap_deck
        gap_audits[mode] = coordinate_audit(output / mode, deck, gap_mesh)
    if (
        gap_audits["default_adjust"]["max_solver_adjustment_m"] < 0.9e-5
        or gap_audits["adjust_no"]["max_solver_adjustment_m"] > 1e-12
    ):
        raise ValueError("Native ADJUST geometry side-effect experiment failed")
    results["gap_keyword_audit"] = {
        "status": "DIAGNOSTIC ONLY; not B08 or approved gap physics",
        "gap_m": 1e-5,
        "preflight_rejection": gap_failure,
        **gap_audits,
    }
    (output / "result.json").write_text(json.dumps(results, indent=2) + "\n")
    return results
