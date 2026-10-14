"""Field deltas distinguish common physical samples from moving raw mesh peaks."""

import math
from typing import Any

COMPARISON_VERSION = "physical-sample-refinement-v1"
METHOD = (
    "Same undeformed physical coordinates and explicit element/body/material sides in both "
    "retained affine C3D10 meshes. Quadratic displacement; tensor interpolation precedes "
    "invariants, with the declared unaveraged/partitioned-smoothed mode. Changes are "
    "compared minus reference; relative change is absolute change / absolute reference, "
    "unavailable at or below the disclosed SI reference floor. Floors are display conventions, "
    "not numerical acceptance tolerances. Raw native extrema are separate moving locations. "
    "One arbitrary comparison cannot establish convergence, accuracy, stability or safety."
)


def scalar(point: dict[str, Any], field: str, smoothed: bool) -> float:
    if field == "displacement":
        return math.hypot(*point["displacement_m"])
    if field in ("ux", "uy", "uz"):
        return float(point["displacement_m"][("ux", "uy", "uz").index(field)])
    stress = point["smoothed_stress" if smoothed else "stress"]
    if field == "von_mises":
        return float(stress["von_mises_pa"])
    if field in ("s1", "s2", "s3"):
        return float(stress["principal_pa"][("s1", "s2", "s3").index(field)])
    return float(stress["tensor_pa"][("sxx", "syy", "szz", "sxy", "syz", "szx").index(field)])


def change(reference: float, compared: float, floor: float) -> dict[str, float | None]:
    delta = compared - reference
    relative = None if abs(reference) <= floor else abs(delta) / abs(reference)
    values = [reference, compared, delta, floor, *([relative] if relative is not None else [])]
    if floor < 0 or not all(math.isfinite(v) for v in values):
        raise ValueError("Comparison arithmetic must be finite")
    return {
        "reference": reference,
        "compared": compared,
        "signed_change": delta,
        "absolute_change": abs(delta),
        "relative_change": relative,
    }


def peak_notes(reference: float, compared: float) -> list[str]:
    if abs(compared) <= abs(reference):
        return []
    return [
        "The raw peak magnitude increased at its mesh-dependent location. This may indicate "
        "an unresolved concentration or singularity; it does not prove divergence or convergence. "
        "Inspect the common physical samples separately."
    ]
