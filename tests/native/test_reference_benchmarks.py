"""Real Gmsh -> C3D10 -> CCX -> strict DAT reference comparisons, no external binaries."""

from pathlib import Path

import pytest

from worker.benchmark import run_case


@pytest.mark.parametrize("case", ["B10", "B12", "B13", "B14"])
def test_real_predeclared_reference(case: str, tmp_path: Path) -> None:
    result = run_case(case, tmp_path / case, development=True)
    assert result["status"] == "DEVELOPMENT PASS; owner acceptance pending"
    assert result["code_aster_executed"] is False
    assert result["ansys_executed"] is False
    assert len(result["runs"]) == (3 if case == "B10" else 2)
    assert all(run["equilibrium"]["passed"] for run in result["runs"])
    assert all(run["nodes"] > 0 and run["elements"] > 0 for run in result["runs"])
    with pytest.raises(FileExistsError):
        run_case(case, tmp_path / case, development=True)
