"""Actual process restart retains native rotated bases, sources and frozen results."""

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from tests.integration.test_local_jobs import configuration, prepared, wait
from tests.integration.test_persistence import Browser, api_process
from tests.native.test_directions import local_face
from worker.direction_benchmarks import placement
from worker.directions import unit
from worker.meshing import dot, sub


def test_rotated_direction_sources_geometry_catalog_and_equilibrium_survive_real_restart(
    tmp_path: Path,
) -> None:
    config = configuration(tmp_path)
    browser = Browser(config.port)
    with api_process(config, tmp_path / "first.log"):
        path, headers = prepared(browser, "rotated-cube-m.step", False)
        geometry_id = browser.request("GET", path)[1]["geometry_revision_id"]
        geometry = browser.request("GET", f"/geometry/{geometry_id}")[1]

        def current() -> dict[str, str]:
            return headers | {"If-Match": f'"{browser.request("GET", path)[1]["revision"]}"'}

        status, state, _ = browser.request(
            "POST",
            path + "/loads",
            {
                "assignment": {
                    "kind": "symmetry",
                    "name": "Native three-plane supports",
                    "geometry_revision_id": geometry_id,
                    "face_ids": [local_face(geometry, a, 0, True) for a in range(3)],
                }
            },
            current(),
        )
        assert status == 200, state
        manifest = json.loads(Path("tests/benchmarks/B06.json").read_bytes())
        basis, _ = placement(manifest, True)
        edge = next(
            e
            for e in geometry["edges"]
            if e["start_m"] is not None
            and abs(dot(unit(sub(tuple(e["end_m"]), tuple(e["start_m"]))), basis[0])) > 1 - 1e-10
        )
        reverse = dot(unit(sub(tuple(edge["end_m"]), tuple(edge["start_m"]))), basis[0]) < 0
        status, saved, _ = browser.request(
            "POST",
            path + "/loads",
            {
                "assignment": {
                    "kind": "directional_force",
                    "name": "Persisted rotated edge source",
                    "geometry_revision_id": geometry_id,
                    "face_ids": [local_face(geometry, 0, 1, True)],
                    "units": "mm-N-MPa",
                    "magnitude": 1000,
                    "direction": {
                        "kind": "straight_edge",
                        "reference_id": edge["id"],
                        "reverse": reverse,
                    },
                }
            },
            current(),
        )
        assert status == 200, saved
        status, _, _ = browser.request(
            "PUT",
            path + "/mesh-controls",
            {
                "units": "m-N-Pa",
                "global_size": 0.5,
                "local_sizes": [],
                "curvature_elements": 0,
                "recovery_enabled": False,
            },
            current(),
        )
        assert status == 200
        saved = browser.request("GET", path + "/loads")[1]

        def submit(mesh_id: str | None = None) -> dict[str, Any]:
            status, job, _ = browser.request(
                "POST",
                path + ("/runs" if mesh_id else "/mesh-jobs"),
                {"mesh_job_id": mesh_id} if mesh_id else {},
                current() | {"Idempotency-Key": str(uuid4())},
            )
            assert status == 202, job
            result = wait(browser, job["id"])
            assert result["status"] == "succeeded", result
            return result

        mesh = submit()
        run = submit(mesh["id"])
        route = f"/runs/{run['id']}/results"
        original = browser.request("GET", route)[1]
        assert original["data"]["equilibrium"]["passed"]
        snapshot = browser.request("GET", f"/jobs/{run['id']}/artifacts/snapshot.json")[1]
    with api_process(config, tmp_path / "second.log"):
        assert browser.request("GET", route)[0] == 401
        headers = {"X-CSRF-Token": browser.request("GET", "/session")[1]["csrf_token"]}
        assert browser.request("GET", path + "/loads")[1] == saved
        assert browser.request("GET", f"/geometry/{geometry_id}")[1] == geometry
        assert browser.request("GET", route)[1] == original
        assert browser.request("GET", f"/jobs/{run['id']}/artifacts/snapshot.json")[1] == snapshot
        status, _, _ = browser.request(
            "PATCH",
            path + "/display-units",
            {"preset": "inch-lbf-psi"},
            headers | {"If-Match": f'"{saved["analysis_revision"]}"'},
        )
        assert status == 200
        assert browser.request("GET", path + "/loads")[1]["setup"] == saved["setup"]
        assert browser.request("GET", route)[1] == original
