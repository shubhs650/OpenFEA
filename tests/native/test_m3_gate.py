"""M3's real bonded workflow through two meshes and all inspection derivatives."""

import hashlib
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.native import test_step_import as step
from tests.native.test_assembly import prepared
from tests.native.test_local_jobs import submit, wait_job
from tests.native.test_mesh_controls import controls
from tests.native.test_result_comparison import element_at
from worker.meshing import cross, norm, sub
from worker.runtime import ROOT

application = step.application
client = step.client


def side(wire: dict[str, Any], point: list[float], body: str) -> int:
    return element_at(
        wire
        | {"elements": {e: ns for e, ns in wire["elements"].items() if wire["owners"][e] == body}},
        point,
    )


def test_bonded_supports_fields_probes_sections_comparison_and_frozen_sources(
    client: TestClient,
) -> None:
    criteria = json.loads((ROOT / "tests/fixtures/native/result-comparison.json").read_text())
    u_tol, s_tol = criteria["axial_displacement_absolute_m"], criteria["axial_stress_absolute_pa"]
    path, geometry = prepared(client)
    bodies = [b["id"] for b in geometry["bodies"]]
    retained = ROOT / ".local/native/validation/T024/product"
    retained.mkdir(parents=True, exist_ok=True)
    runs: list[dict[str, Any]] = []
    wires: list[dict[str, Any]] = []
    identities: list[dict[str, Any]] = []
    inspections: list[dict[str, Any]] = []
    max_u = max_s = 0.0
    for index, local in enumerate(([], [{"kind": "body", "entity_id": bodies[1], "size": 0.4}]), 1):
        controls(client, path, global_size=0.6, local_sizes=local)
        mesh = wait_job(client, submit(client, path)["id"])
        assert mesh["status"] == "succeeded", mesh
        checked = client.post(
            path + "/assembly-preflight",
            json={"mesh_job_id": mesh["id"]},
            headers={"If-Match": f'"{client.get(path).json()["revision"]}"'},
        )
        assert checked.status_code == 200 and checked.json()["mesh_checked"], checked.text
        assert checked.json()["stability_proven"] is False
        run = wait_job(client, submit(client, path, mesh["id"])["id"])
        assert run["status"] == "succeeded", run
        folder = retained / f"run{index}"
        folder.mkdir(exist_ok=True)
        hashes = {}
        for name in (
            "snapshot.json",
            "mesh.json",
            "analysis.inp",
            "analysis.dat",
            "analysis.frd",
            "results.json",
            "assembly.json",
        ):
            downloaded = client.get(f"/api/v1/jobs/{run['id']}/artifacts/{name}")
            assert downloaded.status_code == 200, downloaded.text
            (folder / name).write_bytes(downloaded.content)
            hashes[name] = hashlib.sha256(downloaded.content).hexdigest()
            assert hashes[name] == run["artifacts"][name]["sha256"]
        wire = json.loads((folder / "mesh.json").read_text())
        raw = json.loads((folder / "results.json").read_text())
        assert raw["equilibrium"]["passed"]
        assert raw["assembly"]["max_tie_residual_m"] <= 2e-11
        deck = (folder / "analysis.inp").read_text()
        assert "*EQUATION" in deck and "*TIE" not in deck and "*SPRING" not in deck
        response = client.get(f"/api/v1/runs/{run['id']}/results")
        assert response.status_code == 200, response.text
        view = response.json()
        assert len(view["data"]["fields"]) == 14
        assert {v["body_id"] for v in view["data"]["vertices"]} == set(bodies)
        samples = []
        # Identical interface coordinates explicitly retain each independent body side.
        for body, x in ((bodies[0], 0.5), (bodies[1], 1.5), (bodies[0], 1.0), (bodies[1], 1.0)):
            point = [x, 0.25, 0.25]
            probe = client.post(
                f"/api/v1/runs/{run['id']}/probes",
                json={"element_id": side(wire, point, body), "point_m": point},
            )
            assert probe.status_code == 200, probe.text
            value = probe.json()["vertices"][0]
            assert value["body_id"] == body
            samples.append(probe.json())
        response = client.post(
            f"/api/v1/runs/{run['id']}/sections", json={"point_m": [0, 0.5, 0], "normal": [0, 1, 0]}
        )
        assert response.status_code == 200, response.text
        section = response.json()
        assert {v["body_id"] for v in section["vertices"]} == set(bodies)
        assert all(abs(v["position_m"][1] - 0.5) <= 1e-12 for v in section["vertices"])
        area = 0.0
        for tri in section["triangles"]:
            vertices = [section["vertices"][n] for n in tri]
            assert len({v["body_id"] for v in vertices}) == 1
            a, b, c = (tuple(v["position_m"]) for v in vertices)
            area += norm(cross(sub(b, a), sub(c, a))) / 2
        assert area == pytest.approx(2.0, abs=1e-11)
        for derivative in [view["data"], section, *samples]:
            for v in derivative["vertices"]:
                expected = [-1000 * v["position_m"][0] / 210e9, 0, 0]
                max_u = max(
                    max_u, *(abs(a - b) for a, b in zip(v["displacement_m"], expected, strict=True))
                )
                assert v["displacement_m"] == pytest.approx(expected, abs=u_tol)
                for mode in ("stress", "smoothed_stress"):
                    tensor = v[mode]["tensor_pa"]
                    max_s = max(
                        max_s,
                        *(abs(a - b) for a, b in zip(tensor, [-1000, 0, 0, 0, 0, 0], strict=True)),
                    )
                    assert tensor == pytest.approx([-1000, 0, 0, 0, 0, 0], abs=s_tol)
        identities.append(
            {
                "job": run,
                "hashes": hashes,
                "view_source": {k: v for k, v in view.items() if k != "data"},
                "section_area_m2": area,
            }
        )
        inspections.append({"probes": samples, "section": section})
        runs.append(run)
        wires.append(wire)
    assert len(wires[1]["elements"]) > len(wires[0]["elements"])
    comparisons = []
    for field in ("sxx", "ux", "uz"):
        points = [
            {
                "label": f"Body {i + 1} physical interior",
                "body_id": body,
                "point_m": p,
                "reference_element_id": side(wires[0], p, body),
                "compared_element_id": side(wires[1], p, body),
            }
            for i, (body, p) in enumerate(
                zip(bodies, [[0.5, 0.25, 0.25], [1.5, 0.25, 0.25]], strict=True)
            )
        ]
        response = client.post(
            f"/api/v1/runs/{runs[0]['id']}/comparisons",
            json={
                "compared_run_id": runs[1]["id"],
                "field": field,
                "smoothed": False,
                "points": points,
            },
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert not data["convergence_claim"]
        for row in data["rows"]:
            expected_value = (
                -1000
                if field == "sxx"
                else -1000 * row["sample"]["point_m"][0] / 210e9
                if field == "ux"
                else 0
            )
            for which in ("reference", "compared"):
                assert row[which]["body_id"] == row["sample"]["body_id"]
                assert row["change"][which] == pytest.approx(
                    expected_value, abs=s_tol if field == "sxx" else u_tol
                )
            if field == "uz":
                assert row["change"]["relative_change"] is None
        for which in ("reference", "compared"):
            assert {
                n["body_id"] for n in data[which]["assumptions"] if n["code"] == "yielding"
            } == set(bodies)
            assert data[which]["warnings"]
        comparisons.append(data)
    for run, identity in zip(runs, identities, strict=True):
        for name, digest in identity["hashes"].items():
            assert (
                hashlib.sha256(
                    client.get(f"/api/v1/jobs/{run['id']}/artifacts/{name}").content
                ).hexdigest()
                == digest
            )
    for name, value in {
        "identities": identities,
        "inspections": inspections,
        "comparisons": comparisons,
        "errors": {
            "max_displacement_error_m": max_u,
            "max_stress_error_pa": max_s,
            "criteria": criteria,
        },
    }.items():
        (retained / f"{name}.json").write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
