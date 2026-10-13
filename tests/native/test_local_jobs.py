"""Real API queue -> isolated Gmsh -> frozen deck -> isolated CCX -> raw validation."""

import hashlib
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.native import test_step_import as step_tests
from tests.native.test_face_decks import assign, setup

application = step_tests.application
client = step_tests.client


def wait_job(client: TestClient, identifier: str, timeout: float = 20) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/jobs/{identifier}")
        assert response.status_code == 200, response.text
        job: dict[str, Any] = response.json()
        if job["status"] in ("succeeded", "failed", "cancelled", "interrupted"):
            return job
        time.sleep(0.05)
    pytest.fail(f"Job did not complete: {job}; worker {client.get('/api/v1/local-worker').text}")


def prepared(client: TestClient) -> tuple[str, dict[str, Any]]:
    path, geometry = setup(client)
    fixed = next(f["id"] for f in geometry["faces"] if f["signature"]["center_m"][0] == 0)
    loaded = next(f["id"] for f in geometry["faces"] if f["signature"]["center_m"][0] == 1)
    assign(client, path, geometry, "fixed", [fixed])
    assign(client, path, geometry, "pressure", [loaded], units="m-N-Pa", pressure=1000)
    return path, geometry


def submit(client: TestClient, path: str, mesh: str | None = None) -> dict[str, Any]:
    revision = client.get(path).json()["revision"]
    response = client.post(
        path + ("/runs" if mesh else "/mesh-jobs"),
        json={"mesh_job_id": mesh} if mesh else {},
        headers={"If-Match": f'"{revision}"', "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 202, response.text
    result: dict[str, Any] = response.json()
    return result


def test_real_mesh_and_queued_solve_match_axial_reference(
    client: TestClient, application: FastAPI
) -> None:
    path, geometry = prepared(client)
    mesh = wait_job(client, submit(client, path)["id"])
    assert mesh["status"] == "succeeded", mesh
    assert mesh["summary"]["elements"] == 100
    preview = client.get(f"/api/v1/jobs/{mesh['id']}/mesh-display")
    assert preview.status_code == 200, preview.text
    assert preview.json()["display"]["faces"][0]["triangles"]
    run = wait_job(client, submit(client, path, mesh["id"])["id"])
    assert run["status"] == "succeeded", run
    response = client.get(f"/api/v1/jobs/{run['id']}/artifacts/results.json")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["input_sha256"] == run["input_sha256"]
    assert result["mesh_sha256"] == mesh["artifacts"]["mesh.json"]["sha256"]
    assert result["stress_location"] == "integration_point"
    assert len(result["integration_points"]) == 400
    raw_mesh = client.get(f"/api/v1/jobs/{mesh['id']}/artifacts/mesh.json").json()
    error = max(
        abs(value[axis] - (-1000 / 210e9 * raw_mesh["nodes"][node][0] if axis == 0 else 0))
        for node, value in result["dat"]["displacements_m"].items()
        for axis in range(3)
    )
    assert error <= 1e-13
    stress_error = max(
        abs(point["tensor_pa"][axis] - (-1000 if axis == 0 else 0))
        for point in result["integration_points"]
        for axis in range(6)
    )
    assert stress_error <= 0.01
    for name, descriptor in run["artifacts"].items():
        downloaded = client.get(f"/api/v1/jobs/{run['id']}/artifacts/{name}")
        assert downloaded.status_code == 200, downloaded.text
        assert hashlib.sha256(downloaded.content).hexdigest() == descriptor["sha256"]
    frozen = client.get(f"/api/v1/jobs/{run['id']}/artifacts/snapshot.json").json()
    assert frozen["snapshot"]["geometry"]["id"] == geometry["id"]
    assert run["summary"]["free_equations"] > 0
    output = Path(".local/native/validation/T011")
    output.mkdir(parents=True, exist_ok=True)
    import json

    (output / "axial.json").write_text(
        json.dumps(
            {
                "mesh": mesh,
                "run": run,
                "displacement_error_m": error,
                "raw_tensor_error_pa": stress_error,
            },
            indent=2,
        )
        + "\n"
    )
