"""Independent signed fields and tensor-before-invariant smoothing references."""

from copy import deepcopy
from dataclasses import replace

import pytest

from tests.unit.test_result_views import fixture
from worker.calculix.results import StressPoint
from worker.postprocess.fields import smooth_nodes
from worker.postprocess.tensors import principal, tensor, von_mises
from worker.postprocess.view import build_view
from worker.stress_fixture import hand_mesh


@pytest.mark.parametrize(
    "stress,roots",
    [
        ([5, 5, 5, 0, 0, 0], [5, 5, 5]),
        ([-5, -5, -5, 0, 0, 0], [-5, -5, -5]),
        ([0, 0, 0, 3, 0, 0], [3, 0, -3]),
        ([0, 0, 0, 0, -3, 0], [3, 0, -3]),
        ([0, 0, 0, 0, 0, 3], [3, 0, -3]),
        ([7, 4, 4, 2, 0, 0], [8, 4, 3]),
    ],
)
def test_full_view_fields_have_signed_raw_extrema_units_and_sorted_principals(
    stress: list[float], roots: list[float]
) -> None:
    inputs = fixture(stress)
    original = deepcopy(inputs)
    data = build_view(*inputs)
    assert inputs == original
    fields = {f["key"]: f for f in data["fields"]}
    assert len(fields) == 14 and data["tensor_components"] == ("xx", "yy", "zz", "xy", "yz", "zx")
    assert data["frame"] == "global_cartesian"
    for key, expected in zip(
        ("sxx", "syy", "szz", "sxy", "syz", "szx", "s1", "s2", "s3"), stress + roots, strict=True
    ):
        field = fields[key]
        assert field["unit"] == "Pa" and field["raw_location"] == "integration_point"
        for sample in field["extrema"].values():
            assert sample["value"] == pytest.approx(expected, abs=1e-10)
            assert sample["element_id"] == 1 and sample["integration_point_id"] in (1, 2, 3, 4)
        for vertex in data["vertices"]:
            assert vertex["stress"]["tensor_pa"] == pytest.approx(stress, abs=1e-10)
            assert vertex["smoothed_stress"]["principal_pa"] == pytest.approx(roots, abs=1e-10)
            assert vertex["smoothed_contributions"] == 1
    assert data["warnings"] == ["Frozen warning"]


def test_native_nodal_component_extrema_keep_sign_and_source_node() -> None:
    raw, mesh, materials, deck = fixture([1000, 0, 0, 0, 0, 0])
    raw["dat"]["displacements_m"][2] = [-0.02, 0.03, -0.04]
    fields = {f["key"]: f for f in build_view(raw, mesh, materials, deck)["fields"]}
    for key, limit, value in [
        ("ux", "minimum", -0.02),
        ("uy", "maximum", 0.03),
        ("uz", "minimum", -0.04),
    ]:
        assert fields[key]["unit"] == "m" and fields[key]["raw_location"] == "node"
        sample = fields[key]["extrema"][limit]
        assert sample["node_id"] == 2 and sample["value"] == value


@pytest.mark.parametrize("partition", ["same", "material", "body", "coincident"])
def test_tensor_smoothing_partitions_and_invariants_after_averaging(partition: str) -> None:
    mesh = hand_mesh(True)
    mesh = replace(
        mesh,
        materials={1: "A", 2: "B" if partition == "material" else "A"},
        bodies={1: "first", 2: "second" if partition == "body" else "first"},
    )
    if partition == "coincident":
        mesh = replace(
            mesh,
            nodes=mesh.nodes | {99: mesh.nodes[1]},
            elements=mesh.elements | {2: tuple(99 if n == 1 else n for n in mesh.elements[2])},
        )
    points = [
        StressPoint(
            "element_node",
            e,
            None,
            n,
            mesh.bodies[e],
            mesh.materials[e],
            mesh.nodes[n],
            tensor([6 if e == 1 else -2, 0, 0, 0, 0, 0]),
            {},
        )
        for e, ns in mesh.elements.items()
        for n in ns
    ]
    original = deepcopy(points)
    result = smooth_nodes(points, mesh)
    assert points == original and len(result) == 20
    for p in result:
        if p.node_id not in {1, 99}:
            continue
        expected = 2 if partition == "same" else 6 if p.element_id == 1 else -2
        assert p.tensor_pa == pytest.approx([expected, 0, 0, 0, 0, 0])
        assert von_mises(p.tensor_pa) == abs(expected)
        assert principal(p.tensor_pa) == tuple(sorted([expected, 0, 0], reverse=True))
        assert p.location == "smoothed_node"
        assert p.provenance["contributing_elements"] == (2 if partition == "same" else 1)


@pytest.mark.parametrize("fault", ["missing", "duplicate", "body", "nonfinite"])
def test_smoothing_refuses_incomplete_or_misowned_tensors(fault: str) -> None:
    mesh = hand_mesh()
    points = [
        StressPoint(
            "element_node",
            1,
            None,
            n,
            mesh.bodies[1],
            mesh.materials[1],
            mesh.nodes[n],
            (1, 0, 0, 0, 0, 0),
            {},
        )
        for n in mesh.elements[1]
    ]
    if fault == "missing":
        points.pop()
    elif fault == "duplicate":
        points[-1] = points[0]
    elif fault == "body":
        points[0] = replace(points[0], body_id="foreign")
    else:
        points[0] = replace(points[0], tensor_pa=(float("nan"), 0, 0, 0, 0, 0))
    with pytest.raises(ValueError):
        smooth_nodes(points, mesh)
