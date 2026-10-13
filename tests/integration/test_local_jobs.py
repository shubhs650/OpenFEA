"""Real HTTP queue recovery and abrupt API death with actual native children."""

import fcntl
import hashlib
import os
import signal
import socket
import sqlite3
import subprocess
import time
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from tests.integration.test_persistence import ROOT, ApiConfiguration, Browser, api_process
from tests.native.test_job_lifecycle import descendants
from worker.local_process import process_identity


def configuration(tmp_path: Path) -> ApiConfiguration:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    return ApiConfiguration(
        port,
        os.environ
        | {
            "FEA_ENV": "test",
            "FEA_AUTH_MODE": "local",
            "FEA_BIND_HOST": "127.0.0.1",
            "FEA_DATA_ROOT": str(tmp_path / "data"),
        },
    )


def prepared(browser: Browser) -> tuple[str, dict[str, str]]:
    _, session, _ = browser.request("GET", "/session")
    headers = {"X-CSRF-Token": session["csrf_token"]}
    _, project, _ = browser.request(
        "POST", "/projects", {"name": "Persistent queue fixture"}, headers
    )
    raw = (ROOT / "tests/fixtures/geometry/cube-m.step").read_bytes()
    _, ticket, _ = browser.request(
        "POST",
        f"/projects/{project['id']}/geometry-uploads",
        {"size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()},
        headers,
    )
    with browser.opener.open(
        urllib.request.Request(
            browser.base + f"/geometry-uploads/{ticket['id']}/content",
            data=raw,
            headers=headers | {"Content-Type": "application/step"},
            method="PUT",
        ),
        timeout=5,
    ) as response:
        assert response.status == 200
    _, preview, _ = browser.request(
        "POST",
        f"/projects/{project['id']}/geometry-imports",
        {"upload_id": ticket["id"]},
        headers | {"If-Match": '"1"'},
    )
    assert preview["status"] == "ready", preview
    _, geometry, _ = browser.request(
        "POST",
        f"/geometry-imports/{preview['id']}/confirm",
        {"dimensions_confirmed": True},
        headers | {"If-Match": '"1"'},
    )
    _, analysis, _ = browser.request(
        "POST",
        f"/projects/{project['id']}/analyses",
        {"name": "Frozen queue", "geometry_revision_id": geometry["id"]},
        headers | {"If-Match": '"2"'},
    )
    path = f"/analyses/{analysis['id']}"
    sample = browser.request("GET", "/material-library")[1][0]
    assert (
        browser.request(
            "PUT",
            path + "/materials/" + geometry["bodies"][0]["id"],
            {
                "material": {
                    "kind": "sample",
                    "sample_id": sample["library_id"],
                    "library_version": sample["library_version"],
                    "confirmed": True,
                }
            },
            headers | {"If-Match": '"1"'},
        )[0]
        == 200
    )
    for revision, side, kind in ((2, 0, "fixed"), (3, 1, "pressure")):
        face = next(f for f in geometry["faces"] if f["signature"]["center_m"][0] == side)
        status, result, _ = browser.request(
            "POST",
            path + "/loads",
            {
                "assignment": {
                    "kind": kind,
                    "name": kind,
                    "geometry_revision_id": geometry["id"],
                    "face_ids": [face["id"]],
                    **({"units": "m-N-Pa", "pressure": 1000} if kind == "pressure" else {}),
                }
            },
            headers | {"If-Match": f'"{revision}"'},
        )
        assert status == 200, result
    return path, headers


def submit(
    browser: Browser, path: str, headers: dict[str, str], mesh: str | None = None
) -> dict[str, Any]:
    status, job, _ = browser.request(
        "POST",
        path + ("/runs" if mesh else "/mesh-jobs"),
        {"mesh_job_id": mesh} if mesh else {},
        headers | {"If-Match": '"4"', "Idempotency-Key": str(uuid4())},
    )
    assert status == 202, job
    result: dict[str, Any] = job
    return result


def wait(browser: Browser, identifier: str) -> dict[str, Any]:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        status, job, _ = browser.request("GET", f"/jobs/{identifier}")
        assert status == 200, job
        if job["status"] in ("succeeded", "cancelled", "failed", "interrupted"):
            return job  # type: ignore[no-any-return]
        time.sleep(0.05)
    pytest.fail("Job did not complete: " + str(job))


def test_queued_solve_resumes_after_restart_and_completed_outputs_remain(tmp_path: Path) -> None:
    config = configuration(tmp_path)
    data = Path(config.environment["FEA_DATA_ROOT"])
    data.mkdir()
    browser = Browser(config.port)
    with (data / "native-import.lock").open("a+b") as lock:
        with api_process(config, tmp_path / "first.log"):
            path, headers = prepared(browser)
            mesh = wait(browser, submit(browser, path, headers)["id"])
            assert mesh["status"] == "succeeded", mesh
            fcntl.flock(lock, fcntl.LOCK_EX)
            job = submit(browser, path, headers, mesh["id"])
            assert job["status"] == "queued"
        with api_process(config, tmp_path / "second.log"):
            assert browser.request("GET", f"/jobs/{job['id']}")[0] == 401
            browser.request("GET", "/session")
            assert browser.request("GET", f"/jobs/{job['id']}")[1]["status"] == "queued"
            fcntl.flock(lock, fcntl.LOCK_UN)
            completed = wait(browser, job["id"])
            assert completed["status"] == "succeeded", completed
            result = browser.request("GET", f"/jobs/{job['id']}/artifacts/results.json")[1]
            assert result["input_sha256"] == job["input_sha256"]
        with api_process(config, tmp_path / "third.log"):
            browser.request("GET", "/session")
            assert browser.request("GET", f"/jobs/{job['id']}")[1] == completed
            assert browser.request("GET", f"/jobs/{job['id']}/artifacts/results.json")[1] == result


@contextmanager
def killable_api(config: ApiConfiguration, log: Path) -> Iterator[subprocess.Popen[str]]:
    with log.open("w") as output:
        process = subprocess.Popen(
            [
                str(ROOT / ".venv/bin/python"),
                "-m",
                "uvicorn",
                "app.main:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(config.port),
                "--no-proxy-headers",
                "--app-dir",
                "services/api",
            ],
            cwd=ROOT,
            env=config.environment,
            stdout=output,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            browser = Browser(config.port)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                try:
                    if browser.request("GET", "/health")[0] == 200:
                        break
                except OSError:
                    time.sleep(0.05)
            else:
                pytest.fail("API did not start: " + log.read_text())
            yield process
        finally:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=10)


def test_abrupt_api_death_fences_actual_mesh_and_restarts_only_queued_work(tmp_path: Path) -> None:
    config = configuration(tmp_path)
    browser = Browser(config.port)
    data = Path(config.environment["FEA_DATA_ROOT"])
    with killable_api(config, tmp_path / "killed.log") as api:
        path, headers = prepared(browser)
        job = submit(browser, path, headers)
        deadline = time.monotonic() + 5
        pid = None
        while time.monotonic() < deadline:
            with sqlite3.connect(data / "metadata.sqlite3") as connection:
                row = connection.execute(
                    "SELECT process_pid FROM local_jobs WHERE id=?", (job["id"],)
                ).fetchone()
            if row[0] is not None:
                pid = row[0]
                break
            time.sleep(0.005)
        assert pid is not None and process_identity(pid) is not None
        # Pause the real native child to make the abrupt crash point deterministic.
        deadline = time.monotonic() + 2
        native = None
        while time.monotonic() < deadline and native is None:
            for child in descendants(pid):
                try:
                    command = Path(f"/proc/{child}/cmdline").read_bytes()
                except FileNotFoundError:
                    continue
                if b"/venvs/mesh/bin/python\0" in command:
                    os.kill(child, signal.SIGSTOP)
                    native = child
                    break
            time.sleep(0.005)
        assert native is not None
        # Pause control-plane scheduling while adding a second queued logical job
        # directly through real HTTP before the intentionally abrupt kill.
        next_job = submit(browser, path, headers)
        assert next_job["status"] == "queued"
        api.send_signal(signal.SIGKILL)
        api.wait(timeout=5)
    with api_process(config, tmp_path / "recovered.log"):
        browser.request("GET", "/session")
        next_done = wait(browser, next_job["id"])
        assert next_done["status"] == "succeeded", next_done
        interrupted = browser.request("GET", f"/jobs/{job['id']}")[1]
        assert interrupted["status"] == "interrupted", interrupted
        assert interrupted["reason_code"] == "worker_interrupted"
        assert interrupted["finished_at"] <= next_done["started_at"]
        assert process_identity(pid) is None
        assert process_identity(native) is None
        assert "snapshot.json" in interrupted["artifacts"]
        assert [e["status"] for e in interrupted["events"]].count("running") == 1
