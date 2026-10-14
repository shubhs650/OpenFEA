"""Necessary component support checks and bounded independent-body mortar admission."""

from dataclasses import asdict
from typing import Any

from worker.actions import rigid_rank_directions
from worker.calculix.bonds import Bond, bond_keywords, prepare_bond, typed_mesh
from worker.calculix.mortar import mortar_bond
from worker.directions import IDENTITY, Basis
from worker.meshing import Vec

ASSEMBLY_POLICY = {
    "version": 1,
    "formulation": "consistent-zero-gap-unit-square-mortar",
    "max_solver_bonds": 1,
    "max_trace_nodes": 65,
    "tie_residual_m": 2e-11,
    "no_stabilization": True,
    "necessary_support_rank": 6,
    "stability_proof": False,
}
WARNING = (
    "Connectivity and rigid-motion support checks are necessary only, "
    "not proof of stiffness rank or stability; no weak springs are added."
)


def components(bodies: list[str], edges: list[tuple[str, str]]) -> list[list[str]]:
    groups = [{b} for b in bodies]
    for a, b in edges:
        if a == b or a not in bodies or b not in bodies:
            raise ValueError("Missing/same body in connection")
        left = next(g for g in groups if a in g)
        right = next(g for g in groups if b in g)
        if left is right:
            raise ValueError("Redundant or cyclic body connection; dependent constraints refused")
        left.update(right)
        groups.remove(right)
    return sorted((sorted(g) for g in groups), key=lambda g: g[0])


def support_rank(points: list[tuple[Vec, Vec]], coordinates: list[Vec]) -> int:
    if not coordinates:
        return 0
    origin: Vec = tuple(min(p[a] for p in coordinates) for a in range(3))  # type: ignore[assignment]
    extent = max(max(p[a] for p in coordinates) - origin[a] for a in range(3))
    return rigid_rank_directions(points, origin, extent) if extent > 0 else 0


def mesh_supports(
    mesh: dict[str, Any],
    groups: list[list[str]],
    supports: dict[tuple[int, int], float],
    transforms: dict[int, Basis],
) -> list[dict[str, Any]]:
    typed = typed_mesh(mesh)
    result = []
    for group in groups:
        nodes = {n for e, ns in typed.elements.items() if typed.bodies[e] in group for n in ns}
        rows = [
            (typed.nodes[n], transforms.get(n, IDENTITY)[a - 1]) for n, a in supports if n in nodes
        ]
        rank = support_rank(rows, [typed.nodes[n] for n in nodes])
        if rank < 6:
            raise ValueError(
                f"Detached/underconstrained component {group}: necessary "
                f"rigid-motion support rank {rank}/6. Add independent supports "
                "or explicitly review a valid bond; no weak springs."
            )
        result.append({"body_ids": group, "support_rank": rank, "node_count": len(nodes)})
    return result


def plan(
    mesh: dict[str, Any],
    catalog: dict[str, Any],
    master: str,
    slave: str,
    supports: dict[tuple[int, int], float],
    transforms: dict[int, Basis],
) -> tuple[Bond, dict[str, Any]]:
    if transforms:
        raise ValueError(
            "Bonded solves with transformed node constraints are unvalidated; use global components"
        )
    if len(catalog["bodies"]) != 2:
        raise ValueError("Bounded mortar requires exactly two independent bodies")
    bond = prepare_bond(mesh, catalog, master, slave, {n for n, _ in supports})
    bond, report = mortar_bond(mesh, bond)
    groups = components([b["id"] for b in catalog["bodies"]], [(bond.master_body, bond.slave_body)])
    checked = mesh_supports(mesh, groups, supports, transforms)
    equations = 3 * len(mesh["nodes"]) - len(supports) - 3 * len(bond.slave_nodes)
    if equations <= 0:
        raise ValueError("No actual free equations remain")
    return bond, {
        "policy": ASSEMBLY_POLICY,
        "components": checked,
        "coupling": report,
        "expected_free_equations": equations,
        "intended_slave_nodes": list(bond.slave_nodes),
        "warning": WARNING,
        "bond": asdict(bond),
    }


def keywords(bond: Bond) -> str:
    if bond.formulation != "mortar_equation":
        raise ValueError("Rejected native TIE cannot be enabled as a fallback")
    return bond_keywords(bond)
