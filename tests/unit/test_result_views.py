"""Independent constant fields, reaction accounting and invalid view contracts."""

from copy import deepcopy
from dataclasses import asdict
from typing import Any

import pytest

from worker.calculix.results import GAUSS, StressPoint
from worker.deck import generated_deck
from worker.meshing import FACES, surface_integral
from worker.postprocess.tensors import COMPONENTS, tensor
from worker.postprocess.view import build_view, vector
from worker.stress_fixture import hand_mesh


def fixture(stress: list[float], strength: float | None = 250e6) -> tuple[Any, ...]:
    mesh = hand_mesh(False)
    body = mesh.bodies[1]
    raw_mesh = asdict(mesh) | {
        "units": "m",
        "owners": mesh.bodies,
        "boundary": {
            f"face{i}": [{"element": 1, "face": i, "nodes": [mesh.elements[1][j] for j in indices]}]
            for i, indices in enumerate(FACES, 1)
        },
    }
    points = [
        asdict(
            StressPoint(
                "integration_point",
                1,
                i,
                None,
                body,
                "UPPER",
                vector(
                    [
                        sum(b[j] * mesh.nodes[mesh.elements[1][j]][a] for j in range(4))
                        for a in range(3)
                    ]
                ),
                tensor(stress),
                {
                    "mesh_sha256": mesh.identity(),
                    "components": COMPONENTS,
                    "frame": "global_cartesian",
                    "units": "Pa",
                    "line": i,
                    "source_sha256": "a" * 64,
                },
            )
        )
        for i, b in enumerate(GAUSS, 1)
    ]
    raw = {
        "schema_version": 1,
        "components": list(COMPONENTS),
        "frame": "global_cartesian",
        "stress_location": "integration_point",
        "result_mesh_sha256": mesh.identity(),
        "units": {"displacement": "m", "stress": "Pa", "force": "N"},
        "integration_points": points,
        "warnings": ["Frozen warning"],
        "dat": {
            "source_sha256": "a" * 64,
            "displacements_m": {n: (0, 0, 0) for n in mesh.nodes},
            "external_forces_n": {n: (0, 0, 0) for n in mesh.nodes},
        },
    }
    materials = {body: {"material_id": "UPPER", "yield_strength_pa": strength, "name": "Synthetic"}}
    deck = generated_deck(raw_mesh, {(1, a): 0 for a in (1, 2, 3)}, {}, 210e9, 0.3)
    return raw, raw_mesh, materials, deck


@pytest.mark.parametrize(
    "stress,expected",
    [
        ([1000, 0, 0, 0, 0, 0], 1000),
        ([500, 500, 500, 0, 0, 0], 0),
        ([0, 0, 0, 1000, 0, 0], 3**0.5 * 1000),
    ],
)
def test_constant_tensors_preserve_surface_and_raw_extrema(
    stress: list[float], expected: float
) -> None:
    view = build_view(*fixture(stress))
    assert len(view["vertices"]) == 24 and len(view["triangles"]) == 16
    assert {v["node_id"] for v in view["vertices"]} == set(range(1, 11))
    assert all(
        v["von_mises_pa"] == pytest.approx(expected, rel=1e-12, abs=1e-9) for v in view["vertices"]
    )
    assert view["von_mises"]["maximum"]["value"] == pytest.approx(expected)
    assert view["von_mises"]["maximum"]["location"] == "integration_point"
    assert view["warnings"] == ["Frozen warning"]


@pytest.mark.parametrize(
    "stress,strength,state,factor",
    [
        (0, 250e6, "unbounded", None),
        (1e-7, 250e6, "unbounded", None),
        (1000, None, "unavailable", None),
        (1000, 250e6, "finite", 250000),
        (1000, 500, "finite", 0.5),
    ],
)
def test_zero_missing_and_exceeded_yield_are_truthful(
    stress: float, strength: float | None, state: str, factor: float | None
) -> None:
    view = build_view(*fixture([stress, 0, 0, 0, 0, 0], strength))
    result = view["yield_factors"][0]
    assert result["state"] == state and result["minimum"] == factor
    assert any("does not model plastic" in w for w in view["warnings"]) == (factor == 0.5)


def test_pressure_on_fixed_nodes_is_removed_from_rf_and_support_nodes_deduplicated() -> None:
    raw, wire, materials, _ = fixture([1000, 0, 0, 0, 0, 0])
    face = wire["boundary"]["face1"][0]
    fixed = {(n, a): 0.0 for n in face["nodes"] for a in (1, 2, 3)}
    deck = generated_deck(wire, fixed, {}, 210e9, 0.3, pressure=(1, 1, 1000))
    equivalent = surface_integral([wire["nodes"][n] for n in face["nodes"]], pressure=1000)[2]
    # Independent prescribed equilibrium: RF contains applied + reaction.
    for n, force in zip(face["nodes"], equivalent, strict=True):
        raw["dat"]["external_forces_n"][n] = (force[0], force[1], force[2] - 10)
    # Repeated boundary constraints must not create repeated support reactions.
    deck = deck.replace("*STEP", "1,1,3,0\n*STEP")
    result = build_view(raw, wire, materials, deck)
    assert result["reaction_force_n"] == pytest.approx([0, 0, -60], abs=1e-12)
    assert result["reactions"][0]["node_count"] == 6


def test_extrapolate_tensor_before_invariant_and_keep_raw_peak_separate() -> None:
    raw, mesh, materials, deck = fixture([1000, 0, 0, 0, 0, 0])
    for p, sign in zip(raw["integration_points"], (1, -1, 1, -1), strict=True):
        p["tensor_pa"] = (sign * 1000, 0, 0, 0, 0, 0)
    view = build_view(raw, mesh, materials, deck)
    # Four-point Gauss A-B=1/sqrt(5); opposing corner tensors cancel at edge 1-2.
    corner = next(v for v in view["vertices"] if v["node_id"] == 1)
    midside = next(v for v in view["vertices"] if v["node_id"] == 5)
    assert corner["von_mises_pa"] == pytest.approx(1000 * 5**0.5, rel=1e-12)
    assert midside["von_mises_pa"] == pytest.approx(0, abs=1e-9)
    assert view["von_mises"]["maximum"]["value"] == 1000
    assert view["yield_factors"][0]["minimum"] == 250000


def test_raw_extremum_retains_interior_native_ip_identity() -> None:
    raw, mesh, materials, deck = fixture([1000, 0, 0, 0, 0, 0])
    raw["integration_points"][3]["tensor_pa"] = (5000, 0, 0, 0, 0, 0)
    result = build_view(raw, mesh, materials, deck)
    peak = result["von_mises"]["maximum"]
    assert peak["value"] == 5000 and peak["integration_point_id"] == 4
    assert peak["position_m"] == raw["integration_points"][3]["position_m"]


@pytest.mark.parametrize(
    "fault", ["mesh", "material", "frame", "units", "source", "missing_ip", "nonfinite", "surface"]
)
def test_damaged_derived_inputs_fail_closed(fault: str) -> None:
    raw, mesh, materials, deck = deepcopy(fixture([1000, 0, 0, 0, 0, 0]))
    if fault == "mesh":
        raw["result_mesh_sha256"] = "b" * 64
    elif fault == "material":
        next(iter(materials.values()))["material_id"] = "Wrong"
    elif fault == "frame":
        raw["frame"] = "local"
    elif fault == "units":
        raw["units"]["stress"] = "MPa"
    elif fault == "source":
        raw["integration_points"][0]["provenance"]["source_sha256"] = "b" * 64
    elif fault == "missing_ip":
        raw["integration_points"].pop()
    elif fault == "nonfinite":
        raw["dat"]["displacements_m"][1] = [float("nan"), 0, 0]
    else:
        mesh["boundary"]["face1"][0]["nodes"][0] = 999
    with pytest.raises((ValueError, KeyError)):
        build_view(raw, mesh, materials, deck)
