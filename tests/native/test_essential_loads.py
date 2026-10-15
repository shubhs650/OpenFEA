"""Actual owned STEP/setup/mesh/CCX B03-B05 and global component/gravity workflows."""

import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.domain.errors import DomainError
from app.domain.loads import LoadAssignment, LoadSetup, load_state
from tests.benchmark_review import unsigned_manifest
from tests.native import test_step_import as step_tests
from tests.native.test_face_decks import assign, setup
from tests.native.test_local_jobs import submit, wait_job
from tests.native.test_mesh_controls import controls
from tests.unit.test_materials import custom
from worker.benchmark import run_case
from worker.calculix.results import StressPoint
from worker.essential_benchmarks import evaluate
from worker.local_solve import result_mesh, validate_outputs

application = step_tests.application
client = step_tests.client


def save(client: TestClient, path: str, item: dict[str, Any]) -> dict[str, Any]:
    response = client.post(
        path + "/loads",
        json={"assignment": item},
        headers={"If-Match": f'"{client.get(path).json()["revision"]}"'},
    )
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


def body_gravity(
    client: TestClient,
    path: str,
    geometry: dict[str, Any],
    body_ids: list[str] | None = None,
    acceleration: list[float] | None = None,
    **values: Any,
) -> dict[str, Any]:
    return save(
        client,
        path,
        {
            "kind": "gravity",
            "name": "Body acceleration",
            "geometry_revision_id": geometry["id"],
            "body_ids": body_ids or [b["id"] for b in geometry["bodies"]],
            "units": "m-N-Pa",
            "acceleration": acceleration or [0, 0, -9.80665],
            **values,
        },
    )


def face_ref(geometry: dict[str, Any], axis: int, value: float) -> str:
    return str(
        next(
            f["id"]
            for f in geometry["faces"]
            if abs(f["signature"]["center_m"][axis] - value) < 1e-10
        )
    )


def compute(
    client: TestClient, path: str
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str]:
    mesh = wait_job(client, submit(client, path)["id"])
    assert mesh["status"] == "succeeded", mesh
    run = wait_job(client, submit(client, path, mesh["id"])["id"])
    assert run["status"] == "succeeded", run
    data = client.get(f"/api/v1/jobs/{run['id']}/artifacts/results.json").json()
    raw_mesh = client.get(f"/api/v1/jobs/{run['id']}/artifacts/mesh.json").json()
    deck = client.get(f"/api/v1/jobs/{run['id']}/artifacts/analysis.inp").text
    view = client.get(f"/api/v1/runs/{run['id']}/results")
    assert view.status_code == 200, view.text
    assert view.json()["data"]["equilibrium"] == data["equilibrium"]
    return run, data, raw_mesh, deck


@pytest.mark.parametrize("case", ["B03", "B04", "B05"])
@pytest.mark.parametrize("index", [0, 1])
def test_real_api_essential_benchmarks_match_predeclared_all_node_ip_and_reaction_references(
    client: TestClient,
    case: str,
    index: int,
) -> None:
    manifest = json.loads(Path(f"tests/benchmarks/{case}.json").read_bytes())
    path, geometry = setup(client, "cantilever-m.step" if case == "B03" else "cube-m.step")
    material = custom()
    material["material"]["values"]["poisson_ratio"] = manifest["material"]["nu"]
    material["material"]["values"]["density"] = (
        manifest["material"].get("density_kg_m3", 7850) / 1e12
    )
    response = client.put(
        path + "/materials/" + geometry["bodies"][0]["id"],
        json=material,
        headers={"If-Match": f'"{client.get(path).json()["revision"]}"'},
    )
    assert response.status_code == 200, response.text
    size = manifest["mesh_sizes_m"][index]
    controls(client, path, global_size=size, curvature_elements=0)
    tip = None
    if case == "B03":
        assign(client, path, geometry, "fixed", [face_ref(geometry, 0, 0)])
        tip = face_ref(geometry, 0, 1)
        assign(client, path, geometry, "force", [tip], units="m-N-Pa", force=[0, -1, 0])
    elif case == "B04":
        for axis, name in enumerate("xyz"):
            assign(
                client,
                path,
                geometry,
                "displacement",
                [face_ref(geometry, axis, 0)],
                units="m-N-Pa",
                axis=name,
                displacement=0,
            )
        assign(
            client,
            path,
            geometry,
            "pressure",
            [face_ref(geometry, a, 1) for a in range(3)],
            units="m-N-Pa",
            pressure=1000,
        )
    else:
        assign(client, path, geometry, "fixed", [face_ref(geometry, 2, 0)])
        state = body_gravity(client, path, geometry)
        assert state["previews"][-1]["mass_kg"] == pytest.approx(7850, abs=1e-10)
        assert state["total_force_n"] == pytest.approx([0, 0, -76982.2025], abs=1e-8)
    assert not client.get(path + "/loads").json()["blockers"]
    run, data, mesh, deck = compute(client, path)
    written = result_mesh(mesh, {geometry["bodies"][0]["id"]: "M1"})
    checked = evaluate(
        manifest,
        written,
        mesh["boundary"],
        data["dat"],
        [StressPoint(**p) for p in data["integration_points"]],
        data["equilibrium"],
        tip,
    )
    if case == "B05":
        assert "*DENSITY\n7.850000000000e+03" in deck
        assert "M1,GRAV,9.806650000000e+00,0,0,-1" in deck and "*CLOAD" not in deck
    evidence = Path(".local/native/validation/T015")
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / f"{case}-api-{index + 1}.json").write_text(
        json.dumps(
            {
                "run": run["id"],
                "nodes": len(mesh["nodes"]),
                "elements": len(mesh["elements"]),
                "mesh_size_m": size,
                "manifest": manifest,
                "measurements": checked,
                "artifacts": run["artifacts"],
            },
            indent=2,
        )
        + "\n"
    )


@pytest.mark.parametrize("case", ["B03", "B04", "B05"])
def test_real_cli_essential_benchmark_is_development_only_and_unsigned_refuses_before_output(
    case: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with unsigned_manifest(monkeypatch, case), pytest.raises(ValueError, match="Engineering-owner"):
        run_case(case, tmp_path / "unapproved")
    assert not (tmp_path / "unapproved").exists()
    result = run_case(case, tmp_path / "development", development=True)
    assert (
        result["status"] == "DEVELOPMENT PASS; owner acceptance pending"
        and len(result["runs"]) == 2
    )
    assert all(r["equilibrium"]["passed"] for r in result["runs"])


def test_nonzero_prescribed_displacement_drives_real_reactions_and_free_components(
    client: TestClient,
) -> None:
    path, geometry = setup(client)
    assign(client, path, geometry, "fixed", [face_ref(geometry, 0, 0)])
    assign(
        client,
        path,
        geometry,
        "displacement",
        [face_ref(geometry, 0, 1)],
        units="m-N-Pa",
        axis="x",
        displacement=1e-6,
    )
    _, data, mesh, deck = compute(client, path)
    assert "*STATIC\n*BOUNDARY" in deck and "*CLOAD" not in deck
    for n, p in mesh["nodes"].items():
        assert data["dat"]["displacements_m"][n] == pytest.approx([p[0] * 1e-6, 0, 0], abs=1e-12)
    for p in data["integration_points"]:
        assert p["tensor_pa"] == pytest.approx([210000, 0, 0, 0, 0, 0], abs=0.01)
    assert data["equilibrium"]["applied_force_n"] == [0, 0, 0]
    assert data["equilibrium"]["prescribed_actuator_reference_n"] == pytest.approx(210000, abs=0.01)
    assert data["equilibrium"]["force"]["criterion"] == "relative"


def test_pressure_on_all_six_faces_is_self_equilibrated_without_zero_net_normalizer(
    client: TestClient,
) -> None:
    path, geometry = setup(client)
    material = custom()
    material["material"]["values"]["poisson_ratio"] = 0.3
    assert (
        client.put(
            path + "/materials/" + geometry["bodies"][0]["id"],
            json=material,
            headers={"If-Match": '"2"'},
        ).status_code
        == 200
    )
    for axis, name in enumerate("xyz"):
        assign(
            client,
            path,
            geometry,
            "displacement",
            [face_ref(geometry, axis, 0)],
            units="m-N-Pa",
            axis=name,
            displacement=0,
        )
    state = assign(
        client,
        path,
        geometry,
        "pressure",
        [f["id"] for f in geometry["faces"]],
        units="m-N-Pa",
        pressure=1000,
    )
    assert state["total_force_n"] == pytest.approx([0, 0, 0], abs=1e-10)
    assert state["force_scale_n"] == pytest.approx(6000, abs=1e-10)
    _, data, _, _ = compute(client, path)
    eq = data["equilibrium"]
    assert (
        eq["force"]["reference"] == pytest.approx(6000, abs=1e-10)
        and eq["force"]["criterion"] == "relative"
    )
    assert eq["reaction_force_n"] == pytest.approx([0, 0, 0], abs=0.001)
    assert eq["force"]["relative_residual"] < 1e-6


def test_real_near_zero_load_reports_absolute_equilibrium_without_division(
    client: TestClient,
) -> None:
    path, geometry = setup(client)
    assign(client, path, geometry, "fixed", [face_ref(geometry, 0, 0)])
    assign(
        client,
        path,
        geometry,
        "force",
        [face_ref(geometry, 0, 1)],
        units="m-N-Pa",
        force=[5e-8, 0, 0],
    )
    _, data, _, _ = compute(client, path)
    assert data["equilibrium"]["force"]["criterion"] == "absolute"
    assert data["equilibrium"]["force"]["relative_residual"] is None


def test_partial_constraint_leaves_other_force_component_admissible_and_conflicts_refuse(
    client: TestClient,
) -> None:
    path, geometry = setup(client)
    fixed = face_ref(geometry, 0, 0)
    loaded = face_ref(geometry, 0, 1)
    assign(client, path, geometry, "fixed", [fixed])
    assign(
        client, path, geometry, "displacement", [loaded], units="m-N-Pa", axis="y", displacement=0
    )
    assign(client, path, geometry, "force", [loaded], units="m-N-Pa", force=[1000, 0, 0])
    _, data, _, _ = compute(client, path)
    assert data["equilibrium"]["reaction_force_n"] == pytest.approx([-1000, 0, 0], abs=0.001)
    revision = client.get(path).json()["revision"]
    response = client.post(
        path + "/loads",
        json={
            "assignment": {
                "kind": "displacement",
                "name": "conflict",
                "geometry_revision_id": geometry["id"],
                "face_ids": [fixed],
                "units": "m-N-Pa",
                "axis": "x",
                "displacement": 1e-6,
            }
        },
        headers={"If-Match": f'"{revision}"'},
    )
    assert response.status_code == 422 and response.json()["code"] == "conflicting_constraints"
    assert client.get(path).json()["revision"] == revision


def test_gravity_targets_one_body_and_unloaded_body_needs_no_density(client: TestClient) -> None:
    path, geometry = setup(client, "two-m.step")
    first, second = [b["id"] for b in geometry["bodies"]]
    assign(client, path, geometry, "fixed", [face_ref(geometry, 0, 0), face_ref(geometry, 0, 2)])
    material = custom()
    material["material"]["values"].pop("density")
    assert (
        client.put(
            path + "/materials/" + second,
            json=material,
            headers={"If-Match": f'"{client.get(path).json()["revision"]}"'},
        ).status_code
        == 200
    )
    state = body_gravity(client, path, geometry, [first])
    assert not state["blockers"] and state["previews"][-1]["mass_kg"] == pytest.approx(
        7850, abs=1e-10
    )
    run, data, mesh, deck = compute(client, path)
    assert "M1,GRAV" in deck and "M2,GRAV" not in deck
    view = client.get(f"/api/v1/runs/{run['id']}/results").json()["data"]
    reactions = {b["body_id"]: b for b in view["reactions"]}
    assert reactions[first]["force_n"] == pytest.approx([0, 0, 76982.2025], abs=0.01)
    assert reactions[second]["force_n"] == pytest.approx([0, 0, 0], abs=1e-8)
    second_nodes = {
        n for e, ns in mesh["elements"].items() if mesh["owners"][e] == second for n in ns
    }
    assert all(
        data["dat"]["displacements_m"][str(n)] == pytest.approx([0, 0, 0], abs=1e-12)
        for n in second_nodes
    )


def test_live_density_removal_blocks_new_run_but_frozen_gravity_results_remain_exact(
    client: TestClient,
) -> None:
    path, geometry = setup(client)
    assign(client, path, geometry, "fixed", [face_ref(geometry, 2, 0)])
    body_gravity(client, path, geometry)
    run, _, _, _ = compute(client, path)
    route = f"/api/v1/runs/{run['id']}/results"
    original = client.get(route).json()
    material = custom()
    material["material"]["values"].pop("density")
    assert (
        client.put(
            path + "/materials/" + geometry["bodies"][0]["id"],
            json=material,
            headers={"If-Match": f'"{client.get(path).json()["revision"]}"'},
        ).status_code
        == 200
    )
    state = client.get(path + "/loads").json()
    assert not state["resultant_complete"] and any(
        "weight is unavailable" in b for b in state["blockers"]
    )
    response = client.post(
        path + "/runs",
        json={"mesh_job_id": run["mesh_job_id"]},
        headers={
            "If-Match": f'"{client.get(path).json()["revision"]}"',
            "Idempotency-Key": str(uuid4()),
        },
    )
    assert response.status_code == 422 and response.json()["code"] == "setup_incomplete"
    assert client.get(route).json() == original


def test_actual_mesh_shared_edge_conflict_refuses_even_without_cad_preflight(
    client: TestClient,
    application: FastAPI,
) -> None:
    from app.domain.deck_service import deck_for

    path, geometry = setup(client)
    assign(client, path, geometry, "fixed", [face_ref(geometry, 0, 0)])
    assign(
        client,
        path,
        geometry,
        "force",
        [face_ref(geometry, 0, 1)],
        units="m-N-Pa",
        force=[1000, 0, 0],
    )
    job = wait_job(client, submit(client, path)["id"])
    assert job["status"] == "succeeded", job
    mesh = client.get(f"/api/v1/jobs/{job['id']}/artifacts/mesh.json").json()
    service = application.state.deck_service
    snapshot, display = service.freeze(
        application.state.owner, UUID(path.split("/")[-1]), client.get(path).json()["revision"]
    )
    bad = LoadAssignment(
        id=uuid4(),
        name="Shared-edge conflict",
        kind="displacement",
        geometry_revision_id=snapshot.geometry.id,
        face_ids=[face_ref(geometry, 1, 0)],
        axis="x",
        displacement_m=1e-6,
    )
    snapshot = snapshot.model_copy(
        update={"loads": LoadSetup(assignments=[*snapshot.loads.assignments, bad])}
    )
    preview = load_state(
        snapshot.analysis, snapshot.geometry, snapshot.materials, snapshot.loads, display
    )
    with pytest.raises(DomainError) as error:
        deck_for(snapshot, mesh, preview)
    assert error.value.code == "conflicting_constraints"


def test_real_native_finish_and_coverage_cannot_publish_an_unbalanced_result(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.jobs import runner

    original = validate_outputs
    path, geometry = setup(client)
    assign(client, path, geometry, "fixed", [face_ref(geometry, 0, 0)])
    assign(
        client,
        path,
        geometry,
        "force",
        [face_ref(geometry, 0, 1)],
        units="m-N-Pa",
        force=[1000, 0, 0],
    )
    mesh = wait_job(client, submit(client, path)["id"])
    assert mesh["status"] == "succeeded", mesh

    def corrupt(*args: Any, **kwargs: Any) -> Any:
        result, summary = original(*args, **kwargs)
        raw_mesh = args[1]
        node = next(n for n, p in raw_mesh["nodes"].items() if p[0] == 0)
        actual = result["dat"]["external_forces_n"][int(node)]
        result["dat"]["external_forces_n"][int(node)] = (actual[0] + 100, actual[1], actual[2])
        return result, summary  # Explicit validator-boundary fault, never acceptance evidence.

    monkeypatch.setattr(runner, "validate_outputs", corrupt)
    run = wait_job(client, submit(client, path, mesh["id"])["id"])
    assert run["status"] == "failed" and run["reason_code"] == "equilibrium_failed", run
    assert run["summary"]["equilibrium"]["force"]["residual_norm"] > 99
    assert client.get(f"/api/v1/jobs/{run['id']}/artifacts/analysis.dat").status_code == 200
    assert client.get(f"/api/v1/runs/{run['id']}/results").status_code == 409


def test_cleanup_invalidates_body_gravity_undo_restores_and_body_review_rebinds(
    client: TestClient,
) -> None:
    from tests.native.test_geometry_edits import commit, preview

    path, geometry = setup(client, "hole-m.step")
    before = body_gravity(client, path, geometry)
    edit = preview(client, geometry, path)
    applied = commit(client, geometry, edit)
    blocked = client.get(path + "/loads").json()
    assert blocked["setup"]["assignments"][0]["review_bodies"] == [geometry["bodies"][0]["id"]]
    assert not blocked["resultant_complete"]
    response = client.post(
        path + "/mesh-jobs",
        json={},
        headers={
            "If-Match": f'"{client.get(path).json()["revision"]}"',
            "Idempotency-Key": str(uuid4()),
        },
    )
    assert response.status_code == 422
    undo = client.post(
        f"/api/v1/geometry-edits/{edit['id']}/undo",
        headers={"If-Match": f'"{applied["project"]["revision"]}"'},
    )
    assert undo.status_code == 200, undo.text
    restored = client.get(path + "/loads").json()
    assert (
        restored["total_force_n"] == before["total_force_n"]
        and not restored["setup"]["assignments"][0]["review_bodies"]
    )
    geometry = undo.json()["geometry"]
    edit = preview(client, geometry, path)
    applied = commit(client, geometry, edit)
    assignment = client.get(path + "/loads").json()["setup"]["assignments"][0]
    response = client.put(
        path + f"/loads/{assignment['id']}/bodies",
        json={
            "geometry_revision_id": applied["geometry"]["id"],
            "body_ids": [b["id"] for b in applied["geometry"]["bodies"]],
            "reviewed": True,
        },
        headers={"If-Match": f'"{client.get(path).json()["revision"]}"'},
    )
    assert response.status_code == 200, response.text
    reviewed = response.json()
    assert (
        reviewed["setup"]["assignments"][0]["source_acceleration"]
        == before["setup"]["assignments"][0]["source_acceleration"]
    )
    assert reviewed["total_force_n"] == pytest.approx([0, 0, -76982.2025], abs=1e-8)
