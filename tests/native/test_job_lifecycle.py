"""Real native failures/cancellation, immutable running inputs and sandbox probes."""

import fcntl
import json
import os
import signal
import threading
import time
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.jobs import runner
from tests.native import test_step_import as step_tests
from tests.native.test_local_jobs import prepared, submit, wait_job
from tests.unit.test_materials import custom
from worker import local_solve
from worker.local_process import NativeControl, process_identity, supervise
from worker.runtime import NATIVE

application = step_tests.application
client = step_tests.client


def test_http_idempotent_replay_survives_head_edit_without_duplicate_execution(
    client: TestClient, application: FastAPI
) -> None:
    path, _ = prepared(client)
    headers = {"If-Match": '"4"', "Idempotency-Key": str(uuid4())}
    with (application.state.job_service.storage.root / "native-import.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        first = client.post(path + "/mesh-jobs", json={}, headers=headers)
        assert first.status_code == 202, first.text
        job = first.json()
        assert client.post(path + "/mesh-jobs", json={}, headers=headers).json()["id"] == job["id"]
        assert (
            client.patch(
                path, json={"name": "New live revision"}, headers={"If-Match": '"4"'}
            ).status_code
            == 200
        )
        assert client.post(path + "/mesh-jobs", json={}, headers=headers).json()["id"] == job["id"]
        conflict = client.post(path + "/mesh-jobs", json={}, headers=headers | {"If-Match": '"5"'})
        assert conflict.status_code == 409 and conflict.json()["code"] == "idempotency_conflict"
    completed = wait_job(client, job["id"])
    assert completed["status"] == "succeeded", completed
    assert len(client.get(path + "/jobs").json()) == 1
    assert [e["status"] for e in completed["events"]].count(
        "running"
    ) == 2  # claim + validating stage


def test_edit_after_enqueue_does_not_change_solve_snapshot(
    client: TestClient, application: FastAPI
) -> None:
    path, geometry = prepared(client)
    mesh = wait_job(client, submit(client, path)["id"])
    assert mesh["status"] == "succeeded", mesh
    with (application.state.job_service.storage.root / "native-import.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        run = submit(client, path, mesh["id"])
        assert run["status"] == "queued"
        snapshot = client.get(f"/api/v1/jobs/{run['id']}/artifacts/snapshot.json").json()
        assert (
            client.patch(
                path, json={"name": "Edited while queued"}, headers={"If-Match": '"4"'}
            ).status_code
            == 200
        )
        changed = custom()
        changed["material"]["values"]["young_modulus"] = 105000
        changed["material"]["values"]["poisson_ratio"] = 0
        assert (
            client.put(
                path + "/materials/" + geometry["bodies"][0]["id"],
                json=changed,
                headers={"If-Match": '"5"'},
            ).status_code
            == 200
        )
    finished = wait_job(client, run["id"])
    assert finished["status"] == "succeeded", finished
    assert finished["analysis_revision"] == 4
    assert client.get(f"/api/v1/jobs/{run['id']}/artifacts/snapshot.json").json() == snapshot
    result = client.get(f"/api/v1/jobs/{run['id']}/artifacts/results.json").json()
    raw_mesh = client.get(f"/api/v1/jobs/{mesh['id']}/artifacts/mesh.json").json()
    assert (
        max(
            abs(value[0] + 1000 / 210e9 * raw_mesh["nodes"][node][0])
            for node, value in result["dat"]["displacements_m"].items()
        )
        <= 1e-13
    )
    # The changed material uses the same immutable connectivity in a new run.
    new = wait_job(client, submit(client, path, mesh["id"])["id"])
    assert new["status"] == "succeeded", new
    assert new["artifacts"]["mesh.json"]["sha256"] == mesh["artifacts"]["mesh.json"]["sha256"]
    result = client.get(f"/api/v1/jobs/{new['id']}/artifacts/results.json").json()
    assert (
        max(
            abs(value[0] + 1000 / 105e9 * raw_mesh["nodes"][node][0])
            for node, value in result["dat"]["displacements_m"].items()
        )
        <= 1e-13
    )


@pytest.mark.parametrize(
    "fault", ["solver_error", "missing_frd", "truncated_dat", "missing_resources"]
)
def test_actual_solver_error_or_bad_outputs_never_succeed(
    client: TestClient, application: FastAPI, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    path, _ = prepared(client)
    mesh = wait_job(client, submit(client, path)["id"])
    assert mesh["status"] == "succeeded", mesh

    def injected(input_path: Path, output: Path, control: NativeControl) -> dict[str, Any]:
        # Test-only corruption of the private generated copy: execute the actual
        # pinned CCX, not a fake solver or an uploaded deck endpoint.
        if fault == "solver_error":
            input_path.write_text("*NODE\n" + ",".join(["1"] * 17) + "\n")
        execution = local_solve.solve_snapshot(input_path, output, control)
        if fault == "missing_frd":
            (output / "analysis.frd").unlink()
        elif fault == "truncated_dat":
            (output / "analysis.dat").write_bytes((output / "analysis.dat").read_bytes()[:100])
        elif fault == "missing_resources":
            (output / "resources.json").unlink()
        return execution

    monkeypatch.setattr(runner, "solve_snapshot", injected)
    run = wait_job(client, submit(client, path, mesh["id"])["id"])
    assert run["status"] == "failed", run
    assert "results.json" not in run["artifacts"]
    assert client.get(f"/api/v1/jobs/{run['id']}/artifacts/results.json").status_code == 404
    if fault != "missing_resources":
        resources = client.get(f"/api/v1/jobs/{run['id']}/artifacts/resources.json").json()
        assert (
            resources["returncode"] != 0
            if fault == "solver_error"
            else resources["returncode"] == 0
        )
    else:
        assert run["reason_code"] == "artifact_integrity"
    assert "solver.log" in run["artifacts"]


def descendants(pid: int) -> list[int]:
    # Build one process-tree snapshot per observation. Rescanning all host
    # PIDs at every depth can outlive the real tiny Gmsh job on busy runners.
    children: dict[int, list[int]] = {}
    for path in Path("/proc").iterdir():
        if not path.name.isdigit():
            continue
        try:
            fields = (path / "stat").read_text().rsplit(")", 1)[1].split()
            children.setdefault(int(fields[1]), []).append(int(path.name))
        except (FileNotFoundError, ProcessLookupError):
            pass
    found = []
    stack = [pid]
    while stack:
        direct = children.get(stack.pop(), [])
        found.extend(direct)
        stack.extend(direct)
    return found


def test_cancel_actual_mesher_confirms_native_death_before_next_job(
    client: TestClient, application: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, _ = prepared(client)
    launched = threading.Event()
    actual: list[int] = []
    original = application.state.deck_service.mesh

    def observed(
        snapshot: Any, display: Any, directory: Path, control: NativeControl | None = None
    ) -> dict[str, Any]:
        assert control is not None
        notify = control.started

        def started(pid: int, identity: str) -> None:
            notify(pid, identity)
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                for child in descendants(pid):
                    try:
                        command = Path(f"/proc/{child}/cmdline").read_bytes()
                    except FileNotFoundError:
                        continue
                    if command.startswith(str(NATIVE / "venvs/mesh/bin/python").encode() + b"\0"):
                        # Pause a real pinned process to make HTTP edit/cancel
                        # races reproducible; this is not capacity evidence.
                        os.kill(child, signal.SIGSTOP)
                        actual.extend([pid, child])
                        launched.set()
                        return
                time.sleep(0.005)
            raise AssertionError("Actual Gmsh process was not observed")

        control.started = started
        value: dict[str, Any] = original(snapshot, display, directory, control)
        return value

    monkeypatch.setattr(application.state.deck_service, "mesh", observed)
    job = submit(client, path)
    assert launched.wait(3), client.get(f"/api/v1/jobs/{job['id']}").text
    assert process_identity(actual[-1]) is not None
    assert (
        client.patch(
            path, json={"name": "Edited while mesher runs"}, headers={"If-Match": '"4"'}
        ).status_code
        == 200
    )
    frozen = client.get(f"/api/v1/jobs/{job['id']}/artifacts/snapshot.json").json()
    assert frozen["snapshot"]["analysis"]["revision"] == 4
    assert frozen["snapshot"]["analysis"]["name"] != "Edited while mesher runs"
    cancelled = client.post(f"/api/v1/jobs/{job['id']}/cancel", json={})
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelling"
    final = wait_job(client, job["id"])
    assert final["status"] == "cancelled", final
    assert all(process_identity(pid) is None for pid in actual)
    monkeypatch.setattr(application.state.deck_service, "mesh", original)
    next_job = wait_job(client, submit(client, path)["id"])
    assert next_job["status"] == "succeeded", next_job


def test_solver_namespace_denies_network_fork_private_reads_and_input_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sentinel = tmp_path / "private"
    sentinel.write_text("SYNTHETIC_PRIVATE_SENTINEL")
    input_path = tmp_path / "input.inp"
    input_path.write_text("SYNTHETIC_GENERATED_INPUT")
    code = (
        """import json,os,socket
from pathlib import Path
values={}
operations=[('network',lambda:socket.socket()),('fork',lambda:os.fork()),
    ('input_write',lambda:Path('analysis.inp').write_text('bad'))]
for key,fn in operations:
    try: fn(); values[key]=False
    except OSError: values[key]=True
values['private_hidden']=not Path("""
        + repr(str(sentinel))
        + """).exists()
print(json.dumps(values))
"""
    )

    def probe(
        command: list[str], output: Path, control: NativeControl | None, log_name: str
    ) -> dict[str, float | int | str]:
        # Only this threat probe substitutes a trusted Python diagnostic command;
        # it asserts sandbox denials and never becomes numerical solve evidence.
        command[-3:] = ["/usr/bin/python3", "-c", code]
        return supervise(command, output, control, log_name)

    monkeypatch.setattr(local_solve, "supervise", probe)
    with (tmp_path / "execution.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        result = local_solve.solve_snapshot(
            input_path,
            tmp_path / "output",
            NativeControl(lambda: False, lambda pid, identity: None, lock.fileno()),
        )
    assert result["returncode"] == 0
    assert json.loads((tmp_path / "output/solver.log").read_text()) == {
        "network": True,
        "fork": True,
        "input_write": True,
        "private_hidden": True,
    }


def test_native_symlink_cannot_redirect_host_resource_metadata_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sentinel = tmp_path / "host-sentinel"
    sentinel.write_text("UNCHANGED_SYNTHETIC_HOST_FILE")
    source = tmp_path / "input.inp"
    source.write_text("SYNTHETIC_INPUT")

    def symlink_probe(
        command: list[str], output: Path, control: NativeControl | None, log_name: str
    ) -> dict[str, float | int | str]:
        command[-3:] = [
            "/usr/bin/python3",
            "-c",
            "import os; os.symlink(" + repr(str(sentinel)) + ",'resources.json')",
        ]
        return supervise(command, output, control, log_name)

    monkeypatch.setattr(local_solve, "supervise", symlink_probe)
    with (tmp_path / "lease").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with pytest.raises(FileExistsError):
            local_solve.solve_snapshot(
                source,
                tmp_path / "out",
                NativeControl(lambda: False, lambda pid, identity: None, lock.fileno()),
            )
    assert sentinel.read_text() == "UNCHANGED_SYNTHETIC_HOST_FILE"


def test_job_download_corruption_and_snapshot_owner_checks(
    client: TestClient, application: FastAPI
) -> None:
    path, _ = prepared(client)
    mesh = wait_job(client, submit(client, path)["id"])
    assert mesh["status"] == "succeeded", mesh
    storage = application.state.job_service.storage
    blob = storage.blob_path(UUID(mesh["project_id"]), mesh["artifacts"]["mesh.json"]["sha256"])
    blob.chmod(0o600)
    blob.write_text("corrupted")
    assert client.get(f"/api/v1/jobs/{mesh['id']}/artifacts/mesh.json").status_code == 503
    response = client.post(
        path + "/runs",
        json={"mesh_job_id": mesh["id"]},
        headers={"If-Match": '"4"', "Idempotency-Key": "11111111-1111-1111-1111-111111111111"},
    )
    assert response.status_code == 503, response.text
    assert client.post(f"/api/v1/jobs/{mesh['id']}/cancel", json={}).json()["status"] == "succeeded"
    assert (
        client.delete(
            f"/api/v1/projects/{mesh['project_id']}", headers={"If-Match": '"2"'}
        ).status_code
        == 204
    )
    assert client.get(f"/api/v1/jobs/{mesh['id']}/artifacts/snapshot.json").status_code == 404
