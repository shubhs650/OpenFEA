"""Actual HTTP process restart preserves physical controls, mesh quality and frozen inputs."""

from pathlib import Path
from uuid import uuid4

from tests.integration.test_local_jobs import configuration, prepared, wait
from tests.integration.test_persistence import Browser, api_process


def test_mesh_controls_quality_and_old_snapshot_survive_actual_process_restart(
    tmp_path: Path,
) -> None:
    config = configuration(tmp_path)
    browser = Browser(config.port)
    with api_process(config, tmp_path / "first.log"):
        path, headers = prepared(browser)
        status, settings, _ = browser.request(
            "PUT",
            path + "/mesh-controls",
            {
                "units": "mm-N-MPa",
                "global_size": 250.0,
                "curvature_elements": 16,
                "recovery_enabled": True,
            },
            headers | {"If-Match": '"4"'},
        )
        assert status == 200, settings
        status, admitted, _ = browser.request(
            "POST",
            path + "/mesh-jobs",
            {},
            headers | {"If-Match": '"5"', "Idempotency-Key": str(uuid4())},
        )
        assert status == 202, admitted
        mesh = wait(browser, admitted["id"])
        assert mesh["status"] == "succeeded", mesh
        status, display, _ = browser.request("GET", f"/jobs/{mesh['id']}/mesh-display")
        assert status == 200 and display["quality"]["accepted"]
        status, original, _ = browser.request("GET", f"/jobs/{mesh['id']}/artifacts/snapshot.json")
        assert status == 200 and original["snapshot"]["mesh_setup"]["global_size_m"] == 0.25
    with api_process(config, tmp_path / "second.log"):
        assert browser.request("GET", path + "/mesh-controls")[0] == 401
        headers = {"X-CSRF-Token": browser.request("GET", "/session")[1]["csrf_token"]}
        assert browser.request("GET", path + "/mesh-controls")[1] == settings
        assert browser.request("GET", f"/jobs/{mesh['id']}/mesh-display")[1] == display
        assert browser.request("GET", f"/jobs/{mesh['id']}/artifacts/snapshot.json")[1] == original
        status, _, _ = browser.request(
            "PATCH",
            path + "/display-units",
            {"preset": "inch-lbf-psi"},
            headers | {"If-Match": '"5"'},
        )
        assert status == 200
        assert browser.request("GET", path + "/mesh-controls")[1]["setup"] == settings["setup"]
        assert browser.request("GET", f"/jobs/{mesh['id']}/artifacts/snapshot.json")[1] == original
