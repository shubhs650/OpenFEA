"""Independent volume polynomials, section areas, side ownership and refusal cases."""

import math
from copy import deepcopy
from dataclasses import asdict, replace
from typing import Any

import pytest

from tests.unit.test_result_views import fixture
from worker.calculix.results import GAUSS, StressPoint
from worker.meshing import cross, norm, sub
from worker.postprocess.inspection import inspect_volume
from worker.postprocess.tensors import tensor
from worker.postprocess.view import vector
from worker.stress_fixture import hand_mesh


def stress(p: list[float] | tuple[float, ...], side: int = 1) -> list[float]:
    x, y, z = p
    return [side * 10 + x + 2 * y - z, -4 + y, z, x - y, 2 * z, y + z]


def displacement(p: list[float] | tuple[float, ...]) -> list[float]:
    x, y, z = p
    return [x * x + y * z, y * y - x * z, z * z + 2 * x * y]


def polynomial_fixture(two: bool = False) -> tuple[Any, Any, Any]:
    raw, wire, materials, _ = fixture([0] * 6)
    mesh = hand_mesh(two)
    if two:
        mesh = replace(mesh, bodies={1: "upper", 2: "lower"})
    wire.update(asdict(mesh), owners=mesh.bodies, boundary={})  # No exterior field exists.
    materials = {mesh.bodies[e]: {"material_id": mesh.materials[e]} for e in mesh.elements}
    raw["result_mesh_sha256"] = mesh.identity()
    raw["integration_points"] = [
        asdict(
            StressPoint(
                "integration_point",
                e,
                i,
                None,
                mesh.bodies[e],
                mesh.materials[e],
                vector([sum(b[j] * mesh.nodes[ns[j]][k] for j in range(4)) for k in range(3)]),
                tensor(
                    stress(
                        vector(
                            [sum(b[j] * mesh.nodes[ns[j]][k] for j in range(4)) for k in range(3)]
                        ),
                        e,
                    )
                ),
                {
                    "mesh_sha256": mesh.identity(),
                    "components": ("xx", "yy", "zz", "xy", "yz", "zx"),
                    "frame": "global_cartesian",
                    "units": "Pa",
                    "line": i,
                    "source_sha256": raw["dat"]["source_sha256"],
                },
            )
        )
        for e, ns in mesh.elements.items()
        for i, b in enumerate(GAUSS, 1)
    ]
    raw["dat"]["displacements_m"] = {n: displacement(p) for n, p in mesh.nodes.items()}
    return raw, wire, materials


def area(section: dict[str, Any]) -> float:
    points = section["vertices"]
    return sum(
        norm(
            cross(
                sub(tuple(points[b]["position_m"]), tuple(points[a]["position_m"])),
                sub(tuple(points[c]["position_m"]), tuple(points[a]["position_m"])),
            )
        )
        / 2
        for a, b, c in section["triangles"]
    )


@pytest.mark.parametrize(
    "point,normal,expected_area",
    [
        ((0, 0, 0.25), (0, 0, 1), 0.75**2 / 2),
        ((0.5, 0, 0), (1, 1, 0), math.sqrt(2) / 4),
        ((0, 0, 0), (0, 0, 1), 0.5),
        ((0, 0, 1), (0, 0, 1), 0),
        ((0, 0, 0), (1, 1, 0), 0),
        ((0, 0, 2), (0, 0, 1), 0),
    ],
)
def test_volume_slice_linear_tensor_quadratic_displacement_and_independent_area(
    point: Any, normal: Any, expected_area: float
) -> None:
    inputs = polynomial_fixture()
    original = deepcopy(inputs)
    result = inspect_volume(*inputs, point, normal=normal)
    assert inputs == original
    assert area(result) == pytest.approx(expected_area, abs=1e-12)
    assert len(result["vertices"]) <= 9 and len(result["triangles"]) <= 8
    for v in result["vertices"]:
        p = v["position_m"]
        assert sum((p[k] - point[k]) * normal[k] for k in range(3)) == pytest.approx(0, abs=1e-12)
        assert v["displacement_m"] == pytest.approx(displacement(p), abs=1e-12)
        assert v["barycentric"] == pytest.approx([1 - sum(p), *p], abs=1e-12)
        for mode in ("stress", "smoothed_stress"):
            assert v[mode]["tensor_pa"] == pytest.approx(stress(p), rel=1e-10, abs=1e-8)
        assert "node_id" not in v  # Interior samples cannot impersonate native mesh nodes.
    if expected_area and point[2] == 0.25:
        assert any(all(b > 0 for b in v["barycentric"]) for v in result["vertices"])


@pytest.mark.parametrize("point", [(0.2, 0.3, 0.1), (0.25, 0.25, 0), (0.5, 0, 0), (0, 0, 0)])
def test_physical_probe_interior_face_edge_vertex_and_all_quadratic_nodes(point: Any) -> None:
    result = inspect_volume(*polynomial_fixture(), point, element=1)
    v = result["vertices"][0]
    assert v["position_m"] == pytest.approx(point, abs=1e-12)
    assert v["displacement_m"] == pytest.approx(displacement(point), abs=1e-12)
    assert v["stress"]["tensor_pa"] == pytest.approx(stress(point), rel=1e-10, abs=1e-8)
    assert result["location"] == "element_interpolated" and result["triangles"] == []
    assert "ten quadratic" in result["method"] and "Not a raw" in result["method"]


def test_shared_boundary_requires_side_and_never_averages_material_or_body() -> None:
    inputs = polynomial_fixture(True)
    for e in (1, 2):
        result = inspect_volume(*inputs, (0.25, 0.25, 0), element=e)
        v = result["vertices"][0]
        assert v["element_id"] == e
        assert v["material_id"] == ("UPPER" if e == 1 else "LOWER")
        for mode in ("stress", "smoothed_stress"):
            assert v[mode]["tensor_pa"] == pytest.approx(
                stress((0.25, 0.25, 0), e), rel=1e-10, abs=1e-8
            )
    section = inspect_volume(*inputs, (0, 0, 0), normal=(0, 0, 1))
    assert {v["element_id"] for v in section["vertices"]} == {1, 2}
    assert area(section) == pytest.approx(1)  # Both coincident sides retained, each 0.5 m².


@pytest.mark.parametrize("kind", ["probe", "section"])
def test_curved_c3d10_midpoint_refused_without_linearizing_geometry(kind: str) -> None:
    inputs = polynomial_fixture()
    inputs[1]["nodes"][5] = (0.5, 0.02, 0)
    with pytest.raises(ValueError, match="Curved/non-midpoint"):
        inspect_volume(
            *inputs,
            (0.2, 0.2, 0.2),
            **({"element": 1} if kind == "probe" else {"normal": (1, 0, 0)}),
        )


@pytest.mark.parametrize(
    "options",
    [{"element": 99}, {"element": 1}, {"normal": (0, 0, 0)}, {"normal": (math.nan, 0, 1)}],
)
def test_invalid_side_outside_point_and_nonfinite_normal_refused(options: Any) -> None:
    with pytest.raises(ValueError):
        inspect_volume(*polynomial_fixture(), (2, 2, 2), **options)


@pytest.mark.parametrize("magnitude", [1e-300, 1e300, -1e300])
def test_normal_scale_does_not_change_authoritative_section(magnitude: float) -> None:
    section = inspect_volume(*polynomial_fixture(), (0, 0, 0.25), normal=(0, 0, magnitude))
    assert area(section) == pytest.approx(0.75**2 / 2, abs=1e-12)


def test_invariants_follow_tensor_interpolation_instead_of_averaging_scalar_peaks() -> None:
    raw, wire, materials = polynomial_fixture()
    for p in raw["integration_points"]:
        p["tensor_pa"] = [2 * p["position_m"][0] - 1, 0, 0, 0, 0, 0]
    result = inspect_volume(raw, wire, materials, (0.5, 0.1, 0.1), element=1)
    for mode in ("stress", "smoothed_stress"):
        assert result["vertices"][0][mode]["tensor_pa"] == pytest.approx([0] * 6, abs=1e-12)
        assert result["vertices"][0][mode]["von_mises_pa"] == pytest.approx(0, abs=1e-12)
        assert result["vertices"][0][mode]["principal_pa"] == pytest.approx([0] * 3, abs=1e-12)
