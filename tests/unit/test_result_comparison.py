"""Independent comparison arithmetic, physical signatures and assumption screening."""

from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.domain.imports import GeometryDisplay
from app.domain.jobs import JobInput
from app.domain.refinement import physics, signature
from tests.unit import test_materials as materials
from tests.unit.test_analyses import snapshot
from tests.unit.test_result_inspection import polynomial_fixture
from tests.unit.test_result_views import fixture
from worker.postprocess.comparison import change, scalar
from worker.postprocess.inspection import inspect_volume
from worker.postprocess.view import build_view

application = materials.application
client = materials.client


@pytest.mark.parametrize(
    "reference,compared,floor,relative",
    [
        (0, 5, 1e-6, None),
        (1e-13, 2e-13, 1e-12, None),
        (-1e-6, 3, 1e-6, None),
        (-2, -3, 1e-6, 0.5),
        (4, -2, 1e-6, 1.5),
    ],
)
def test_near_zero_signed_absolute_and_relative_changes(
    reference: float, compared: float, floor: float, relative: float | None
) -> None:
    result = change(reference, compared, floor)
    assert result["signed_change"] == pytest.approx(compared - reference)
    assert result["absolute_change"] == pytest.approx(abs(compared - reference))
    assert result["relative_change"] == relative


@pytest.mark.parametrize(
    "reference,compared", [(float("nan"), 1), (1, float("inf")), (-1e308, 1e308)]
)
def test_nonfinite_comparison_refuses(reference: float, compared: float) -> None:
    with pytest.raises(ValueError):
        change(reference, compared, 1e-12)


def test_batch_physical_samples_retain_coordinates_and_quadratic_values() -> None:
    points = [(1, (0.2, 0.3, 0.1)), (1, (0.5, 0, 0)), (1, (0, 0, 0))]
    result = inspect_volume(*polynomial_fixture(), points[0][1], probes=points)
    for (element, point), v in zip(points, result["vertices"], strict=True):
        assert v["element_id"] == element and v["position_m"] == pytest.approx(point)
        assert scalar(v, "ux", False) == pytest.approx(
            point[0] ** 2 + point[1] * point[2], abs=1e-12
        )
        assert scalar(v, "sxx", False) == pytest.approx(
            10 + point[0] + 2 * point[1] - point[2], abs=1e-8
        )
        assert scalar(v, "sxx", True) == pytest.approx(scalar(v, "sxx", False), abs=1e-8)


@pytest.mark.parametrize("kind", ["yield", "missing_yield", "large_displacement", "singularity"])
def test_assumption_notes_survive_json_and_do_not_claim_design_validity(kind: str) -> None:
    raw, mesh, material, deck = fixture(
        [1000, 0, 0, 0, 0, 0], strength=None if kind == "missing_yield" else 500
    )
    if kind == "large_displacement":
        raw["dat"]["displacements_m"][2] = [0.02, 0, 0]
    view = build_view(raw, mesh, material, deck)
    notes = {n["code"]: n for n in view["assumptions"]}
    assert notes["yielding"]["triggered"] is (None if kind == "missing_yield" else True)
    assert notes["yielding"]["metric"] == pytest.approx(1000)
    assert notes["small_deformation"]["triggered"] is (kind == "large_displacement")
    assert notes["small_deformation"]["threshold"] == 0.01
    assert notes["stress_singularity"]["triggered"] is None
    assert "No automatic singularity detection" in notes["stress_singularity"]["message"]
    import json

    assert json.loads(json.dumps(view))["assumptions"] == view["assumptions"]


@pytest.mark.parametrize("field", ["name", "units", "mesh", "load_label", "assignment_id"])
def test_signature_ignores_only_presentation_identity_and_mesh_controls(
    client: TestClient, application: FastAPI, field: str
) -> None:
    original = snapshot(client, application)
    a = JobInput(
        kind="solve",
        snapshot=original,
        display=GeometryDisplay(
            brep_sha256=original.geometry.brep_sha256, lod="coarse", bodies=[], faces=[]
        ),
        policy={"calculix": "2.23"},
    )
    raw = a.model_dump(mode="json")
    b = raw["snapshot"]
    if field == "name":
        b["analysis"]["name"] = "Renamed"
    elif field == "units":
        b["materials"]["display_units"] = "inch-lbf-psi"
    elif field == "mesh":
        b["mesh_setup"]["global_size_m"] = 0.25
    elif field == "load_label":
        b["loads"]["assignments"][0]["name"] = "Renamed support"
    else:
        b["loads"]["assignments"][0]["id"] = str(uuid4())
    copied = JobInput.model_validate(raw)
    assert physics(a) == physics(copied) and signature(physics(a)) == signature(physics(copied))


@pytest.mark.parametrize("field", ["geometry", "material", "load", "support", "bond", "solver"])
def test_signature_distinguishes_changed_physics(
    client: TestClient, application: FastAPI, field: str
) -> None:
    original = snapshot(client, application)
    a = JobInput(
        kind="solve",
        snapshot=original,
        display=GeometryDisplay(
            brep_sha256=original.geometry.brep_sha256, lod="coarse", bodies=[], faces=[]
        ),
        policy={"calculix": "2.23"},
    )
    value = physics(a)
    changed = deepcopy(value)
    key = {
        "geometry": "geometry",
        "material": "materials",
        "load": "loads_and_supports",
        "support": "loads_and_supports",
        "bond": "bonds",
        "solver": "solver_policy",
    }[field]
    if field == "material":
        changed[key][0]["material"]["properties"]["young_modulus_pa"] *= 2
    elif field == "load":
        changed[key][-1]["pressure_pa"] = 999
    elif field == "support":
        changed[key] = []
    elif field == "geometry":
        changed[key]["id"] = str(uuid4())
    elif field == "bond":
        changed[key] = [{"master_face_id": "other", "slave_face_id": "different"}]
    else:
        changed[key]["calculix"] = "different"
    assert signature(value) != signature(changed)


@pytest.mark.parametrize("peak,expected_notice", [(200, True), (90, False)])
def test_moving_peak_trend_is_separate_from_unchanged_physical_sample(
    peak: float, expected_notice: bool
) -> None:
    from worker.postprocess.comparison import peak_notes

    fixed = change(10, 10, 1e-6)
    moving_peak = change(100, peak, 1e-6)
    assert fixed["absolute_change"] == 0
    assert moving_peak["signed_change"] == peak - 100
    notes = peak_notes(100, peak)
    assert bool(notes) is expected_notice
    if notes:
        assert "does not prove divergence or convergence" in notes[0]


def test_essentially_zero_stress_does_not_invent_a_finite_yield_assessment() -> None:
    view = build_view(*fixture([0] * 6, strength=1e-8))
    assert view["yield_factors"][0]["state"] == "unbounded"
    assert next(n for n in view["assumptions"] if n["code"] == "yielding")["triggered"] is None
