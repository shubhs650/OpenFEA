"""Real import/queue/CCX core results; no mocked native fields or statuses."""

import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.domain.errors import DomainError
from app.jobs import service as job_service
from tests.native import test_step_import as step_tests
from tests.native.test_face_decks import assign, setup
from tests.native.test_local_jobs import prepared, submit, wait_job
from tests.unit.test_materials import custom
from worker.postprocess.view import build_view

application = step_tests.application
client = step_tests.client


def view(client: TestClient, run: dict[str, Any]) -> dict[str, Any]:
    response = client.get(f"/api/v1/runs/{run['id']}/results")
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    assert result["input_sha256"] == run["input_sha256"]
    assert result["results_sha256"] == run["artifacts"]["results.json"]["sha256"]
    assert result["data"]["processor"] == "affine-c3d10-full-fields-v4"
    return result


def test_real_axial_core_results_reactions_frozen_yield_and_edit_history(
    client: TestClient, application: FastAPI
) -> None:
    path, geometry = prepared(client)
    mesh = wait_job(client, submit(client, path)["id"])
    run = wait_job(client, submit(client, path, mesh["id"])["id"])
    result = view(client, run)
    data = result["data"]
    expected_u = 1000 / 210e9
    assert data["displacement"]["maximum"]["value"] == pytest.approx(expected_u, abs=1e-13)
    assert data["von_mises"]["maximum"]["value"] == pytest.approx(1000, abs=0.01)
    assert all(v["von_mises_pa"] == pytest.approx(1000, abs=0.01) for v in data["vertices"])
    assert data["yield_factors"][0]["minimum"] == pytest.approx(250000, rel=1e-5)
    assert data["reaction_force_n"] == pytest.approx([1000, 0, 0], abs=0.001)
    assert data["reaction_moment_nm"] == pytest.approx([0, 500, -500], abs=0.001)
    fields = {f["key"]: f for f in data["fields"]}
    assert len(fields) == 14
    for vertex in data["vertices"]:
        for mode in ["stress", "smoothed_stress"]:
            assert vertex[mode]["tensor_pa"] == pytest.approx([-1000, 0, 0, 0, 0, 0], abs=0.01)
            assert vertex[mode]["principal_pa"] == pytest.approx([0, 0, -1000], abs=0.01)
        assert vertex["displacement_m"][0] == pytest.approx(
            -1000 * vertex["position_m"][0] / 210e9, abs=1e-13
        )
    assert fields["ux"]["extrema"]["minimum"]["value"] == pytest.approx(-expected_u, abs=1e-13)
    assert fields["sxx"]["extrema"]["minimum"]["value"] == pytest.approx(-1000, abs=0.01)
    raw_names = ["snapshot.json", "analysis.inp", "analysis.dat", "analysis.frd", "results.json"]
    originals = {
        n: client.get(f"/api/v1/jobs/{run['id']}/artifacts/{n}").content for n in raw_names
    }
    out = Path(".local/native/validation/T021")
    out.mkdir(parents=True, exist_ok=True)
    (out / "axial-view.json").write_text(json.dumps(result, indent=2) + "\n")
    original = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
    changed = custom()
    changed["material"]["values"].pop("yield_strength")
    assert (
        client.put(
            path + "/materials/" + geometry["bodies"][0]["id"],
            json=changed,
            headers={"If-Match": '"4"'},
        ).status_code
        == 200
    )
    assert (
        hashlib.sha256(json.dumps(view(client, run), sort_keys=True).encode()).hexdigest()
        == original
    )
    assert {
        n: client.get(f"/api/v1/jobs/{run['id']}/artifacts/{n}").content for n in raw_names
    } == originals
    later = wait_job(client, submit(client, path, mesh["id"])["id"])
    assert view(client, later)["data"]["yield_factors"][0]["state"] == "unavailable"
    output = Path(".local/native/validation/T012")
    output.mkdir(parents=True, exist_ok=True)
    (output / "axial.json").write_text(
        json.dumps(
            {
                "run": run["id"],
                "data": {k: v for k, v in data.items() if k not in {"vertices", "triangles"}},
                "displacement_error_m": abs(data["displacement"]["maximum"]["value"] - expected_u),
                "vm_error_pa": abs(data["von_mises"]["maximum"]["value"] - 1000),
                "max_contour_error_pa": max(
                    abs(v["von_mises_pa"] - 1000) for v in data["vertices"]
                ),
            },
            indent=2,
        )
        + "\n"
    )


def test_actual_planar_bracket_import_to_result_extrema_and_reactions(client: TestClient) -> None:
    path, geometry = setup(client, "bracket-m.step")
    assert (
        client.put(
            path + "/materials/" + geometry["bodies"][0]["id"],
            json=custom(),
            headers={"If-Match": '"2"'},
        ).status_code
        == 200
    )
    fixed = next(
        f["id"] for f in geometry["faces"] if abs(f["signature"]["center_m"][2] - 0.06) < 1e-10
    )
    loaded = next(
        f["id"] for f in geometry["faces"] if abs(f["signature"]["center_m"][0] - 0.08) < 1e-10
    )
    assign(client, path, geometry, "fixed", [fixed])
    assign(client, path, geometry, "force", [loaded], force=[0, 0, -10], units="m-N-Pa")
    mesh = wait_job(client, submit(client, path)["id"])
    run = wait_job(client, submit(client, path, mesh["id"])["id"])
    result = view(client, run)
    raw = client.get(f"/api/v1/jobs/{run['id']}/artifacts/results.json").json()
    data = result["data"]
    assert data["reaction_force_n"] == pytest.approx([0, 0, 10], abs=0.001)
    # Independent inverse four-point Gauss formula; include ALL volume elements,
    # not just boundary incidences, before equal weighting at a matching node.
    wire = client.get(f"/api/v1/jobs/{run['id']}/artifacts/mesh.json").json()
    by_element: dict[int, dict[int, list[float]]] = {}
    for point in raw["integration_points"]:
        by_element.setdefault(point["element_id"], {})[point["integration_point_id"]] = point[
            "tensor_pa"
        ]
    contributions: dict[int, list[list[float]]] = {}
    for eid, nodes in wire["elements"].items():
        gauss = by_element[int(eid)]
        mean = [sum(gauss[i][k] for i in (1, 2, 3, 4)) / 4 for k in range(6)]
        corners = [
            [5**0.5 * gauss[i][k] + (1 - 5**0.5) * mean[k] for k in range(6)] for i in (1, 2, 3, 4)
        ]
        nodal = corners + [
            [(corners[a][k] + corners[b][k]) / 2 for k in range(6)]
            for a, b in [(0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3)]
        ]
        for n, t in zip(nodes, nodal, strict=True):
            contributions.setdefault(n, []).append(t)
    averaging_errors: list[float] = []
    changes: list[float] = []
    for vertex in data["vertices"]:
        values = contributions[vertex["node_id"]]
        expected = [sum(t[k] for t in values) / len(values) for k in range(6)]
        actual = vertex["smoothed_stress"]["tensor_pa"]
        assert actual == pytest.approx(expected, rel=1e-10, abs=1e-8)
        assert vertex["smoothed_contributions"] == len(values)
        averaging_errors.extend(abs(a - b) for a, b in zip(actual, expected, strict=True))
        changes.extend(
            abs(a - b) for a, b in zip(actual, vertex["stress"]["tensor_pa"], strict=True)
        )
    assert max(changes) > 1e-3  # A real varying field exercises the averaging toggle.
    retained = Path(".local/native/validation/T021")
    retained.mkdir(parents=True, exist_ok=True)
    (retained / "bracket-view.json").write_text(json.dumps(result, indent=2) + "\n")
    (retained / "smoothing-reference.json").write_text(
        json.dumps(
            {
                "method": "Independent inverse four-point Gauss extrapolation, "
                "then all-incident equal tensor mean",
                "max_tensor_error_pa": max(averaging_errors),
                "max_visible_tensor_change_pa": max(changes),
                "relative_criterion": 1e-10,
                "absolute_floor_pa": 1e-8,
            },
            indent=2,
        )
        + "\n"
    )
    # F applied at (0.08,0.01,0.005): applied moment (-0.1,0.8,0) N m.
    assert data["reaction_moment_nm"] == pytest.approx([0.1, -0.8, 0], abs=0.0001)
    assert data["displacement"]["maximum"]["value"] > 0
    assert data["von_mises"]["maximum"]["value"] > 0
    node = str(data["displacement"]["maximum"]["node_id"])
    import math

    assert data["displacement"]["maximum"]["value"] == math.hypot(
        *raw["dat"]["displacements_m"][node]
    )
    sample = data["von_mises"]["maximum"]
    assert any(
        p["element_id"] == sample["element_id"]
        and p["integration_point_id"] == sample["integration_point_id"]
        for p in raw["integration_points"]
    )
    output = Path(".local/native/validation/T012")
    output.mkdir(parents=True, exist_ok=True)
    (output / "bracket.json").write_text(
        json.dumps(
            {
                "run": run["id"],
                "nodes": run["summary"]["nodes"],
                "elements": run["summary"]["elements"],
                "displacement": data["displacement"],
                "von_mises": data["von_mises"],
                "reaction_force_n": data["reaction_force_n"],
                "reaction_moment_nm": data["reaction_moment_nm"],
            },
            indent=2,
        )
        + "\n"
    )


@pytest.mark.parametrize("pressure", [0, 1e-10])
def test_actual_zero_or_essentially_zero_stress_has_no_finite_factor(
    client: TestClient, pressure: float
) -> None:
    path, geometry = setup(client)
    fixed = next(f["id"] for f in geometry["faces"] if f["signature"]["center_m"][0] == 0)
    loaded = next(f["id"] for f in geometry["faces"] if f["signature"]["center_m"][0] == 1)
    assign(client, path, geometry, "fixed", [fixed])
    assign(client, path, geometry, "pressure", [loaded], pressure=pressure or 1000, units="m-N-Pa")
    if pressure == 0:
        assign(
            client,
            path,
            geometry,
            "pressure",
            [loaded],
            pressure=-1000,
            units="m-N-Pa",
            combine_confirmed=True,
        )
    mesh = wait_job(client, submit(client, path)["id"])
    run = wait_job(client, submit(client, path, mesh["id"])["id"])
    factor = view(client, run)["data"]["yield_factors"][0]
    assert factor["state"] == "unbounded" and factor["minimum"] is None


def test_result_api_refuses_unfinished_mesh_foreign_tombstone_and_corruption(
    client: TestClient, application: FastAPI
) -> None:
    path, geometry = prepared(client)
    mesh = wait_job(client, submit(client, path)["id"])
    assert client.get(f"/api/v1/runs/{mesh['id']}/results").status_code == 409
    run = wait_job(client, submit(client, path, mesh["id"])["id"])
    assert view(client, run)
    with pytest.raises(DomainError) as denied:
        application.state.job_service.result_view(uuid4(), UUID(run["id"]))
    assert denied.value.status == 404
    storage = application.state.job_service.storage
    dat_blob = storage.blob_path(
        UUID(geometry["project_id"]), run["artifacts"]["analysis.dat"]["sha256"]
    )
    original_dat = dat_blob.read_bytes()
    dat_blob.chmod(0o600)
    dat_blob.write_bytes(b"damaged DAT\n")
    assert client.get(f"/api/v1/runs/{run['id']}/results").status_code == 503
    dat_blob.write_bytes(original_dat)
    assert view(client, run)
    blob = storage.blob_path(
        UUID(geometry["project_id"]), run["artifacts"]["results.json"]["sha256"]
    )
    blob.chmod(0o600)
    blob.write_bytes(b"{}")
    assert client.get(f"/api/v1/runs/{run['id']}/results").status_code == 503
    project = client.get(f"/api/v1/projects/{geometry['project_id']}").json()
    assert (
        client.delete(
            f"/api/v1/projects/{geometry['project_id']}",
            headers={"If-Match": f'"{project["revision"]}"'},
        ).status_code
        == 204
    )
    assert client.get(f"/api/v1/runs/{run['id']}/results").status_code == 404


def test_real_pressure_touching_support_subtracts_applied_nodal_force(client: TestClient) -> None:
    path, geometry = setup(client)
    fixed = next(f["id"] for f in geometry["faces"] if f["signature"]["center_m"][0] == 0)
    loaded = next(f["id"] for f in geometry["faces"] if f["signature"]["center_m"][1] == 1)
    assign(client, path, geometry, "fixed", [fixed])
    assign(client, path, geometry, "pressure", [loaded], pressure=1000, units="m-N-Pa")
    mesh = wait_job(client, submit(client, path)["id"])
    run = wait_job(client, submit(client, path, mesh["id"])["id"])
    data = view(client, run)["data"]
    assert data["reaction_force_n"] == pytest.approx([0, 1000, 0], abs=0.001)
    assert data["reaction_moment_nm"] == pytest.approx([-500, 0, 500], abs=0.001)


def test_real_two_body_contours_and_yield_keep_material_sides_separate(client: TestClient) -> None:
    path, geometry = setup(client, "two-m.step")
    for i, body in enumerate(geometry["bodies"]):
        material = custom()
        material["material"]["values"].update(
            young_modulus=210000 / (i + 1), poisson_ratio=0, yield_strength=250 / (i + 1)
        )
        revision = client.get(path).json()["revision"]
        assert (
            client.put(
                path + "/materials/" + body["id"],
                json=material,
                headers={"If-Match": f'"{revision}"'},
            ).status_code
            == 200
        )
        faces = [f for f in geometry["faces"] if f["body_id"] == body["id"]]
        fixed = min(faces, key=lambda f: f["signature"]["center_m"][0])
        loaded = max(faces, key=lambda f: f["signature"]["center_m"][0])
        assign(client, path, geometry, "fixed", [fixed["id"]])
        assign(
            client,
            path,
            geometry,
            "pressure",
            [loaded["id"]],
            units="m-N-Pa",
            pressure=1000 * (i + 1),
        )
    mesh = wait_job(client, submit(client, path)["id"])
    run = wait_job(client, submit(client, path, mesh["id"])["id"])
    data = view(client, run)["data"]
    for i, body in enumerate(geometry["bodies"]):
        vertices = [v for v in data["vertices"] if v["body_id"] == body["id"]]
        assert vertices and all(v["material_id"] == f"M{i + 1}" for v in vertices)
        assert all(v["von_mises_pa"] == pytest.approx(1000 * (i + 1), abs=0.01) for v in vertices)
        for v in vertices:
            for mode in ["stress", "smoothed_stress"]:
                assert v[mode]["tensor_pa"] == pytest.approx(
                    [-1000 * (i + 1), 0, 0, 0, 0, 0], abs=0.01
                )
                assert v[mode]["principal_pa"] == pytest.approx([0, 0, -1000 * (i + 1)], abs=0.01)
        factor = next(f for f in data["yield_factors"] if f["body_id"] == body["id"])
        assert factor["minimum"] == pytest.approx(250000 / (i + 1) ** 2, rel=1e-5)
    assert data["reaction_force_n"] == pytest.approx([3000, 0, 0], abs=0.001)


def test_tombstone_during_actual_result_derivation_prevents_publication(
    client: TestClient, application: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, geometry = prepared(client)
    mesh = wait_job(client, submit(client, path)["id"])
    run = wait_job(client, submit(client, path, mesh["id"])["id"])
    original = build_view

    def delete_after_derivation(*args: Any) -> dict[str, Any]:
        data = original(*args)
        project = client.get(f"/api/v1/projects/{geometry['project_id']}").json()
        assert (
            client.delete(
                f"/api/v1/projects/{geometry['project_id']}",
                headers={"If-Match": f'"{project["revision"]}"'},
            ).status_code
            == 204
        )
        return data

    monkeypatch.setattr(job_service, "build_view", delete_after_derivation)
    assert client.get(f"/api/v1/runs/{run['id']}/results").status_code == 404
