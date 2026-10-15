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
        inspection_route = f"/runs/{run['id']}/sections"
        inspection_payload = {"point_m": [0.5, 0, 0], "normal": [1, 0, 0]}
        status, inspection, _ = browser.request(
            "POST", inspection_route, inspection_payload, headers
        )
        assert status == 200 and inspection["vertices"]
        assert inspection["results_sha256"] == original["results_sha256"]
        second_run = wait(browser, submit(browser, path, headers, mesh["id"])["id"])
        wire = browser.request("GET", f"/jobs/{run['id']}/artifacts/mesh.json")[1]
        zero = next(int(n) for n, p in wire["nodes"].items() if p == [0, 0, 0])
        eid = next(int(e) for e, ns in wire["elements"].items() if zero in ns[:4])
        comparison_route = f"/runs/{run['id']}/comparisons"
        comparison_payload = {
            "compared_run_id": second_run["id"],
            "field": "uz",
            "points": [
                {
                    "label": "Saved fixed corner",
                    "body_id": wire["owners"][str(eid)],
                    "point_m": [0, 0, 0],
                    "reference_element_id": eid,
                    "compared_element_id": eid,
                }
            ],
        }
        status, comparison, _ = browser.request(
            "POST", comparison_route, comparison_payload, headers
        )
        assert status == 200, comparison
        assert comparison["rows"][0]["change"]["relative_change"] is None
        assert comparison["reference"]["assumptions"] == original["data"]["assumptions"]
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
        fresh_session = browser.request("GET", "/session")[1]
        assert (
            browser.request(
                "POST",
                inspection_route,
                inspection_payload,
                {"X-CSRF-Token": fresh_session["csrf_token"]},
            )[1]
            == inspection
        )
        assert (
            browser.request(
                "POST",
                comparison_route,
                comparison_payload,
                {"X-CSRF-Token": fresh_session["csrf_token"]},
            )[1]
            == comparison
        )
        assert browser.request("GET", route)[1] == original
        assert browser.request("GET", raw_route)[1] == raw_original
        assert (
            browser.request("GET", path + "/materials")[1]["setup"]["display_units"]
            == "inch-lbf-psi"
        )
