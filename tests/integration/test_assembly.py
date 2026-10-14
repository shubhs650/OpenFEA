"""Actual-process bonded solve, restart and frozen constraint/result history."""

from pathlib import Path
from uuid import uuid4

from tests.integration.test_local_jobs import configuration, prepared, wait
from tests.integration.test_persistence import Browser, api_process
from tests.unit.test_materials import custom


def test_bonded_run_constraints_and_result_bytes_survive_real_restart(tmp_path: Path) -> None:
    config = configuration(tmp_path)
    browser = Browser(config.port)
    with api_process(config, tmp_path / "first.log"):
        path, headers = prepared(browser, "bond-zero-m.step", basic_loads=False)
        _, analysis, _ = browser.request("GET", path)
        geometry = browser.request("GET", f"/geometry/{analysis['geometry_revision_id']}")[1]
        revision = 2
        for body in geometry["bodies"]:
            material = custom()
            material["material"]["values"]["poisson_ratio"] = 0
            status, _, _ = browser.request(
                "PUT",
                path + "/materials/" + body["id"],
                material,
                headers | {"If-Match": f'"{revision}"'},
            )
            assert status == 200
            revision += 1
        for kind, x in [("fixed", 0), ("pressure", 2)]:
            face = next(
                f for f in geometry["faces"] if abs(f["signature"]["center_m"][0] - x) < 1e-12
            )
            assignment = {
                "kind": kind,
                "name": kind,
                "geometry_revision_id": geometry["id"],
                "face_ids": [face["id"]],
            }
            if kind == "pressure":
                assignment |= {"units": "m-N-Pa", "pressure": 1000}
            assert (
                browser.request(
                    "POST",
                    path + "/loads",
                    {"assignment": assignment},
                    headers | {"If-Match": f'"{revision}"'},
                )[0]
                == 200
            )
            revision += 1
        status, report, _ = browser.request(
            "POST", path + "/bond-candidates", {}, headers | {"If-Match": f'"{revision}"'}
        )
        assert status == 200
        pair = report["report"]["pairs"][0]
        payload = {
            "geometry_revision_id": geometry["id"],
            "name": "Persistent reviewed bond",
            "master_face_id": pair["master_face_id"],
            "slave_face_id": pair["slave_face_id"],
            "gap_tolerance_m": 0,
            "gap_approved": False,
            "assumptions_confirmed": True,
        }
        assert (
            browser.request(
                "POST", path + "/bonds", payload, headers | {"If-Match": f'"{revision}"'}
            )[0]
            == 200
        )
        revision += 1
        status, job, _ = browser.request(
            "POST",
            path + "/mesh-jobs",
            {},
            headers | {"If-Match": f'"{revision}"', "Idempotency-Key": str(uuid4())},
        )
        assert status == 202
        mesh = wait(browser, job["id"])
        assert mesh["status"] == "succeeded", mesh
        status, job, _ = browser.request(
            "POST",
            path + "/runs",
            {"mesh_job_id": mesh["id"]},
            headers | {"If-Match": f'"{revision}"', "Idempotency-Key": str(uuid4())},
        )
        assert status == 202
        run = wait(browser, job["id"])
        assert run["status"] == "succeeded", run
        result = browser.request("GET", f"/runs/{run['id']}/results")[1]
        frozen = browser.request("GET", f"/jobs/{run['id']}/artifacts/snapshot.json")[1]
        constraints = browser.request("GET", f"/jobs/{run['id']}/artifacts/assembly.json")[1]
        saved = browser.request("GET", path + "/bonds")[1]
    with api_process(config, tmp_path / "second.log"):
        assert browser.request("GET", path + "/bonds")[0] == 401
        browser.request("GET", "/session")
        assert browser.request("GET", path + "/bonds")[1] == saved
        assert browser.request("GET", f"/runs/{run['id']}/results")[1] == result
        assert browser.request("GET", f"/jobs/{run['id']}/artifacts/snapshot.json")[1] == frozen
        assert (
            browser.request("GET", f"/jobs/{run['id']}/artifacts/assembly.json")[1] == constraints
        )
        assert browser.request("GET", f"/jobs/{run['id']}")[1]["artifacts"] == run["artifacts"]
        assert constraints["expected_free_equations"] == run["summary"]["free_equations"]
