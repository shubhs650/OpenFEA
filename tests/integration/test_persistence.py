"""Real Uvicorn HTTP sessions and SQLite durability across process termination/restart."""

import json
import os
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ApiConfiguration:
    port: int
    environment: dict[str, str] = field(repr=False)


@contextmanager
def api_process(configuration: ApiConfiguration, log: Path) -> Iterator[None]:
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
                str(configuration.port),
                "--no-proxy-headers",
                "--app-dir",
                "services/api",
            ],
            cwd=ROOT,
            env=configuration.environment,
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    pytest.fail("API exited before readiness: " + log.read_text())
                try:
                    with opener.open(
                        f"http://127.0.0.1:{configuration.port}/api/v1/health", timeout=1
                    ) as response:
                        assert json.load(response)["status"] == "ok"
                        break
                except (urllib.error.URLError, TimeoutError):
                    time.sleep(0.1)
            else:
                pytest.fail("API readiness timed out: " + log.read_text())
            yield
        finally:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            assert process.returncode in (0, -signal.SIGTERM), log.read_text()
            assert "Application shutdown complete" in log.read_text()


class Browser:
    def __init__(self, port: int) -> None:
        self.base = f"http://127.0.0.1:{port}/api/v1"
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(CookieJar())
        )

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, Any], dict[str, str]]:
        request = urllib.request.Request(
            self.base + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers=(headers or {}) | {"Content-Type": "application/json"},
            method=method,
        )
        try:
            response = self.opener.open(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            data = response.read()
            return response.status, json.loads(data) if data else {}, dict(response.headers)


def test_projects_and_analyses_survive_real_process_restart(tmp_path: Path) -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])
    environment = os.environ | {
        "FEA_ENV": "test",
        "FEA_AUTH_MODE": "local",
        "FEA_BIND_HOST": "127.0.0.1",
        "FEA_DATA_ROOT": str(tmp_path / "data"),
    }
    browser = Browser(port)
    configuration = ApiConfiguration(port, environment)
    with api_process(configuration, tmp_path / "first.log"):
        status, session, _ = browser.request("GET", "/session")
        assert status == 200
        headers = {"X-CSRF-Token": session["csrf_token"]}
        status, project, _ = browser.request(
            "POST", "/projects", {"name": "Persistent bracket"}, headers
        )
        assert status == 201
        path = f"/projects/{project['id']}"
        status, analysis, _ = browser.request(
            "POST", path + "/analyses", {"name": "First setup"}, headers | {"If-Match": '"1"'}
        )
        assert status == 201
        analysis_path = f"/analyses/{analysis['id']}"
        status, updated, _ = browser.request(
            "PATCH", analysis_path, {"name": "Saved setup"}, headers | {"If-Match": '"1"'}
        )
        assert status == 200 and updated["revision"] == 2
        status, _, _ = browser.request(
            "PATCH", analysis_path, {"name": "Lost edit"}, headers | {"If-Match": '"1"'}
        )
        assert status == 409
        # Reject a cross-origin request over real HTTP.
        status, _, _ = browser.request(
            "GET", "/projects", headers={"Origin": "https://evil.example"}
        )
        assert status == 403
    with api_process(configuration, tmp_path / "second.log"):
        assert browser.request("GET", path)[0] == 401
        status, reopened, _ = browser.request("GET", "/session")
        assert status == 200 and reopened["owner_id"] == session["owner_id"]
        assert browser.request("GET", path)[1] == project
        assert browser.request("GET", analysis_path)[1] == updated
        assert browser.request("GET", analysis_path + "/revisions/1")[1] == analysis
        headers = {"X-CSRF-Token": reopened["csrf_token"], "If-Match": '"1"'}
        assert browser.request("DELETE", path, headers=headers)[0] == 204
        assert browser.request("GET", analysis_path)[0] == 404
    with api_process(configuration, tmp_path / "third.log"):
        browser.request("GET", "/session")
        assert browser.request("GET", path)[0] == 404
        assert browser.request("GET", "/projects")[1]["total"] == 0
