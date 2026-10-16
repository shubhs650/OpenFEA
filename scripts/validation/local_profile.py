"""Collect non-identifying local hardware/headroom facts; never infer supported capacity."""

import argparse
import json
import platform
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from worker.runtime import ROOT


def collect(scratch: Path) -> dict[str, Any]:
    release = platform.release()
    wsl = platform.system() == "Linux" and "microsoft" in release.lower()
    memory: dict[str, int] = {}
    if Path("/proc/meminfo").is_file():
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, value = line.split(":", 1)
            if key in ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree"):
                memory[key + "_bytes"] = int(value.split()[0]) * 1024
    windows = None
    error = None
    if wsl:
        executable = shutil.which("powershell.exe")
        if executable:
            command = (
                "$c=Get-CimInstance Win32_Processor | Select-Object -First 1;"
                "$m=Get-CimInstance Win32_ComputerSystem;"
                "$g=@(Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM);"
                "[ordered]@{cpu_model=$c.Name;physical_ram_bytes=$m.TotalPhysicalMemory;"
                "gpu=$g} | ConvertTo-Json -Depth 4 -Compress"
            )
            try:
                result = subprocess.run(
                    [executable, "-NoProfile", "-NonInteractive", "-Command", command],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                windows = json.loads(result.stdout.strip().lstrip("\ufeff"))
            except (OSError, ValueError, subprocess.SubprocessError):
                error = (
                    "Windows hardware observation unavailable; "
                    "collect it manually, without serials/hostnames"
                )
        else:
            error = "Windows PowerShell interop unavailable; collect physical RAM/CPU/GPU manually"
    disk = shutil.disk_usage(scratch)
    cpu_model = platform.processor()
    if Path("/proc/cpuinfo").is_file():
        cpu_model = next(
            (
                line.split(":", 1)[1].strip()
                for line in Path("/proc/cpuinfo").read_text().splitlines()
                if line.startswith("model name")
            ),
            cpu_model,
        )
    cgroup = Path("/sys/fs/cgroup/memory.max")
    return {
        "schema_version": 1,
        "captured_at": datetime.now(UTC).isoformat(),
        "code_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "platform_system": platform.system(),
        "kernel_release": release,
        "python": platform.python_version(),
        "is_wsl": wsl,
        "cpu_model": cpu_model,
        "visible_memory": memory,
        "cgroup_memory_max": cgroup.read_text().strip() if cgroup.is_file() else None,
        "scratch_disk": {
            "total_bytes": disk.total,
            "used_bytes": disk.used,
            "free_bytes": disk.free,
        },
        "windows_hardware": windows,
        "observation_error": error,
        "classification": "Hardware/headroom observation only; "
        "no laptop/capacity/performance acceptance",
        "supported_workload_capacity": "NOT DETERMINED; "
        "owner must review actual bounded workload measurements",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.exit(2, "Refusing to overwrite retained profile evidence\n")
    result = collect(args.scratch)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as target:
        target.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(result["classification"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
