"""Real STEP -> saved loads -> isolated mesh -> downloaded CCX deck references."""

import json
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.native import test_step_import as step_tests
from tests.native.test_step_import import import_fixture
from tests.unit.test_materials import custom
from worker.benchmark import solve

application = step_tests.application
client = step_tests.client


def setup(client: TestClient, fixture: str = "cube-m.step") -> tuple[str, dict[str, Any]]:
    project, imported = import_fixture(client, fixture)
    geometry = client.post(
        f"/api/v1/geometry-imports/{imported['id']}/confirm",
        json={"dimensions_confirmed": True},
        headers={"If-Match": '"1"'},
    ).json()
    response = client.post(
        f"/api/v1/projects/{project}/analyses",
        json={"name": "Deck reference", "geometry_revision_id": geometry["id"]},
        headers={"If-Match": '"2"'},
    )
    assert response.status_code == 201, response.text
    path = f"/api/v1/analyses/{response.json()['id']}"
    for index, body in enumerate(geometry["bodies"], 1):
        material = custom()
        material["material"]["values"]["poisson_ratio"] = 0
        result = client.put(
            path + "/materials/" + body["id"], json=material, headers={"If-Match": f'"{index}"'}
        )
        assert result.status_code == 200, result.text
    return path, geometry


def assign(
    client: TestClient,
    path: str,
    geometry: dict[str, Any],
    kind: str,
    faces: list[str],
    **values: Any,
) -> dict[str, Any]:
    revision = client.get(path).json()["revision"]
    result = client.post(
        path + "/loads",
        headers={"If-Match": f'"{revision}"'},
        json={
            "assignment": {
                "name": kind,
                "kind": kind,
                "geometry_revision_id": geometry["id"],
                "face_ids": faces,
                **values,
            }
        },
    )
    assert result.status_code == 200, result.text
    state: dict[str, Any] = result.json()
    return state


def exported(client: TestClient, path: str) -> tuple[dict[str, Any], str]:
    revision = client.get(path).json()["revision"]
    result = client.post(path + "/deck-exports", headers={"If-Match": f'"{revision}"'})
    assert result.status_code == 201, result.text
    metadata = result.json()
    downloaded = client.get(f"/api/v1/deck-exports/{metadata['id']}/input")
    assert downloaded.status_code == 200, downloaded.text
    assert downloaded.headers["content-disposition"] == 'attachment; filename="analysis.inp"'
    return metadata, downloaded.text


@pytest.mark.parametrize(
    ("axis", "side", "pressure"),
    [(a, s, p) for a in range(3) for s in (0, 1) for p in (1000, -1000)],
)
def test_all_six_pressure_orientations_both_signs_and_actual_solver(
    client: TestClient, application: FastAPI, tmp_path: Path, axis: int, side: int, pressure: float
) -> None:
    path, geometry = setup(client)
    face = next(f for f in geometry["faces"] if abs(f["signature"]["center_m"][axis] - side) < 1e-9)
    fixed = next(
        f for f in geometry["faces"] if abs(f["signature"]["center_m"][axis] - (1 - side)) < 1e-9
    )
    assign(client, path, geometry, "fixed", [fixed["id"], fixed["id"]])
    state = assign(
        client,
        path,
        geometry,
        "pressure",
        [face["id"], face["id"]],
        units="m-N-Pa",
        pressure=pressure,
    )
    expected = [0.0, 0.0, 0.0]
    expected[axis] = pressure * (1 if side == 0 else -1)
    assert state["total_force_n"] == pytest.approx(expected, abs=1e-10)
    marker = state["markers"][-1]
    assert marker["direction"][axis] == (1 if expected[axis] > 0 else -1)
    assert len(state["setup"]["assignments"][-1]["face_ids"]) == 1
    metadata, deck = exported(client, path)
    assert "*DLOAD\n" in deck and "*CLOAD" not in deck
    assert metadata["summary"]["force_error_n"] < 1e-8
    repeated, again = exported(client, path)
    assert repeated == metadata and again == deck
    directory = tmp_path / "solve"
    directory.mkdir()
    displacement, stress, reactions = solve(directory, deck)
    mesh = json.loads(
        application.state.deck_service.storage.read(
            application.state.repository.get_analysis(
                application.state.owner, UUID(path.split("/")[-1])
            ).project_id,
            metadata["mesh_sha256"],
        )
    )
    nodes = {int(n): p for n, p in mesh["nodes"].items()}
    fixed_nodes = {n for f in mesh["boundary"][fixed["id"]] for n in f["nodes"]}
    reaction = [sum(reactions[n][k] for n in fixed_nodes) for k in range(3)]
    assert reaction == pytest.approx([-v for v in expected], abs=0.001)
    expected_stress = -pressure
    assert max(abs(row[2 + axis] - expected_stress) for row in stress) <= 0.01
    assert (
        max(
            abs(displacement[n][axis] - expected[axis] * abs(p[axis] - (1 - side)) / 210e9)
            for n, p in nodes.items()
        )
        <= 1e-13
    )
    evidence = Path(".local/native/validation/T010")
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / f"pressure-{axis}-{side}-{pressure}.json").write_text(
        json.dumps(
            {
                "metadata": metadata,
                "reaction_n": reaction,
                "expected_applied_n": expected,
                "max_raw_stress_error_pa": max(
                    abs(row[2 + axis] - expected_stress) for row in stress
                ),
            },
            indent=2,
        )
        + "\n"
    )


def test_two_body_total_force_dedup_units_and_frozen_history(
    client: TestClient, application: FastAPI, tmp_path: Path
) -> None:
    path, geometry = setup(client, "two-m.step")
    loaded, fixed = [], []
    for body in geometry["bodies"]:
        faces = [f for f in geometry["faces"] if f["body_id"] == body["id"]]
        loaded.append(max(faces, key=lambda f: f["signature"]["center_m"][0])["id"])
        fixed.append(min(faces, key=lambda f: f["signature"]["center_m"][0])["id"])
    assign(client, path, geometry, "fixed", fixed)
    state = assign(
        client, path, geometry, "force", loaded + loaded, units="m-N-Pa", force=[1000, 0, 0]
    )
    assert state["total_force_n"] == pytest.approx([1000, 0, 0], abs=1e-10)
    assert len(state["setup"]["assignments"][-1]["face_ids"]) == 2
    metadata, deck = exported(client, path)
    directory = tmp_path / "solve"
    directory.mkdir()
    _, _, reactions = solve(directory, deck)
    mesh = json.loads(
        application.state.deck_service.storage.read(
            UUID(geometry["project_id"]), metadata["mesh_sha256"]
        )
    )
    for ref in fixed:
        ns = {n for f in mesh["boundary"][ref] for n in f["nodes"]}
        assert sum(reactions[n][0] for n in ns) == pytest.approx(-500, abs=0.001)
    for unit in ("inch-lbf-psi", "mm-N-MPa", "m-N-Pa"):
        revision = client.get(path).json()["revision"]
        assert (
            client.patch(
                path + "/display-units",
                json={"preset": unit},
                headers={"If-Match": f'"{revision}"'},
            ).status_code
            == 200
        )
        _, after = exported(client, path)
        assert after == deck
    revision = client.get(path).json()["revision"]
    load = state["setup"]["assignments"][-1]
    assert (
        client.delete(
            path + "/loads/" + load["id"], headers={"If-Match": f'"{revision}"'}
        ).status_code
        == 200
    )
    assert client.get(f"/api/v1/deck-exports/{metadata['id']}/input").text == deck
    frozen = client.get(f"/api/v1/deck-exports/{metadata['id']}/snapshot").json()
    assert frozen["snapshot"]["loads"] == state["setup"]
    assert (
        client.get(path + f"/revisions/{state['analysis_revision']}/loads").json()["setup"]
        == state["setup"]
    )
