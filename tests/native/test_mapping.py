"""Real CAD -> display triangles -> reordered Gmsh -> quadratic CCX checks."""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Literal

import pytest

from worker.benchmark import run_case, solve
from worker.deck import generated_deck
from worker.meshing import (
    Vec,
    add,
    cross,
    face_nodes,
    norm,
    resultant,
    scale,
    sub,
    surface_integral,
    total_face_force,
)
from worker.runtime import ROOT, quadratic_mesh, sha256, synthetic_geometry


@pytest.mark.parametrize("fixture", ["box", "bracket", "two"])
def test_all_faces_survive_tessellation_and_reordered_mesh(
    fixture: Literal["box", "bracket", "two"], tmp_path: Path
) -> None:
    synthetic_geometry(tmp_path, fixture)
    catalog = json.loads((tmp_path / "catalog.json").read_text())
    quadratic_mesh(tmp_path, 0.6)
    first = json.loads((tmp_path / "mesh.json").read_text())
    quadratic_mesh(tmp_path, 0.6, 1000)
    mesh = json.loads((tmp_path / "mesh.json").read_text())
    assert first["revision"] == mesh["revision"] == catalog["revision"]
    assert set(first["face_tags"]) == set(mesh["face_tags"])
    assert all(first["face_tags"][f] != mesh["face_tags"][f] for f in mesh["face_tags"])
    nodes: dict[int, Vec] = {int(n): tuple(p) for n, p in mesh["nodes"].items()}
    assert len(set(mesh["owners"].values())) == (2 if fixture == "two" else 1)
    observed_faces = []
    for face in catalog["faces"]:
        display_area = 0.0
        display_normal: Vec = (0, 0, 0)
        for triangle in face["triangles"]:
            a, b, c = [tuple(p) for p in triangle]
            vector = scale(cross(sub(b, a), sub(c, a)), 0.5)
            display_area += norm(vector)
            display_normal = add(display_normal, vector)
        assert display_area == pytest.approx(face["area"], abs=1e-10)
        area = 0.0
        center_integral: Vec = (0, 0, 0)
        loads: dict[int, Vec] = {}
        for boundary in mesh["boundary"][face["id"]]:
            ns = boundary["nodes"]
            measured, center, values = surface_integral([nodes[n] for n in ns], pressure=1)
            area += measured
            center_integral = add(center_integral, scale(center, measured))
            for n, value in zip(ns, values, strict=True):
                loads[n] = add(loads.get(n, (0, 0, 0)), value)
        assert area == pytest.approx(face["area"], abs=1e-10)
        assert scale(center_integral, 1 / area) == pytest.approx(face["center"], abs=1e-10)
        force, moment = resultant(loads, nodes)
        assert force == pytest.approx(scale(display_normal, -1), abs=1e-10)
        assert moment == pytest.approx(cross(tuple(face["center"]), force), abs=1e-10)
        observed_faces.append(
            {
                "id": face["id"],
                "old_tag": first["face_tags"][face["id"]],
                "new_tag": mesh["face_tags"][face["id"]],
                "area_m2": area,
                "area_error_m2": abs(area - face["area"]),
                "pressure_resultant_n": force,
                "pressure_moment_nm": moment,
            }
        )
    output = ROOT / f".local/native/validation/T003/{fixture}"
    output.mkdir(parents=True, exist_ok=True)
    for name in ("catalog.json", "mesh.json", "geometry.brep", "mesh.msh"):
        shutil.copy2(tmp_path / name, output / name)
    (output / "result.json").write_text(
        json.dumps(
            {
                "code_commit": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
                ).strip(),
                "fixture": fixture,
                "revision": mesh["revision"],
                "faces": observed_faces,
                "nodes": len(nodes),
                "elements": len(mesh["elements"]),
                "bodies": len(catalog["bodies"]),
                "gmsh_version": mesh["gmsh_version"],
                "catalog_sha256": sha256(tmp_path / "catalog.json"),
                "mesh_sha256": sha256(tmp_path / "mesh.json"),
                "status": "PASS synthetic planar mapping",
            },
            indent=2,
        )
        + "\n"
    )


@pytest.mark.parametrize("face", [1, 2, 3, 4])
@pytest.mark.parametrize("pressure", [7.0, -7.0])
def test_ccx_pressure_matches_consistent_nodal_loads_all_faces(
    face: int, pressure: float, tmp_path: Path
) -> None:
    # Independent hand tetra; corner nodes fixed, all six midsides free (18 equations).
    nodes: dict[int, Vec] = {
        1: (0, 0, 0),
        2: (1, 0, 0),
        3: (0, 1, 0),
        4: (0, 0, 1),
        5: (0.5, 0, 0),
        6: (0.5, 0.5, 0),
        7: (0, 0.5, 0),
        8: (0, 0, 0.5),
        9: (0.5, 0, 0.5),
        10: (0, 0.5, 0.5),
    }
    mesh = {"nodes": nodes, "elements": {1: tuple(range(1, 11))}, "boundary": {}}
    supports = {(n, axis): 0.0 for n in range(1, 5) for axis in range(1, 4)}
    ns = face_nodes(tuple(range(1, 11)), face)
    loads = dict(
        zip(ns, surface_integral([nodes[n] for n in ns], pressure=pressure)[2], strict=True)
    )
    nodal = tmp_path / "nodal"
    native = tmp_path / "pressure"
    nodal.mkdir()
    native.mkdir()
    u1, _, rf1 = solve(nodal, generated_deck(mesh, supports, loads, 210e9, 0.3))
    u2, _, rf2 = solve(native, generated_deck(mesh, supports, {}, 210e9, 0.3, (1, face, pressure)))
    assert any(norm(u2[n]) > 0 for n in range(5, 11))
    for n in nodes:
        assert u1[n] == pytest.approx(u2[n], rel=1e-5, abs=1e-18)
        assert rf1[n] == pytest.approx(rf2[n], rel=1e-5, abs=1e-6)
    balance_f, balance_m = resultant(rf2, nodes)
    assert balance_f == pytest.approx((0, 0, 0), abs=1e-5)
    assert balance_m == pytest.approx((0, 0, 0), abs=1e-5)
    output = ROOT / f".local/native/validation/T003/pressure-{face}-{pressure:g}"
    output.mkdir(parents=True, exist_ok=True)
    for mode, source in (("nodal", nodal), ("pressure", native)):
        for name in ("analysis.inp", "analysis.dat", "solver.log"):
            shutil.copy2(source / name, output / f"{mode}-{name}")
    (output / "result.json").write_text(
        json.dumps(
            {
                "code_commit": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
                ).strip(),
                "ccx_face": face,
                "pressure_pa": pressure,
                "status": "PASS",
                "max_displacement_difference_m": max(
                    abs(u1[n][k] - u2[n][k]) for n in nodes for k in range(3)
                ),
                "max_rf_difference_n": max(
                    abs(rf1[n][k] - rf2[n][k]) for n in nodes for k in range(3)
                ),
                "force_balance_n": balance_f,
                "moment_balance_nm": balance_m,
                "nodal_deck_sha256": sha256(nodal / "analysis.inp"),
                "pressure_deck_sha256": sha256(native / "analysis.inp"),
            },
            indent=2,
        )
        + "\n"
    )


@pytest.mark.parametrize("case", ["B01", "B02"])
def test_real_analytical_cases(case: str, tmp_path: Path) -> None:
    result = run_case(case, tmp_path, development=True)
    assert len(result["runs"]) == 2
    output = ROOT / f".local/native/validation/T003/{case}"
    output.mkdir(parents=True, exist_ok=True)
    shutil.copytree(tmp_path, output, dirs_exist_ok=True)


def test_total_force_over_two_cad_faces_with_supported_loaded_nodes(tmp_path: Path) -> None:
    synthetic_geometry(tmp_path, "box")
    quadratic_mesh(tmp_path, 0.6, 2000)
    mesh = json.loads((tmp_path / "mesh.json").read_text())
    catalog = json.loads((tmp_path / "catalog.json").read_text())
    selected = [f for f in catalog["faces"] if f["center"][0] < 1e-9 or f["center"][1] < 1e-9]
    assert len(selected) == 2
    faces = [tuple(f["nodes"]) for cad in selected for f in mesh["boundary"][cad["id"]]]
    nodes: dict[int, Vec] = {int(n): tuple(p) for n, p in mesh["nodes"].items()}
    total: Vec = (11, -7, 3)
    loads = total_face_force(faces + faces, nodes, total)
    force, moment = resultant(loads, nodes)
    assert force == pytest.approx(total, abs=1e-12)
    assert moment == pytest.approx(cross((0.25, 0.25, 0.5), total), abs=1e-12)
    supports = {(n, k): 0.0 for n, p in nodes.items() if p[0] < 1e-9 for k in (1, 2, 3)}
    _, _, rf = solve(tmp_path, generated_deck(mesh, supports, loads, 210e9, 0.3))
    reactions = {n: sub(rf[n], loads.get(n, (0, 0, 0))) for n in nodes}
    reaction_force, reaction_moment = resultant(reactions, nodes)
    assert add(force, reaction_force) == pytest.approx((0, 0, 0), abs=1e-5)
    assert add(moment, reaction_moment) == pytest.approx((0, 0, 0), abs=1e-5)
    for n in nodes:
        if (n, 1) not in supports:
            assert reactions[n] == pytest.approx((0, 0, 0), abs=1e-5)
    output = ROOT / ".local/native/validation/T003/two-face-force"
    output.mkdir(parents=True, exist_ok=True)
    (output / "result.json").write_text(
        json.dumps(
            {
                "code_commit": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
                ).strip(),
                "selected_face_ids": [f["id"] for f in selected],
                "applied_force_n": force,
                "applied_moment_nm": moment,
                "reaction_force_n": reaction_force,
                "reaction_moment_nm": reaction_moment,
                "status": "PASS",
            },
            indent=2,
        )
        + "\n"
    )
