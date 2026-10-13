"""Fail-closed zero-gap planar C3D10 ties and narrow native geometry audits."""

import hashlib
import json
import math
import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from worker.calculix.results import Mesh
from worker.meshing import Vec, add, dot, norm, scale, sub, surface_integral

COINCIDENCE_M = 1e-8  # Above CCX's 1e-10 automatic-tolerance threshold.


def mesh_hash(mesh: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(mesh, sort_keys=True, allow_nan=False).encode()).hexdigest()


def typed_mesh(mesh: dict[str, Any]) -> Mesh:
    result = Mesh(
        {int(n): tuple(p) for n, p in mesh["nodes"].items()},
        {int(e): tuple(ns) for e, ns in mesh["elements"].items()},
        {int(e): b for e, b in mesh["owners"].items()},
        {int(e): "ISOTROPIC" for e in mesh["elements"]},
        mesh["revision"],
    )
    result.validate()
    return result


def barycentric(point: Vec, corners: list[Vec]) -> tuple[float, float, float] | None:
    a, b, c = corners
    v0, v1, v2 = sub(b, a), sub(c, a), sub(point, a)
    d00, d01, d11 = dot(v0, v0), dot(v0, v1), dot(v1, v1)
    determinant = d00 * d11 - d01 * d01
    if determinant <= 1e-20:
        raise ValueError("Degenerate bond master triangle")
    r = (d11 * dot(v2, v0) - d01 * dot(v2, v1)) / determinant
    s = (d00 * dot(v2, v1) - d01 * dot(v2, v0)) / determinant
    t = 1 - r - s
    if min(t, r, s) < -1e-10 or max(t, r, s) > 1 + 1e-10:
        return None
    return (t, r, s)


@dataclass(frozen=True)
class Projection:
    slave_node: int
    master_nodes: tuple[int, ...]
    weights: tuple[float, ...]
    distance_m: float


@dataclass(frozen=True)
class Bond:
    revision: str
    mesh_sha256: str
    master_ref: str
    slave_ref: str
    master_body: str
    slave_body: str
    master_faces: tuple[tuple[int, int], ...]
    slave_nodes: tuple[int, ...]
    projections: tuple[Projection, ...]
    formulation: str = "native_tie"


class UnresolvedBond(ValueError):
    def __init__(self, reason: str, uncovered: list[int] | None = None) -> None:
        self.uncovered_nodes = uncovered or []
        super().__init__(f"Unresolved bond: {reason}; uncovered nodes={self.uncovered_nodes}")


def prepare_bond(
    mesh: dict[str, Any],
    catalog: dict[str, Any],
    master_ref: str,
    slave_ref: str,
    constrained_nodes: set[int] | None = None,
) -> Bond:
    typed = typed_mesh(mesh)
    if mesh["units"] != "m" or catalog["units"] != "m" or mesh["revision"] != catalog["revision"]:
        raise UnresolvedBond("stale revision or non-SI geometry")
    faces = {f["id"]: f for f in catalog["faces"]}
    if len(faces) != len(catalog["faces"]) or master_ref not in faces or slave_ref not in faces:
        raise UnresolvedBond("missing or ambiguous immutable face references")
    master_body, slave_body = faces[master_ref]["body"], faces[slave_ref]["body"]
    if not re.fullmatch(
        re.escape(mesh["revision"]) + r":b[1-9]\d*:f[1-9]\d*", master_ref
    ) or not re.fullmatch(re.escape(mesh["revision"]) + r":b[1-9]\d*:f[1-9]\d*", slave_ref):
        raise UnresolvedBond("face reference is not revision/body/face bound")
    if master_body == slave_body:
        raise UnresolvedBond("tie requires two independent bodies")
    if abs(faces[master_ref]["area"] - faces[slave_ref]["area"]) > 1e-8:
        raise UnresolvedBond("partial interface overlap is outside the zero-gap scope")
    body_nodes = {
        b: {n for e, ns in typed.elements.items() if typed.bodies[e] == b for n in ns}
        for b in (master_body, slave_body)
    }
    if body_nodes[master_body] & body_nodes[slave_body]:
        raise UnresolvedBond("bodies share node IDs; independently meshed surfaces required")
    # Axis-aligned authored blocks only: overlap is never hidden by tie tolerance.
    bounds = {
        b: (
            [min(typed.nodes[n][k] for n in body_nodes[b]) for k in range(3)],
            [max(typed.nodes[n][k] for n in body_nodes[b]) for k in range(3)],
        )
        for b in body_nodes
    }
    if all(
        min(bounds[master_body][1][k], bounds[slave_body][1][k])
        - max(bounds[master_body][0][k], bounds[slave_body][0][k])
        > COINCIDENCE_M
        for k in range(3)
    ):
        raise UnresolvedBond("body volume overlap beyond numerical coincidence")
    selected = {}
    normals = {}
    for ref, body in ((master_ref, master_body), (slave_ref, slave_body)):
        if ref not in mesh["boundary"] or not mesh["boundary"][ref]:
            raise UnresolvedBond("missing selected surface")
        patches = mesh["boundary"][ref]
        area = 0.0
        normal: Vec = (0, 0, 0)
        for patch in patches:
            eid = patch["element"]
            if typed.bodies.get(eid) != body:
                raise UnresolvedBond("surface element body mismatch")
            ns = tuple(patch["nodes"])
            from worker.meshing import face_nodes

            if face_nodes(typed.elements[eid], patch["face"]) != ns:
                raise UnresolvedBond("quadratic face membership mismatch")
            points = [typed.nodes[n] for n in ns]
            patch_area, _, loads = surface_integral(points, pressure=-1)
            area += patch_area
            for force in loads:
                normal = add(normal, force)
        if abs(area - faces[ref]["area"]) > 1e-8:
            raise UnresolvedBond("selected mesh does not cover the complete CAD face")
        if abs(norm(normal) - area) > 1e-8:
            raise UnresolvedBond("nonplanar/curved bond is outside the validated scope")
        selected[ref] = patches
        normals[ref] = scale(normal, 1 / area)
    if norm(add(normals[master_ref], normals[slave_ref])) > 1e-8:
        raise UnresolvedBond("bond faces do not have opposing normals")
    master_faces = tuple(sorted((p["element"], p["face"]) for p in selected[master_ref]))
    slave_nodes = tuple(sorted({n for p in selected[slave_ref] for n in p["nodes"]}))
    if set(slave_nodes) & (constrained_nodes or set()):
        raise UnresolvedBond("slave node already constrained by an SPC/MPC")
    projections = []
    uncovered = []
    for n in slave_nodes:
        matches = []
        for patch in sorted(selected[master_ref], key=lambda p: (p["element"], p["face"])):
            ns = tuple(patch["nodes"])
            corners = [typed.nodes[node] for node in ns[:3]]
            normal = normals[master_ref]
            signed_distance = dot(sub(typed.nodes[n], corners[0]), normal)
            if abs(signed_distance) > COINCIDENCE_M:
                continue
            projected = sub(typed.nodes[n], scale(normal, signed_distance))
            bary = barycentric(projected, corners)
            if bary is None:
                continue
            t, r, s = bary
            weights = (
                t * (2 * t - 1),
                r * (2 * r - 1),
                s * (2 * s - 1),
                4 * t * r,
                4 * r * s,
                4 * s * t,
            )
            matches.append(Projection(n, ns, weights, abs(signed_distance)))
        if not matches:
            uncovered.append(n)
        else:
            # Multiple hits at shared edges are equivalent; select deterministically.
            projections.append(matches[0])
    if uncovered:
        raise UnresolvedBond("missing coverage or unapproved physical gap", uncovered)
    return Bond(
        mesh["revision"],
        mesh_hash(mesh),
        master_ref,
        slave_ref,
        master_body,
        slave_body,
        master_faces,
        slave_nodes,
        tuple(projections),
    )


def require_supported_bodies(
    mesh: dict[str, Any], bonds: list[Bond], supported_nodes: set[int]
) -> None:
    typed = typed_mesh(mesh)
    bodies = set(typed.bodies.values())
    reached = {typed.bodies[e] for e, ns in typed.elements.items() if supported_nodes & set(ns)}
    for bond in bonds:
        if bond.revision != mesh["revision"] or bond.mesh_sha256 != mesh_hash(mesh):
            raise UnresolvedBond("stale bond snapshot")
    while True:
        previous = set(reached)
        for bond in bonds:
            if {bond.master_body, bond.slave_body} & reached:
                reached.update((bond.master_body, bond.slave_body))
        if previous == reached:
            break
    if reached != bodies:
        raise UnresolvedBond(
            f"detached body without a support/tie path: {sorted(bodies - reached)}"
        )
    # Connectivity is a necessary preflight, not proof of stiffness rank.


def bond_keywords(bond: Bond) -> str:
    if bond.formulation == "mortar_equation":
        lines = [
            f"** zero-gap mortar master {bond.master_ref}",
            f"** zero-gap mortar slave {bond.slave_ref}",
            "*EQUATION",
        ]
        for projection in bond.projections:
            for axis in (1, 2, 3):
                terms = [(projection.slave_node, axis, 1.0)]
                terms += [
                    (n, axis, -weight)
                    for n, weight in zip(projection.master_nodes, projection.weights, strict=True)
                    if weight != 0
                ]
                lines.append(str(len(terms)))
                for i in range(0, len(terms), 4):
                    lines.append(",".join(f"{n},{d},{v:.12e}" for n, d, v in terms[i : i + 4]))
        return "\n".join(lines) + "\n"
    if bond.formulation != "native_tie":
        raise ValueError("Unsupported bond formulation")
    lines = [
        f"** bond master {bond.master_ref}",
        f"** bond slave {bond.slave_ref}",
        "*NSET,NSET=BOND_SLAVE_NODES",
    ]
    nodes = bond.slave_nodes
    lines += [",".join(str(n) for n in nodes[i : i + 16]) for i in range(0, len(nodes), 16)]
    lines += [
        "*SURFACE,NAME=BOND_SLAVE,TYPE=NODE",
        "BOND_SLAVE_NODES",
        "*SURFACE,NAME=BOND_MASTER,TYPE=ELEMENT",
    ]
    lines += [f"{eid},S{face}" for eid, face in bond.master_faces]
    lines += [
        f"*TIE,NAME=BOND,POSITION TOLERANCE={COINCIDENCE_M:.12e},ADJUST=NO",
        "BOND_SLAVE,BOND_MASTER",
    ]
    return "\n".join(lines) + "\n"


def tie_residual(bond: Bond, displacements: dict[int, Vec]) -> float:
    residual = 0.0
    for projection in bond.projections:
        value: Vec = (0, 0, 0)
        for n, weight in zip(projection.master_nodes, projection.weights, strict=True):
            value = add(value, scale(displacements[n], weight))
        residual = max(residual, norm(sub(displacements[projection.slave_node], value)))
    return residual


def solver_uncovered_nodes(directory: Path) -> list[int]:
    found = set()
    for suffix in ("_WarnNodeMissTiedContact.nam", "_WarnNodeMissMasterIntersect.nam"):
        path = directory / f"analysis{suffix}"
        if path.exists():
            for line in path.read_text().splitlines():
                if line.strip().startswith("*NSET") or not line.strip():
                    continue
                for value in line.strip().strip(",").split(","):
                    if not value.strip().isdigit():
                        raise ValueError("Malformed solver tie coverage warning")
                    found.add(int(value))
    return sorted(found)


def binary_frd_coordinates(path: Path, expected_nodes: set[int]) -> dict[int, Vec]:
    """CCX 2.23 little-endian x86_64 binary geometry only, not a binary stress parser."""
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("Oversized coordinate-audit artifact")
    raw = path.read_bytes()
    match = re.search(rb"^    2C[^\n]*\n", raw[:8192], re.M)
    if match is None or match[0].split() != [b"2C", str(len(expected_nodes)).encode(), b"3"]:
        raise ValueError("Unsupported native binary coordinate block")
    start = match.end()
    if len(raw) < start + 28 * len(expected_nodes) or not raw.endswith(b" 9999\n"):
        raise ValueError("Truncated native binary coordinate audit")
    if not raw[start + 28 * len(expected_nodes) :].startswith(b"    3C"):
        raise ValueError("Binary coordinate length does not end at the native topology block")
    coordinates = {}
    for offset in range(start, start + 28 * len(expected_nodes), 28):
        n, x, y, z = struct.unpack_from("<i3d", raw, offset)
        if n not in expected_nodes or n in coordinates or not all(map(math.isfinite, (x, y, z))):
            raise ValueError("Invalid native binary coordinate record")
        coordinates[n] = (x, y, z)
    return coordinates
