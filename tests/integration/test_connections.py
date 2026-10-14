"""Actual API-process restart preserves approved pair, provenance and old history."""

from pathlib import Path

from tests.integration.test_local_jobs import configuration, prepared
from tests.integration.test_persistence import Browser, api_process


def test_reviewed_gap_and_independent_copy_survive_real_restart(tmp_path: Path) -> None:
    config = configuration(tmp_path)
    browser = Browser(config.port)
    with api_process(config, tmp_path / "first.log"):
        path, headers = prepared(browser, "bond-gap-m.step", basic_loads=False)
        status, measured, _ = browser.request(
            "POST", path + "/bond-candidates", {}, headers | {"If-Match": '"2"'}
        )
        assert status == 200, measured
        pair = measured["report"]["pairs"][0]
        request = {
            "geometry_revision_id": measured["geometry_revision_id"],
            "name": "Persistent gap",
            "master_face_id": pair["master_face_id"],
            "slave_face_id": pair["slave_face_id"],
            "gap_tolerance_m": 1e-5,
            "gap_approved": True,
            "assumptions_confirmed": True,
        }
        status, saved, _ = browser.request(
            "POST", path + "/bonds", request, headers | {"If-Match": '"2"'}
        )
        assert status == 200 and saved["analysis_revision"] == 3, saved
        status, copy, _ = browser.request(
            "POST",
            path + "/duplicates",
            {"source_revision": 3, "name": "Independent pair"},
            headers | {"If-Match": '"3"'},
        )
        assert status == 201
        copy_path = f"/analyses/{copy['id']}"
    with api_process(config, tmp_path / "second.log"):
        assert browser.request("GET", path + "/bonds")[0] == 401
        _, session, _ = browser.request("GET", "/session")
        assert browser.request("GET", path + "/bonds")[1] == saved
        assert browser.request("GET", path + "/revisions/2/bonds")[1]["setup"]["assignments"] == []
        assert browser.request("GET", copy_path + "/bonds")[1]["setup"] == saved["setup"]
        bond = saved["setup"]["assignments"][0]
        assert (
            browser.request(
                "DELETE", path + "/bonds/" + bond["id"], None, headers | {"If-Match": '"3"'}
            )[0]
            == 403
        )
        assert (
            browser.request(
                "DELETE",
                path + "/bonds/" + bond["id"],
                None,
                {"X-CSRF-Token": session["csrf_token"], "If-Match": '"3"'},
            )[0]
            == 200
        )
        assert browser.request("GET", copy_path + "/bonds")[1]["setup"] == saved["setup"]
