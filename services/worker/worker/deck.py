"""Deterministic internally generated C3D10 decks; no arbitrary deck input API."""

from typing import Any

from worker.meshing import Vec


def generated_deck(
    mesh: dict[str, Any],
    supports: dict[tuple[int, int], float],
    loads: dict[int, Vec],
    young: float,
    poisson: float,
    pressure: tuple[int, int, float] | None = None,
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
    lines += [
        "*MATERIAL,NAME=ISOTROPIC",
        "*ELASTIC",
        f"{young:.12e},{poisson:.12e}",
        "*SOLID SECTION,ELSET=EALL,MATERIAL=ISOTROPIC",
        "*BOUNDARY",
    ]
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
        "*EL PRINT,ELSET=EALL",
        "S",
        "*NODE FILE",
        "U",
        "*EL FILE",
        "S",
        "*END STEP",
    ]
    return "\n".join(lines) + "\n"
