"""T029 faults on real HTTP jobs, CCX bytes and isolated native processes."""

import errno
import fcntl
import os
import shutil
import signal
import threading
import time
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.jobs import runner, stages
from tests.native import test_step_import as step_tests
from tests.native.test_job_lifecycle import descendants
from tests.native.test_local_jobs import prepared, submit, wait_job
from worker import local_process, local_solve
from worker.local_process import NativeControl, NativeStop, process_identity, supervise
from worker.runtime import ROOT

application = step_tests.application
client = step_tests.client


@pytest.mark.parametrize("fault", ["once", "twice", "corrupt_checkpoint", "cancel"])
def test_actual_parser_termination_reuses_ccx_once_and_obeys_fencing_and_cancel(
    client: TestClient, application: FastAPI, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    path, _ = prepared(client)
    mesh = wait_job(client, submit(client, path)["id"])
    assert mesh["status"] == "succeeded", mesh
    solves: list[Path] = []
    processes: list[int] = []
    parsing = threading.Event()
    release = threading.Event()
    original_solve, original_supervise = local_solve.solve_snapshot, supervise
    calls = 0

    def solve(*args: Any, **kwargs: Any) -> dict[str, Any]:
        solves.append(args[0])
        return original_solve(*args, **kwargs)

    def observed(
        command: list[str], output: Path, control: NativeControl, log_name: str
    ) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        notify = control.started
        should_kill = calls == 1 or fault == "twice"

        def started(pid: int, identity: str) -> None:
            notify(pid, identity)
            if not should_kill:
                return
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                for child in descendants(pid):
                    try:
                        cmd = Path(f"/proc/{child}/cmdline").read_bytes()
                    except FileNotFoundError:
                        continue
                    if cmd.startswith(str(ROOT / ".venv/bin/python").encode() + b"\0"):
                        processes.extend([pid, child])
                        os.kill(child, signal.SIGSTOP)
                        if fault == "cancel":
                            parsing.set()
                            assert release.wait(3)
                        os.kill(child, signal.SIGTERM)
                        os.kill(child, signal.SIGCONT)
                        return
                time.sleep(0.002)
            raise AssertionError("Actual isolated result parser was not observed")

        control.started = started
        try:
            return original_supervise(command, output, control, log_name)
        finally:
            control.started = notify

    original_reuse = application.state.job_service.repository.reusable

    def reuse(*args: Any, **kwargs: Any) -> Any:
        saved = original_reuse(*args, **kwargs)
        if saved is not None and fault == "corrupt_checkpoint":
            manifest, _ = saved
            blob = application.state.job_service.storage.blob_path(
                UUID(mesh["project_id"]), manifest["analysis.dat"].sha256
            )
            blob.chmod(0o600)
            blob.write_bytes(b"CORRUPTED_SYNTHETIC_DAT")
        return saved

    monkeypatch.setattr(application.state.job_service.repository, "reusable", reuse)
    monkeypatch.setattr(runner, "solve_snapshot", solve)
    monkeypatch.setattr(stages, "supervise", observed)
    submitted = submit(client, path, mesh["id"])
    if fault == "cancel":
        assert parsing.wait(4)
        response = client.post(f"/api/v1/jobs/{submitted['id']}/cancel", json={})
        assert response.status_code == 200 and response.json()["status"] == "cancelling"
        release.set()
    final = wait_job(client, submitted["id"])
    assert len(solves) == 1, "Validation recovery must never run CCX twice"
    assert all(process_identity(pid) is None for pid in processes)
    assert len(final["attempts"]) == (1 if fault == "cancel" else 2)
    assert (
        final["status"]
        == {
            "once": "succeeded",
            "twice": "interrupted",
            "corrupt_checkpoint": "failed",
            "cancel": "cancelled",
        }[fault]
    ), final
    if fault == "once":
        assert final["summary"]["reused_stage"] == "solving"
        previous, recovered = final["attempts"]
        assert previous["reason_code"] == "parser_interrupted"
        assert previous["finished_at"] <= recovered["started_at"]
        for name in ("analysis.dat", "analysis.frd", "solver.log", "resources.json"):
            assert previous["artifacts"][name]["sha256"] == final["artifacts"][name]["sha256"]
            assert (
                client.get(f"/api/v1/jobs/{final['id']}/attempts/1/artifacts/{name}").status_code
                == 200
            )
        assert (
            client.get(f"/api/v1/jobs/{final['id']}/attempts/9/artifacts/analysis.dat").status_code
            == 404
        )
    else:
        assert "results.json" not in final["artifacts"]
        assert client.get(f"/api/v1/jobs/{final['id']}/artifacts/results.json").status_code == 404
    if fault == "corrupt_checkpoint":
        assert final["reason_code"] == "artifact_integrity"


@pytest.mark.parametrize("fault", ["reserve", "enospc"])
def test_disk_pressure_fails_without_retry_or_solver_then_queue_recovers(
    client: TestClient, application: FastAPI, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    path, _ = prepared(client)
    mesh = wait_job(client, submit(client, path)["id"])
    assert mesh["status"] == "succeeded", mesh
    original = Path.write_bytes
    calls: list[Path] = []
    original_solve = local_solve.solve_snapshot

    def solve(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(args[0])
        return original_solve(*args, **kwargs)

    monkeypatch.setattr(runner, "solve_snapshot", solve)
    with monkeypatch.context() as patch:
        if fault == "reserve":
            usage = shutil.disk_usage
            patch.setattr(shutil, "disk_usage", lambda path: usage(path)._replace(free=0))
        else:

            def write(path: Path, data: bytes) -> int:
                if path.name == "mesh.json" and path.parent.name == "attempt-1":
                    raise OSError(errno.ENOSPC, "Injected bounded disk-full fault")
                return original(path, data)

            patch.setattr(Path, "write_bytes", write)
        final = wait_job(client, submit(client, path, mesh["id"])["id"])
    assert final["status"] == "failed" and final["reason_code"] == "disk_full", final
    assert len(final["attempts"]) == 1 and not calls and "results.json" not in final["artifacts"]
    recovered = wait_job(client, submit(client, path, mesh["id"])["id"])
    assert recovered["status"] == "succeeded" and len(calls) == 1, recovered


@pytest.mark.parametrize("fault", ["rss", "scratch", "log", "wall"])
def test_real_supervisor_enforces_sampled_and_final_resource_limits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    # Small controlled diagnostic limits avoid consuming the production RSS cap.
    # These probes are process-control evidence, not a capacity benchmark/solve.
    codes = {
        "rss": "import time; x=bytearray(32*1024**2); time.sleep(10)",
        "scratch": "from pathlib import Path; "
        "[Path(str(i)).open('wb').truncate(49*1024**2) for i in range(4)]",
        "log": "import os; os.write(1,b'x'*(8*1024**2+1))",
        "wall": "import time; time.sleep(10)",
    }
    if fault == "rss":
        monkeypatch.setattr(local_process, "RSS_BYTES", 8 * 1024**2)
    if fault == "wall":
        monkeypatch.setattr(local_process, "STAGE_SECONDS", 0.15)
    pids: list[int] = []

    def probe(
        command: list[str], output: Path, control: NativeControl, log_name: str
    ) -> dict[str, Any]:
        command[-3:] = ["/usr/bin/python3", "-c", codes[fault]]
        return supervise(command, output, control, log_name)

    monkeypatch.setattr(local_solve, "supervise", probe)
    source = tmp_path / "analysis.inp"
    source.write_text("SYNTHETIC_CONTROL_PROBE")
    with (tmp_path / "lease").open("a+b") as lease:
        fcntl.flock(lease, fcntl.LOCK_EX)
        with pytest.raises(NativeStop) as failure:
            local_solve.solve_snapshot(
                source,
                tmp_path / "output",
                NativeControl(
                    lambda: False, lambda pid, identity: pids.append(pid), lease.fileno()
                ),
            )
    assert (
        failure.value.reason
        == {
            "rss": "resource_exceeded",
            "scratch": "resource_exceeded",
            "log": "output_limit",
            "wall": "wall_limit",
        }[fault]
    )
    assert pids and all(process_identity(pid) is None for pid in pids)


def test_expired_real_execution_heartbeat_is_fenced_before_single_retry(
    client: TestClient, application: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import text

    path, _ = prepared(client)
    original = application.state.deck_service.mesh
    pids: list[int] = []

    def observed(*args: Any, **kwargs: Any) -> dict[str, Any]:
        control = args[3]
        notify = control.started

        def started(pid: int, identity: str) -> None:
            notify(pid, identity)
            if pids:
                return
            pids.append(pid)
            os.killpg(pid, signal.SIGSTOP)
            with application.state.repository.write() as connection:
                connection.execute(
                    text("UPDATE local_jobs SET heartbeat_at=:at WHERE status='running'"),
                    {"at": (datetime.now(UTC) - timedelta(seconds=11)).isoformat()},
                )

        control.started = started
        result: dict[str, Any] = original(*args, **kwargs)
        return result

    monkeypatch.setattr(application.state.deck_service, "mesh", observed)
    final = wait_job(client, submit(client, path)["id"])
    assert final["status"] == "succeeded", final
    assert len(final["attempts"]) == 2
    assert final["attempts"][0]["reason_code"] == "lease_lost"
    assert final["attempts"][0]["finished_at"] <= final["attempts"][1]["started_at"]
    assert all(process_identity(pid) is None for pid in pids)
