"""Actual API restarts retain gravity/component sources and frozen equilibrium/results."""

from pathlib import Path
from typing import Any
from uuid import uuid4

from tests.integration.test_local_jobs import configuration, prepared, wait
from tests.integration.test_persistence import Browser, api_process


def test_essential_load_sources_reactions_and_equilibrium_survive_process_restart(
    tmp_path: Path,
) -> None:
    config = configuration(tmp_path)
    browser = Browser(config.port)
    with api_process(config, tmp_path / "first.log"):
        path, headers = prepared(browser)
        _, state, _ = browser.request("GET", path + "/loads")
        geometry = browser.request("GET", f"/geometry/{state['geometry_revision_id']}")[1]
        pressure = next(a for a in state["setup"]["assignments"] if a["kind"] == "pressure")
        status, _, _ = browser.request(
            "DELETE", path + f"/loads/{pressure['id']}", headers=headers | {"If-Match": '"4"'}
        )
        assert status == 200
        for revision, item in (
            (
                5,
                {
                    "kind": "displacement",
                    "name": "Prescribed x",
                    "face_ids": pressure["face_ids"],
                    "axis": "x",
                    "displacement": 0.001,
                },
            ),
            (
                6,
                {
                    "kind": "gravity",
                    "name": "Gravity",
                    "body_ids": [geometry["bodies"][0]["id"]],
                    "acceleration": [0, 0, -9806.65],
                },
            ),
        ):
            status, saved, _ = browser.request(
                "POST",
                path + "/loads",
                {
                    "assignment": item
                    | {"geometry_revision_id": geometry["id"], "units": "mm-N-MPa"}
                },
                headers | {"If-Match": f'"{revision}"'},
            )
            assert status == 200, saved

        def submit(mesh: str | None = None) -> dict[str, Any]:
            status, job, _ = browser.request(
                "POST",
                path + ("/runs" if mesh else "/mesh-jobs"),
                {"mesh_job_id": mesh} if mesh else {},
                headers | {"If-Match": '"7"', "Idempotency-Key": str(uuid4())},
            )
            assert status == 202, job
            return wait(browser, job["id"])

        mesh = submit()
        assert mesh["status"] == "succeeded", mesh
        run = submit(mesh["id"])
        assert run["status"] == "succeeded", run
        route = f"/runs/{run['id']}/results"
        status, original, _ = browser.request("GET", route)
        assert status == 200, original
        assert original["data"]["equilibrium"]["passed"]
        snapshot = browser.request("GET", f"/jobs/{run['id']}/artifacts/snapshot.json")[1]
    with api_process(config, tmp_path / "second.log"):
        assert browser.request("GET", route)[0] == 401
        headers = {"X-CSRF-Token": browser.request("GET", "/session")[1]["csrf_token"]}
        assert browser.request("GET", path + "/loads")[1] == saved
        assert browser.request("GET", route)[1] == original
        assert browser.request("GET", f"/jobs/{run['id']}/artifacts/snapshot.json")[1] == snapshot
        status, _, _ = browser.request(
            "PATCH",
            path + "/display-units",
            {"preset": "inch-lbf-psi"},
            headers | {"If-Match": '"7"'},
        )
        assert status == 200
        assert browser.request("GET", path + "/loads")[1]["setup"] == saved["setup"]
        assert browser.request("GET", route)[1] == original
