"""Run only a server-generated input in isolated CCX 2.23; validate raw outputs."""

import json
import re
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any

from worker.calculix.results import PARSER_VERSION, Mesh, parse_dat, parse_frd
from worker.local_process import NativeControl, supervise
from worker.runtime import NATIVE, verified_tool
from worker.step_import import ImportSandboxError


def solve_snapshot(input_path: Path, output: Path, control: NativeControl) -> dict[str, Any]:
    bwrap = shutil.which("bwrap")
    if bwrap is None:
        raise ImportSandboxError("Bubblewrap is required for local solve")
    solver = verified_tool("ccx")
    output.mkdir(mode=0o700)
    if shutil.disk_usage(output).free < 1024**3:
        raise ImportSandboxError("Less than 1 GiB scratch reserve")
    (output / "tmp").mkdir()
    command = [bwrap, "--unshare-all", "--new-session", "--die-with-parent", "--cap-drop", "ALL"]
    for path in ("/usr", "/lib", "/lib64", str(NATIVE / "bin"), str(NATIVE / "lib")):
        command += ["--ro-bind", path, path]
    if Path("/etc/ld.so.cache").is_file():
        command += ["--ro-bind", "/etc/ld.so.cache", "/etc/ld.so.cache"]
    command += [
        "--dev",
        "/dev",
        "--proc",
        "/proc",
        "--dir",
        "/work",
        "--bind",
        str(output),
        "/work/out",
        "--symlink",
        "/work/out/tmp",
        "/tmp",
        "--ro-bind",
        str(input_path),
        "/work/out/analysis.inp",
        "--chdir",
        "/work/out",
        str(verified_tool("netdeny")),
        str(solver),
        "-i",
        "analysis",
    ]
    return supervise(command, output, control, "solver.log")


def validate_outputs(
    output: Path,
    raw_mesh: dict[str, Any],
    materials: dict[str, str],
    execution: dict[str, Any],
    input_hash: str,
    deck_hash: str,
    mesh_hash: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    log = (output / "solver.log").read_text(errors="replace")
    if execution["returncode"] != 0 or "Job finished" not in log:
        raise ValueError("Solver did not complete")
    if re.search(
        r"\*ERROR|singular|zero pivot|negative pivot|not positive definite|no convergence|\bnan\b",
        log,
        re.I,
    ):
        raise ValueError("Solver reported invalid numerical execution")
    equations = re.search(r"number of equations\s*+:?\s*+(\d+)", log, re.I)
    if equations is None or int(equations[1]) <= 0:
        raise ValueError("No actual free equations were solved")
    mesh = Mesh(
        {
            int(n): (
                float(f"{point[0]:.12e}"),
                float(f"{point[1]:.12e}"),
                float(f"{point[2]:.12e}"),
            )
            for n, point in raw_mesh["nodes"].items()
        },
        {int(e): tuple(ns) for e, ns in raw_mesh["elements"].items()},
        {int(e): body for e, body in raw_mesh["owners"].items()},
        {int(e): materials[body] for e, body in raw_mesh["owners"].items()},
        raw_mesh["revision"],
    )
    dat = parse_dat(output / "analysis.dat", mesh)
    frd = parse_frd(output / "analysis.frd", mesh)
    samples = [asdict(sample) for sample in dat.pop("samples")]
    warnings = [line.strip()[:200] for line in log.splitlines() if "*WARNING" in line.upper()]
    result = {
        "schema_version": 1,
        "input_sha256": input_hash,
        "deck_sha256": deck_hash,
        "mesh_sha256": mesh_hash,
        "result_mesh_sha256": mesh.identity(),
        "parser": PARSER_VERSION,
        "units": {"displacement": "m", "stress": "Pa", "force": "N"},
        "frame": "global_cartesian",
        "stress_location": "integration_point",
        "components": ["xx", "yy", "zz", "xy", "yz", "zx"],
        "dat": dat,
        "integration_points": samples,
        "frd_location": "solver_averaged_node",
        "frd_warning": "Native extrapolated/averaged stress may cross material/body boundaries; "
        "diagnostic only",
        "frd": [asdict(p) for p in frd],
        "warnings": warnings,
    }
    summary = {
        "nodes": len(mesh.nodes),
        "elements": len(mesh.elements),
        "free_equations": int(equations[1]),
        "stress_samples": len(samples),
        "parser": PARSER_VERSION,
        "warnings": warnings,
        "execution": execution,
        "validation": "Raw DAT/FRD coverage, geometry, ownership, frame and finite values checked; "
        "no convergence claim",
    }
    # Ensure canonical serialized values remain finite, including derived metadata.
    json.dumps(result, allow_nan=False)
    return result, summary
