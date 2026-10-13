"""Independent tetra, surface and identity adversarial checks; no native dependencies."""

import copy
from pathlib import Path

import pytest

from worker.benchmark import run_case
from worker.geometry import match_faces
from worker.meshing import (
    EDGES,
    FACES,
    Vec,
    convert_tetra,
    cross,
    face_nodes,
    resultant,
    scale,
    surface_integral,
    total_face_force,
)

POINTS: dict[int, Vec] = {
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
GMSH = [1, 2, 3, 4, 5, 6, 7, 8, 10, 9]
CCX = tuple(range(1, 11))


def test_independent_midside_and_all_face_ordering() -> None:
    assert convert_tetra(GMSH, POINTS) == CCX
    # Independent edge specification, rather than only checking exported constants.
    expected_edges = [(1, 2), (2, 3), (3, 1), (1, 4), (2, 4), (3, 4)]
    assert [(CCX[a], CCX[b]) for a, b in EDGES] == expected_edges
    expected_faces = [
        (1, 3, 2, 7, 6, 5),
        (1, 2, 4, 5, 9, 8),
        (2, 3, 4, 6, 10, 9),
        (3, 1, 4, 7, 8, 10),
    ]
    assert [face_nodes(CCX, i) for i in range(1, 5)] == expected_faces
    assert len(FACES) == 4


@pytest.mark.parametrize(
    "face,area,centroid,normal",
    [
        (1, 0.5, (1 / 3, 1 / 3, 0), (0, 0, -1)),
        (2, 0.5, (1 / 3, 0, 1 / 3), (0, -1, 0)),
        (3, 3**0.5 / 2, (1 / 3, 1 / 3, 1 / 3), (1 / 3**0.5, 1 / 3**0.5, 1 / 3**0.5)),
        (4, 0.5, (0, 1 / 3, 1 / 3), (-1, 0, 0)),
    ],
)
def test_quadratic_face_pressure_resultant_moment(
    face: int, area: float, centroid: Vec, normal: Vec
) -> None:
    ns = face_nodes(CCX, face)
    measured_area, measured_center, values = surface_integral([POINTS[n] for n in ns], pressure=7)
    assert measured_area == pytest.approx(area, abs=1e-13)
    assert measured_center == pytest.approx(centroid, abs=1e-13)
    force, moment = resultant(dict(zip(ns, values, strict=True)), POINTS)
    expected = scale(normal, -7 * area)
    assert force == pytest.approx(expected, abs=1e-12)
    assert moment == pytest.approx(cross(centroid, expected), abs=1e-12)
    # Consistent quadratic loading puts no force on planar triangle corners.
    assert [v for value in values[:3] for v in value] == pytest.approx([0] * 9, abs=1e-12)
    for value in values[3:]:
        assert value == pytest.approx(scale(expected, 1 / 3), abs=1e-12)
    reversed_values = surface_integral([POINTS[n] for n in ns], pressure=-7)[2]
    assert [v for value in reversed_values for v in value] == pytest.approx(
        [-v for value in values for v in value], abs=1e-12
    )


@pytest.mark.parametrize("second", [2, 3])
def test_total_force_two_faces_duplicate_selection(second: int) -> None:
    faces = [face_nodes(CCX, 1), face_nodes(CCX, second)]
    total: Vec = (11, -7, 3)
    loads = total_face_force(faces + faces, POINTS, total)
    force, moment = resultant(loads, POINTS)
    assert force == pytest.approx(total, abs=1e-12)
    second_area = 0.5 if second == 2 else 3**0.5 / 2
    second_center: Vec = (1 / 3, 0, 1 / 3) if second == 2 else (1 / 3, 1 / 3, 1 / 3)
    center: Vec = (
        1 / 3,
        (1 / 6 + second_area * second_center[1]) / (0.5 + second_area),
        second_area * second_center[2] / (0.5 + second_area),
    )
    assert moment == pytest.approx(cross(center, total), abs=1e-12)


def test_curved_quadratic_pressure_independent_polynomial_integrals() -> None:
    # x=r,y=s,z=k*r*s => normal=(-k*s,-k*r,1). Integrate monomials analytically.
    k, pressure = 0.4, 7
    points: list[Vec] = [
        (0, 0, 0),
        (1, 0, 0),
        (0, 1, 0),
        (0.5, 0, 0),
        (0.5, 0.5, k / 4),
        (0, 0.5, 0),
    ]
    values = surface_integral(points, pressure=pressure)[2]
    nodes = dict(enumerate(points, 1))
    force, moment = resultant(dict(enumerate(values, 1)), nodes)
    assert force == pytest.approx((pressure * k / 6, pressure * k / 6, -pressure / 2), abs=1e-12)
    assert moment == pytest.approx(
        (-pressure * (1 / 6 + k * k / 60), pressure * (1 / 6 + k * k / 60), 0), abs=1e-12
    )


@pytest.mark.parametrize(
    "fault", ["negative", "zero", "curved", "nan", "wrong_permutation", "duplicate"]
)
def test_invalid_quadratic_elements_fail_closed(fault: str) -> None:
    nodes = POINTS.copy()
    tags = GMSH.copy()
    if fault == "negative":
        nodes = {n: (-p[0], p[1], p[2]) for n, p in nodes.items()}
    elif fault == "zero":
        nodes = {n: (p[0], p[1], 0) for n, p in nodes.items()}
    elif fault == "curved":
        nodes[5] = (0.5, 0, 0.1)
    elif fault == "nan":
        nodes[1] = (float("nan"), 0, 0)
    elif fault == "wrong_permutation":
        tags[-1], tags[-2] = tags[-2], tags[-1]
    else:
        tags[-1] = tags[-2]
    with pytest.raises(ValueError):
        convert_tetra(tags, nodes)


def test_empty_and_zero_area_load_rejected() -> None:
    with pytest.raises(ValueError, match="Empty"):
        total_face_force([], POINTS, (1, 0, 0))
    with pytest.raises(ValueError, match="Zero-area"):
        surface_integral([(0, 0, 0)] * 6)


def test_positive_corner_volume_with_interior_inversion_is_rejected() -> None:
    nodes = {n: (p[0], p[1], p[2] * 1e-10) for n, p in POINTS.items()}
    # Below the midpoint tolerance, yet larger than this thin tetra's height.
    nodes[8] = (0, 0, -0.5e-9)
    with pytest.raises(ValueError, match="Jacobian"):
        convert_tetra(GMSH, nodes)


@pytest.mark.parametrize("fault", ["stale", "missing", "ambiguous", "adjacency"])
def test_unresolved_face_identity(fault: str) -> None:
    catalog = {
        "revision": "immutable",
        "faces": [
            {
                "id": "immutable:b1:f1",
                "body": "b1",
                "area": 1,
                "center": [0, 0, 0],
                "bounds": [0] * 6,
                "neighbors": [],
            }
        ],
    }
    imported = [
        {
            "tag": 999,
            "body": "b1",
            "area": 1,
            "center": [0, 0, 0],
            "bounds": [0] * 6,
            "neighbors": [],
        }
    ]
    revision = "immutable"
    if fault == "stale":
        revision = "changed"
    elif fault == "missing":
        imported[0]["area"] = 2
    elif fault == "ambiguous":
        imported.append(copy.deepcopy(imported[0]))
    else:
        imported[0]["neighbors"] = [1]
    with pytest.raises(ValueError, match="Unresolved"):
        match_faces(catalog, imported, revision)


def test_unsigned_benchmark_cannot_be_reported_as_accepted(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Engineering-owner review pending"):
        run_case("B01", tmp_path / "not-created")
    assert not (tmp_path / "not-created").exists()
