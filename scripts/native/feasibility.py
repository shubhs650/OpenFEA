"""T006 allowlisted real cleanup/mesh/solve experiments, development evidence only."""

import argparse
import json
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from worker.cleanup import cleanup_fixture, cleanup_preview
from worker.resources import measured_native
from worker.runtime import NATIVE, ROOT, sha256, synthetic_geometry, verified_tool


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".local/native/validation/T006/run")
    parser.add_argument("--meshes", action="store_true", help="Run graduated workloads explicitly")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error("Output must be fresh; preserve prior measurements")
    output.mkdir(parents=True)
    manifest_path = ROOT / "tests/benchmarks/T006.json"
    manifest = json.loads(manifest_path.read_text())
    budget = manifest["budget"]
    limits = {
        "rss_mib": budget["rss_mib"],
        "disk_mib": budget["scratch_mib"],
        "timeout": budget["wall_seconds"],
    }
    result: dict[str, object] = {
        "code_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "utc_started": datetime.now(UTC).isoformat(),
        "platform": platform.platform(),
        "cpu_quota": Path("/sys/fs/cgroup/cpu.max").read_text().strip(),
        "memory_limit": Path("/sys/fs/cgroup/memory.max").read_text().strip(),
        "native_build_sha256": sha256(NATIVE / "build.json"),
        "ccx_sha256": sha256(verified_tool("ccx")),
        "threads": 1,
        "status": "DEVELOPMENT ONLY; laptop/GPU/engineering acceptance pending",
        "manifest_sha256": sha256(manifest_path),
    }
    edits = []
    for kind in ("hole", "fillet"):
        source = output / kind
        catalog = cleanup_fixture(source, kind)
        face = next(f["id"] for f in catalog["faces"] if f["surface"] == "cylinder")
        edits.append(cleanup_preview(source, output / (kind + "-preview"), face))
    result["edits"] = edits
    runs: list[dict[str, Any]] = []
    result["runs"] = runs
    # Fixed settings before measurement; actual counts are reported, not called exact targets.
    if args.meshes:
        for workload in manifest["workloads"]:
            target, size = workload["target_elements"], workload["mesh_size_m"]
            directory = output / f"mesh-{target}"
            directory.mkdir()
            synthetic_geometry(directory, "box")
            run: dict[str, Any] = {"target_elements": target, "mesh_size_m": size}
            runs.append(run)
            run["mesh"] = measured_native(
                [
                    str(NATIVE / "venvs/mesh/bin/python"),
                    "-I",
                    str(ROOT / "services/worker/worker/meshing_native/build.py"),
                    str(size),
                    "0",
                    "null",
                ],
                directory,
                "mesh",
                **limits,
            )
            if run["mesh"]["status"] != "completed":
                run["remaining_stages"] = "not run; resource/native stop"
                run["artifacts"] = {
                    p.name: {"bytes": p.stat().st_size, "sha256": sha256(p)}
                    for p in directory.iterdir()
                    if p.is_file()
                }
                break
            run.update(json.loads((directory / "mesh-summary.json").read_text()))
            if (
                run["elements"] > manifest["solve_admission_elements"]
                or run["free_equations"] > manifest["solve_admission_free_equations"]
            ):
                run["remaining_stages"] = (
                    "not run; explicit 30k element/120k free-equation solve cap"
                )
                run["coarsening_proposal"] = {
                    "mesh_size_m": manifest["workloads"][0]["mesh_size_m"],
                    "requires_explicit_request": True,
                    "message": "Request a fresh coarser mesh; prior mesh/results are invalidated",
                }
                continue
            script = str(ROOT / "services/worker/worker/resource_native/process.py")
            for stage, command in (
                ("prepare", [str(ROOT / ".venv/bin/python"), "-I", script, "prepare"]),
                ("solve", [str(verified_tool("ccx")), "-i", "analysis"]),
                ("post", [str(ROOT / ".venv/bin/python"), "-I", script, "post"]),
            ):
                measured = measured_native(command, directory, stage, **limits)
                run[stage] = measured
                if measured["status"] != "completed":
                    run["remaining_stages"] = "not run; resource/native stop"
                    break
            if (directory / "display.json").exists():
                display = json.loads((directory / "display.json").read_text())
                del display["vertices"]
                run["fields"] = display
            run["artifacts"] = {
                p.name: {"bytes": p.stat().st_size, "sha256": sha256(p)}
                for p in directory.iterdir()
                if p.is_file()
            }
            (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return (
        2
        if any(
            isinstance(run.get(stage), dict) and run[stage]["status"] != "completed"
            for run in runs
            for stage in ("mesh", "prepare", "solve", "post")
        )
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
