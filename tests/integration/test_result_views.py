"""Actual completed result views retain frozen inputs across API process restarts."""

from pathlib import Path

from tests.integration.test_local_jobs import configuration, prepared, submit, wait
from tests.integration.test_persistence import Browser, api_process


def test_derived_results_survive_real_api_restart_and_display_unit_edits(tmp_path: Path) -> None:
    config = configuration(tmp_path)
    browser = Browser(config.port)
    with api_process(config, tmp_path / "first.log"):
        path, headers = prepared(browser)
        mesh = wait(browser, submit(browser, path, headers)["id"])
        run = wait(browser, submit(browser, path, headers, mesh["id"])["id"])
        assert run["status"] == "succeeded", run
        route = f"/runs/{run['id']}/results"
        status, original, _ = browser.request("GET", route)
        assert status == 200, original
        assert original["input_sha256"] == run["input_sha256"]
        assert len(original["data"]["fields"]) == 14
        assert original["data"]["frame"] == "global_cartesian"
        assert all(
            len(v["smoothed_stress"]["principal_pa"]) == 3 for v in original["data"]["vertices"]
        )
        raw_route = f"/jobs/{run['id']}/artifacts/results.json"
        raw_original = browser.request("GET", raw_route)[1]
        status, _, _ = browser.request(
            "PATCH",
            path + "/display-units",
            {"preset": "inch-lbf-psi"},
            headers | {"If-Match": '"4"'},
        )
        assert status == 200
        assert browser.request("GET", route)[1] == original
    with api_process(config, tmp_path / "second.log"):
        assert browser.request("GET", route)[0] == 401
        browser.request("GET", "/session")
        assert browser.request("GET", route)[1] == original
        assert browser.request("GET", raw_route)[1] == raw_original
        assert (
            browser.request("GET", path + "/materials")[1]["setup"]["display_units"]
            == "inch-lbf-psi"
        )
