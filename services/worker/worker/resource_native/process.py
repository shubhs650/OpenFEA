"""Bounded preparation/postprocessing for real graduated B01 diagnostic workloads."""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from worker.benchmark import dat_rows
from worker.deck import generated_deck
from worker.runtime import ROOT, sha256

mesh = json.loads(Path("mesh.json").read_text())
manifest = json.loads((ROOT / "tests/benchmarks/B01.json").read_text())
gradient = manifest["displacement_gradient"]
nodes = {int(n): tuple(p) for n, p in mesh["nodes"].items()}
boundary = [face for values in mesh["boundary"].values() for face in values]
expected = {
    n: tuple(sum(gradient[k][j] * p[j] for j in range(3)) for k in range(3))
    for n, p in nodes.items()
}
boundary_nodes = {n for face in boundary for n in face["nodes"]}
equations = 3 * (len(nodes) - len(boundary_nodes))
if equations <= 0:
    raise ValueError("Resource patch must contain free interior equations")
if sys.argv[1] == "prepare":
    # An admission ceiling, not a RAM estimator. No automatic coarsening/retry.
    capacity = json.loads((ROOT / "tests/benchmarks/T006.json").read_text())
    if (
        len(mesh["elements"]) > capacity["solve_admission_elements"]
        or equations > capacity["solve_admission_free_equations"]
    ):
        raise ValueError("Development solve admission cap exceeded; explicitly choose coarser mesh")
    supports = {(n, k + 1): expected[n][k] for n in boundary_nodes for k in range(3)}
    material = manifest["material"]
    Path("analysis.inp").write_text(
        generated_deck(mesh, supports, {}, material["E_pa"], material["nu"])
    )
elif sys.argv[1] == "post":
    log = Path("solve.log").read_text()
    reported = re.search(r"number of equations\s*:?\s*(\d+)", log, re.I)
    if (
        "*ERROR" in log
        or "Job finished" not in log
        or not reported
        or int(reported[1]) != equations
    ):
        raise ValueError("Invalid native solve transcript/equation count")
    raw = Path("analysis.dat").read_text()
    urows = dat_rows(raw, "displacements", 4)
    srows = dat_rows(raw, "stresses", 8)
    displacement = {int(r[0]): r[1:] for r in urows}
    if len(urows) != len(nodes) or set(displacement) != set(nodes):
        raise ValueError("Missing/duplicate displacements")
    if len(srows) != 4 * len(mesh["elements"]) or {(int(r[0]), int(r[1])) for r in srows} != {
        (int(e), ip) for e in mesh["elements"] for ip in range(1, 5)
    }:
        raise ValueError("Missing/duplicate stress points")
    tolerance = manifest["tolerances"]
    for n, value in displacement.items():
        for k in range(3):
            if abs(value[k] - expected[n][k]) > max(
                tolerance["displacement_absolute_m"], tolerance["relative"] * abs(expected[n][k])
            ):
                raise ValueError("Frozen B01 displacement tolerance failed")
    for row in srows:
        for k, reference in enumerate(manifest["expected_stress_ccx_pa"]):
            if abs(row[k + 2] - reference) > max(
                tolerance["stress_absolute_pa"], tolerance["relative"] * abs(reference)
            ):
                raise ValueError("Frozen B01 stress tolerance failed")
    # Piecewise constant IP1 per exterior element, deliberately labelled, no smoothing.
    stress = {int(r[0]): r[2] for r in srows if r[1] == 1}
    vertices = []
    for face in boundary:
        ns = face["nodes"]
        for triangle in ((0, 3, 5), (3, 1, 4), (5, 4, 2), (3, 4, 5)):
            for index in triangle:
                node = ns[index]
                vertices.extend([*nodes[node], displacement[node][0], stress[face["element"]]])
    payload = {
        "vertices": vertices,
        "volume_elements": len(mesh["elements"]),
        "surface_triangles": len(vertices) // 15,
        "equations": equations,
        "mesh_sha256": sha256(Path("mesh.json")),
        "dat_sha256": sha256(Path("analysis.dat")),
        "ux_error_m": max(
            abs(displacement[n][k] - expected[n][k]) for n in nodes for k in range(3)
        ),
        "stress_error_pa": max(
            abs(r[k + 2] - manifest["expected_stress_ccx_pa"][k]) for r in srows for k in range(6)
        ),
    }
    Path("display.json").write_text(json.dumps(payload) + "\n")
    from worker.resource_viewer import write_viewer

    write_viewer(Path("display.html"), payload)
else:
    raise ValueError("Unknown diagnostic stage")
