"""Actual native two-mesh comparisons, mismatch/ownership guards and retained warnings."""

import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.domain.comparisons import ComparisonRequest
from app.domain.errors import DomainError
from app.jobs import service as jobs
from tests.native import test_step_import as step
from tests.native.test_local_jobs import prepared, submit, wait_job
from tests.native.test_mesh_controls import controls
from tests.unit.test_materials import custom
from worker.meshing import cross, dot, sub
from worker.postprocess.inspection import inspect_volume
from worker.postprocess.view import vector

application = step.application
client = step.client


def element_at(wire: dict[str, Any], point: list[float]) -> int:
    # Independent fixture locator only; product requires an explicit side.
    for eid, nodes in wire["elements"].items():
        p = [tuple(wire["nodes"][str(n)]) for n in nodes[:4]]
        a, b, c = (sub(p[k], p[0]) for k in (1, 2, 3))
        d = sub(vector(point), p[0])
        det = dot(a, cross(b, c))
        weights = [dot(d, cross(b, c)) / det, dot(a, cross(d, c)) / det, dot(a, cross(b, d)) / det]
        if min(*weights, 1 - sum(weights)) >= -1e-12 and max(weights) <= 1 + 1e-12:
            return int(eid)
    raise AssertionError("Physical fixture point is not in the retained mesh")


def request(
    run: dict[str, Any],
    first: dict[str, Any],
    second: dict[str, Any],
    body: str,
    field: str = "sxx",
) -> dict[str, Any]:
    locations: list[list[float]] = [[0.25, 0.25, 0.25], [0, 0, 0]]
    return {
        "compared_run_id": run["id"],
        "field": field,
        "smoothed": False,
        "points": [
            {
                "label": f"Fixed physical sample {k}",
                "body_id": body,
                "point_m": p,
                "reference_element_id": element_at(first, p),
                "compared_element_id": element_at(second, p),
            }
            for k, p in enumerate(locations)
        ],
    }


def test_actual_two_mesh_analytical_comparison_and_all_refusal_paths(
    client: TestClient, application: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, geometry = prepared(client)
    mesh1 = wait_job(client, submit(client, path)["id"])
    run1 = wait_job(client, submit(client, path, mesh1["id"])["id"])
    controls(client, path, global_size=0.3)
    mesh2 = wait_job(client, submit(client, path)["id"])
    run2 = wait_job(client, submit(client, path, mesh2["id"])["id"])
    assert run1["status"] == run2["status"] == "succeeded"
    wires = [client.get(f"/api/v1/jobs/{r['id']}/artifacts/mesh.json").json() for r in (run1, run2)]
    assert len(wires[1]["elements"]) > len(wires[0]["elements"])
    payload = request(run2, wires[0], wires[1], geometry["bodies"][0]["id"])
    route = f"/api/v1/runs/{run1['id']}/comparisons"
    original = client.get(f"/api/v1/jobs/{run1['id']}/artifacts/results.json").content
    exported = []
    for field in ("sxx", "ux", "uz"):
        response = client.post(route, json=payload | {"field": field})
        assert response.status_code == 200, response.text
        data = response.json()
        assert (
            data["convergence_claim"] is False
            and data["reference"]["source"]["job_id"] == run1["id"]
        )
        for row in data["rows"]:
            p = row["sample"]["point_m"]
            expected = -1000 if field == "sxx" else -1000 * p[0] / 210e9 if field == "ux" else 0
            tolerance = 0.01 if field == "sxx" else 1e-13
            assert row["change"]["reference"] == pytest.approx(expected, abs=tolerance)
            assert row["change"]["compared"] == pytest.approx(expected, abs=tolerance)
            if abs(expected) <= data["reference_floor"]:
                assert row["change"]["relative_change"] is None
            assert row["reference"]["position_m"] == pytest.approx(p, abs=1e-12)
            assert row["compared"]["position_m"] == pytest.approx(p, abs=1e-12)
        exported.append(data)
    out = Path(".local/native/validation/T023")
    out.mkdir(parents=True, exist_ok=True)
    (out / "axial-comparisons.json").write_text(json.dumps(exported, indent=2) + "\n")
    for index, run in enumerate((run1, run2)):
        folder = out / f"run{index + 1}"
        folder.mkdir(exist_ok=True)
        for name in (
            "snapshot.json",
            "mesh.json",
            "analysis.inp",
            "analysis.dat",
            "analysis.frd",
            "results.json",
        ):
            (folder / name).write_bytes(
                client.get(f"/api/v1/jobs/{run['id']}/artifacts/{name}").content
            )
    assert client.get(f"/api/v1/jobs/{run1['id']}/artifacts/results.json").content == original
    assert client.post(route, json=payload, headers={"X-CSRF-Token": ""}).status_code == 403
    assert client.post(route, json=payload | {"compared_run_id": mesh2["id"]}).status_code == 409
    bad = {**payload, "points": [{**payload["points"][0], "body_id": "different-body"}]}
    assert client.post(route, json=bad).status_code == 422
    bad = {**payload, "points": [{**payload["points"][0], "point_m": [10, 10, 10]}]}
    assert client.post(route, json=bad).status_code == 422
    with pytest.raises(DomainError) as denied:
        application.state.job_service.compare_results(
            uuid4(), UUID(run1["id"]), ComparisonRequest.model_validate(payload)
        )
    assert denied.value.status == 404
    # Retained source expiry never falls back to a former successful comparison.
    blob = application.state.job_service.storage.blob_path(
        UUID(geometry["project_id"]), run2["artifacts"]["analysis.dat"]["sha256"]
    )
    raw = blob.read_bytes()
    blob.unlink()
    assert client.post(route, json=payload).status_code == 503
    blob.write_bytes(raw)
    real = inspect_volume
    calls = 0

    def delete_after_sampling(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        result = real(*args, **kwargs)
        calls += 1
        if calls == 2:
            project = client.get(f"/api/v1/projects/{geometry['project_id']}").json()
            assert (
                client.delete(
                    f"/api/v1/projects/{geometry['project_id']}",
                    headers={"If-Match": f'"{project["revision"]}"'},
                ).status_code
                == 204
            )
        return result

    monkeypatch.setattr(jobs, "inspect_volume", delete_after_sampling)
    assert client.post(route, json=payload).status_code == 404


def test_actual_yield_and_displacement_explanations_retained_in_comparison_export(
    client: TestClient,
) -> None:
    path, geometry = prepared(client)
    material = custom()
    material["material"]["values"].update(
        young_modulus=0.01, poisson_ratio=0, yield_strength=0.0005
    )
    assert (
        client.put(
            path + "/materials/" + geometry["bodies"][0]["id"],
            json=material,
            headers={"If-Match": '"4"'},
        ).status_code
        == 200
    )
    mesh = wait_job(client, submit(client, path)["id"])
    runs = [wait_job(client, submit(client, path, mesh["id"])["id"]) for _ in range(2)]
    assert all(r["status"] == "succeeded" for r in runs), runs
    wire = client.get(f"/api/v1/jobs/{runs[0]['id']}/artifacts/mesh.json").json()
    payload = request(runs[1], wire, wire, geometry["bodies"][0]["id"])
    response = client.post(f"/api/v1/runs/{runs[0]['id']}/comparisons", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()
    assert any("same mesh" in w for w in data["warnings"])
    for side in ("reference", "compared"):
        notes = {n["code"]: n for n in data[side]["assumptions"]}
        assert notes["yielding"]["triggered"] and notes["small_deformation"]["triggered"]
        assert notes["small_deformation"]["metric"] == pytest.approx(0.1, abs=1e-6)
        assert notes["stress_singularity"]["triggered"] is None
        assert any("does not model plastic" in w for w in data[side]["warnings"])
    out = Path(".local/native/validation/T023")
    out.mkdir(parents=True, exist_ok=True)
    (out / "warning-comparison.json").write_text(json.dumps(data, indent=2) + "\n")
