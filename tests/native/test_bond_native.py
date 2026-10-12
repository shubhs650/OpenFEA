"""Actual nonmatching C3D10 coupling, rejected native ties and geometry audits."""

import shutil
from pathlib import Path

from worker.bond_fixture import native_diagnostics, run_b07
from worker.runtime import ROOT


def test_nonmatching_two_block_bond_and_reversed_roles_against_monolithic(tmp_path: Path) -> None:
    result = run_b07(tmp_path, development=True)
    assert result["status"].startswith("DEVELOPMENT PASS")
    assert set(result["bonded_cases"]) == {"left_master", "right_master"}
    for case in result["bonded_cases"].values():
        assert sorted(case["body_nodes"].values()) == [231, 423]
        assert case["body_count"] == 2
        assert case["solver_uncovered_nodes"] == []
        assert case["intended_slave_nodes"] in (37, 65)
        assert case["coordinate_audit"]["max_solver_adjustment_m"] == 0
        assert case["relative_end_displacement_difference_to_monolithic"] < 1e-6
        assert case["coupling"]["affine_reproduction_error"] < 1e-12
        assert case["coupling"]["uniform_traction_transfer_error"] < 1e-12
        assert case["mean_end_ux_m"] > 0
    shutil.copytree(tmp_path, ROOT / ".local/native/validation/T005/B07", dirs_exist_ok=True)


def test_rejected_native_tie_missing_coverage_singularity_and_adjustment(tmp_path: Path) -> None:
    result = native_diagnostics(tmp_path)
    candidate = result["native_tie_candidate"]
    assert candidate["max_stress_error_pa"] > 5e4
    assert candidate["uncovered_nodes"] == []
    assert candidate["coordinate_audit"]["max_solver_adjustment_m"] == 0
    assert len(result["partial_master"]["uncovered_nodes"]) > 0
    assert "detached" in result["untied"]["preflight_diagnosis"]
    assert result["gap_keyword_audit"]["default_adjust"]["max_solver_adjustment_m"] > 0.9e-5
    assert result["gap_keyword_audit"]["adjust_no"]["max_solver_adjustment_m"] == 0
    shutil.copytree(
        tmp_path, ROOT / ".local/native/validation/T005/diagnostics", dirs_exist_ok=True
    )


def test_real_failed_ccx_retains_complete_transcript(tmp_path: Path) -> None:
    import pytest

    from worker.runtime import NativeOperationError, solve_generated

    # Internal malformed diagnostic; never an uploaded-deck execution API.
    (tmp_path / "analysis.inp").write_text(
        "*NODE,NSET=NALL\n1,invalid,0,0\n*STEP\n*STATIC\n*END STEP\n"
    )
    with pytest.raises(NativeOperationError) as failure:
        solve_generated(tmp_path)
    assert failure.value.result.returncode != 0
    assert "Version 2.23" in failure.value.result.stdout
    assert "*ERROR" in failure.value.result.stdout
