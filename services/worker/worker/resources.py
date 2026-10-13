"""Measured native diagnostic runner with an RSS/disk watchdog, never a capacity promise."""

import json
import os
import re
import shutil
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

from worker.runtime import ROOT, native_environment, verified_tool


def process_tree_rss(pid: int) -> int:
    """Linux snapshot sum over the owned tree; shared pages may be counted twice."""
    try:
        status = Path(f"/proc/{pid}/status").read_text()
        match = re.search(r"^VmRSS:\s+(\d+) kB", status, re.M)
        rss = int(match[1]) * 1024 if match else 0
    except (FileNotFoundError, ProcessLookupError):
        return 0
    try:
        children = Path(f"/proc/{pid}/task/{pid}/children").read_text().split()
    except FileNotFoundError:
        # Some cloud kernels omit task/children. Preserve RSS and discover PPIDs instead.
        children = []
        for path in Path("/proc").iterdir():
            if not path.name.isdigit():
                continue
            try:
                fields = (path / "stat").read_text().rsplit(")", 1)[1].split()
                if int(fields[1]) == pid:
                    children.append(path.name)
            except (FileNotFoundError, ProcessLookupError):
                continue
    return rss + sum(process_tree_rss(int(child)) for child in children)


def measured_native(
    command: list[str],
    directory: Path,
    name: str,
    *,
    rss_mib: int = 1536,
    disk_mib: int = 256,
    timeout: float = 90,
) -> dict[str, Any]:
    if rss_mib < 128 or disk_mib < 1 or timeout <= 0 or not re.fullmatch(r"[a-z-]+", name):
        raise ValueError("Invalid diagnostic budget/name")
    directory.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(directory).free < 1024**3:
        raise RuntimeError("Less than 1 GiB scratch reserve; workload not started")
    started = time.monotonic()
    process = subprocess.Popen(
        [
            str(verified_tool("netdeny")),
            str(ROOT / ".venv/bin/python"),
            "-I",
            str(ROOT / "services/worker/worker/resource_native/measure.py"),
            f"{name}-usage.json",
            *command,
        ],
        cwd=directory,
        env=native_environment(directory),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        close_fds=True,
        start_new_session=True,
    )
    peak = 0
    disk_peak = 0
    stopped: str | None = None
    try:
        while True:
            peak = max(peak, process_tree_rss(process.pid))
            disk_peak = max(
                disk_peak, sum(p.stat().st_size for p in directory.rglob("*") if p.is_file())
            )
            if peak > rss_mib * 1024**2:
                stopped = "rss_budget_exceeded"
            elif disk_peak > disk_mib * 1024**2:
                stopped = "disk_budget_exceeded"
            elif time.monotonic() - started > timeout:
                stopped = "wall_budget_exceeded"
            if stopped:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    stdout, stderr = process.communicate(timeout=1)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    stdout, stderr = process.communicate()
                break
            try:
                stdout, stderr = process.communicate(timeout=0.05)
                break
            except subprocess.TimeoutExpired:
                continue
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    transcript = stdout + stderr
    (directory / f"{name}.log").write_text(transcript)
    timing = directory / f"{name}-usage.json"
    usage = json.loads(timing.read_text()) if timing.exists() else {}
    report = {
        "status": stopped or ("completed" if process.returncode == 0 else "native_failed"),
        "returncode": process.returncode,
        "wall_seconds": time.monotonic() - started,
        "sampled_tree_peak_rss_bytes": peak,
        "sampled_disk_peak_bytes": disk_peak,
        "native_maxrss_bytes": usage.get("maxrss_bytes"),
        "native_user_seconds": usage.get("user_seconds"),
        "native_system_seconds": usage.get("system_seconds"),
        "rss_budget_mib": rss_mib,
        "disk_budget_mib": disk_mib,
        "sampling_seconds": 0.05,
        "command": command,
    }
    (directory / f"{name}-resources.json").write_text(json.dumps(report, indent=2) + "\n")
    return report
