"""Immutable reviewed connectivity and a separate actual-mesh assembly admission."""

import hashlib
import json
from typing import TYPE_CHECKING, Any

from app.domain.connections import COINCIDENCE_M, POLICY, BondSetup, validate_pair
from app.domain.errors import DomainError
from app.domain.models import GeometryRevision
from worker.calculix.assembly import components, plan
from worker.calculix.bonds import Bond

if TYPE_CHECKING:
    from app.domain.loads import DeckSnapshot

from worker.directions import IDENTITY, Basis


def reviewed_groups(
    geometry: GeometryRevision, setup: BondSetup
) -> tuple[list[list[str]], list[str]]:
    bodies = [b.id for b in geometry.bodies]
    faces = {f.id: f for f in geometry.faces}
    errors = []
    edges = []
    used: set[str] = set()
    for item in setup.assignments:
        try:
            if item.geometry_revision_id != geometry.id or item.policy != POLICY:
                raise ValueError("Connection geometry/policy needs explicit review")
            validate_pair(item, item.pair)
            raw = json.dumps(
                {
                    "geometry_id": str(geometry.id),
                    "report": item.review_report.model_dump(mode="json"),
                },
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
            if hashlib.sha256(raw).hexdigest() != item.review_sha256 or item.review_report.overlaps:
                raise ValueError("Frozen connection review failed integrity/overlap checks")
            pair = item.pair
            if (pair.master_face_id, pair.slave_face_id) != (
                item.master_face_id,
                item.slave_face_id,
            ):
                raise ValueError("Connection role mismatch")
            original = next(
                (
                    p
                    for p in item.review_report.pairs
                    if {p.master_face_id, p.slave_face_id}
                    == {item.master_face_id, item.slave_face_id}
                ),
                None,
            )
            if original is None or not original.eligible:
                raise ValueError("Connection not present in the frozen report")
            if original.master_face_id != pair.master_face_id:
                original = original.model_copy(
                    update={
                        "master_face_id": original.slave_face_id,
                        "slave_face_id": original.master_face_id,
                        "master_normal": original.slave_normal,
                        "slave_normal": original.master_normal,
                        "master_center_m": original.slave_center_m,
                        "slave_center_m": original.master_center_m,
                        "master_coverage": original.slave_coverage,
                        "slave_coverage": original.master_coverage,
                    }
                )
            if original != pair:
                raise ValueError("Connection measurements disagree with frozen report")
            a, b = faces[item.master_face_id], faces[item.slave_face_id]
            if used & {a.id, b.id}:
                raise ValueError("Redundant face connection")
            used.update((a.id, b.id))
            edges.append((a.body_id, b.body_id))
            if item.pair.gap_m > COINCIDENCE_M:
                errors.append(
                    "Physical-gap product solving is unvalidated; the axial "
                    "B08 experiment does not certify rotation/shear/bending over a void."
                )
            normal = item.pair.master_normal
            if not any(
                max(abs(x - y) for x, y in zip(normal, axis, strict=True)) <= 1e-10
                for axis in (*IDENTITY, *(tuple(-x for x in axis) for axis in IDENTITY))
            ):
                errors.append(
                    "Bonded solving is limited to the validated axis-aligned unit-square interface."
                )
        except (ValueError, KeyError, DomainError):
            errors.append(
                f"{item.name}: stale, invalid or redundant connection "
                f"review; remove and review again."
            )
    try:
        groups = components(bodies, edges)
    except ValueError as error:
        errors.append(str(error))
        groups = [[b] for b in bodies]
    if len(setup.assignments) > 1:
        errors.append(
            "Multiple solver bonds are unvalidated; redundant/dependent "
            "constraints cannot be silently removed."
        )
    return groups, errors


def mesh_plan(
    snapshot: "DeckSnapshot",
    mesh: dict[str, Any],
    supports: dict[tuple[int, int], float],
    transforms: dict[int, Basis],
) -> tuple[Bond | None, dict[str, Any]]:
    groups, errors = reviewed_groups(snapshot.geometry, snapshot.bonds)
    if errors:
        raise DomainError(422, "assembly_preflight", " ".join(errors))
    from worker.calculix.assembly import mesh_supports

    if not snapshot.bonds.assignments:
        try:
            return None, {"components": mesh_supports(mesh, groups, supports, transforms)}
        except ValueError as error:
            raise DomainError(422, "insufficient_constraints", str(error)) from None
    item = snapshot.bonds.assignments[0]
    catalog = {
        "revision": snapshot.geometry.brep_sha256,
        "units": "m",
        "bodies": [{"id": b.id} for b in snapshot.geometry.bodies],
        "faces": [
            {"id": f.id, "body": f.body_id, "area": f.signature["area_m2"]}
            for f in snapshot.geometry.faces
        ],
    }
    try:
        return plan(mesh, catalog, item.master_face_id, item.slave_face_id, supports, transforms)
    except ValueError as error:
        raise DomainError(422, "assembly_preflight", str(error)) from None


def validate_solution(
    snapshot: "DeckSnapshot",
    mesh: dict[str, Any],
    deck: str,
    result: dict[str, Any],
    summary: dict[str, Any],
) -> dict[str, Any]:
    from dataclasses import asdict, replace

    from worker.actions import deck_actions
    from worker.calculix.bonds import tie_residual
    from worker.local_solve import result_mesh

    materials = {b.id: f"M{i}" for i, b in enumerate(snapshot.geometry.bodies, 1)}
    actions = deck_actions(deck, result_mesh(mesh, materials), mesh["boundary"])
    bond, report = mesh_plan(snapshot, mesh, actions.supports, actions.transforms)
    if bond is not None:
        # Compare the actual generated decimal equation rows, never an unwritten
        # full-precision projection. All nonzero coefficients are retained.
        from worker.calculix.assembly import keywords

        if keywords(bond) not in deck:
            raise ValueError("Written connection equations disagree with the frozen mesh/review")
        if summary["free_equations"] != report["expected_free_equations"]:
            raise ValueError(
                "Native free-equation count does not cover every intended slave translation"
            )
        displacements = {int(n): tuple(u) for n, u in result["dat"]["displacements_m"].items()}
        written = replace(
            bond,
            projections=tuple(
                replace(p, weights=tuple(float(f"{w:.12e}") for w in p.weights))
                for p in bond.projections
            ),
        )
        residual = tie_residual(written, displacements)
        report["bond"] = asdict(written)
        report["coefficient_encoding"] = (
            "actual 12-decimal exponent values written in the frozen deck"
        )
        if residual > report["policy"]["tie_residual_m"]:
            raise ValueError("Native displacement violates the frozen mortar connection")
        report["max_tie_residual_m"] = residual
        if result["warnings"]:
            raise ValueError(
                "Bonded native solver warnings require review; output is diagnostic only"
            )
    return report
