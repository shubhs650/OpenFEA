"""Bounded, filesystem-isolated STEP parsing with no Docker/privilege requirement."""

import json
import os
import shutil
import signal
import struct
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from worker.resources import process_tree_rss
from worker.runtime import NATIVE, ROOT, native_environment, sha256, verified_tool


class ImportSandboxError(RuntimeError):
    pass


def process_filter() -> bytes:
    """x86_64 BPF: threads allowed; fork, namespace escape and mount/ptrace refused."""
    instructions = [
        (0x20, 0, 0, 4),
        (0x15, 1, 0, 0xC000003E),
        (0x06, 0, 0, 0x80000000),
        (0x20, 0, 0, 0),
        (0x15, 0, 1, 435),
        (0x06, 0, 0, 0x50000 | 38),
    ]
    for syscall in (57, 58, 272, 308, 165, 101):
        instructions.extend([(0x15, 0, 1, syscall), (0x06, 0, 0, 0x50000 | 1)])
    instructions.extend(
        [
            (0x15, 0, 3, 56),
            (0x20, 0, 0, 16),
            (0x45, 1, 0, 0x10000),
            (0x06, 0, 0, 0x50000 | 1),
            (0x06, 0, 0, 0x7FFF0000),
        ]
    )
    return b"".join(struct.pack("HBBI", *instruction) for instruction in instructions)


def scratch_usage(directory: Path) -> int:
    """Bound scanning itself; do not follow native-created symlinks or deep trees."""
    stack = [(directory, 0)]
    size, count = 0, 0
    while stack:
        parent, depth = stack.pop()
        if depth > 4:
            return 193 * 1024**2
        with os.scandir(parent) as entries:
            for entry in entries:
                count += 1
                if count > 128:
                    return 193 * 1024**2
                try:
                    size += entry.stat(follow_symlinks=False).st_size
                    if entry.is_dir(follow_symlinks=False):
                        stack.append((Path(entry.path), depth + 1))
                except FileNotFoundError:
                    continue
    return size


def inspect_step(source: Path, output: Path, unit: str | None = None) -> dict[str, Any]:
    bubblewrap = shutil.which("bwrap")
    if bubblewrap is None:
        raise ImportSandboxError("Bubblewrap is required for isolated STEP imports")
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    if shutil.disk_usage(output).free < 1024**3:
        raise ImportSandboxError("Less than 1 GiB scratch reserve; import was not started")
    (output / "tmp").mkdir()
    python = NATIVE / "venvs/cad/bin/python"
    if not python.is_file():
        raise ImportSandboxError("Pinned CAD environment is unavailable")
    command = [
        bubblewrap,
        "--unshare-all",
        "--new-session",
        "--die-with-parent",
        "--cap-drop",
        "ALL",
        "--ro-bind",
        "/usr",
        "/usr",
        "--ro-bind",
        "/lib",
        "/lib",
        "--ro-bind",
        "/lib64",
        "/lib64",
        "--dev",
        "/dev",
        "--proc",
        "/proc",
        "--ro-bind",
        str(Path(sys.base_prefix).resolve()),
        str(Path(sys.base_prefix).resolve()),
        "--ro-bind",
        str(python.parent.parent),
        str(python.parent.parent),
        "--ro-bind",
        str(verified_tool("netdeny")),
        "/limits",
        "--ro-bind",
        str(ROOT / "services/worker/worker/geometry_native/import_step.py"),
        "/import.py",
        "--dir",
        "/work",
        "--ro-bind",
        str(source),
        "/work/source.step",
        "--bind",
        str(output),
        "/work/out",
        "--symlink",
        "/work/out/tmp",
        "/tmp",
        "--chdir",
        "/work/out",
        "/limits",
        str(python),
        "-I",
        "/import.py",
        unit or "auto",
    ]
    if Path("/etc/ld.so.cache").is_file():
        command[1:1] = ["--ro-bind", "/etc/ld.so.cache", "/etc/ld.so.cache"]
    filter_path = output.parent / "process-filter.bpf"
    filter_path.write_bytes(process_filter())
    started = time.monotonic()
    with (output / "native.log").open("wb") as log, filter_path.open("rb") as filter_file:
        command[1:1] = ["--seccomp", str(filter_file.fileno())]
        process = subprocess.Popen(
            command,
            env=native_environment(Path("/work/out")),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            close_fds=True,
            pass_fds=(filter_file.fileno(),),
            start_new_session=True,
        )
        stopped: str | None = None
        peak = 0
        try:
            while process.poll() is None:
                peak = max(peak, process_tree_rss(process.pid))
                disk = scratch_usage(output)
                if disk > 192 * 1024**2 or peak > 1536 * 1024**2:
                    stopped = "Import exceeded the memory/output resource budget"
                    break
                if time.monotonic() - started > 60:
                    stopped = "Import exceeded the 60 second processing limit"
                    break
                time.sleep(0.05)
            if stopped:
                os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        finally:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
    if scratch_usage(output) > 192 * 1024**2:
        stopped = "Import exceeded the output resource budget"
    if stopped or process.returncode != 0:
        raise ImportSandboxError(stopped or "Isolated CAD import failed; inspect the source STEP")
    descriptor = output / "inspection.json"
    if (
        descriptor.is_symlink()
        or not descriptor.is_file()
        or descriptor.stat().st_size > 2 * 1024**2
    ):
        raise ImportSandboxError("CAD returned an invalid inspection record")
    result: dict[str, Any] = json.loads(descriptor.read_text())
    if result.get("status") == "ready":
        result["metadata"]["validation"]["runtime"] = {
            "bubblewrap_sha256": sha256(Path(bubblewrap)),
            "bubblewrap_version": subprocess.check_output(
                [bubblewrap, "--version"], text=True
            ).strip(),
            "netdeny_sha256": sha256(verified_tool("netdeny")),
            "cad_python_sha256": sha256(python.resolve()),
            "cad_binding_sha256": sha256(
                next((python.parent.parent / "lib/python3.12/site-packages/OCP").glob("*.so"))
            ),
            "cad_lock_sha256": sha256(ROOT / "services/worker/environments/cad/uv.lock"),
            "process_filter_sha256": sha256(filter_path),
            "worker_sha256": sha256(ROOT / "services/worker/worker/geometry_native/import_step.py"),
            "wall_seconds": time.monotonic() - started,
            "sampled_peak_rss_bytes": peak,
            "wall_limit_seconds": 60,
            "rss_limit_mib": 1536,
            "output_limit_mib": 192,
            "filesystem_isolated": True,
            "network_disabled": True,
        }
    return result
