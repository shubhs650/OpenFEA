"""Deterministic internally generated C3D10 decks; no arbitrary deck input API."""

import math
import re
from typing import Any

from worker.meshing import Vec


def generated_deck(
    mesh: dict[str, Any],
    supports: dict[tuple[int, int], float],
    loads: dict[int, Vec],
    young: float,
    poisson: float,
    pressure: tuple[int, int, float] | None = None,
    *,
    materials: dict[str, tuple[float, float]] | None = None,
    element_materials: dict[int, str] | None = None,
    stress_coordinates: bool = False,
) -> str:
    lines = ["** OpenFEA SI generated deck; C3D10 affine validation scope", "*NODE,NSET=NALL"]
    for n, point in sorted(mesh["nodes"].items(), key=lambda item: int(item[0])):
        lines.append(f"{n}," + ",".join(f"{v:.12e}" for v in point))
    lines.append("*ELEMENT,TYPE=C3D10,ELSET=EALL")
    for eid, ns in sorted(mesh["elements"].items(), key=lambda item: int(item[0])):
        lines.append(f"{eid}," + ",".join(str(n) for n in ns))
    for index, (ref, faces) in enumerate(sorted(mesh.get("boundary", {}).items()), 1):
        lines += [f"** immutable CAD face {ref}", f"*SURFACE,NAME=FACE{index},TYPE=ELEMENT"]
        lines += [f"{f['element']},S{f['face']}" for f in sorted(faces, key=lambda f: f["element"])]
    if (materials is None) != (element_materials is None):
        raise ValueError("Materials and element ownership must be supplied together")
    if materials is not None and element_materials is not None:
        if set(element_materials) != {int(e) for e in mesh["elements"]}:
            raise ValueError("Every element requires one material")
        if set(element_materials.values()) != set(materials):
            raise ValueError("Material definitions and assignments disagree")
        for name, (modulus, ratio) in sorted(materials.items()):
            if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,31}", name):
                raise ValueError("Invalid internal material name")
            if not math.isfinite(modulus) or modulus <= 0 or not 0 <= ratio <= 0.45:
                raise ValueError("Material outside development validation range")
            lines += [
                f"*ELSET,ELSET={name}",
                ",".join(str(e) for e, m in sorted(element_materials.items()) if m == name),
                f"*MATERIAL,NAME={name}",
                "*ELASTIC",
                f"{modulus:.12e},{ratio:.12e}",
                f"*SOLID SECTION,ELSET={name},MATERIAL={name}",
            ]
    else:
        lines += [
            "*MATERIAL,NAME=ISOTROPIC",
            "*ELASTIC",
            f"{young:.12e},{poisson:.12e}",
            "*SOLID SECTION,ELSET=EALL,MATERIAL=ISOTROPIC",
        ]
    lines.append("*BOUNDARY")
    lines += [
        f"{node},{axis},{axis},{value:.12e}" for (node, axis), value in sorted(supports.items())
    ]
    lines += ["*STEP", "*STATIC"]
    if loads:
        lines.append("*CLOAD")
        for n, force in sorted(loads.items()):
            lines += [
                f"{n},{axis},{value:.12e}" for axis, value in enumerate(force, 1) if value != 0
            ]
    if pressure:
        eid, face, value = pressure
        lines += ["*DLOAD", f"{eid},P{face},{value:.12e}"]
    lines += [
        "*NODE PRINT,NSET=NALL",
        "U,RF",
        "*EL PRINT,ELSET=EALL,GLOBAL=YES" if stress_coordinates else "*EL PRINT,ELSET=EALL",
        "S,COORD" if stress_coordinates else "S",
        "*NODE FILE",
        "U",
        "*EL FILE,GLOBAL=YES" if stress_coordinates else "*EL FILE",
        "S,NOE" if stress_coordinates else "S",
        "*END STEP",
    ]
    return "\n".join(lines) + "\n"
