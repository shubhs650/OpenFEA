"""Duplicate setup, cross-analysis mesh identity and original runs survive actual restart."""

from pathlib import Path
from uuid import uuid4

from tests.integration.test_local_jobs import configuration, prepared, wait
from tests.integration.test_persistence import Browser, api_process


def test_independent_analysis_and_shared_mesh_survive_real_restart(tmp_path: Path) -> None:
    config = configuration(tmp_path)
    browser = Browser(config.port)
    with api_process(config, tmp_path / "first.log"):
        path, headers = prepared(browser)
        status, admitted, _ = browser.request(
            "POST",
            path + "/mesh-jobs",
            {},
            headers | {"If-Match": '"4"', "Idempotency-Key": str(uuid4())},
        )
        assert status == 202
        mesh = wait(browser, admitted["id"])
        assert mesh["status"] == "succeeded", mesh
        status, copy, _ = browser.request(
            "POST",
            path + "/duplicates",
            {"source_revision": 4, "name": "Persistent variant"},
            headers | {"If-Match": '"4"'},
        )
        assert status == 201
        copy_path = f"/analyses/{copy['id']}"
        status, candidates, _ = browser.request("GET", copy_path + "/compatible-meshes")
        assert status == 200 and candidates["items"][0]["job"]["id"] == mesh["id"]
        status, run, _ = browser.request(
            "POST",
            copy_path + "/runs",
            {"mesh_job_id": mesh["id"]},
            headers | {"If-Match": '"1"', "Idempotency-Key": str(uuid4())},
        )
        assert status == 202
        run = wait(browser, run["id"])
        assert run["status"] == "succeeded", run
        frozen = browser.request("GET", f"/jobs/{run['id']}/artifacts/snapshot.json")[1]
        result = browser.request("GET", f"/runs/{run['id']}/results")[1]
    with api_process(config, tmp_path / "second.log"):
        assert browser.request("GET", copy_path + "/compatible-meshes")[0] == 401
        browser.request("GET", "/session")
        assert browser.request("GET", copy_path)[1] == copy
        assert browser.request("GET", path)[1]["revision"] == 4
        assert browser.request("GET", copy_path + "/compatible-meshes")[1] == candidates
        assert browser.request("GET", f"/jobs/{run['id']}/artifacts/snapshot.json")[1] == frozen
        assert browser.request("GET", f"/runs/{run['id']}/results")[1] == result
        assert frozen["mesh"]["compatibility_sha256"] == candidates["compatibility_sha256"]
