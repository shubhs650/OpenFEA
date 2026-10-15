"""Actual native CAD directions, node frames, CCX rotation and owned setup workflows."""

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.benchmark_review import unsigned_manifest
from tests.native import test_step_import as step_tests
from tests.native.test_essential_loads import compute, save
from tests.native.test_face_decks import setup
from tests.native.test_mesh_controls import controls
from tests.unit.test_materials import custom
from worker.calculix.results import StressPoint
from worker.direction_benchmarks import evaluate_rotation, placement
from worker.directions import local_vector
from worker.local_solve import result_mesh
from worker.meshing import sub

application = step_tests.application
client = step_tests.client


def local_face(geometry: dict[str, Any], axis: int, coordinate: float, rotated: bool) -> str:
    manifest = json.loads(Path("tests/benchmarks/B06.json").read_bytes())
    basis, translation = placement(manifest, rotated)
    return str(
        next(
            f["id"]
            for f in geometry["faces"]
            if abs(
                local_vector(sub(tuple(f["signature"]["center_m"]), translation), basis)[axis]
                - coordinate
            )
            < 1e-10
        )
    )


def patch(client: TestClient, rotated: bool, size: float) -> tuple[str, dict[str, Any]]:
    path, geometry = setup(client, "rotated-cube-m.step" if rotated else "cube-m.step")
    material = custom()
    material["material"]["values"]["poisson_ratio"] = 0.3
    response = client.put(
        path + "/materials/" + geometry["bodies"][0]["id"],
        json=material,
        headers={"If-Match": f'"{client.get(path).json()["revision"]}"'},
    )
    assert response.status_code == 200, response.text
    controls(client, path, global_size=size, curvature_elements=0)
    for axis in range(3):
        save(
            client,
            path,
            {
                "kind": "symmetry",
                "name": f"Plane {axis}",
                "geometry_revision_id": geometry["id"],
                "face_ids": [local_face(geometry, axis, 0, rotated)],
            },
        )
    ref = local_face(geometry, 0, 1, rotated)
    state = save(
        client,
        path,
        {
            "kind": "directional_force",
            "name": "Axial native normal",
            "geometry_revision_id": geometry["id"],
            "face_ids": [ref],
            "units": "m-N-Pa",
            "magnitude": 1000,
            "direction": {"kind": "plane_normal", "reference_id": ref, "reverse": False},
        },
    )
    assert not state["blockers"], state
    return path, geometry


@pytest.mark.parametrize("rotated", [False, True])
@pytest.mark.parametrize("index", [0, 1])
def test_real_api_rotation_checks_every_vector_tensor_invariant_and_external_span(
    client: TestClient, rotated: bool, index: int
) -> None:
    manifest = json.loads(Path("tests/benchmarks/B06.json").read_bytes())
    size = manifest["mesh_sizes_m"][index]
    path, geometry = patch(client, rotated, size)
    assert len(geometry["edges"]) == 12 and len(geometry["vertices"]) == 8
    run, data, mesh, deck = compute(client, path)
    written = result_mesh(mesh, {geometry["bodies"][0]["id"]: "M1"})
    measured = evaluate_rotation(
        manifest,
        rotated,
        written,
        data["dat"],
        [StressPoint(**s) for s in data["integration_points"]],
        data["equilibrium"],
    )
    if rotated:
        assert (
            "*TRANSFORM" in deck
            and "*NODE PRINT,NSET=NALL,GLOBAL=YES" in deck
            and "*NODE FILE,GLOBAL=YES" in deck
        )
    assert data["equilibrium"]["passed"]
    output = Path(".local/native/validation/T016")
    output.mkdir(parents=True, exist_ok=True)
    (output / f"B06-api-{int(rotated)}-{index + 1}.json").write_text(
        json.dumps(
            {
                "placement": rotated,
                "mesh_size_m": size,
                "nodes": len(mesh["nodes"]),
                "elements": len(mesh["elements"]),
                "measurements": measured,
                "manifest": manifest,
                "artifacts": run["artifacts"],
            },
            indent=2,
        )
        + "\n"
    )


def preview(
    client: TestClient, path: str, geometry: dict[str, Any], selection: dict[str, Any]
) -> dict[str, Any]:
    response = client.post(
        path + "/direction-previews",
        json={"geometry_revision_id": geometry["id"], "directions": [selection]},
        headers={"If-Match": f'"{client.get(path).json()["revision"]}"'},
    )
    assert response.status_code == 200, response.text
    return response.json()[0]  # type: ignore[no-any-return]


def remove_driver(client: TestClient, path: str) -> None:
    state = client.get(path + "/loads").json()
    driver = next(a for a in state["setup"]["assignments"] if a["kind"] == "directional_force")
    response = client.delete(
        path + "/loads/" + driver["id"], headers={"If-Match": f'"{state["analysis_revision"]}"'}
    )
    assert response.status_code == 200, response.text


def test_native_direction_catalog_reversal_cylinder_and_curved_symmetry_refusal(
    client: TestClient,
) -> None:
    path, geometry = setup(client, "cylinder-m.step")
    revision = client.get(path).json()["revision"]
    side = next(
        f
        for f in geometry["faces"]
        if str(f["signature"]["surface_type"]).endswith("GeomAbs_Cylinder")
    )
    selected = {"kind": "cylinder_axis", "reference_id": side["id"]}
    first = preview(client, path, geometry, selected)
    reverse = preview(client, path, geometry, selected | {"reverse": True})
    assert first["vector"] == pytest.approx([0, 0, 1], abs=1e-14)
    assert reverse["vector"] == pytest.approx([0, 0, -1], abs=1e-14)
    assert client.get(path).json()["revision"] == revision  # real read-only preview
    curved = next(e for e in geometry["edges"] if not e["curve_type"].endswith("GeomAbs_Line"))
    bad = client.post(
        path + "/direction-previews",
        json={
            "geometry_revision_id": geometry["id"],
            "directions": [{"kind": "straight_edge", "reference_id": curved["id"]}],
        },
        headers={"If-Match": f'"{revision}"'},
    )
    assert bad.status_code == 422 and bad.json()["code"] == "invalid_direction"
    planar = next(
        f
        for f in geometry["faces"]
        if str(f["signature"]["surface_type"]).endswith("GeomAbs_Plane")
    )
    state = save(
        client,
        path,
        {
            "kind": "displacement",
            "name": "Axis component",
            "geometry_revision_id": geometry["id"],
            "face_ids": [planar["id"]],
            "units": "mm-N-MPa",
            "displacement": 0,
            "direction": selected,
        },
    )
    assert state["setup"]["assignments"][-1]["direction"]["kind"] == "cylinder_axis"
    refused = client.post(
        path + "/loads",
        json={
            "assignment": {
                "kind": "symmetry",
                "name": "Curved refusal",
                "geometry_revision_id": geometry["id"],
                "face_ids": [side["id"]],
            }
        },
        headers={"If-Match": f'"{state["analysis_revision"]}"'},
    )
    assert refused.status_code == 422 and refused.json()["code"] == "invalid_direction"
    assert len(client.get(path + "/loads").json()["setup"]["assignments"]) == 1
    mesh = client.post(
        path + "/deck-exports", headers={"If-Match": f'"{state["analysis_revision"]}"'}
    )
    assert mesh.status_code == 422  # actual cylinder setup stays outside affine/planar solve


@pytest.mark.parametrize("reversed_load", [False, True])
def test_real_straight_edge_force_both_signs_preserve_magnitude_and_global_reactions(
    client: TestClient, reversed_load: bool
) -> None:
    from worker.directions import unit
    from worker.meshing import dot

    path, geometry = patch(client, True, 0.5)
    remove_driver(client, path)
    manifest = json.loads(Path("tests/benchmarks/B06.json").read_bytes())
    basis, _ = placement(manifest, True)
    edge = next(
        e
        for e in geometry["edges"]
        if e["start_m"] is not None
        and abs(dot(unit(sub(tuple(e["end_m"]), tuple(e["start_m"]))), basis[0])) > 1 - 1e-10
    )
    sign = dot(unit(sub(tuple(edge["end_m"]), tuple(edge["start_m"]))), basis[0]) < 0
    selection = {
        "kind": "straight_edge",
        "reference_id": edge["id"],
        "reverse": bool(sign) ^ reversed_load,
    }
    vector = preview(client, path, geometry, selection)["vector"]
    assert vector == pytest.approx([(-1 if reversed_load else 1) * v for v in basis[0]], abs=1e-12)
    state = save(
        client,
        path,
        {
            "kind": "directional_force",
            "name": "Edge sign",
            "geometry_revision_id": geometry["id"],
            "face_ids": [local_face(geometry, 0, 1, True)],
            "units": "m-N-Pa",
            "magnitude": 1000,
            "direction": selection,
        },
    )
    assert state["setup"]["assignments"][-1]["source_magnitude"] == 1000
    _, data, mesh, _ = compute(client, path)
    if reversed_load:
        manifest["force_n"] = -1000
    evaluate_rotation(
        manifest,
        True,
        result_mesh(mesh, {geometry["bodies"][0]["id"]: "M1"}),
        data["dat"],
        [StressPoint(**s) for s in data["integration_points"]],
        data["equilibrium"],
    )


def test_real_nonzero_directional_displacement_drives_rotated_patch_and_actuator_reference(
    client: TestClient,
) -> None:
    path, geometry = patch(client, True, 0.5)
    remove_driver(client, path)
    manifest = json.loads(Path("tests/benchmarks/B06.json").read_bytes())
    ref = local_face(geometry, 0, 1, True)
    save(
        client,
        path,
        {
            "kind": "displacement",
            "name": "Native imposed axial motion",
            "geometry_revision_id": geometry["id"],
            "face_ids": [ref],
            "units": "m-N-Pa",
            "displacement": 1000 / 210e9,
            "direction": {"kind": "plane_normal", "reference_id": ref},
        },
    )
    _, data, mesh, deck = compute(client, path)
    assert "*CLOAD" not in deck and "*BOUNDARY" in deck.split("*STEP")[1]
    assert data["equilibrium"]["prescribed_actuator_reference_n"] == pytest.approx(1000, abs=0.001)
    evaluate_rotation(
        manifest,
        True,
        result_mesh(mesh, {geometry["bodies"][0]["id"]: "M1"}),
        data["dat"],
        [StressPoint(**s) for s in data["integration_points"]],
        data["equilibrium"],
        driven=True,
    )


def test_actual_shared_vertices_deduplicate_symmetry_and_refuse_tiny_contradictory_motion(
    client: TestClient,
) -> None:
    path, geometry = patch(client, True, 0.5)
    ref = local_face(geometry, 0, 0, True)
    initial = client.get(path + "/loads").json()
    same = save(
        client,
        path,
        {
            "kind": "displacement",
            "name": "Duplicate reversed normal zero",
            "geometry_revision_id": geometry["id"],
            "face_ids": [ref],
            "units": "m-N-Pa",
            "displacement": 0,
            "direction": {"kind": "plane_normal", "reference_id": ref, "reverse": True},
        },
    )
    bad = client.post(
        path + "/loads",
        json={
            "assignment": {
                "kind": "displacement",
                "name": "Tiny contradiction",
                "geometry_revision_id": geometry["id"],
                "face_ids": [ref],
                "units": "m-N-Pa",
                "displacement": 1e-20,
                "direction": {"kind": "plane_normal", "reference_id": ref},
            }
        },
        headers={"If-Match": f'"{same["analysis_revision"]}"'},
    )
    assert bad.status_code == 422 and bad.json()["code"] == "conflicting_constraints"
    assert client.get(path + "/loads").json()["setup"] == same["setup"]
    run, _, mesh, deck = compute(client, path)
    assert run["summary"]["equilibrium"]["passed"]
    from worker.actions import deck_actions

    written = result_mesh(mesh, {geometry["bodies"][0]["id"]: "M1"})
    actions = deck_actions(deck, written, mesh["boundary"])
    expected = {
        (n, ref)
        for assignment in initial["setup"]["assignments"]
        if assignment["kind"] == "symmetry"
        for ref in assignment["face_ids"]
        for face in mesh["boundary"][ref]
        for n in face["nodes"]
    }
    assert len(actions.supports) == len(expected)


def test_native_b06_cli_executes_four_cases_and_unsigned_refuses_before_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from worker.benchmark import run_case

    refused = tmp_path / "unsigned"
    with unsigned_manifest(monkeypatch, "B06"), pytest.raises(ValueError, match="owner"):
        run_case("B06", refused, False)
    assert not refused.exists()
    result = run_case("B06", tmp_path / "diagnostic", True)
    assert len(result["runs"]) == 4
    assert result["status"] == "DEVELOPMENT PASS; owner acceptance pending"
    assert all(r["equilibrium"]["passed"] for r in result["runs"])


def test_native_cleanup_invalidates_all_geometry_directions_review_and_undo_preserve_sources(
    client: TestClient,
) -> None:
    from tests.native import test_geometry_edits as edits

    path, geometry = setup(client, "hole-m.step")
    material = custom()
    material["material"]["values"]["poisson_ratio"] = 0.3
    result = client.put(
        path + "/materials/" + geometry["bodies"][0]["id"],
        json=material,
        headers={"If-Match": f'"{client.get(path).json()["revision"]}"'},
    )
    assert result.status_code == 200, result.text
    controls(client, path, global_size=0.5, curvature_elements=0)
    for axis in range(3):
        save(
            client,
            path,
            {
                "kind": "symmetry",
                "name": f"Original symmetry {axis}",
                "geometry_revision_id": geometry["id"],
                "face_ids": [local_face(geometry, axis, 0, False)],
            },
        )
    ref = local_face(geometry, 0, 1, False)
    original = save(
        client,
        path,
        {
            "kind": "directional_force",
            "name": "Reviewed original magnitude",
            "geometry_revision_id": geometry["id"],
            "face_ids": [ref],
            "units": "mm-N-MPa",
            "magnitude": 1000,
            "direction": {"kind": "plane_normal", "reference_id": ref},
        },
    )["setup"]
    edit = edits.preview(client, geometry, path)
    committed = edits.commit(client, geometry, edit)
    blocked = client.get(path + "/loads").json()
    assert all(a["review_direction"] and a["review_faces"] for a in blocked["setup"]["assignments"])
    assert not blocked["markers"] and not blocked["resultant_complete"]
    refusal = client.post(
        path + "/deck-exports", headers={"If-Match": f'"{blocked["analysis_revision"]}"'}
    )
    assert refusal.status_code == 422
    undo = client.post(
        f"/api/v1/geometry-edits/{edit['id']}/undo",
        headers={"If-Match": f'"{committed["project"]["revision"]}"'},
    )
    assert undo.status_code == 200, undo.text
    restored = client.get(path + "/loads").json()["setup"]
    assert all(not a["review_direction"] and not a["review_faces"] for a in restored["assignments"])
    restored_geometry = undo.json()["geometry"]
    for old, new in zip(original["assignments"], restored["assignments"], strict=True):
        assert (
            old["source_magnitude"] == new["source_magnitude"] and old["force_n"] == new["force_n"]
        )
        if new["direction"]:
            assert new["direction"]["geometry_revision_id"] == restored_geometry["id"]
            assert new["direction"]["vector"] == old["direction"]["vector"]
        assert all(
            d["geometry_revision_id"] == restored_geometry["id"]
            for d in new["symmetry_directions"].values()
        )
    second = edits.preview(client, restored_geometry, path)
    current = edits.commit(client, restored_geometry, second)["geometry"]
    pending = client.get(path + "/loads").json()["setup"]["assignments"]
    for old in pending:
        faces = (
            [local_face(current, axis, 0, False)]
            if old["kind"] == "symmetry" and (axis := int(old["name"][-1])) in range(3)
            else [local_face(current, 0, 1, False)]
        )
        changed = client.put(
            path + f"/loads/{old['id']}/faces",
            json={"geometry_revision_id": current["id"], "face_ids": faces, "reviewed": True},
            headers={"If-Match": f'"{client.get(path).json()["revision"]}"'},
        )
        assert changed.status_code == 200, changed.text
        if old["direction"]:
            assert changed.json()["setup"]["assignments"][-1]["review_direction"]
            selected = {"kind": "plane_normal", "reference_id": faces[0]}
            rebound = client.put(
                path + f"/loads/{old['id']}/direction",
                json={
                    "geometry_revision_id": current["id"],
                    "direction": selected,
                    "reviewed": True,
                },
                headers={"If-Match": f'"{client.get(path).json()["revision"]}"'},
            )
            assert rebound.status_code == 200, rebound.text
            assert rebound.json()["setup"]["assignments"][-1]["source_magnitude"] == 1000
    run, data, mesh, _ = compute(client, path)
    manifest = json.loads(Path("tests/benchmarks/B06.json").read_bytes())
    evaluate_rotation(
        manifest,
        False,
        result_mesh(mesh, {current["bodies"][0]["id"]: "M1"}),
        data["dat"],
        [StressPoint(**s) for s in data["integration_points"]],
        data["equilibrium"],
    )
    old_view = client.get(f"/api/v1/runs/{run['id']}/results").json()
    project = client.get("/api/v1/projects/" + current["project_id"]).json()
    refused = client.post(
        f"/api/v1/geometry-edits/{second['id']}/undo",
        headers={"If-Match": f'"{project["revision"]}"'},
    )
    assert refused.status_code == 409  # must not overwrite later explicit reference edits
    assert client.get(f"/api/v1/runs/{run['id']}/results").json() == old_view


def test_actual_local_native_output_cannot_masquerade_as_global(
    client: TestClient, tmp_path: Path
) -> None:
    from worker.local_solve import validate_outputs
    from worker.runtime import sha256, solve_generated

    path, geometry = patch(client, True, 0.5)
    run, _, mesh, deck = compute(client, path)
    local = deck.replace("*NODE PRINT,NSET=NALL,GLOBAL=YES", "*NODE PRINT,NSET=NALL,GLOBAL=NO")
    output = tmp_path / "local-output"
    output.mkdir()
    (output / "analysis.inp").write_text(local)
    result = solve_generated(output)
    assert "Job finished" in result.stdout
    (output / "solver.log").write_text(result.stdout + result.stderr)
    assert " L" in (output / "analysis.dat").read_text()
    with pytest.raises(ValueError):
        validate_outputs(
            output,
            mesh,
            {geometry["bodies"][0]["id"]: "M1"},
            {"returncode": 0},
            run["input_sha256"],
            sha256(output / "analysis.inp"),
            run["artifacts"]["mesh.json"]["sha256"],
        )


def test_direction_preview_is_owned_csrf_and_head_guarded_and_read_only(client: TestClient) -> None:
    from uuid import uuid4

    path, geometry = patch(client, True, 0.5)
    state = client.get(path + "/loads").json()
    revision = state["analysis_revision"]
    payload = {
        "geometry_revision_id": geometry["id"],
        "directions": [{"kind": "plane_normal", "reference_id": local_face(geometry, 0, 1, True)}],
    }
    assert client.post(path + "/direction-previews", json=payload).status_code == 428
    assert (
        client.post(
            path + "/direction-previews", json=payload, headers={"If-Match": f'"{revision - 1}"'}
        ).status_code
        == 409
    )
    assert (
        client.post(
            path + "/direction-previews",
            json=payload | {"geometry_revision_id": str(uuid4())},
            headers={"If-Match": f'"{revision}"'},
        ).status_code
        == 422
    )
    csrf = client.headers.pop("X-CSRF-Token")
    assert (
        client.post(
            path + "/direction-previews", json=payload, headers={"If-Match": f'"{revision}"'}
        ).status_code
        == 403
    )
    client.headers["X-CSRF-Token"] = csrf
    assert (
        client.post(
            f"/api/v1/analyses/{uuid4()}/direction-previews",
            json=payload,
            headers={"If-Match": f'"{revision}"'},
        ).status_code
        == 404
    )
    success = client.post(
        path + "/direction-previews", json=payload, headers={"If-Match": f'"{revision}"'}
    )
    assert success.status_code == 200
    assert client.get(path + "/loads").json() == state
