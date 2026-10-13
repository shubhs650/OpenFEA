"""T006 allowlisted real cleanup/mesh/solve experiments, development evidence only."""

import argparse
import json
import platform
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from worker.cleanup import cleanup_fixture, cleanup_preview
from worker.resources import measured_native
from worker.runtime import NATIVE, ROOT, sha256, synthetic_geometry, verified_tool


def cgroup_value(name: str) -> str | None:
    """Hosted runners may expose a different cgroup layout or no cgroup files."""
    try:
        return (Path("/sys/fs/cgroup") / name).read_text().strip()
    except OSError:
        return None


def run_workloads(
    output: Path, manifest: dict[str, Any], limits: dict[str, Any], result: dict[str, Any]
) -> bool:
    """Run the declared ladder once; persist every stop before returning failure."""
    runs: list[dict[str, Any]] = []
    result["runs"] = runs

    def snapshot() -> None:
        (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")

    def stop_ladder(index: int, stage: str) -> None:
        result["status"] = f"DEVELOPMENT FAILED; {stage} stopped the workload ladder"
        for pending in manifest["workloads"][index + 1 :]:
            runs.append(
                {
                    "target_elements": pending["target_elements"],
                    "mesh_size_m": pending["mesh_size_m"],
                    "status": "NOT RUN; previous native/resource stage failed",
                }
            )
        snapshot()

    def stage_report(
        command: list[str] | Callable[[], list[str]], directory: Path, stage: str
    ) -> dict[str, Any]:
        try:
            return measured_native(
                command() if callable(command) else command, directory, stage, **limits
            )
        except Exception as error:
            # Resource admission and native launch can fail before a child returns a report.
            return {
                "status": "stage_error",
                "error_type": type(error).__name__,
                "error": str(error),
            }

    # Fixed settings before measurement; actual counts are reported, not called exact targets.
    for index, workload in enumerate(manifest["workloads"]):
        target, size = workload["target_elements"], workload["mesh_size_m"]
        directory = output / f"mesh-{target}"
        directory.mkdir()
        run: dict[str, Any] = {"target_elements": target, "mesh_size_m": size}
        runs.append(run)
        try:
            synthetic_geometry(directory, "box")
        except Exception as error:
            run["geometry"] = {
                "status": "stage_error",
                "error_type": type(error).__name__,
                "error": str(error),
            }
            stop_ladder(index, "geometry")
            return False
        run["mesh"] = stage_report(
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
        )
        snapshot()
        if run["mesh"]["status"] != "completed":
            run["remaining_stages"] = "not run; resource/native stop"
            run["artifacts"] = {
                p.name: {"bytes": p.stat().st_size, "sha256": sha256(p)}
                for p in directory.iterdir()
                if p.is_file()
            }
            stop_ladder(index, "mesh")
            return False
        try:
            run.update(json.loads((directory / "mesh-summary.json").read_text()))
        except (OSError, ValueError, TypeError) as error:
            run["mesh"] = {
                **run["mesh"],
                "status": "artifact_validation_failed",
                "error": str(error),
            }
            run["remaining_stages"] = "not run; invalid mesh artifact"
            stop_ladder(index, "mesh")
            return False
        if (
            run["elements"] > manifest["solve_admission_elements"]
            or run["free_equations"] > manifest["solve_admission_free_equations"]
        ):
            run["remaining_stages"] = "not run; explicit 30k element/120k free-equation solve cap"
            run["coarsening_proposal"] = {
                "mesh_size_m": manifest["workloads"][0]["mesh_size_m"],
                "requires_explicit_request": True,
                "message": "Request a fresh coarser mesh; prior mesh/results are invalidated",
            }
            snapshot()
            continue
        script = str(ROOT / "services/worker/worker/resource_native/process.py")
        failed_stage = None
        for stage, command in (
            ("prepare", [str(ROOT / ".venv/bin/python"), "-I", script, "prepare"]),
            ("solve", lambda: [str(verified_tool("ccx")), "-i", "analysis"]),
            ("post", [str(ROOT / ".venv/bin/python"), "-I", script, "post"]),
        ):
            run[stage] = stage_report(command, directory, stage)
            snapshot()
            if run[stage]["status"] != "completed":
                run["remaining_stages"] = "not run; resource/native stop"
                failed_stage = stage
                break
        if failed_stage is None:
            try:
                display = json.loads((directory / "display.json").read_text())
                del display["vertices"]
                run["fields"] = display
            except (OSError, ValueError, TypeError, KeyError) as error:
                run["post"] = {
                    **run["post"],
                    "status": "artifact_validation_failed",
                    "error": str(error),
                }
                failed_stage = "post"
        run["artifacts"] = {
            p.name: {"bytes": p.stat().st_size, "sha256": sha256(p)}
            for p in directory.iterdir()
            if p.is_file()
        }
        if failed_stage is not None:
            run.setdefault("remaining_stages", "not run; invalid native artifact")
            stop_ladder(index, failed_stage)
            return False
        snapshot()
    return True


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
        "cpu_quota": cgroup_value("cpu.max"),
        "memory_limit": cgroup_value("memory.max"),
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
    completed = True
    if args.meshes:
        completed = run_workloads(output, manifest, limits, result)
    else:
        result["runs"] = []
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if completed else 2


if __name__ == "__main__":
    raise SystemExit(main())
