"""Recovery revisions survive actual API shutdown; browser undo remains session-local."""

import os
import socket
from pathlib import Path

from tests.integration.test_persistence import ApiConfiguration, Browser, api_process


def test_restore_and_conflict_copy_survive_actual_restart(tmp_path: Path) -> None:
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
        _, project, _ = browser.request("POST", "/projects", {"name": "Recovery"}, headers)
        status, analysis, _ = browser.request(
            "POST",
            f"/projects/{project['id']}/analyses",
            {"name": "Initial"},
            headers | {"If-Match": '"1"'},
        )
        assert status == 201
        path = f"/analyses/{analysis['id']}"
        assert (
            browser.request("PATCH", path, {"name": "Changed"}, headers | {"If-Match": '"1"'})[0]
            == 200
        )
        status, restored, _ = browser.request(
            "POST", path + "/restores", {"target_revision": 1}, headers | {"If-Match": '"2"'}
        )
        assert status == 200 and restored["name"] == "Initial" and restored["revision"] == 3
        status, copy, _ = browser.request(
            "POST",
            path + "/conflict-copies",
            {"source_revision": 2, "name": "Conflict copy"},
            headers | {"If-Match": '"3"'},
        )
        assert status == 201
    with api_process(configuration, tmp_path / "second.log"):
        assert browser.request("GET", path)[0] == 401
        browser.request("GET", "/session")
        assert browser.request("GET", path)[1] == restored
        assert browser.request("GET", path + "/revisions/2")[1]["name"] == "Changed"
        assert browser.request("GET", f"/analyses/{copy['id']}")[1] == copy
        assert browser.request("GET", f"/analyses/{copy['id']}/jobs")[1] == []
