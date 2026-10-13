"""A failed measured stage must stop the entire declared workload ladder."""

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, cast

import pytest

from worker.resources import measured_native
from worker.runtime import ROOT

spec = importlib.util.spec_from_file_location("feasibility", ROOT / "scripts/native/feasibility.py")
assert spec is not None and spec.loader is not None
feasibility = importlib.util.module_from_spec(spec)
spec.loader.exec_module(feasibility)


def manifest() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((ROOT / "tests/benchmarks/T006.json").read_text()))


@pytest.mark.parametrize("failed_stage", ["mesh", "prepare", "solve", "post"])
def test_real_native_failure_prevents_later_workloads(
    failed_stage: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "ladder"
    output.mkdir()
    calls: list[tuple[str, str]] = []

    def controlled_native(
        command: list[str], directory: Path, name: str, **limits: Any
    ) -> dict[str, Any]:
        calls.append((directory.name, name))
        if name == "mesh":
            # Tiny real Gmsh mesh for sequencing only; nominal labels are not capacity data.
            command = [*command]
            command[3] = "0.6"
        if name == failed_stage:
            command = [str(ROOT / ".venv/bin/python"), "-I", "-c", "raise SystemExit(7)"]
        return measured_native(command, directory, name, **limits)

    monkeypatch.setattr(feasibility, "measured_native", controlled_native)
    result: dict[str, Any] = {"status": "DEVELOPMENT ONLY"}
    completed = feasibility.run_workloads(
        output, manifest(), {"rss_mib": 1536, "disk_mib": 256, "timeout": 90}, result
    )
    saved = json.loads((output / "result.json").read_text())
    assert not completed
    assert saved == result
    assert saved["runs"][0][failed_stage]["status"] == "native_failed"
    assert saved["runs"][0][failed_stage]["returncode"] != 0
    assert (output / "mesh-5000" / f"{failed_stage}.log").exists()
    assert saved["runs"][0]["remaining_stages"] == "not run; resource/native stop"
    assert [run["status"] for run in saved["runs"][1:]] == [
        "NOT RUN; previous native/resource stage failed"
    ] * 2
    assert [directory for directory, _stage in calls] == ["mesh-5000"] * len(calls)
    assert not (output / "mesh-25000").exists()
    assert not (output / "mesh-100000").exists()


def test_real_resource_stop_prevents_later_workloads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "ladder"
    output.mkdir()
    allocation = (
        "import time\na=[]\nfor _ in range(64):\n"
        " a.append(bytearray(16*1024**2))\n time.sleep(.02)\n"
    )

    def controlled_native(
        command: list[str], directory: Path, name: str, **limits: Any
    ) -> dict[str, Any]:
        if name == "mesh":
            command = [*command]
            command[3] = "0.6"
        if name == "prepare":
            command = [str(ROOT / ".venv/bin/python"), "-I", "-c", allocation]
            limits["rss_mib"] = 128
        return measured_native(command, directory, name, **limits)

    monkeypatch.setattr(feasibility, "measured_native", controlled_native)
    result: dict[str, Any] = {"status": "DEVELOPMENT ONLY"}
    completed = feasibility.run_workloads(
        output, manifest(), {"rss_mib": 1536, "disk_mib": 256, "timeout": 90}, result
    )
    saved = json.loads((output / "result.json").read_text())
    assert not completed
    assert saved["runs"][0]["prepare"]["status"] == "rss_budget_exceeded"
    assert saved["runs"][0]["prepare"]["returncode"] != 0
    assert len(saved["runs"]) == 3
    assert all(run["status"].startswith("NOT RUN") for run in saved["runs"][1:])
    assert not (output / "mesh-25000").exists()


def test_prelaunch_resource_error_is_persisted_and_stops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "ladder"
    output.mkdir()

    def refused(command: list[str], directory: Path, name: str, **limits: Any) -> Any:
        raise RuntimeError("Less than 1 GiB scratch reserve; workload not started")

    monkeypatch.setattr(feasibility, "measured_native", refused)
    result: dict[str, Any] = {"status": "DEVELOPMENT ONLY"}
    assert not feasibility.run_workloads(output, manifest(), {}, result)
    saved = json.loads((output / "result.json").read_text())
    assert saved["runs"][0]["mesh"]["status"] == "stage_error"
    assert "scratch reserve" in saved["runs"][0]["mesh"]["error"]
    assert all(run["status"].startswith("NOT RUN") for run in saved["runs"][1:])


def test_cli_exits_nonzero_after_real_mesh_stage_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "new-run"
    read_text = Path.read_text

    def no_cgroup_v2(path: Path, *args: Any, **kwargs: Any) -> str:
        if path == Path("/sys/fs/cgroup/cpu.max") or path == Path("/sys/fs/cgroup/memory.max"):
            raise FileNotFoundError(path)
        return read_text(path, *args, **kwargs)

    def fail_mesh(command: list[str], directory: Path, name: str, **limits: Any) -> dict[str, Any]:
        assert name == "mesh"
        child = [str(ROOT / ".venv/bin/python"), "-I", "-c", "raise SystemExit(7)"]
        return measured_native(child, directory, name, **limits)

    monkeypatch.setattr(feasibility, "measured_native", fail_mesh)
    monkeypatch.setattr(Path, "read_text", no_cgroup_v2)
    monkeypatch.setattr(sys, "argv", ["feasibility.py", "--meshes", "--output", str(output)])
    assert feasibility.main() == 2
    saved = json.loads((output / "result.json").read_text())
    assert saved["cpu_quota"] is None and saved["memory_limit"] is None
    assert len(saved["edits"]) == 2  # real native cleanup still completed
    assert saved["runs"][0]["mesh"]["status"] == "native_failed"
    assert all(run["status"].startswith("NOT RUN") for run in saved["runs"][1:])


def test_admission_stop_is_separate_from_native_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "ladder"
    output.mkdir()
    selected = manifest()
    selected["workloads"] = selected["workloads"][:1]
    selected["solve_admission_elements"] = 0
    calls: list[str] = []

    def tiny_mesh(command: list[str], directory: Path, name: str, **limits: Any) -> dict[str, Any]:
        calls.append(name)
        command = [*command]
        command[3] = "0.6"
        return measured_native(command, directory, name, **limits)

    monkeypatch.setattr(feasibility, "measured_native", tiny_mesh)
    result: dict[str, Any] = {"status": "DEVELOPMENT ONLY"}
    assert feasibility.run_workloads(output, selected, {}, result)
    assert calls == ["mesh"]
    run = result["runs"][0]
    assert run["elements"] > 0
    assert run["coarsening_proposal"]["requires_explicit_request"] is True
    assert run["remaining_stages"].startswith("not run; explicit")
