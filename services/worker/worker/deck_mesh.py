"""Bounded preview mesh export, isolated from project storage and the network."""

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from worker.resources import process_tree_rss
from worker.runtime import NATIVE, ROOT, native_environment, verified_tool
from worker.step_import import ImportSandboxError, process_filter, scratch_usage


def mesh_snapshot(inputs: Path, output: Path, sizes: list[float]) -> dict[str, Any]:
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
    filter_path = output.parent / "process-filter.bpf"
    filter_path.write_bytes(process_filter())
    started = time.monotonic()
    with filter_path.open("rb") as filter_file, (output / "native.log").open("wb") as log:
        command += [
            "--seccomp",
            str(filter_file.fileno()),
            "/limits",
            str(python),
            "-I",
            str(ROOT / "services/worker/worker/meshing_native/build.py"),
            str(min(sizes)),
            "0",
            json.dumps(sizes),
            "3000",
        ]
        process = subprocess.Popen(
            command,
            env=native_environment(Path("/work/out")),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            pass_fds=(filter_file.fileno(),),
            close_fds=True,
            start_new_session=True,
        )
        stopped = False
        try:
            while process.poll() is None:
                if (
                    time.monotonic() - started > 60
                    or process_tree_rss(process.pid) > 1536 * 1024**2
                    or scratch_usage(output) > 192 * 1024**2
                ):
                    stopped = True
                    break
                time.sleep(0.05)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    if stopped or process.returncode or scratch_usage(output) > 192 * 1024**2:
        raise ImportSandboxError("Isolated mesh export failed or exceeded its resource budget")
    mesh_path = output / "mesh.json"
    if mesh_path.is_symlink() or not mesh_path.is_file() or mesh_path.stat().st_size > 32 * 1024**2:
        raise ImportSandboxError("Invalid mesh output")
    result: dict[str, Any] = json.loads(mesh_path.read_bytes())
    return result
