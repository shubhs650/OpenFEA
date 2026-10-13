"""Cancellable bounded native-process supervision with an inherited execution lock."""

import json
import os
import signal
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from worker.resources import process_tree_rss
from worker.runtime import native_environment
from worker.step_import import process_filter, scratch_usage


class NativeStop(RuntimeError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def process_identity(pid: int) -> str | None:
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        if fields[0] == "Z":
            return None
        return Path("/proc/sys/kernel/random/boot_id").read_text().strip() + ":" + fields[19]
    except (FileNotFoundError, ProcessLookupError):
        return None


@dataclass
class NativeControl:
    cancel: Callable[[], bool]
    started: Callable[[int, str], None]
    lease_fd: int
    mesh_attempt: Callable[[int, str, int], None] | None = None


def supervise(
    command: list[str],
    output: Path,
    control: NativeControl | None,
    log_name: str,
    *,
    scratch_root: Path | None = None,
) -> dict[str, float | int | str]:
    """All callers supply a Bubblewrap command ending in a verified native launcher."""
    filter_path = output.parent / "process-filter.bpf"
    filter_path.write_bytes(process_filter())
    started = time.monotonic()
    scratch_root = scratch_root or output
    peak = disk_peak = 0
    reason: str | None = None
    with filter_path.open("rb") as filter_file, (output / log_name).open("wb") as log:
        fds: tuple[int, ...] = (filter_file.fileno(),)
        command[1:1] = ["--seccomp", str(filter_file.fileno())]
        if control:
            # Bubblewrap retains the same flock open-file description until its
            # sandbox exits, including after abrupt control-plane death.
            command[1:1] = ["--sync-fd", str(control.lease_fd)]
            fds += (control.lease_fd,)
            if control.cancel():
                raise NativeStop("cancelled")
        process = subprocess.Popen(
            command,
            env=native_environment(Path("/work/out")),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            close_fds=True,
            pass_fds=fds,
            start_new_session=True,
        )
        try:
            if control:
                identity = process_identity(process.pid)
                if identity is not None:
                    control.started(process.pid, identity)
            while process.poll() is None:
                if control and control.cancel():
                    reason = "cancelled"
                peak = max(peak, process_tree_rss(process.pid))
                disk_peak = max(disk_peak, scratch_usage(scratch_root))
                if peak > 1536 * 1024**2 or disk_peak > 192 * 1024**2:
                    reason = "resource_exceeded"
                elif time.monotonic() - started > 60:
                    reason = "wall_limit"
                if reason:
                    break
                time.sleep(0.05)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=2)
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        result: dict[str, float | int | str] = {
            "returncode": process.returncode,
            "wall_seconds": time.monotonic() - started,
            "peak_rss_bytes": peak,
            "peak_scratch_bytes": disk_peak,
        }
    if scratch_usage(scratch_root) > 192 * 1024**2:
        reason = "resource_exceeded"
    # A native-created symlink must never redirect this trusted host-side write.
    descriptor = os.open(
        output / "resources.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(descriptor, "w") as metadata:
        metadata.write(json.dumps(result, allow_nan=False) + "\n")
    if reason:
        raise NativeStop(reason)
    return result


def fence(pid: int | None, identity: str | None) -> None:
    """Retire only the recorded process instance, never a recycled PID/group."""
    if pid is None or identity is None or process_identity(pid) != identity:
        return
    os.killpg(pid, signal.SIGKILL)
    deadline = time.monotonic() + 3
    while process_identity(pid) == identity and time.monotonic() < deadline:
        time.sleep(0.05)
    if process_identity(pid) == identity:
        raise RuntimeError("Previous native execution could not be fenced")
