"""Fail-closed CCX 2.23 ASCII single-static-step S/COORD and FRD adapters."""

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from worker.meshing import Vec, convert_tetra, norm, sub
from worker.postprocess.tensors import COMPONENTS, Tensor, tensor

PARSER_VERSION = "ccx-2.23-single-static-ascii-v1"
B = (5 - math.sqrt(5)) / 20
A = 1 - 3 * B
# Pinned gauss.f: gauss3d5 columns. Barycentric order matches CCX corners 1..4.
GAUSS = ((A, B, B, B), (B, A, B, B), (B, B, A, B), (B, B, B, A))


@dataclass(frozen=True)
class Mesh:
    nodes: dict[int, Vec]
    elements: dict[int, tuple[int, ...]]
    bodies: dict[int, str]
    materials: dict[int, str]
    revision: str

    def validate(self) -> None:
        if not self.revision or not self.elements or not self.nodes:
            raise ValueError("Missing immutable result mesh")
        if set(self.bodies) != set(self.elements) or set(self.materials) != set(self.elements):
            raise ValueError("Incomplete element body/material ownership")
        used = {n for ns in self.elements.values() for n in ns}
        if (
            used != set(self.nodes)
            or any(n <= 0 for n in used)
            or any(e <= 0 for e in self.elements)
        ):
            raise ValueError("Invalid/orphan result mesh entities")
        for ns in self.elements.values():
            if len(ns) != 10:
                raise ValueError("Result mesh must use C3D10 only")
            gmsh = (*ns[:8], ns[9], ns[8])
            convert_tetra(gmsh, self.nodes)

    def identity(self) -> str:
        payload = asdict(self)
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, allow_nan=False).encode()
        ).hexdigest()


@dataclass(frozen=True)
class StressPoint:
    location: Literal[
        "integration_point",
        "element_node",
        "element_interpolated",
        "solver_averaged_node",
        "smoothed_node",
    ]
    element_id: int | None
    integration_point_id: int | None
    node_id: int | None
    body_id: str | None
    material_id: str | None
    position_m: Vec
    tensor_pa: Tensor
    provenance: dict[str, Any]


def read_ascii(path: Path) -> tuple[str, str]:
    if not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("Missing or oversized native result")
    raw = path.read_bytes()
    if not raw.endswith(b"\n"):
        raise ValueError("Truncated native output")
    try:
        return raw.decode("ascii"), hashlib.sha256(raw).hexdigest()
    except UnicodeDecodeError as error:
        raise ValueError("Only pinned ASCII native output is supported") from error


def number(text: str) -> float:
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EDed][+-]?\d+)?", text):
        raise ValueError("Malformed native number")
    value = float(text.upper().replace("D", "E"))
    if not math.isfinite(value):
        raise ValueError("Nonfinite native number")
    return value


def section(text: str, prefix: str, columns: int) -> tuple[float, list[tuple[int, list[str]]]]:
    lines = text.splitlines()
    matches = [
        (i, re.fullmatch(re.escape(prefix) + r"\s+([\d.EeDd+-]+)", line.strip()))
        for i, line in enumerate(lines)
        if line.strip().startswith(prefix.split(" (")[0])
    ]
    if len(matches) != 1 or matches[0][1] is None:
        raise ValueError(f"Missing, repeated or unsupported {prefix.split(' (')[0]} section")
    start, heading = matches[0]
    assert heading is not None
    rows: list[tuple[int, list[str]]] = []
    for i in range(start + 1, len(lines)):
        parts = lines[i].split()
        if not parts:
            if rows:
                break
            continue
        if len(parts) != columns or not parts[0].isdigit():
            raise ValueError("Malformed or truncated DAT record")
        rows.append((i + 1, parts))
    # CCX ends its final COORD row with one newline, without a blank separator.
    # Complete entity coverage is checked by the caller, including at EOF.
    if not rows:
        raise ValueError("Empty DAT section")
    return number(heading[1]), rows


def identifier(value: str) -> int:
    if not value.isdigit() or int(value) <= 0:
        raise ValueError("Invalid native entity ID")
    return int(value)


def parse_dat(path: Path, mesh: Mesh) -> dict[str, Any]:
    mesh.validate()
    mesh_digest = mesh.identity()
    text, digest = read_ascii(path)
    steps = re.findall(r"S T E P\s+(\d+)", text)
    increments = re.findall(r"INCREMENT\s+(\d+)", text)
    if steps != ["1"] or increments != ["1"]:
        raise ValueError("Only one static step/increment is supported")
    stress_time, stress_rows = section(
        text, "stresses (elem, integ.pnt.,sxx,syy,szz,sxy,sxz,syz) for set EALL and time", 8
    )
    coord_time, coords = section(
        text, "global coordinates (elem, integ.pnt.,x,y,z) for set EALL and time", 5
    )
    displ_time, displacements = section(text, "displacements (vx,vy,vz) for set NALL and time", 4)
    force_time, forces = section(text, "forces (fx,fy,fz) for set NALL and time", 4)
    if len({stress_time, coord_time, displ_time, force_time}) != 1 or stress_time != 1:
        raise ValueError("Mismatched/unsupported DAT frame times")
    consumed = {line for rows in (stress_rows, coords, displacements, forces) for line, _ in rows}
    for index, content in enumerate(text.splitlines(), 1):
        if (
            content.strip()
            and index not in consumed
            and not re.fullmatch(r"(?:S T E P\s+1|INCREMENT\s+1)", content.strip())
            and not any(
                content.strip().startswith(prefix)
                for prefix in ("stresses (", "global coordinates (", "displacements (", "forces (")
            )
        ):
            raise ValueError("Unrecognized/trailing DAT content")
    expected = {(e, i) for e in mesh.elements for i in range(1, 5)}
    positions: dict[tuple[int, int], Vec] = {}
    coord_lines: dict[tuple[int, int], int] = {}
    for coord_line, row in coords:
        key = (identifier(row[0]), identifier(row[1]))
        if key in positions or key not in expected:
            raise ValueError("Duplicate/unknown integration coordinate")
        p: Vec = (number(row[2]), number(row[3]), number(row[4]))
        ns = mesh.elements[key[0]]
        bary = GAUSS[key[1] - 1]
        predicted = tuple(sum(bary[j] * mesh.nodes[ns[j]][k] for j in range(4)) for k in range(3))
        if norm(sub(p, (predicted[0], predicted[1], predicted[2]))) > 1e-6:
            raise ValueError("Integration location disagrees with frozen C3D10 mesh")
        positions[key] = p
        coord_lines[key] = coord_line
    if set(positions) != expected:
        raise ValueError("Missing integration coordinates")
    samples = []
    seen = set()
    for line, row in stress_rows:
        key = (identifier(row[0]), identifier(row[1]))
        if key in seen or key not in expected:
            raise ValueError("Duplicate/unknown integration stress")
        seen.add(key)
        raw = [number(v) for v in row[2:]]
        canonical = tensor([raw[i] for i in (0, 1, 2, 3, 5, 4)])
        samples.append(
            StressPoint(
                "integration_point",
                key[0],
                key[1],
                None,
                mesh.bodies[key[0]],
                mesh.materials[key[0]],
                positions[key],
                canonical,
                {
                    "source": path.name,
                    "source_sha256": digest,
                    "line": line,
                    "coordinate_line": coord_lines[key],
                    "parser": PARSER_VERSION,
                    "frame": "global_cartesian",
                    "time": stress_time,
                    "units": "Pa",
                    "components": COMPONENTS,
                    "source_components": ("xx", "yy", "zz", "xy", "xz", "yz"),
                    "method": "native_DAT_integration_point",
                    "mesh_sha256": mesh_digest,
                },
            )
        )
    if seen != expected:
        raise ValueError("Missing integration stresses")
    vectors = {}
    for name, rows in (("displacements_m", displacements), ("external_forces_n", forces)):
        values = {}
        for _line, row in rows:
            n = identifier(row[0])
            if n in values or n not in mesh.nodes:
                raise ValueError("Duplicate/unknown DAT node")
            values[n] = (number(row[1]), number(row[2]), number(row[3]))
        if set(values) != set(mesh.nodes):
            raise ValueError("Missing DAT node vectors")
        vectors[name] = values
    return {"samples": samples, "source_sha256": digest, **vectors}


def parse_frd(path: Path, mesh: Mesh) -> list[StressPoint]:
    mesh.validate()
    mesh_digest = mesh.identity()
    node_elements: dict[int, list[int]] = {n: [] for n in mesh.nodes}
    for eid, connectivity in sorted(mesh.elements.items()):
        for n in connectivity:
            node_elements[n].append(eid)
    text, digest = read_ascii(path)
    lines = text.splitlines()
    if not lines or lines[-1].strip() != "9999":
        raise ValueError("Truncated FRD terminator")
    if not any(line.strip() == "1UVERSION           Version 2.23" for line in lines):
        raise ValueError("Unsupported FRD solver version")
    if sum(line.startswith(" -4  STRESS ") for line in lines) != 1:
        raise ValueError("Expected exactly one real static FRD stress field")
    start = next(i for i, line in enumerate(lines) if line.startswith(" -4  STRESS "))
    frame = lines[start - 1].split()
    if (
        len(frame) != 7
        or frame[0] != "100CL"
        or number(frame[2]) != 1
        or identifier(frame[3]) != len(mesh.nodes)
        or frame[-2:] != ["1", "1"]
    ):
        raise ValueError("Unsupported FRD frame time/step/node count")
    if lines[start].split() != ["-4", "STRESS", "6", "1"]:
        raise ValueError("Unsupported FRD stress layout")
    names = [line.split()[1] for line in lines[start + 1 : start + 7] if line.startswith(" -5")]
    if names != ["SXX", "SYY", "SZZ", "SXY", "SYZ", "SZX"]:
        raise ValueError("Unexpected FRD component order")
    records: dict[int, StressPoint] = {}
    i = start + 7
    while i < len(lines) and lines[i].startswith(" -1"):
        line = lines[i]
        if len(line) != 85:
            raise ValueError("Truncated/unsupported fixed-width FRD stress row")
        n = identifier(line[3:13].strip())
        if n not in mesh.nodes or n in records:
            raise ValueError("Duplicate/unknown FRD stress node")
        values = tensor([number(line[13 + 12 * k : 25 + 12 * k].strip()) for k in range(6)])
        contributors = node_elements[n]
        records[n] = StressPoint(
            "solver_averaged_node",
            None,
            None,
            n,
            None,
            None,
            mesh.nodes[n],
            values,
            {
                "source": path.name,
                "source_sha256": digest,
                "line": i + 1,
                "parser": PARSER_VERSION,
                "frame": "global_cartesian",
                "units": "Pa",
                "components": COMPONENTS,
                "source_components": COMPONENTS,
                "method": "native_FRD_extrapolated_nodal_average",
                "contributing_elements": contributors,
                "mesh_sha256": mesh_digest,
                "warning": "May average across material/body boundaries; diagnostic only",
            },
        )
        i += 1
    if i >= len(lines) or lines[i].strip() != "-3" or set(records) != set(mesh.nodes):
        raise ValueError("Missing/truncated FRD stress records")
    # Verify geometry from the same file, including canonical C3D10 topology.
    geometry = [j for j, line in enumerate(lines) if line.startswith("    2C")]
    topology = [j for j, line in enumerate(lines) if line.startswith("    3C")]
    if len(geometry) != 1 or len(topology) != 1:
        raise ValueError("Missing/repeated FRD mesh")
    if lines[geometry[0]].split() != ["2C", str(len(mesh.nodes)), "1"]:
        raise ValueError("FRD node count or ASCII format disagrees")
    if lines[topology[0]].split() != ["3C", str(len(mesh.elements)), "1"]:
        raise ValueError("FRD element count or ASCII format disagrees")
    material_names = {}
    for line in lines:
        if line.startswith("    1UMAT"):
            code = identifier(line[9:14].strip())
            if code in material_names:
                raise ValueError("Duplicate FRD material code")
            material_names[code] = line[14:].strip()
    found_nodes = set()
    j = geometry[0] + 1
    while lines[j].startswith(" -1"):
        line = lines[j]
        if len(line) != 49:
            raise ValueError("Malformed FRD coordinates")
        n = identifier(line[3:13].strip())
        if n in found_nodes or n not in mesh.nodes:
            raise ValueError("Unknown/duplicate FRD geometry node")
        p: Vec = (
            number(line[13:25].strip()),
            number(line[25:37].strip()),
            number(line[37:49].strip()),
        )
        if norm(sub(p, mesh.nodes[n])) > 1e-5:
            raise ValueError("FRD coordinates disagree with result mesh")
        found_nodes.add(n)
        j += 1
    if lines[j].strip() != "-3" or found_nodes != set(mesh.nodes):
        raise ValueError("Missing FRD geometry nodes")
    found_elements = set()
    j = topology[0] + 1
    while lines[j].startswith(" -1"):
        header = lines[j].split()
        if len(header) != 5 or header[2] != "6":
            raise ValueError("Unsupported FRD element")
        eid = identifier(header[1])
        if eid not in mesh.elements or eid in found_elements:
            raise ValueError("Unknown/duplicate FRD element")
        if material_names.get(identifier(header[4])) != mesh.materials[eid]:
            raise ValueError("FRD material ownership disagrees with frozen mesh")
        ns = tuple(identifier(v) for v in lines[j + 1][3:].split())
        if not lines[j + 1].startswith(" -2") or ns != mesh.elements[eid]:
            raise ValueError("FRD connectivity disagrees with result mesh")
        found_elements.add(eid)
        j += 2
    if lines[j].strip() != "-3" or found_elements != set(mesh.elements):
        raise ValueError("Missing FRD elements")
    return [records[n] for n in sorted(records)]
