"""T002 availability checks: actual native libraries and one real CCX equation."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from worker.runtime import ROOT, Component, probe, sha256, solve_reference, verified_tool

FIXTURE = ROOT / "tests/fixtures/native"


@pytest.mark.parametrize("component", ["cad", "mesh", "post"])
def test_separate_native_capabilities(component: Component, tmp_path: Path) -> None:
    result = probe(component, tmp_path)
    assert result["component"] == component
    output = ROOT / ".local/native/validation"
    output.mkdir(parents=True, exist_ok=True)
    (output / f"{component}.json").write_text(json.dumps(result, indent=2) + "\n")


@pytest.mark.parametrize("component", ["cad", "mesh", "post"])
def test_native_process_has_no_network(component: Component, tmp_path: Path) -> None:
    result = probe(component, tmp_path, network_only=True)
    assert result["network_denied"] is True
    checked = result["checked"]
    assert isinstance(checked, list) and len(checked) == 3


def test_missing_solver_fails_clearly(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FEA_CCX_PATH", str(tmp_path / "absent-ccx"))
    with pytest.raises(RuntimeError, match="Missing executable ccx"):
        verified_tool("ccx")


def test_modified_solver_fails_before_execution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    impostor = tmp_path / "ccx"
    impostor.write_text("untrusted content; must never execute")
    impostor.chmod(0o700)
    monkeypatch.setenv("FEA_CCX_PATH", str(impostor))
    with pytest.raises(RuntimeError, match="Unverified ccx binary"):
        verified_tool("ccx")


def dat_section(text: str, heading: str, columns: int) -> list[list[float]]:
    rows: list[list[float]] = []
    active = False
    for line in text.splitlines():
        if line.strip().startswith(heading):
            active = True
            continue
        parts = line.split()
        if active and parts:
            if not parts[0].isdigit():
                if rows:
                    break
                continue
            assert len(parts) == columns
            rows.append([float(value) for value in parts])
    assert rows, f"No native {heading} output found"
    return rows


def test_real_c3d10_reference(tmp_path: Path) -> None:
    # The deck and analytical expectations are declared in the fixture before running CCX.
    shutil.copy2(FIXTURE / "smoke.inp", tmp_path / "smoke.inp")
    reference = json.loads((FIXTURE / "smoke.json").read_text())
    result = solve_reference(tmp_path)
    assert "Version 2.23" in result.stdout
    assert "Job finished" in result.stdout
    assert "*ERROR" not in result.stdout + result.stderr
    equations = re.search(r"number of equations\s*:?\s*(\d+)", result.stdout, re.I)
    assert equations and int(equations[1]) == reference["solver_equations"]
    assert (tmp_path / "smoke.frd").stat().st_size > 0
    raw = (tmp_path / "smoke.dat").read_text()
    displacements = dat_section(raw, "displacements", 4)
    stresses = dat_section(raw, "stresses", 8)
    forces = dat_section(raw, "forces", 4)
    assert len(displacements) == 10
    assert len(stresses) == reference["expected_integration_points"]
    assert len(forces) == 10
    free = next(row for row in displacements if row[0] == 2)
    assert free[1] == pytest.approx(
        reference["expected_node2_ux_m"],
        rel=reference["relative_tolerance"],
        abs=reference["displacement_absolute_tolerance_m"],
    )
    for row in stresses:
        assert row[0] == 1
        assert row[2:] == pytest.approx(
            reference["expected_stress_pa"],
            rel=reference["relative_tolerance"],
            abs=reference["stress_absolute_tolerance_pa"],
        )
    balance = [sum(row[axis] for row in forces) for axis in (1, 2, 3)]
    assert balance == pytest.approx([0, 0, 0], abs=reference["force_balance_absolute_tolerance_n"])
    output = ROOT / ".local/native/validation"
    output.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(tmp_path / "smoke.dat", output / "smoke.dat")
    (output / "solver.log").write_text(result.stdout + result.stderr)
    (output / "result.json").write_text(
        json.dumps(
            {
                "code_commit": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
                ).strip(),
                "fixture_sha256": sha256(FIXTURE / "smoke.inp"),
                "reference_sha256": sha256(FIXTURE / "smoke.json"),
                "solver_sha256": sha256(verified_tool("ccx")),
                "displacements": displacements,
                "stresses_raw_order": stresses,
                "force_balance_n": balance,
                "free_node2_ux_m": free[1],
                "relative_displacement_error": abs(free[1] - reference["expected_node2_ux_m"])
                / abs(reference["expected_node2_ux_m"]),
                "equations": int(equations[1]),
                "network_policy": "seccomp: all socket creation denied",
                "numerical_status": "passed predeclared T002 smoke; not a release benchmark",
            },
            indent=2,
        )
        + "\n"
    )
