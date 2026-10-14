"""Independent direction/basis, compatible constraint and written-frame references."""

import math

import pytest

from worker.actions import deck_actions, external_balance, rigid_rank_directions
from worker.calculix.results import Mesh
from worker.deck import generated_deck
from worker.directions import (
    IDENTITY,
    compile_constraints,
    constraint_frame,
    frame,
    global_vector,
    local_vector,
)
from worker.meshing import cross, dot, scale


def test_signed_basis_is_orthonormal_right_handed_and_reversal_is_visible() -> None:
    direction = (2.0, -3.0, 6.0)
    positive, negative = frame(direction), frame(scale(direction, -1))
    assert positive[0] == pytest.approx([2 / 7, -3 / 7, 6 / 7], abs=1e-15)
    assert negative[0] == pytest.approx([-2 / 7, 3 / 7, -6 / 7], abs=1e-15)
    for basis in [positive, negative]:
        for i in range(3):
            for j in range(3):
                assert dot(basis[i], basis[j]) == pytest.approx(float(i == j), abs=1e-15)
        assert dot(cross(basis[0], basis[1]), basis[2]) == pytest.approx(1, abs=1e-15)
    vector = (3.0, 4.0, 5.0)
    assert global_vector(local_vector(vector, positive), positive) == pytest.approx(
        vector, abs=1e-14
    )


@pytest.mark.parametrize(
    "primary,secondary",
    [
        ((0, 0, 0), None),
        ((math.nan, 0, 0), None),
        ((1, 0, 0), (2, 0, 0)),
        ((1, 0, 0), (1, 1e-12, 0)),
    ],
)
def test_invalid_or_singular_basis_refuses(
    primary: tuple[float, float, float], secondary: tuple[float, float, float] | None
) -> None:
    with pytest.raises(ValueError):
        frame(primary, secondary)


def test_duplicate_and_reversed_constraints_deduplicate_without_overwriting() -> None:
    direction = frame((1, 1, 0))[0]
    resolved = constraint_frame(
        [(direction, 1e-6), (direction, 1e-6), (scale(direction, -1), -1e-6)]
    )
    assert len(resolved.values) == 1
    assert resolved.values[1] == 1e-6
    with pytest.raises(ValueError, match="Conflicting"):
        constraint_frame([(direction, 1e-6), (direction, 1e-6 + 1e-21)])
    with pytest.raises(ValueError, match="Conflicting"):
        constraint_frame([(direction, 1e-20), (scale(direction, -1), 1e-20)])


def test_combined_dependent_rows_check_values_and_reject_near_singular_independence() -> None:
    diagonal = frame((1, 1, 0))[0]
    compatible = constraint_frame(
        [(IDENTITY[0], 1e-6), (IDENTITY[1], 1e-6), (diagonal, math.sqrt(2) * 1e-6)]
    )
    assert len(compatible.values) == 2
    with pytest.raises(ValueError, match="Contradictory"):
        constraint_frame([(IDENTITY[0], 0), (IDENTITY[1], 0), (diagonal, 1e-20)])
    with pytest.raises(ValueError, match="Ill-conditioned"):
        constraint_frame([(IDENTITY[0], 0), ((1, 1e-11, 0), 0)])


def test_exact_legacy_global_components_keep_identity_and_values() -> None:
    supports, transforms = compile_constraints(
        {8: [(IDENTITY[1], 0), (IDENTITY[0], 1e-6)], 3: [(scale(IDENTITY[2], -1), 0)]}
    )
    assert supports == {(8, 2): 0, (8, 1): 1e-6, (3, 3): 0}
    assert transforms == {}
    with pytest.raises(ValueError):
        compile_constraints({8: [(IDENTITY[1], 0), (IDENTITY[1], 1e-30)]})


def test_direction_rigid_rank_uses_rotations_and_not_only_translation_axes() -> None:
    a = frame((1, 2, 3))
    points = [global_vector(p, a) for p in [(0, 0, 0), (0, 1, 0), (0, 0, 1)]]
    rows = [(p, q) for p in points for q in a]
    assert rigid_rank_directions(rows, (0, 0, 0), 1) == 6
    assert rigid_rank_directions([(p, a[0]) for p in points], (0, 0, 0), 1) == 3


def test_written_transform_cload_and_external_reaction_project_in_global_frame() -> None:
    basis = frame((1, 1, 0))
    raw = {"nodes": {"1": [0, 0, 0]}, "elements": {}, "boundary": {}}
    supports: dict[tuple[int, int], float] = {(1, 1): 0}
    load = global_vector((0, 2, 0), basis)  # allowed tangent concentrated load in this math fixture
    deck = generated_deck(raw, supports, {1: load}, 210e9, 0.3, transforms={1: basis})
    mesh = Mesh({1: (0, 0, 0)}, {}, {}, {}, "direction-fixture")
    written = deck_actions(deck, mesh, {})
    assert written.applied[1] == pytest.approx(load, abs=1e-12)
    normal_reaction = scale(basis[0], 3)
    dat = {
        "external_forces_n": {"1": [load[i] + normal_reaction[i] for i in range(3)]},
        "displacements_m": {"1": [0, 0, 0]},
    }
    equilibrium, bodies = external_balance(
        dat,
        mesh,
        {},
        deck,
        {
            "resultant_complete": True,
            "total_force_n": load,
            "total_moment_nm": [0, 0, 0],
            "force_scale_n": 2,
            "moment_scale_nm": 0,
            "characteristic_length_m": 1,
        },
    )
    assert equilibrium["reaction_force_n"] == pytest.approx(normal_reaction, abs=1e-12)
    assert not equilibrium["passed"]  # tangent applied force is deliberately unbalanced
    assert bodies == []
    for keyword in ["*NODE PRINT,NSET=NALL,GLOBAL=YES", "*NODE FILE,GLOBAL=YES"]:
        with pytest.raises(ValueError, match="global vectors"):
            deck_actions(deck.replace(keyword, keyword.replace(",GLOBAL=YES", "")), mesh, {})
    duplicate = deck.replace(
        "*BOUNDARY", "*TRANSFORM,NSET=LOCAL1,TYPE=R\n1,0,0,0,1,0\n*BOUNDARY", 1
    )
    with pytest.raises(ValueError, match="overwrite"):
        deck_actions(duplicate, mesh, {})


def test_direction_edge_cannot_borrow_topology_vertices_from_another_body() -> None:
    from app.domain.models import GeometryMetadata

    metadata = {
        "source_sha256": "a" * 64,
        "brep_sha256": "b" * 64,
        "units": {"source_length_unit": "m", "confirmed": True},
        "bodies": [{"id": "body1"}, {"id": "body2"}],
        "faces": [
            {"id": "face1", "body_id": "body1", "signature": {}},
            {"id": "face2", "body_id": "body2", "signature": {}},
        ],
        "vertices": [
            {"id": "v1", "body_id": "body1", "point_m": [0, 0, 0], "face_ids": ["face1"]},
            {"id": "v2", "body_id": "body2", "point_m": [1, 0, 0], "face_ids": ["face2"]},
            {"id": "v3", "body_id": "body1", "point_m": [1, 0, 0], "face_ids": ["face1"]},
        ],
        "edges": [
            {
                "id": "edge1",
                "body_id": "body1",
                "curve_type": "GeomAbs_Line",
                "face_ids": ["face1"],
                "vertex_ids": ["v2"],
                "start_m": [0, 0, 0],
                "end_m": [1, 0, 0],
            }
        ],
        "validation": {},
    }
    with pytest.raises(ValueError, match="body vertex ownership"):
        GeometryMetadata.model_validate(metadata)
    metadata["edges"][0]["vertex_ids"] = ["v1", "v3"]  # type: ignore[index]
    assert GeometryMetadata.model_validate(metadata).edges[0].body_id == "body1"
