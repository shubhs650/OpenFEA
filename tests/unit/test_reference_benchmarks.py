"""Pending reference reviews fail closed; nonfinite and out-of-tolerance results fail."""

from pathlib import Path

import pytest

from tests.benchmark_review import unsigned_manifest
from worker.benchmark import run_case
from worker.reference_benchmarks import compare, reference_displacement


@pytest.mark.parametrize("case", ["B10", "B12", "B13", "B14"])
def test_unsigned_reference_refuses_before_output(
    case: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / case
    with unsigned_manifest(monkeypatch, case), pytest.raises(ValueError, match="Engineering-owner"):
        run_case(case, output)
    assert not output.exists()


@pytest.mark.parametrize("actual", [float("nan"), float("inf"), 1.002])
def test_reference_failure_cannot_be_reported_as_pass(actual: float) -> None:
    with pytest.raises(ValueError, match="Predeclared reference failed"):
        compare(actual, 1, 0.001, 1e-10)


def test_published_corner_and_point_values_match_independent_continuum_formulas() -> None:
    assert reference_displacement("B12", (1, 1, 1)) == (0.002, 0.002, 0.002)
    assert reference_displacement("B13", (0, 0, 0))[2] == pytest.approx(-1.721655e-6)
