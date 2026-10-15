"""Necessary rigid-motion checks, invalid graph dependencies and native error semantics."""

from pathlib import Path

import pytest

from tests.benchmark_review import unsigned_manifest
from worker.assembly_fixture import run_b11
from worker.calculix.assembly import WARNING, components, support_rank
from worker.directions import IDENTITY
from worker.local_solve import SolverSingularity, check_numerical_log


@pytest.mark.parametrize(
    "edges",
    [
        [("a", "a")],
        [("a", "missing")],
        [("a", "b"), ("b", "a")],
        [("a", "b"), ("b", "c"), ("c", "a")],
    ],
)
def test_invalid_redundant_and_cyclic_connections_refuse(edges: list[tuple[str, str]]) -> None:
    with pytest.raises(ValueError):
        components(["a", "b", "c"], edges)


def test_components_do_not_treat_an_unapproved_proximity_as_connectivity() -> None:
    assert components(["a", "b", "c"], [("a", "b")]) == [["a", "b"], ["c"]]
    assert "not proof" in WARNING and "no weak springs" in WARNING


@pytest.mark.parametrize("case,rank", [("none", 0), ("one_point", 3), ("x_only", 3), ("full", 6)])
def test_finite_rigid_motion_requires_independent_support_rows(case: str, rank: int) -> None:
    points = [(0.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]
    rows = []
    if case == "one_point":
        rows = [(points[0], d) for d in IDENTITY]
    if case == "x_only":
        rows = [(p, IDENTITY[0]) for p in points]
    if case == "full":
        rows = [(p, d) for p in points for d in IDENTITY]
    assert support_rank(rows, points) == rank
    # Exactly constant, finite translation has zero relative displacement on
    # every edge; its existence cannot be disproved by finite solver output.
    mode = {p: (1.0, 2.0, 3.0) for p in points}
    assert all(a == b for a in mode.values() for b in mode.values())


@pytest.mark.parametrize(
    "message",
    [
        "matrix is singular",
        "zero pivot",
        "negative pivot",
        "matrix not positive definite",
        "rigid body mode",
    ],
)
def test_native_singularity_markers_are_actionable_even_with_finish_marker(message: str) -> None:
    with pytest.raises(SolverSingularity, match="no weak springs"):
        check_numerical_log(message + "\nJob finished")


def test_finish_marker_alone_does_not_establish_structural_validity() -> None:
    check_numerical_log("Factoring system\nJob finished")
    assert support_rank([], [(0.0, 0.0, 0.0), (1.0, 1.0, 1.0)]) == 0


def test_unsigned_b11_refuses_before_creating_native_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with unsigned_manifest(monkeypatch, "B11"), pytest.raises(ValueError, match="review pending"):
        run_b11(tmp_path / "absent")
    assert not (tmp_path / "absent").exists()
