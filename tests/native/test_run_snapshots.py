"""Native multi-material run ownership/warnings and queued tool-contract refusal."""

import fcntl
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.native import test_step_import as step_tests
from tests.native.test_face_decks import assign, setup
from tests.native.test_local_jobs import prepared, submit, wait_job
from tests.unit.test_materials import custom

application = step_tests.application
client = step_tests.client


def test_two_body_queue_preserves_material_ownership_and_one_total_force(
    client: TestClient,
) -> None:
    path, geometry = setup(client, "two-m.step")
    material = custom()
    material["material"]["values"].update(
        young_modulus=105000, poisson_ratio=0, density=None, yield_strength=None
    )
    assert (
        client.put(
            path + "/materials/" + geometry["bodies"][1]["id"],
            json=material,
            headers={"If-Match": '"3"'},
        ).status_code
        == 200
    )
    fixed, loaded, origins = [], [], {}
    for body in geometry["bodies"]:
        faces = [f for f in geometry["faces"] if f["body_id"] == body["id"]]
        first = min(faces, key=lambda f: f["signature"]["center_m"][0])
        last = max(faces, key=lambda f: f["signature"]["center_m"][0])
        fixed.append(first["id"])
        loaded.append(last["id"])
        origins[body["id"]] = first["signature"]["center_m"][0]
    assign(client, path, geometry, "fixed", fixed)
    assign(client, path, geometry, "force", loaded + loaded, units="m-N-Pa", force=[1000, 0, 0])
    mesh = wait_job(client, submit(client, path)["id"])
    assert mesh["status"] == "succeeded", mesh
    run = wait_job(client, submit(client, path, mesh["id"])["id"])
    assert run["status"] == "succeeded", run
    result = client.get(f"/api/v1/jobs/{run['id']}/artifacts/results.json").json()
    raw = client.get(f"/api/v1/jobs/{mesh['id']}/artifacts/mesh.json").json()
    max_displacement_error = 0.0
    reactions = []
    for index, body in enumerate(geometry["bodies"]):
        nodes = {n for e, b in raw["owners"].items() if b == body["id"] for n in raw["elements"][e]}
        modulus = 210e9 if index == 0 else 105e9
        max_displacement_error = max(
            max_displacement_error,
            *[
                abs(
                    result["dat"]["displacements_m"][str(n)][0]
                    - 500 / modulus * (raw["nodes"][str(n)][0] - origins[body["id"]])
                )
                for n in nodes
            ],
        )
        support_nodes = {n for f in raw["boundary"][fixed[index]] for n in f["nodes"]}
        reaction = sum(result["dat"]["external_forces_n"][str(n)][0] for n in support_nodes)
        assert reaction == pytest.approx(-500, abs=0.001)
        reactions.append(reaction)
    assert max_displacement_error <= 1e-13
    assert {p["material_id"] for p in result["integration_points"]} == {"M1", "M2"}
    assert result["warnings"] and result["warnings"] == run["summary"]["warnings"]
    frozen = client.get(f"/api/v1/jobs/{run['id']}/artifacts/snapshot.json").json()
    assert frozen["warnings"]
    output = Path(".local/native/validation/T011")
    output.mkdir(parents=True, exist_ok=True)
    (output / "two-body.json").write_text(
        json.dumps(
            {
                "run": run,
                "displacement_error_m": max_displacement_error,
                "body_reactions_n": reactions,
                "total_force_n": 1000,
                "materials": [210e9, 105e9],
            },
            indent=2,
        )
        + "\n"
    )


def test_changed_tool_contract_fails_queued_input_before_execution(
    client: TestClient, application: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, _ = prepared(client)
    service = application.state.job_service
    with (service.storage.root / "native-import.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        job = submit(client, path)
        original = service.policy

        def changed() -> dict[str, Any]:
            value: dict[str, Any] = original()
            value["job_schema"] = 2
            return value

        monkeypatch.setattr(service, "policy", changed)
    final = wait_job(client, job["id"])
    assert final["status"] == "failed" and final["reason_code"] == "tool_contract_changed"
    assert "mesh.json" not in final["artifacts"]
    assert final["started_at"] is not None
