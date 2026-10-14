"""Deterministic internally generated C3D10 decks; no arbitrary deck input API."""

import math
import re
from typing import Any

from worker.directions import IDENTITY, Basis, frame, local_vector
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
    pressures: list[tuple[int, int, float]] | None = None,
    densities: dict[str, float] | None = None,
    gravities: dict[str, Vec] | None = None,
    transforms: dict[int, Basis] | None = None,
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
    definitions = set(materials) if materials is not None else {"ISOTROPIC"}
    if densities and (
        not set(densities) <= definitions
        or any(not math.isfinite(v) or v <= 0 for v in densities.values())
    ):
        raise ValueError("Gravity density must be positive and assigned to a known material")
    if gravities:
        targets = definitions if materials is not None else {"EALL"}
        if not set(gravities) <= targets or any(
            not all(math.isfinite(v) for v in g) for g in gravities.values()
        ):
            raise ValueError("Invalid internally generated gravity set/vector")
        if any(
            (name if materials is not None else "ISOTROPIC") not in (densities or {})
            for name in gravities
        ):
            raise ValueError("Every gravity set requires density")
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
            identifiers = [str(e) for e, m in sorted(element_materials.items()) if m == name]
            lines.append(f"*ELSET,ELSET={name}")
            lines += [",".join(identifiers[i : i + 16]) for i in range(0, len(identifiers), 16)]
            lines += [
                f"*MATERIAL,NAME={name}",
                "*ELASTIC",
                f"{modulus:.12e},{ratio:.12e}",
            ]
            if densities and name in densities:
                lines += ["*DENSITY", f"{densities[name]:.12e}"]
            lines.append(f"*SOLID SECTION,ELSET={name},MATERIAL={name}")
    else:
        lines += [
            "*MATERIAL,NAME=ISOTROPIC",
            "*ELASTIC",
            f"{young:.12e},{poisson:.12e}",
        ]
        if densities and "ISOTROPIC" in densities:
            lines += ["*DENSITY", f"{densities['ISOTROPIC']:.12e}"]
        lines.append("*SOLID SECTION,ELSET=EALL,MATERIAL=ISOTROPIC")
    transforms = transforms or {}
    if not set(transforms) <= {int(n) for n in mesh["nodes"]}:
        raise ValueError("Transform references an unknown global node")
    groups: dict[Basis, list[int]] = {}
    written_transforms: dict[int, Basis] = {}
    for n, basis in sorted(transforms.items()):
        verified = frame(basis[0], basis[1])
        if any(
            abs(a - b) > 1e-10
            for x, y in zip(basis, verified, strict=True)
            for a, b in zip(x, y, strict=True)
        ):
            raise ValueError("Invalid rectangular node frame")
        groups.setdefault(basis, []).append(n)
    for index, (basis, frame_nodes) in enumerate(groups.items(), 1):
        lines.append(f"*NSET,NSET=LOCAL{index}")
        names = list(map(str, frame_nodes))
        lines += [",".join(names[i : i + 16]) for i in range(0, len(names), 16)]
        lines.append(f"*TRANSFORM,NSET=LOCAL{index},TYPE=R")
        numbers = [float(f"{v:.12e}") for axis in basis[:2] for v in axis]
        lines.append(",".join(f"{v:.12e}" for v in numbers))
        written = frame((numbers[0], numbers[1], numbers[2]), (numbers[3], numbers[4], numbers[5]))
        written_transforms.update({n: written for n in frame_nodes})
    lines.append("*BOUNDARY")
    lines += [
        f"{node},{axis},{axis},{value:.12e}"
        for (node, axis), value in sorted(supports.items())
        if value == 0
    ]
    lines += ["*STEP", "*STATIC"]
    if any(value != 0 for value in supports.values()):
        lines.append("*BOUNDARY")
        lines += [
            f"{node},{axis},{axis},{value:.12e}"
            for (node, axis), value in sorted(supports.items())
            if value != 0
        ]
    if loads:
        lines.append("*CLOAD")
        for n, force in sorted(loads.items()):
            force = local_vector(force, written_transforms.get(n, IDENTITY))
            lines += [
                f"{n},{axis},{value:.12e}" for axis, value in enumerate(force, 1) if value != 0
            ]
    if pressure:
        eid, face, value = pressure
        lines += ["*DLOAD", f"{eid},P{face},{value:.12e}"]
    if pressures:
        lines.append("*DLOAD")
        lines += [f"{eid},P{face},{value:.12e}" for eid, face, value in sorted(pressures)]
    if gravities and any(any(g) for g in gravities.values()):
        lines.append("*DLOAD")
        for name, acceleration in sorted(gravities.items()):
            for axis, value in enumerate(acceleration):
                if value != 0:
                    direction = [(-1 if value < 0 else 1) if a == axis else 0 for a in range(3)]
                    lines.append(f"{name},GRAV,{abs(value):.12e}," + ",".join(map(str, direction)))
    lines += [
        "*NODE PRINT,NSET=NALL,GLOBAL=YES" if transforms else "*NODE PRINT,NSET=NALL",
        "U,RF",
        "*EL PRINT,ELSET=EALL,GLOBAL=YES" if stress_coordinates else "*EL PRINT,ELSET=EALL",
        "S,COORD" if stress_coordinates else "S",
        "*NODE FILE,GLOBAL=YES" if transforms else "*NODE FILE",
        "U",
        "*EL FILE,GLOBAL=YES" if stress_coordinates else "*EL FILE",
        "S,NOE" if stress_coordinates else "S",
        "*END STEP",
    ]
    return "\n".join(lines) + "\n"
