"""Real native T004/B09 stress-provenance diagnostics and review artifacts."""

import hashlib
import json
import platform
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any

from worker.benchmark import solve
from worker.calculix.results import PARSER_VERSION, Mesh, parse_dat, parse_frd
from worker.deck import generated_deck
from worker.postprocess.fields import element_nodes
from worker.postprocess.tensors import COMPONENTS, principal, von_mises
from worker.runtime import NATIVE, ROOT, execute, sha256, verified_tool


def hand_mesh(two_materials: bool = False) -> Mesh:
    nodes = {
        1: (0.0, 0.0, 0.0),
        2: (1.0, 0.0, 0.0),
        3: (0.0, 1.0, 0.0),
        4: (0.0, 0.0, 1.0),
        5: (0.5, 0.0, 0.0),
        6: (0.5, 0.5, 0.0),
        7: (0.0, 0.5, 0.0),
        8: (0.0, 0.0, 0.5),
        9: (0.5, 0.0, 0.5),
        10: (0.0, 0.5, 0.5),
    }
    elements = {1: tuple(range(1, 11))}
    materials = {1: "UPPER"}
    if two_materials:
        nodes.update(
            {11: (0.0, 0.0, -1.0), 12: (0.0, 0.0, -0.5), 13: (0.0, 0.5, -0.5), 14: (0.5, 0.0, -0.5)}
        )
        elements[2] = (1, 3, 2, 11, 7, 6, 5, 12, 13, 14)
        materials[2] = "LOWER"
    revision = hashlib.sha256(
        json.dumps({"nodes": nodes, "elements": elements}, sort_keys=True).encode()
    ).hexdigest()
    mesh = Mesh(nodes, elements, {e: f"{revision}:b1" for e in elements}, materials, revision)
    mesh.validate()
    return mesh


def diagnostic_case(directory: Path, case: str) -> tuple[Mesh, dict[str, Any]]:
    if case not in ("B09", "hydrostatic", "pure-shear", "varying-shear"):
        raise ValueError("Unsupported stress diagnostic")
    directory.mkdir(parents=True, exist_ok=True)
    mesh = hand_mesh(case == "B09")
    supports = {}
    for n, (x, y, z) in mesh.nodes.items():
        if case == "B09":
            value = (0.001 * x, -0.0003 * y, -0.0003 * z)
        elif case == "hydrostatic":
            value = (0.001 * x, 0.001 * y, 0.001 * z)
        elif case == "pure-shear":
            value = (0.0004 * y, 0.0, 0.0)
        else:
            value = (0.001 * y * z, 0.0, 0.0)
        for axis, v in enumerate(value, 1):
            if (n, axis) != (2, 1):
                supports[n, axis] = v
    materials = {"UPPER": (210e9, 0.3)}
    if case == "B09":
        materials["LOWER"] = (70e9, 0.3)
    wire = asdict(mesh)
    deck = generated_deck(
        wire,
        supports,
        {},
        210e9,
        0.3,
        materials=materials,
        element_materials=mesh.materials,
        stress_coordinates=True,
    )
    solve(directory, deck)
    dat = parse_dat(directory / "analysis.dat", mesh)
    frd = parse_frd(directory / "analysis.frd", mesh)
    derived = element_nodes(dat["samples"], mesh)

    def encoded(point: Any) -> dict[str, Any]:
        record = asdict(point)
        record["von_mises_pa"] = von_mises(point.tensor_pa)
        record["principal_pa"] = principal(point.tensor_pa)
        return record

    payload = {
        "schema": 1,
        "case": case,
        "components": COMPONENTS,
        "frame": "global_cartesian",
        "units": {"length": "m", "stress": "Pa"},
        "mesh": wire,
        "parser": PARSER_VERSION,
        "integration_points": [encoded(p) for p in dat["samples"]],
        "element_nodes": [encoded(p) for p in derived],
        "solver_averaged_nodes": [encoded(p) for p in frd],
        "displacements_m": dat["displacements_m"],
        "source_sha256": {
            "dat": sha256(directory / "analysis.dat"),
            "frd": sha256(directory / "analysis.frd"),
            "deck": sha256(directory / "analysis.inp"),
        },
        "warnings": [
            "Development diagnostic; engineering-owner acceptance pending",
            "Element-node values are derived by linear extrapolation from raw DAT IP tensors",
            "FRD stress is solver-averaged and may smear material interfaces; diagnostic only",
        ],
    }
    (directory / "stress.json").write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    return mesh, payload


def run_b09(output: Path, development: bool = False) -> dict[str, Any]:
    manifest_path = ROOT / "tests/benchmarks/B09.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest["reviewer_signoff"].startswith("PENDING") and not development:
        raise ValueError("Engineering-owner B09 review pending; use DEVELOPMENT=1 for diagnostics")
    mesh, payload = diagnostic_case(output, "B09")
    tolerance = manifest["tolerances"]
    max_error = 0.0
    for point in payload["integration_points"] + payload["element_nodes"]:
        reference = manifest["expected_canonical_stress_pa"][point["material_id"]]
        for expected, actual in zip(reference, point["tensor_pa"], strict=True):
            max_error = max(max_error, abs(actual - expected))
            if abs(actual - expected) > max(
                tolerance["stress_absolute_pa"], tolerance["relative"] * abs(expected)
            ):
                raise ValueError("B09 material tensor tolerance failed")
    for n, p in mesh.nodes.items():
        expected = (0.001 * p[0], -0.0003 * p[1], -0.0003 * p[2])
        if any(
            abs(a - b) > tolerance["displacement_absolute_m"]
            for a, b in zip(payload["displacements_m"][n], expected, strict=True)
        ):
            raise ValueError("B09 displacement tolerance failed")
    shared = sorted(set(mesh.elements[1]) & set(mesh.elements[2]))
    for point in payload["solver_averaged_nodes"]:
        if point["node_id"] in shared:
            value = point["tensor_pa"][0]
            if (
                abs(value - manifest["expected_interface_frd_xx_pa"])
                > tolerance["relative"] * manifest["expected_interface_frd_xx_pa"]
            ):
                raise ValueError("B09 native FRD averaging demonstration failed")
    execute(
        [
            str(NATIVE / "venvs/post/bin/python"),
            "-I",
            str(ROOT / "services/worker/worker/postprocess/vtk_export.py"),
        ],
        output,
    )
    template = (ROOT / "services/worker/worker/postprocess/display.html").read_text()
    data = json.dumps(payload, allow_nan=False).replace("<", "\\u003c").replace("&", "\\u0026")
    (output / "stress.html").write_text(template.replace("__RESULT_DATA__", data))
    vtk = json.loads((output / "vtk-report.json").read_text())
    result = {
        "case": "B09",
        "status": "DEVELOPMENT PASS; owner review pending",
        "code_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "manifest_sha256": sha256(manifest_path),
        "reviewer_signoff": manifest["reviewer_signoff"],
        "ccx_version": "2.23",
        "ccx_sha256": sha256(verified_tool("ccx")),
        "parser": PARSER_VERSION,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "threads": 1,
        "mesh_sha256": mesh.identity(),
        "geometry_revision": mesh.revision,
        "source_sha256": payload["source_sha256"],
        "stress_json_sha256": sha256(output / "stress.json"),
        "max_tensor_error_pa": max_error,
        "shared_node_ids": shared,
        "raw_dat_xx_pa_by_material": {
            "UPPER": payload["integration_points"][0]["tensor_pa"][0],
            "LOWER": payload["integration_points"][4]["tensor_pa"][0],
        },
        "frd_shared_xx_pa": [
            p["tensor_pa"][0] for p in payload["solver_averaged_nodes"] if p["node_id"] in shared
        ],
        "vtk": vtk,
        "warnings": payload["warnings"],
    }
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
