"""Independent polynomial body integration and external-component balance references."""

from dataclasses import asdict
from typing import Any

import pytest

from worker.actions import (
    balance_check,
    constrain,
    deck_actions,
    external_balance,
    gravity_forces,
    rigid_rank,
)
from worker.deck import generated_deck
from worker.meshing import FACES, Vec, resultant
from worker.stress_fixture import hand_mesh


def wire() -> tuple[Any, dict[str, Any], dict[str, Any]]:
    mesh = hand_mesh(False)
    raw = asdict(mesh) | {
        "boundary": {
            f"face{i}": [{"element": 1, "face": i, "nodes": [mesh.elements[1][j] for j in indices]}]
            for i, indices in enumerate(FACES, 1)
        }
    }
    dat = {
        "displacements_m": {n: (0, 0, 0) for n in mesh.nodes},
        "external_forces_n": {n: (0, 0, 0) for n in mesh.nodes},
    }
    return mesh, raw, dat


def test_exact_body_shape_integrals_preserve_negative_corner_weights_and_moment() -> None:
    mesh, _, _ = wire()
    forces = gravity_forces(mesh.nodes, mesh.elements, {1: (0, 0, -3)}, {1: 1200})
    # Unit reference tetra has V=1/6, integral N_corner=-1/120,
    # integral N_edge=1/30; rho*g=-3600. No production result is the reference.
    assert all(forces[n] == pytest.approx((0, 0, 30), abs=1e-12) for n in range(1, 5))
    assert all(forces[n] == pytest.approx((0, 0, -120), abs=1e-12) for n in range(5, 11))
    force, moment = resultant(forces, mesh.nodes)
    assert force == pytest.approx((0, 0, -600), abs=1e-12)
    assert moment == pytest.approx((-150, 150, 0), abs=1e-12)


def test_written_gravity_is_subtracted_on_supports_with_exact_weight_balance() -> None:
    mesh, raw, dat = wire()
    supported = raw["boundary"]["face1"][0]["nodes"]
    deck = generated_deck(
        raw,
        {(n, a): 0 for n in supported for a in (1, 2, 3)},
        {},
        0,
        0,
        materials={"UPPER": (210e9, 0)},
        element_materials={1: "UPPER"},
        densities={"UPPER": 1200},
        gravities={"UPPER": (0, 0, -3)},
    )
    assert "UPPER,GRAV,3.000000000000e+00,0,0,-1" in deck and "*CLOAD" not in deck
    for n in mesh.nodes:
        equivalent = 30 if n <= 4 else -120
        reaction = {1: 300, 2: 150, 3: 150}.get(n, 0)
        dat["external_forces_n"][n] = (0, 0, equivalent + reaction)
    checked, bodies = external_balance(dat, mesh, raw["boundary"], deck)
    assert checked["passed"]
    assert checked["reaction_force_n"] == pytest.approx((0, 0, 600), abs=1e-12)
    assert checked["reaction_moment_nm"] == pytest.approx((150, -150, 0), abs=1e-12)
    assert checked["force"]["reference"] == pytest.approx(600, abs=1e-12)
    assert bodies[0]["node_count"] == 6 and bodies[0]["constrained_dof_count"] == 18


def test_partial_supports_prescribed_actuators_and_internal_free_rf_are_distinct() -> None:
    mesh, raw, dat = wire()
    deck = generated_deck(raw, {(1, 1): 0, (2, 1): 0.001}, {}, 210e9, 0)
    deck = deck.replace(
        "*END STEP", "*BOUNDARY\n1,1,1,0\n1,1,1,0\n*EQUATION\n2\n3,1,1,4,1,-1\n*END STEP"
    )
    dat["displacements_m"][2] = (0.001, 0, 0)
    dat["external_forces_n"][1] = (-10, 999, 0)
    dat["external_forces_n"][2] = (10, -888, 0)
    dat["external_forces_n"][3] = (1e6, 2e6, -3e6)
    checked, bodies = external_balance(dat, mesh, raw["boundary"], deck)
    assert checked["passed"] and checked["reaction_force_n"] == pytest.approx((0, 0, 0))
    assert checked["prescribed_actuator_reference_n"] == 10
    assert checked["force"]["criterion"] == "relative" and checked["force"]["reference"] == 10
    assert bodies[0]["node_count"] == 2 and bodies[0]["constrained_dof_count"] == 2
    # A forged displacement result cannot credit the prescribed support contract.
    dat["displacements_m"][2] = (0, 0, 0)
    with pytest.raises(ValueError, match="prescribed displacement"):
        external_balance(dat, mesh, raw["boundary"], deck)


@pytest.mark.parametrize("reference", [0, 1e-20, 1e-8])
def test_near_zero_uses_absolute_balance_without_fake_normalized_percentage(
    reference: float,
) -> None:
    good = balance_check((5e-7, 0, 0), reference, 1e-6)
    bad = balance_check((2e-6, 0, 0), reference, 1e-6)
    assert good["criterion"] == "absolute" and good["relative_residual"] is None
    assert good["passed"] and not bad["passed"]


def test_self_equilibrated_loads_use_magnitudes_instead_of_zero_net_force() -> None:
    mesh, raw, dat = wire()
    deck = generated_deck(raw, {(1, 1): 0}, {2: (10, 0, 0), 5: (-10, 0, 0)}, 210e9, 0)
    dat["external_forces_n"][2] = (10, 0, 0)
    dat["external_forces_n"][5] = (-10, 0, 0)
    checked, _ = external_balance(dat, mesh, raw["boundary"], deck)
    assert checked["applied_force_n"] == pytest.approx((0, 0, 0))
    assert checked["force"]["reference"] == 20 and checked["force"]["criterion"] == "relative"
    assert checked["passed"]
    dat["external_forces_n"][1] = (1, 0, 0)
    assert not external_balance(dat, mesh, raw["boundary"], deck)[0]["passed"]


@pytest.mark.parametrize(
    "points,axes,expected",
    [
        ([(0, 0, 0)], (1, 2, 3), 3),
        ([(0, 0, 0), (1, 0, 0)], (1, 2, 3), 5),
        ([(0, 0, 0), (1, 0, 0), (0, 1, 0)], (1, 2, 3), 6),
        ([(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)], (1,), 3),
    ],
)
def test_rigid_component_rank_is_dimensionless_and_translation_invariant(
    points: list[Vec], axes: tuple[int, ...], expected: int
) -> None:
    assert rigid_rank(((p, a) for p in points for a in axes), (0, 0, 0), 1) == expected
    moved = [(p[0] + 1e6, p[1] - 2e6, p[2] + 3e6) for p in points]
    assert rigid_rank(((p, a) for p in moved for a in axes), (1e6, -2e6, 3e6), 1) == expected


def test_duplicate_components_deduplicate_and_conflicting_values_refuse() -> None:
    supports: dict[tuple[int, int], float] = {}
    constrain(supports, 1, 1, 0)
    constrain(supports, 1, 1, 0)
    assert supports == {(1, 1): 0}
    with pytest.raises(ValueError, match="Conflicting"):
        constrain(supports, 1, 1, 0.000001)
    mesh, raw, _ = wire()
    deck = generated_deck(raw, {(1, 1): 0}, {}, 210e9, 0)
    with pytest.raises(ValueError, match="Conflicting"):
        deck_actions(deck.replace("*STEP", "1,1,1,0.001\n*STEP"), mesh, raw["boundary"])


def test_written_gravity_missing_or_negative_density_and_nonfinite_rf_refuse() -> None:
    mesh, raw, dat = wire()
    deck = generated_deck(
        raw,
        {(1, 1): 0},
        {},
        0,
        0,
        materials={"UPPER": (210e9, 0)},
        element_materials={1: "UPPER"},
        densities={"UPPER": 1200},
        gravities={"UPPER": (0, 0, -3)},
    )
    with pytest.raises(ValueError, match="density"):
        deck_actions(deck.replace("1.200000000000e+03", "-1"), mesh, raw["boundary"])
    dat["external_forces_n"][4] = (float("nan"), 0, 0)
    with pytest.raises(ValueError, match="Nonfinite"):
        external_balance(dat, mesh, raw["boundary"], deck)
