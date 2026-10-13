"""Native full-tensor, integration location, discontinuity and export evidence."""

import json
import shutil
from pathlib import Path

import pytest

from worker.calculix.results import parse_dat
from worker.postprocess.fields import element_nodes, probe_element
from worker.postprocess.tensors import principal, von_mises
from worker.runtime import ROOT
from worker.stress_fixture import diagnostic_case, run_b09


@pytest.mark.parametrize("case", ["hydrostatic", "pure-shear", "varying-shear"])
def test_native_tensor_and_location_diagnostics(case: str, tmp_path: Path) -> None:
    references = json.loads((ROOT / "tests/fixtures/native/stress-cases.json").read_text())
    mesh, payload = diagnostic_case(tmp_path, case)
    tolerance = references["tolerances"]
    if case != "varying-shear":
        reference = references["cases"][case]
        for point in payload["integration_points"] + payload["element_nodes"]:
            assert point["tensor_pa"] == pytest.approx(
                reference["expected_canonical_stress_pa"],
                rel=tolerance["relative"],
                abs=tolerance["stress_absolute_pa"],
            )
            assert point["von_mises_pa"] == pytest.approx(
                reference["expected_von_mises_pa"],
                rel=tolerance["relative"],
                abs=tolerance["stress_absolute_pa"],
            )
            expected_principal = (
                [525e6] * 3
                if case == "hydrostatic"
                else [
                    reference["expected_canonical_stress_pa"][3],
                    0,
                    -reference["expected_canonical_stress_pa"][3],
                ]
            )
            assert point["principal_pa"] == pytest.approx(
                expected_principal, rel=tolerance["relative"], abs=tolerance["stress_absolute_pa"]
            )
    else:
        mu = references["material"]["E_pa"] / (2 * (1 + references["material"]["nu"]))
        for point in payload["integration_points"] + payload["element_nodes"]:
            _x, y, z = point["position_m"]
            assert point["tensor_pa"] == pytest.approx(
                [0, 0, 0, mu * 0.001 * z, 0, mu * 0.001 * y],
                rel=tolerance["relative"],
                abs=tolerance["stress_absolute_pa"],
            )
            shear = mu * 0.001 * (y * y + z * z) ** 0.5
            assert point["principal_pa"] == pytest.approx(
                [shear, 0, -shear], rel=tolerance["relative"], abs=tolerance["stress_absolute_pa"]
            )
        points = element_nodes(parse_dat(tmp_path / "analysis.dat", mesh)["samples"], mesh)
        sample = probe_element(points, mesh, 1, (0.25, 0.25, 0.25, 0.25))
        assert sample.tensor_pa == pytest.approx(
            [0, 0, 0, mu * 0.00025, 0, mu * 0.00025], rel=1e-5, abs=100
        )
        assert sample.position_m == (0.25, 0.25, 0.25)
        assert sample.provenance["method"] == "element_owned_linear_stress_interpolation"
        # IP 3/4 have different y/z; this catches DAT xz/yz permutations and numbering.
        assert (
            payload["integration_points"][2]["tensor_pa"][5]
            > payload["integration_points"][2]["tensor_pa"][3]
        )
        assert (
            payload["integration_points"][3]["tensor_pa"][3]
            > payload["integration_points"][3]["tensor_pa"][5]
        )
    for point in payload["integration_points"]:
        assert point["location"] == "integration_point"
        assert point["provenance"]["method"] == "native_DAT_integration_point"
        assert point["provenance"]["frame"] == "global_cartesian"
        assert len(principal(tuple(point["tensor_pa"]))) == 3
        assert von_mises(tuple(point["tensor_pa"])) >= 0
    output = ROOT / f".local/native/validation/T004/{case}"
    shutil.copytree(tmp_path, output, dirs_exist_ok=True)


def test_native_two_material_jump_and_vtk_roundtrip(tmp_path: Path) -> None:
    result = run_b09(tmp_path, development=True)
    payload = json.loads((tmp_path / "stress.json").read_text())
    for node in result["shared_node_ids"]:
        sides = [p for p in payload["element_nodes"] if p["node_id"] == node]
        assert len(sides) == 2
        assert {p["material_id"] for p in sides} == {"UPPER", "LOWER"}
        assert {round(p["tensor_pa"][0]) for p in sides} == {210000000, 70000000}
        assert len({p["element_id"] for p in sides}) == 2
    assert result["vtk"]["element_owned_points"] == 20
    assert result["vtk"]["global_nodes"] == 14
    assert result["vtk"]["tensor_roundtrip"] == "exact"
    assert (tmp_path / "element_nodes.vtu").stat().st_size > 0
    assert (tmp_path / "integration_points.vtp").stat().st_size > 0
    assert (tmp_path / "stress.html").stat().st_size > 0
    shutil.copytree(tmp_path, ROOT / ".local/native/validation/T004/B09", dirs_exist_ok=True)
