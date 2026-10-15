"""Independent tensor references and rejection of damaged real output fixtures."""

from dataclasses import replace
from pathlib import Path

import pytest

from tests.benchmark_review import unsigned_manifest
from worker.calculix.results import parse_dat, parse_frd
from worker.postprocess.fields import element_nodes, probe_element
from worker.postprocess.tensors import principal, tensor, von_mises
from worker.runtime import ROOT
from worker.stress_fixture import hand_mesh, run_b09

FIXTURE = ROOT / "tests/fixtures/native/stress"


@pytest.mark.parametrize(
    "stress,expected_vm,expected_principal",
    [
        ([5, 5, 5, 0, 0, 0], 0, (5, 5, 5)),
        ([-5, -5, -5, 0, 0, 0], 0, (-5, -5, -5)),
        ([9, 0, 0, 0, 0, 0], 9, (9, 0, 0)),
        ([0, 0, 0, 3, 0, 0], 3 * 3**0.5, (3, 0, -3)),
        ([0, 0, 0, 0, 3, 0], 3 * 3**0.5, (3, 0, -3)),
        ([0, 0, 0, 0, 0, 3], 3 * 3**0.5, (3, 0, -3)),
        ([7, 4, 4, 2, 0, 0], (21) ** 0.5, (8, 4, 3)),
        ([29 / 6, 29 / 6, 7 / 3, 25 / 6, 5 / 3, -5 / 3], 75**0.5, (9, 4, -1)),
    ],
)
def test_independent_tensor_invariants(
    stress: list[float], expected_vm: float, expected_principal: tuple[float, float, float]
) -> None:
    t = tensor(stress)
    assert von_mises(t) == pytest.approx(expected_vm, rel=1e-12, abs=1e-12)
    assert principal(t) == pytest.approx(expected_principal, rel=1e-12, abs=1e-12)


@pytest.mark.parametrize("value", [[0] * 5, [float("nan")] * 6, [float("inf")] * 6])
def test_invalid_tensor_rejected(value: list[float]) -> None:
    with pytest.raises(ValueError):
        tensor(value)


def test_real_fixture_raw_and_derived_provenance() -> None:
    mesh = hand_mesh(True)
    raw = parse_dat(FIXTURE / "analysis.dat", mesh)["samples"]
    derived = element_nodes(raw, mesh)
    averaged = parse_frd(FIXTURE / "analysis.frd", mesh)
    assert len(raw) == 8 and len(derived) == 20 and len(averaged) == 14
    assert all(p.node_id is None and p.integration_point_id is not None for p in raw)
    assert all(p.location == "element_node" and p.integration_point_id is None for p in derived)
    assert all(p.location == "solver_averaged_node" and p.element_id is None for p in averaged)
    upper = probe_element(derived, mesh, 1, (0.4, 0.2, 0.4, 0))
    lower = probe_element(derived, mesh, 2, (0.4, 0.4, 0.2, 0))
    assert upper.position_m == lower.position_m
    assert upper.tensor_pa[0] == pytest.approx(210e6)
    assert lower.tensor_pa[0] == pytest.approx(70e6)
    assert upper.material_id != lower.material_id
    with pytest.raises(ValueError, match="inside"):
        probe_element(derived, mesh, 1, (1.1, -0.1, 0, 0))
    with pytest.raises(ValueError, match="four"):
        element_nodes(raw[:-1], mesh)
    with pytest.raises(ValueError, match="ownership"):
        element_nodes([replace(p, material_id="wrong") for p in raw], mesh)
    with pytest.raises(ValueError, match="provenance"):
        element_nodes(raw, replace(mesh, revision="changed"))


def test_unsigned_b09_refuses_acceptance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with unsigned_manifest(monkeypatch, "B09"), pytest.raises(ValueError, match="review pending"):
        run_b09(tmp_path / "not-created")
    assert not (tmp_path / "not-created").exists()


@pytest.mark.parametrize(
    "fault",
    [
        "truncate",
        "missing_ip",
        "duplicate_ip",
        "nan",
        "order",
        "location",
        "frame_time",
        "second_step",
    ],
)
def test_damaged_dat_fails_closed(fault: str, tmp_path: Path) -> None:
    text = (FIXTURE / "analysis.dat").read_text()
    stress_rows = [
        line for line in text.splitlines() if len(line.split()) == 8 and line.split()[0].isdigit()
    ]
    if fault == "truncate":
        text = text[:-8]
    elif fault == "missing_ip":
        text = text.replace(stress_rows[-1] + "\n", "")
    elif fault == "duplicate_ip":
        text = text.replace(stress_rows[-1], stress_rows[0])
    elif fault == "nan":
        text = text.replace("2.100000E+08", "NaN")
    elif fault == "order":
        text = text.replace("sxy,sxz,syz", "sxy,syz,sxz")
    elif fault == "location":
        text = text.replace("1.381966E-01", "2.381966E-01")
    elif fault == "frame_time":
        text = text.replace("0.1000000E+01", "0.2000000E+01", 1)
    else:
        text += "\n S T E P 2\n"
    path = tmp_path / "analysis.dat"
    path.write_text(text)
    with pytest.raises(ValueError):
        parse_dat(path, hand_mesh(True))


@pytest.mark.parametrize(
    "fault",
    [
        "truncate",
        "missing_node",
        "duplicate_node",
        "bad_width",
        "order",
        "connectivity",
        "coordinate",
    ],
)
def test_damaged_frd_fails_closed(fault: str, tmp_path: Path) -> None:
    text = (FIXTURE / "analysis.frd").read_text()
    start = text.index(" -4  STRESS")
    stress = [line for line in text[start:].splitlines() if line.startswith(" -1")]
    if fault == "truncate":
        text = text[:-6]
    elif fault == "missing_node":
        text = text.replace(stress[-1] + "\n", "")
    elif fault == "duplicate_node":
        text = text.replace(stress[-1], stress[0])
    elif fault == "bad_width":
        text = text.replace(stress[0], stress[0][:-1])
    elif fault == "order":
        text = text.replace("SYZ", "SXZ")
    elif fault == "connectivity":
        text = text.replace(" -2         1         2", " -2         2         1", 1)
    else:
        text = text.replace(" -1         1 0.00000E+00", " -1         1 1.00000E+00", 1)
    path = tmp_path / "analysis.frd"
    path.write_text(text)
    with pytest.raises(ValueError):
        parse_frd(path, hand_mesh(True))
