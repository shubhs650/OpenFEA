"""Undo restores a real solvable setup; existing raw results stay immutable."""

import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

from tests.native import test_step_import as step
from tests.native.test_local_jobs import prepared, submit, wait_job

application = step.application
client = step.client


def test_restored_setup_solves_again_without_mutating_frozen_run(client: TestClient) -> None:
    path, geometry = prepared(client)
    mesh = wait_job(client, submit(client, path)["id"])
    run = wait_job(client, submit(client, path, mesh["id"])["id"])
    assert run["status"] == "succeeded", run
    raw_path = f"/api/v1/jobs/{run['id']}/artifacts/results.json"
    original = client.get(raw_path).content
    force = next(
        a
        for a in client.get(path + "/loads").json()["setup"]["assignments"]
        if a["kind"] == "pressure"
    )
    assert (
        client.delete(path + "/loads/" + force["id"], headers={"If-Match": '"4"'}).status_code
        == 200
    )
    assert (
        client.post(
            path + "/restores", json={"target_revision": 4}, headers={"If-Match": '"5"'}
        ).status_code
        == 200
    )
    restored = wait_job(client, submit(client, path, mesh["id"])["id"])
    assert restored["status"] == "succeeded", restored
    results = client.get(f"/api/v1/jobs/{restored['id']}/artifacts/results.json").json()
    points = client.get(f"/api/v1/jobs/{mesh['id']}/artifacts/mesh.json").json()["nodes"]
    u_error = max(
        abs(u[axis] - (-1000 / 210e9 * points[node][0] if axis == 0 else 0))
        for node, u in results["dat"]["displacements_m"].items()
        for axis in range(3)
    )
    s_error = max(
        abs(point["tensor_pa"][axis] - (-1000 if axis == 0 else 0))
        for point in results["integration_points"]
        for axis in range(6)
    )
    assert u_error <= 1e-13
    assert s_error <= 0.01
    assert client.get(raw_path).content == original
    # Recovery copies the historical complete setup, never the source's jobs/results.
    copied = client.post(
        path + "/conflict-copies",
        json={"source_revision": 4, "name": "Recovered setup"},
        headers={"If-Match": '"6"'},
    )
    assert copied.status_code == 201
    copy_path = "/api/v1/analyses/" + copied.json()["id"]
    assert client.get(copy_path + "/jobs").json() == []
    assert (
        client.get(copy_path + "/loads").json()["setup"]
        == client.get(path + "/loads").json()["setup"]
    )
    report = {
        "u_error_m": u_error,
        "stress_error_pa": s_error,
        "u_tolerance_m": 1e-13,
        "stress_tolerance_pa": 0.01,
        "frozen_results_sha256": hashlib.sha256(original).hexdigest(),
        "geometry_revision_id": geometry["id"],
        "run_revision": restored["analysis_revision"],
        "native_run": restored["id"],
    }
    output = Path("work/T017-native-measurements.json")
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
