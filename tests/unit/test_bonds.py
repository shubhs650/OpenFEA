"""Independent mortar virtual-work references and rejected bond selections."""

import struct
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from tests.benchmark_review import unsigned_manifest
from worker.bond_fixture import run_b07
from worker.calculix.bonds import (
    binary_frd_coordinates,
    bond_keywords,
    prepare_bond,
    require_supported_bodies,
)
from worker.calculix.mortar import coupling, solve_mass
from worker.meshing import Vec, face_nodes
from worker.stress_fixture import hand_mesh


def patch() -> tuple[dict[str, Any], dict[str, Any], str, str]:
    upper = hand_mesh()
    points = dict(upper.nodes)
    lower = {
        101: (0.0, 0.0, 0.0),
        102: (0.0, 1.0, 0.0),
        103: (1.0, 0.0, 0.0),
        104: (0.0, 0.0, -1.0),
        105: (0.0, 0.5, 0.0),
        106: (0.5, 0.5, 0.0),
        107: (0.5, 0.0, 0.0),
        108: (0.0, 0.0, -0.5),
        109: (0.0, 0.5, -0.5),
        110: (0.5, 0.0, -0.5),
    }
    points.update(lower)
    elements = {1: tuple(range(1, 11)), 2: tuple(range(101, 111))}
    master, slave = "r:b1:f1", "r:b2:f1"
    mesh = {
        "revision": "r",
        "units": "m",
        "nodes": points,
        "elements": elements,
        "owners": {1: "r:b1", 2: "r:b2"},
        "boundary": {
            master: [{"element": 1, "face": 1, "nodes": face_nodes(elements[1], 1)}],
            slave: [{"element": 2, "face": 1, "nodes": face_nodes(elements[2], 1)}],
        },
    }
    catalog = {
        "revision": "r",
        "units": "m",
        "faces": [
            {"id": master, "body": "r:b1", "area": 0.5},
            {"id": slave, "body": "r:b2", "area": 0.5},
        ],
    }
    return mesh, catalog, master, slave


def test_complete_quadratic_coverage_and_stale_constraint_snapshot() -> None:
    mesh, catalog, master, slave = patch()
    bond = prepare_bond(mesh, catalog, master, slave)
    assert set(bond.slave_nodes) == {101, 102, 103, 105, 106, 107}
    assert len(bond.projections) == 6
    assert all(sum(p.weights) == pytest.approx(1, abs=1e-12) for p in bond.projections)
    keywords = bond_keywords(bond)
    assert "ADJUST=NO" in keywords and "POSITION TOLERANCE=1.000000000000e-08" in keywords
    assert "BOND_SLAVE,BOND_MASTER" in keywords
    require_supported_bodies(mesh, [bond], {1})
    with pytest.raises(ValueError, match="detached"):
        require_supported_bodies(mesh, [], {1})
    with pytest.raises(ValueError, match="stale"):
        require_supported_bodies(mesh, [replace(bond, revision="changed")], {1})


@pytest.mark.parametrize(
    "fault", ["stale", "same_body", "partial", "gap", "overlap", "wrong_normal", "slave_spc"]
)
def test_invalid_bond_refuses_to_emit_solver_constraints(fault: str) -> None:
    mesh, catalog, master, slave = patch()
    constrained = set()
    if fault == "stale":
        catalog["revision"] = "changed"
    elif fault == "same_body":
        slave = master
    elif fault == "partial":
        mesh["boundary"][master] = []
    elif fault in ("gap", "overlap"):
        shift = -0.001 if fault == "gap" else 0.001
        for n, p in mesh["nodes"].items():
            if n > 100:
                mesh["nodes"][n] = (p[0], p[1], p[2] + shift)
    elif fault == "wrong_normal":
        mesh["boundary"][slave] = [
            {"element": 2, "face": 2, "nodes": face_nodes(mesh["elements"][2], 2)}
        ]
    else:
        constrained = {101}
    with pytest.raises(ValueError, match="Unresolved"):
        prepare_bond(mesh, catalog, master, slave, constrained)


def nested_triangle() -> tuple[dict[int, Vec], list[tuple[int, ...]], list[tuple[int, ...]]]:
    nodes: dict[int, Vec] = {
        1: (0, 0, 0),
        2: (1, 0, 0),
        3: (0, 1, 0),
        4: (0.5, 0, 0),
        5: (0.5, 0.5, 0),
        6: (0, 0.5, 0),
    }
    coords = {p: n + 100 for n, p in nodes.items()}
    nodes.update({n + 100: p for n, p in list(nodes.items())})
    slave_faces = []
    for corners in ((101, 104, 106), (104, 102, 105), (106, 105, 103), (104, 105, 106)):
        mids = []
        for i, j in ((0, 1), (1, 2), (2, 0)):
            a, b = nodes[corners[i]], nodes[corners[j]]
            p: Vec = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, 0)
            if p not in coords:
                coords[p] = 200 + len(coords)
                nodes[coords[p]] = p
            mids.append(coords[p])
        slave_faces.append((*corners, *mids))
    return nodes, slave_faces, [(1, 2, 3, 4, 5, 6)]


@pytest.mark.parametrize("reverse", [False, True])
def test_mortar_affine_reproduction_force_and_moment_virtual_work(reverse: bool) -> None:
    nodes, slave_faces, master_faces = nested_triangle()
    if reverse:
        slave_faces, master_faces = master_faces, slave_faces
    slaves, masters, mass, coupled, area = coupling(nodes, slave_faces, master_faces)
    projection = solve_mass(mass, coupled)
    assert area == pytest.approx(0.5, abs=1e-12)
    for i, n in enumerate(slaves):
        assert sum(projection[i]) == pytest.approx(1, abs=1e-12)
        for k in range(3):
            assert sum(
                projection[i][j] * nodes[m][k] for j, m in enumerate(masters)
            ) == pytest.approx(nodes[n][k], abs=1e-12)
    slave_load = [sum(row) for row in mass]
    master_load = [
        sum(projection[i][j] * slave_load[i] for i in range(len(slaves)))
        for j in range(len(masters))
    ]
    assert sum(master_load) == pytest.approx(0.5, abs=1e-12)
    assert sum(master_load[j] * nodes[m][0] for j, m in enumerate(masters)) == pytest.approx(
        1 / 6, abs=1e-12
    )
    assert sum(master_load[j] * nodes[m][1] for j, m in enumerate(masters)) == pytest.approx(
        1 / 6, abs=1e-12
    )
    # Exact integrals of tri6 shape functions: corners zero, midsides area/3.
    if not reverse:
        assert master_load == pytest.approx([0, 0, 0, 1 / 6, 1 / 6, 1 / 6], abs=1e-12)
    with pytest.raises(ValueError, match="no stabilization"):
        solve_mass([[0.0]], [[1.0]])


@pytest.mark.parametrize(
    "fault", ["truncated", "duplicate", "nonfinite", "wrong_ids", "wrong_format"]
)
def test_binary_geometry_audit_is_narrow_and_fail_closed(fault: str, tmp_path: Path) -> None:
    header = b"    2C 2 3\n"
    record1 = struct.pack("<i3d", 1, 0.0, 0.0, 0.0)
    record2 = struct.pack("<i3d", 2, 1.0, 0.0, 0.0)
    if fault == "truncated":
        record2 = record2[:-1]
    elif fault == "duplicate":
        record2 = record1
    elif fault == "nonfinite":
        record2 = struct.pack("<i3d", 2, float("nan"), 0.0, 0.0)
    elif fault == "wrong_ids":
        record2 = struct.pack("<i3d", 3, 1.0, 0.0, 0.0)
    else:
        header = b"    2C 2 1\n"
    p = tmp_path / "analysis.frd"
    p.write_bytes(header + record1 + record2 + b"    3C 0 2\n 9999\n")
    with pytest.raises(ValueError):
        binary_frd_coordinates(p, {1, 2})


def test_unsigned_b07_stops_before_creating_a_solver_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with unsigned_manifest(monkeypatch, "B07"), pytest.raises(ValueError, match="review pending"):
        run_b07(tmp_path / "absent")
    assert not (tmp_path / "absent").exists()
