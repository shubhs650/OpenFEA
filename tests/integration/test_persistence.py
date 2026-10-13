"""Real Uvicorn HTTP sessions and SQLite durability across process termination/restart."""

import hashlib
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
    ) -> tuple[int, Any, dict[str, str]]:
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


def test_face_loads_and_frozen_deck_survive_real_process_restart(tmp_path: Path) -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])
    configuration = ApiConfiguration(
        port,
        os.environ
        | {
            "FEA_ENV": "test",
            "FEA_AUTH_MODE": "local",
            "FEA_BIND_HOST": "127.0.0.1",
            "FEA_DATA_ROOT": str(tmp_path / "data"),
        },
    )
    browser = Browser(port)
    with api_process(configuration, tmp_path / "loads-first.log"):
        _, session, _ = browser.request("GET", "/session")
        headers = {"X-CSRF-Token": session["csrf_token"]}
        _, project, _ = browser.request(
            "POST", "/projects", {"name": "Frozen deck restart"}, headers
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
        assert preview["status"] == "ready"
        _, geometry, _ = browser.request(
            "POST",
            f"/geometry-imports/{preview['id']}/confirm",
            {"dimensions_confirmed": True},
            headers | {"If-Match": '"1"'},
        )
        _, analysis, _ = browser.request(
            "POST",
            f"/projects/{project['id']}/analyses",
            {"name": "Restart loads", "geometry_revision_id": geometry["id"]},
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
        for revision, side, kind in ((2, 0, "fixed"), (3, 1, "force")):
            face = next(f for f in geometry["faces"] if f["signature"]["center_m"][0] == side)
            status, saved, _ = browser.request(
                "POST",
                path + "/loads",
                {
                    "assignment": {
                        "kind": kind,
                        "name": kind,
                        "geometry_revision_id": geometry["id"],
                        "face_ids": [face["id"]],
                        **({"units": "m-N-Pa", "force": [1000, 0, 0]} if kind == "force" else {}),
                    }
                },
                headers | {"If-Match": f'"{revision}"'},
            )
            assert status == 200, saved
        status, metadata, _ = browser.request(
            "POST", path + "/deck-exports", headers=headers | {"If-Match": '"4"'}
        )
        assert status == 201, metadata
        download = browser.base + f"/deck-exports/{metadata['id']}/input"
        with browser.opener.open(download, timeout=5) as response:
            deck = response.read()
        assert hashlib.sha256(deck).hexdigest() == metadata["deck_sha256"]
        # Change the live setup after publication, before the process goes away.
        identifier = saved["setup"]["assignments"][-1]["id"]
        assert (
            browser.request(
                "DELETE", path + "/loads/" + identifier, headers=headers | {"If-Match": '"4"'}
            )[0]
            == 200
        )
    with api_process(configuration, tmp_path / "loads-second.log"):
        assert browser.request("GET", path + "/loads")[0] == 401
        browser.request("GET", "/session")
        assert browser.request("GET", path + "/loads")[1]["analysis_revision"] == 5
        assert browser.request("GET", path + "/revisions/4/loads")[1] == saved
        assert browser.request("GET", path + "/deck-exports")[1] == [metadata]
        with browser.opener.open(download, timeout=5) as response:
            assert response.read() == deck
        frozen = browser.request("GET", f"/deck-exports/{metadata['id']}/snapshot")[1]
        assert frozen["snapshot"]["loads"] == saved["setup"]


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


def test_imported_body_material_snapshot_survives_real_api_restart(tmp_path: Path) -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])
    configuration = ApiConfiguration(
        port,
        os.environ
        | {
            "FEA_ENV": "test",
            "FEA_AUTH_MODE": "local",
            "FEA_BIND_HOST": "127.0.0.1",
            "FEA_DATA_ROOT": str(tmp_path / "data"),
        },
    )
    browser = Browser(port)
    with api_process(configuration, tmp_path / "first.log"):
        _, session, _ = browser.request("GET", "/session")
        headers = {"X-CSRF-Token": session["csrf_token"]}
        _, project, _ = browser.request(
            "POST", "/projects", {"name": "Material restart fixture"}, headers
        )
        raw = (ROOT / "tests/fixtures/geometry/cube-mm.step").read_bytes()
        _, ticket, _ = browser.request(
            "POST",
            f"/projects/{project['id']}/geometry-uploads",
            {"size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()},
            headers,
        )
        request = urllib.request.Request(
            browser.base + f"/geometry-uploads/{ticket['id']}/content",
            data=raw,
            headers=headers | {"Content-Type": "application/step"},
            method="PUT",
        )
        with browser.opener.open(request, timeout=5) as response:
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
            {"name": "Restart setup", "geometry_revision_id": geometry["id"]},
            headers | {"If-Match": '"2"'},
        )
        path = f"/analyses/{analysis['id']}"
        body = geometry["bodies"][0]["id"]
        status, assigned, _ = browser.request(
            "PUT",
            path + f"/materials/{body}",
            {
                "material": {
                    "kind": "sample",
                    "sample_id": "al-6061-t6-rod",
                    "library_version": browser.request("GET", "/material-library")[1][0][
                        "library_version"
                    ],
                    "confirmed": True,
                }
            },
            headers | {"If-Match": '"1"'},
        )
        assert status == 200
        status, saved, _ = browser.request(
            "PATCH",
            path + "/display-units",
            {"preset": "inch-lbf-psi"},
            headers | {"If-Match": '"2"'},
        )
        assert status == 200 and saved["setup"]["assignments"] == assigned["setup"]["assignments"]
    with api_process(configuration, tmp_path / "second.log"):
        assert browser.request("GET", path + "/materials")[0] == 401
        _, reopened, _ = browser.request("GET", "/session")
        assert reopened["owner_id"] == session["owner_id"]
        assert browser.request("GET", path + "/materials")[1] == saved
        assert browser.request("GET", path + "/revisions/2/materials")[1] == assigned
        assert browser.request("GET", f"/geometry/{geometry['id']}")[1] == geometry
        headers = {"X-CSRF-Token": reopened["csrf_token"], "If-Match": '"3"'}
        status, switched, _ = browser.request(
            "PATCH", path + "/display-units", {"preset": "mm-N-MPa"}, headers
        )
        assert status == 200 and switched["setup"]["assignments"] == saved["setup"]["assignments"]
        assert (
            browser.request("PATCH", path + "/display-units", {"preset": "m-N-Pa"}, headers)[0]
            == 409
        )
