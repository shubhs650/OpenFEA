"""Bounded preview mesh export, isolated from project storage and the network."""

import hashlib
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from worker.local_process import NativeControl, NativeStop, supervise
from worker.runtime import NATIVE, ROOT, verified_tool
from worker.step_import import ImportSandboxError, scratch_usage


def _mesh_attempt(
    inputs: Path, output: Path, sizes: list[float], *, control: NativeControl | None = None
) -> dict[str, Any]:
    bwrap = shutil.which("bwrap")
    python = NATIVE / "venvs/mesh/bin/python"
    if bwrap is None or not python.is_file():
        raise ImportSandboxError("Pinned Gmsh and Bubblewrap are required for deck export")
    output.mkdir(mode=0o700)
    if shutil.disk_usage(output).free < 1024**3:
        raise ImportSandboxError("Less than 1 GiB scratch reserve; export was not started")
    (output / "tmp").mkdir()
    command = [bwrap, "--unshare-all", "--new-session", "--die-with-parent", "--cap-drop", "ALL"]
    for path in (
        "/usr",
        "/lib",
        "/lib64",
        str(Path(sys.base_prefix).resolve()),
        str(python.parent.parent),
        str(ROOT / "services/worker"),
    ):
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
    ]
    for input_path in sorted(inputs.iterdir()):
        command += ["--ro-bind", str(input_path), "/work/out/" + input_path.name]
    command += ["--ro-bind", str(verified_tool("netdeny")), "/limits", "--chdir", "/work/out"]
    command += [
        "/limits",
        str(python),
        "-I",
        str(ROOT / "services/worker/worker/meshing_native/build.py"),
        str(min(sizes)),
        "0",
        json.dumps(sizes),
        "3000",
    ]
    execution = supervise(command, output, control, "native.log")
    status_path = output / "mesh-status.json"
    if (
        status_path.is_file()
        and not status_path.is_symlink()
        and status_path.stat().st_size <= 2 * 1024**2
    ):
        status = json.loads(status_path.read_bytes())
    else:
        status = {
            "status": "native_generation" if execution["returncode"] != 0 else "output_validation"
        }
    if not isinstance(status, dict):
        raise MeshFailure("output_validation", "Invalid native stage record", {})
    if status.get("status") != "passed" or execution["returncode"] != 0:
        raise MeshFailure(
            str(status.get("status", "output_validation")), "Native mesh did not pass", status
        )
    mesh_path = output / "mesh.json"
    if mesh_path.is_symlink() or not mesh_path.is_file() or mesh_path.stat().st_size > 32 * 1024**2:
        raise MeshFailure("output_validation", "Invalid mesh output", {})
    value: dict[str, Any] = json.loads(mesh_path.read_bytes())
    if not isinstance(value, dict):
        raise MeshFailure("output_validation", "Invalid mesh record", {})
    return value


PROFILES = ("Delaunay", "Frontal", "Delaunay + Netgen optimization")


class MeshFailure(ImportSandboxError):
    def __init__(self, reason: str, message: str, summary: dict[str, Any]) -> None:
        self.reason, self.summary = reason, summary
        super().__init__(message)


def mesh_snapshot(
    inputs: Path,
    output: Path,
    sizes: list[float],
    *,
    control: NativeControl | None = None,
    face_sizes: dict[str, float] | None = None,
    curvature_elements: int = 16,
    recovery_enabled: bool = False,
) -> dict[str, Any]:
    output.mkdir(mode=0o700)
    settings = {
        "body_sizes_m": sizes,
        "face_sizes_m": face_sizes or {},
        "curvature_elements": curvature_elements,
    }
    records: list[dict[str, Any]] = []
    allowed = 3 if recovery_enabled else 1
    started = time.monotonic()
    last_failure = MeshFailure("native_generation", "Meshing failed", {})
    for index in range(allowed):
        if control and control.cancel():
            raise NativeStop("cancelled")
        if time.monotonic() - started > 180 or scratch_usage(output) > 192 * 1024**2:
            raise NativeStop("resource_exceeded")
        if control and control.mesh_attempt:
            control.mesh_attempt(index + 1, PROFILES[index], allowed)
        config = {**settings, "profile": index}
        (inputs / "mesh-controls.json").write_text(json.dumps(config, allow_nan=False))
        attempt = output / f"attempt-{index + 1}"
        value = None
        stopped: NativeStop | None = None
        try:
            value = _mesh_attempt(inputs, attempt, sizes, control=control)
            if not isinstance(value.get("quality"), dict):
                value = None
                raise ValueError("Missing native mesh quality record")
            record = {
                "status": "passed",
                "quality": {k: v for k, v in value["quality"].items() if k != "cells"},
            }
        except MeshFailure as failure:
            last_failure = failure
            record = failure.summary | {"status": failure.reason}
        except (ValueError, KeyError, TypeError, OSError):
            last_failure = MeshFailure("output_validation", "Native output failed verification", {})
            record = {"status": "output_validation"}
        except NativeStop as failure:
            stopped = failure
            record = {"status": failure.reason}
        record.update(number=index + 1, profile=PROFILES[index], settings=config)
        for name, alias in (
            ("native.log", f"mesh-attempt-{index + 1}.log"),
            ("resources.json", f"mesh-attempt-{index + 1}-resources.json"),
        ):
            path = attempt / name
            if path.is_file() and not path.is_symlink() and path.stat().st_size <= 32 * 1024**2:
                raw = path.read_bytes()
                (output / alias).write_bytes(raw)
                record[alias + "_sha256"] = hashlib.sha256(raw).hexdigest()
                (output / name).write_bytes(raw)
        candidate = attempt / "mesh.json"
        if (
            candidate.is_file()
            and not candidate.is_symlink()
            and candidate.stat().st_size <= 32 * 1024**2
        ):
            (output / "mesh.json").write_bytes(candidate.read_bytes())
        records.append(record)
        report = {"mesh_attempts": records, "max_mesh_attempts": allowed, "sizing_unchanged": True}
        (output / "recovery.json").write_text(json.dumps(report, allow_nan=False) + "\n")
        if stopped is not None:
            raise stopped
        if scratch_usage(output) > 192 * 1024**2:
            raise NativeStop("resource_exceeded")
        if value is not None:
            return value
        if last_failure.reason not in ("quality_failed", "native_generation"):
            break
    raise MeshFailure(
        last_failure.reason,
        f"Mesh failed after {len(records)} of {allowed} permitted attempts",
        report,
    )
