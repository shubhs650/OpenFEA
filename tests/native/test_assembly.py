"""Actual reviewed independent-body mortar -> immutable API deck/job/result validation."""

import json
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.native import test_step_import as step_tests
from tests.native.test_connections import inspect, request
from tests.native.test_face_decks import assign, setup
from tests.native.test_local_jobs import submit, wait_job

application = step_tests.application
client = step_tests.client


def prepared(
    client: TestClient,
    reverse: bool = False,
    fixture: str = "bond-zero-m.step",
    approve: bool = True,
) -> tuple[str, dict[str, Any]]:
    path, geometry = setup(client, fixture)
    start = next(f["id"] for f in geometry["faces"] if abs(f["signature"]["center_m"][0]) < 1e-12)
    end = max(geometry["faces"], key=lambda f: f["signature"]["center_m"][0])["id"]
    assign(client, path, geometry, "fixed", [start])
    assign(client, path, geometry, "pressure", [end], units="m-N-Pa", pressure=1000)
    if approve:
        pair = inspect(client, path)["report"]["pairs"][0]
        payload = request(geometry, pair)
        if reverse:
            payload["master_face_id"], payload["slave_face_id"] = (
                payload["slave_face_id"],
                payload["master_face_id"],
            )
        revision = client.get(path).json()["revision"]
        response = client.post(path + "/bonds", json=payload, headers={"If-Match": f'"{revision}"'})
        assert response.status_code == 200, response.text
    revision = client.get(path).json()["revision"]
    sized = client.put(
        path + "/mesh-controls",
        json={
            "units": "m-N-Pa",
            "global_size": 0.6,
            "local_sizes": [
                {"kind": "body", "entity_id": geometry["bodies"][1]["id"], "size": 0.4}
            ],
        },
        headers={"If-Match": f'"{revision}"'},
    )
    assert sized.status_code == 200, sized.text
    return path, geometry


@pytest.mark.parametrize("reverse", [False, True])
def test_reviewed_nonmatching_assembly_real_solve_has_complete_constraints_and_external_balance(
    client: TestClient, reverse: bool
) -> None:
    path, geometry = prepared(client, reverse)
    preview = client.get(path + "/loads").json()
    assert not preview["blockers"], preview
    assert len(preview["assembly"]["components"]) == 1
    assert preview["assembly"]["components"][0]["support_rank"] == 6
    assert not preview["assembly"]["stability_proven"]
    mesh = wait_job(client, submit(client, path)["id"])
    assert mesh["status"] == "succeeded", mesh
    revision = client.get(path).json()["revision"]
    before = client.get(path + "/jobs").json()
    checked = client.post(
        path + "/assembly-preflight",
        json={"mesh_job_id": mesh["id"]},
        headers={"If-Match": f'"{revision}"'},
    )
    assert checked.status_code == 200 and checked.json()["mesh_checked"], checked.text
    assert client.get(path + "/jobs").json() == before
    run = wait_job(client, submit(client, path, mesh["id"])["id"])
    assert run["status"] == "succeeded", run
    result = client.get(f"/api/v1/jobs/{run['id']}/artifacts/results.json").json()
    rawmesh = client.get(f"/api/v1/jobs/{mesh['id']}/artifacts/mesh.json").json()
    u = result["dat"]["displacements_m"]
    error = max(
        abs(value[a] - (-1000 * rawmesh["nodes"][n][0] / 210e9 if a == 0 else 0))
        for n, value in u.items()
        for a in range(3)
    )
    assert error <= 1e-13
    stress = max(
        abs(p["tensor_pa"][a] - (-1000 if a == 0 else 0))
        for p in result["integration_points"]
        for a in range(6)
    )
    assert stress <= 0.01
    assert result["equilibrium"]["passed"]
    assert result["assembly"]["max_tie_residual_m"] <= 2e-11
    assert result["assembly"]["expected_free_equations"] == run["summary"]["free_equations"]
    assert client.get(f"/api/v1/runs/{run['id']}/results").status_code == 200
    deck = client.get(f"/api/v1/jobs/{run['id']}/artifacts/analysis.inp").text
    assert "*EQUATION" in deck and "*TIE" not in deck and "*SPRING" not in deck
    artifact = client.get(f"/api/v1/jobs/{run['id']}/artifacts/assembly.json")
    assert artifact.status_code == 200
    output = Path(".local/native/validation/T020")
    output.mkdir(parents=True, exist_ok=True)
    (output / f"assembly-{'reverse' if reverse else 'forward'}.json").write_text(
        json.dumps(
            {
                "u_error_m": error,
                "stress_error_pa": stress,
                "assembly": result["assembly"],
                "equilibrium": result["equilibrium"],
            },
            indent=2,
        )
    )


def preflight(client: TestClient, path: str, mesh: str) -> dict[str, Any]:
    response = client.post(
        path + "/assembly-preflight",
        json={"mesh_job_id": mesh},
        headers={"If-Match": f'"{client.get(path).json()["revision"]}"'},
    )
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


def test_detached_loaded_body_is_refused_without_a_job_or_weak_springs(client: TestClient) -> None:
    path, _ = prepared(client, approve=False)
    state = client.get(path + "/loads").json()
    assert state["assembly"]["components"][1]["support_rank"] == 0
    assert any("Detached" in b for b in state["blockers"])
    mesh = wait_job(client, submit(client, path)["id"])
    assert mesh["status"] == "succeeded"
    before = client.get(path + "/jobs").json()
    checked = preflight(client, path, mesh["id"])
    assert checked["blockers"] and not checked["stability_proven"]
    response = client.post(
        path + "/runs",
        json={"mesh_job_id": mesh["id"]},
        headers={
            "If-Match": f'"{client.get(path).json()["revision"]}"',
            "Idempotency-Key": str(uuid4()),
        },
    )
    assert response.status_code == 422 and "rank 0/6" in response.json()["message"]
    assert client.get(path + "/jobs").json() == before


def test_connected_but_underconstrained_is_not_a_stability_pass(client: TestClient) -> None:
    path, geometry = prepared(client)
    fixed = next(
        a
        for a in client.get(path + "/loads").json()["setup"]["assignments"]
        if a["kind"] == "fixed"
    )
    revision = client.get(path).json()["revision"]
    assert (
        client.delete(
            path + "/loads/" + fixed["id"], headers={"If-Match": f'"{revision}"'}
        ).status_code
        == 200
    )
    assign(
        client,
        path,
        geometry,
        "displacement",
        fixed["face_ids"],
        units="m-N-Pa",
        axis="x",
        displacement=0,
    )
    state = client.get(path + "/loads").json()
    assert state["assembly"]["components"][0]["support_rank"] == 3
    assert any("underconstrained" in b for b in state["blockers"])


def test_slave_spc_conflict_is_a_real_mesh_refusal(client: TestClient) -> None:
    path, geometry = prepared(client)
    bond = client.get(path + "/bonds").json()["setup"]["assignments"][0]
    assign(
        client,
        path,
        geometry,
        "displacement",
        [bond["slave_face_id"]],
        units="m-N-Pa",
        axis="x",
        displacement=0,
    )
    mesh = wait_job(client, submit(client, path)["id"])
    assert mesh["status"] == "succeeded", mesh
    check = preflight(client, path, mesh["id"])
    assert not check["mesh_checked"] and "already constrained" in " ".join(check["blockers"])
    assert "analysis.inp" not in mesh["artifacts"]
    assert client.get(path + "/jobs").json()[-1]["kind"] == "mesh"


def test_physical_gap_remains_explicitly_blocked_after_review(client: TestClient) -> None:
    path, _ = prepared(client, fixture="bond-gap-m.step")
    state = client.get(path + "/loads").json()
    assert any("Physical-gap" in b for b in state["blockers"])
    mesh = wait_job(client, submit(client, path)["id"])
    assert mesh["status"] == "succeeded", mesh
    assert "Physical-gap" in " ".join(preflight(client, path, mesh["id"])["blockers"])


def test_b11_real_native_finite_output_is_diagnostic_only(tmp_path: Path) -> None:
    import shutil

    from worker.assembly_fixture import run_b11
    from worker.runtime import ROOT

    result = run_b11(tmp_path / "B11", development=True)
    assert result["status"].startswith("DEVELOPMENT PASS")
    assert "rank 0/6" in result["detached_refusal"]
    assert "rank 3/6" in result["underconstrained_refusal"]
    assert result["native"]["credited_as_result"] is False
    assert result["native"]["max_finite_native_displacement_m"] is not None
    assert result["weak_springs"] is False and result["stability_proven"] is False
    shutil.copytree(
        tmp_path / "B11", ROOT / ".local/native/validation/T020/B11", dirs_exist_ok=True
    )


def test_trace_cap_refuses_without_coarsening_or_dropping_nodes(client: TestClient) -> None:
    path, _ = prepared(client)
    revision = client.get(path).json()["revision"]
    response = client.put(
        path + "/mesh-controls",
        json={"units": "m-N-Pa", "global_size": 0.3},
        headers={"If-Match": f'"{revision}"'},
    )
    assert response.status_code == 200, response.text
    mesh = wait_job(client, submit(client, path)["id"])
    assert mesh["status"] == "succeeded", mesh
    assert "65 trace nodes" in " ".join(preflight(client, path, mesh["id"])["blockers"])
    assert client.get(path + "/mesh-controls").json()["setup"]["global_size_m"] == 0.3


def test_conflicting_displacement_never_overwrites_a_support(client: TestClient) -> None:
    path, geometry = prepared(client)
    fixed = next(
        a
        for a in client.get(path + "/loads").json()["setup"]["assignments"]
        if a["kind"] == "fixed"
    )
    before = client.get(path + "/loads").json()
    response = client.post(
        path + "/loads",
        json={
            "assignment": {
                "kind": "displacement",
                "name": "Conflict",
                "geometry_revision_id": geometry["id"],
                "face_ids": fixed["face_ids"],
                "units": "m-N-Pa",
                "axis": "x",
                "displacement": 0.001,
            }
        },
        headers={"If-Match": f'"{before["analysis_revision"]}"'},
    )
    assert response.status_code == 422 and response.json()["code"] == "conflicting_constraints", (
        response.text
    )
    assert client.get(path + "/loads").json() == before


def test_preflight_guards_owner_csrf_head_and_does_not_admit_work(client: TestClient) -> None:
    path, _ = prepared(client)
    mesh = wait_job(client, submit(client, path)["id"])
    revision = client.get(path).json()["revision"]
    assert (
        client.post(
            path + "/assembly-preflight",
            json={"mesh_job_id": mesh["id"]},
            headers={"If-Match": '"1"'},
        ).status_code
        == 409
    )
    assert (
        client.post(
            path + "/assembly-preflight",
            json={"mesh_job_id": mesh["id"]},
            headers={"If-Match": f'"{revision}"', "X-CSRF-Token": "bad"},
        ).status_code
        == 403
    )
    from uuid import UUID

    from app.domain.errors import DomainError

    service = cast(FastAPI, client.app).state.job_service
    with pytest.raises(DomainError) as error:
        service.assembly_preflight(uuid4(), UUID(path.split("/")[-1]), revision, UUID(mesh["id"]))
    assert error.value.status == 404
    assert len(client.get(path + "/jobs").json()) == 1


@pytest.mark.parametrize("fault", ["equation_count", "continuity"])
def test_native_bond_failure_cannot_publish_results(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    from tests.native.parser_faults import corrupt_parser

    path, _ = prepared(client)
    mesh = wait_job(client, submit(client, path)["id"])

    if fault == "equation_count":
        transform = 'summary["free_equations"] += 1'
    else:
        source = client.get(path + "/bonds").json()["setup"]["assignments"][0]["slave_face_id"]
        raw = client.get(f"/api/v1/jobs/{mesh['id']}/artifacts/mesh.json").json()
        node = raw["boundary"][source][0]["nodes"][0]
        transform = (
            'values=result["dat"]["displacements_m"]\n'
            f"values[{node}]=[values[{node}][0]+0.001,*values[{node}][1:]]"
        )
    corrupt_parser(monkeypatch, transform)
    run = wait_job(client, submit(client, path, mesh["id"])["id"])
    assert run["status"] == "failed" and run["reason_code"] == "invalid_output", run
    assert "results.json" not in run["artifacts"]
    assert all(
        name in run["artifacts"]
        for name in ("analysis.inp", "analysis.dat", "analysis.frd", "solver.log")
    )
    assert client.get(f"/api/v1/runs/{run['id']}/results").status_code == 409
