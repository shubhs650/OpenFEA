"""Force/length/second presets; conversion happens only at explicit boundaries."""

import math
from typing import Literal

from app.domain.base import StrictModel

PresetID = Literal["mm-N-MPa", "m-N-Pa", "inch-lbf-psi"]
Quantity = Literal["length", "force", "stress", "density", "acceleration"]


class Unit(StrictModel):
    label: str
    to_si: float


class UnitPreset(StrictModel):
    id: PresetID
    label: str
    length: Unit
    force: Unit
    stress: Unit
    density: Unit
    acceleration: Unit


INCH_M = 0.0254
LBF_N = 4.4482216152605  # exact international pound (0.45359237 kg) * 9.80665 m/s²
PRESETS: dict[PresetID, UnitPreset] = {
    "mm-N-MPa": UnitPreset(
        id="mm-N-MPa",
        label="mm–N–MPa",
        length=Unit(label="mm", to_si=1e-3),
        force=Unit(label="N", to_si=1),
        stress=Unit(label="MPa", to_si=1e6),
        density=Unit(label="tonne/mm³", to_si=1e12),
        acceleration=Unit(label="mm/s²", to_si=1e-3),
    ),
    "m-N-Pa": UnitPreset(
        id="m-N-Pa",
        label="m–N–Pa",
        length=Unit(label="m", to_si=1),
        force=Unit(label="N", to_si=1),
        stress=Unit(label="Pa", to_si=1),
        density=Unit(label="kg/m³", to_si=1),
        acceleration=Unit(label="m/s²", to_si=1),
    ),
    "inch-lbf-psi": UnitPreset(
        id="inch-lbf-psi",
        label="inch–lbf–psi",
        length=Unit(label="inch", to_si=INCH_M),
        force=Unit(label="lbf", to_si=LBF_N),
        stress=Unit(label="psi", to_si=LBF_N / INCH_M**2),
        density=Unit(label="lbf·s²/inch⁴", to_si=LBF_N / INCH_M**4),
        acceleration=Unit(label="inch/s²", to_si=INCH_M),
    ),
}


def unit_for(preset: PresetID, quantity: Quantity) -> Unit:
    selected = PRESETS[preset]
    return {
        "length": selected.length,
        "force": selected.force,
        "stress": selected.stress,
        "density": selected.density,
        "acceleration": selected.acceleration,
    }[quantity]


def to_si(value: float, preset: PresetID, quantity: Quantity) -> float:
    result = value * unit_for(preset, quantity).to_si
    if not math.isfinite(value) or not math.isfinite(result):
        raise ValueError("Quantity must be finite in SI")
    return result


def from_si(value: float, preset: PresetID, quantity: Quantity) -> float:
    result = value / unit_for(preset, quantity).to_si
    if not math.isfinite(value) or not math.isfinite(result):
        raise ValueError("Quantity must be finite in display units")
    return result
