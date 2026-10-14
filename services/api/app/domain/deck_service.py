"""Freeze owned inputs, export a real bounded mesh, retain immutable deck bytes."""

import fcntl
import hashlib
import json
import math
import shutil
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from app.domain.errors import DomainError, stale_revision
from app.domain.import_service import ImportService
from app.domain.imports import GeometryDisplay
from app.domain.loads import DeckExport, DeckSnapshot, LoadState, load_state
from app.domain.mesh import estimate, sizing
from app.persistence.repository import Repository
from worker.deck import generated_deck
from worker.deck_mesh import mesh_snapshot
from worker.local_process import NativeControl
from worker.mesh_quality import mesh_quality
from worker.meshing import (
    GMSH_TO_CCX,
    Vec,
    add,
    convert_tetra,
    resultant,
    surface_integral,
    total_face_force,
)
from worker.runtime import NATIVE, ROOT, sha256, verified_tool
from worker.step_import import ImportSandboxError


def canonical(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode()


def deck_for(
    snapshot: DeckSnapshot,
    mesh: dict[str, Any],
    preview: LoadState,
    *,
    stress_coordinates: bool = False,
) -> tuple[str, dict[str, float | int | str | list[str]]]:
    quality = mesh_quality(mesh)
    if not quality["accepted"] or not quality["all_affine"]:
        raise ValueError("Mesh quality failed or curved C3D10 solve is not validated")
    nodes: dict[int, Vec] = {int(n): tuple(p) for n, p in mesh["nodes"].items()}
    if mesh["revision"] != snapshot.geometry.brep_sha256 or mesh["units"] != "m":
        raise ValueError("Stale mesh")
    if set(mesh["boundary"]) != {f.id for f in snapshot.geometry.faces}:
        raise ValueError("Incomplete face mapping")
    if not 1 <= len(mesh["elements"]) <= 3000 or len(nodes) > 30000:
        raise ValueError("Preview mesh cap exceeded")
    supports = {
        (n, axis): 0.0
        for assignment in snapshot.loads.assignments
        if assignment.kind == "fixed"
        for ref in assignment.face_ids
        for face in mesh["boundary"][ref]
        for n in face["nodes"]
        for axis in (1, 2, 3)
    }
    loads: dict[int, Vec] = {}
    equivalent: dict[int, Vec] = {}
    pressures: dict[tuple[int, int], float] = {}
    max_area_error = max_force_error = max_moment_error = 0.0
    for assignment in snapshot.loads.assignments:
        if assignment.kind == "fixed":
            continue
        faces = [face for ref in assignment.face_ids for face in mesh["boundary"][ref]]
        expected = next(p for p in preview.previews if p.assignment_id == assignment.id)
        area = sum(surface_integral([nodes[n] for n in face["nodes"]])[0] for face in faces)
        max_area_error = max(max_area_error, abs(area - expected.area_m2))
        actual: dict[int, Vec] = {}
        if assignment.kind == "force":
            assert assignment.force_n is not None
            actual = total_face_force([tuple(f["nodes"]) for f in faces], nodes, assignment.force_n)
            # CCX CLOAD on constrained DOFs is not an admissible applied-force contract.
            # Preserve every integrated value; refuse instead of dropping/redistributing it.
            if any(
                abs(value) > 1e-10 and (n, axis) in supports
                for n, force in actual.items()
                for axis, value in enumerate(force, 1)
            ):
                raise DomainError(
                    422,
                    "force_on_fixed_dof",
                    "Distributed force reaches fixed degrees of freedom. "
                    "Select separated load/support faces.",
                )
            for n, vector in actual.items():
                loads[n] = add(loads.get(n, (0, 0, 0)), vector)
        else:
            assert assignment.pressure_pa is not None
            for face in faces:
                key = (face["element"], face["face"])
                pressures[key] = pressures.get(key, 0) + assignment.pressure_pa
                values = surface_integral(
                    [nodes[n] for n in face["nodes"]], pressure=assignment.pressure_pa
                )[2]
                for n, vector in zip(face["nodes"], values, strict=True):
                    actual[n] = add(actual.get(n, (0, 0, 0)), vector)
        force, moment = resultant(actual, nodes)
        max_force_error = max(
            max_force_error, *(abs(a - b) for a, b in zip(force, expected.force_n, strict=True))
        )
        max_moment_error = max(
            max_moment_error, *(abs(a - b) for a, b in zip(moment, expected.moment_nm, strict=True))
        )
        for n, vector in actual.items():
            equivalent[n] = add(equivalent.get(n, (0, 0, 0)), vector)
    if (
        not all(math.isfinite(v) for v in (max_area_error, max_force_error, max_moment_error))
        or max_area_error > 1e-8
        or max_force_error > 1e-8
        or max_moment_error > 1e-8
    ):
        raise ValueError("Mesh loads disagree with the frozen CAD resultant/moment")
    names = {b.id: f"M{i}" for i, b in enumerate(snapshot.geometry.bodies, 1)}
    materials = {
        names[a.body_id]: (
            a.material.properties.young_modulus_pa,
            a.material.properties.poisson_ratio,
        )
        for a in snapshot.materials.assignments
    }
    text = generated_deck(
        mesh,
        supports,
        loads,
        0,
        0,
        materials=materials,
        element_materials={int(e): names[b] for e, b in mesh["owners"].items()},
        pressures=[(e, f, p) for (e, f), p in pressures.items() if p != 0],
        stress_coordinates=stress_coordinates,
    )

    # Audit the actual written numbers, including the combined/rounded pressures.
    # Do not credit full-precision intermediates if decimal export changes physics.
    def written(value: float) -> float:
        return float(f"{value:.12e}")

    written_nodes: dict[int, Vec] = {
        n: (written(p[0]), written(p[1]), written(p[2])) for n, p in nodes.items()
    }
    written_loads: dict[int, Vec] = {
        n: (written(p[0]), written(p[1]), written(p[2])) for n, p in loads.items()
    }
    for connectivity in mesh["elements"].values():
        convert_tetra([connectivity[i] for i in GMSH_TO_CCX], written_nodes)
    for (element, face_number), pressure in pressures.items():
        face = next(
            f
            for values in mesh["boundary"].values()
            for f in values
            if f["element"] == element and f["face"] == face_number
        )
        values = surface_integral(
            [written_nodes[n] for n in face["nodes"]], pressure=written(pressure)
        )[2]
        for n, value in zip(face["nodes"], values, strict=True):
            written_loads[n] = add(written_loads.get(n, (0, 0, 0)), value)
    written_force, written_moment = resultant(written_loads, written_nodes)
    written_force_error = max(
        abs(a - b) for a, b in zip(written_force, preview.total_force_n, strict=True)
    )
    written_moment_error = max(
        abs(a - b) for a, b in zip(written_moment, preview.total_moment_nm, strict=True)
    )
    if (
        not all(math.isfinite(v) for v in (*written_force, *written_moment))
        or written_force_error > 1e-8
        or written_moment_error > 1e-8
    ):
        raise ValueError("Written deck changes the applied force or moment")
    force, moment = resultant(equivalent, nodes)
    return text, {
        "nodes": len(nodes),
        "elements": len(mesh["elements"]),
        "scope": "coarse planar affine C3D10 preview; independent bodies; "
        "no solve or convergence claim",
        "area_error_m2": max_area_error,
        "force_error_n": max_force_error,
        "moment_error_nm": max_moment_error,
        "written_force_error_n": written_force_error,
        "written_moment_error_nm": written_moment_error,
        "force_x_n": force[0],
        "force_y_n": force[1],
        "force_z_n": force[2],
        "moment_x_nm": moment[0],
        "moment_y_nm": moment[1],
        "moment_z_nm": moment[2],
        "warnings": preview.warnings,
    }


class DeckService:
    def __init__(self, repository: Repository, imports: ImportService) -> None:
        self.repository, self.imports, self.storage = repository, imports, imports.storage

    def state(self, owner: UUID, analysis: UUID, revision: int | None = None) -> LoadState:
        current, geometry, materials, loads = self.repository.load_inputs(owner, analysis, revision)
        display = (
            self.imports.display(owner, geometry.id, "coarse")
            if geometry and loads.assignments
            else None
        )
        return load_state(current, geometry, materials, loads, display)

    def freeze(
        self, owner: UUID, analysis: UUID, expected: int, *, mesh_only: bool = False
    ) -> tuple[DeckSnapshot, GeometryDisplay]:
        current, geometry, materials, loads = self.repository.load_inputs(owner, analysis)
        if current.revision != expected:
            raise stale_revision()
        if geometry is None:
            raise DomainError(422, "geometry_required", "Accept geometry first")
        display = self.imports.display(owner, geometry.id, "coarse")
        preview = load_state(current, geometry, materials, loads, display)
        if preview.blockers and not mesh_only:
            raise DomainError(422, "setup_incomplete", " ".join(preview.blockers))
        if mesh_only and any(a.review_faces for a in loads.assignments):
            raise DomainError(422, "setup_incomplete", " ".join(preview.blockers))
        if len(geometry.faces) > 100 or (
            not mesh_only
            and any(
                not str(f.signature.get("surface_type", "")).endswith("GeomAbs_Plane")
                for f in geometry.faces
            )
        ):
            raise DomainError(
                422,
                "unsupported_mesh",
                "Deck export requires at most 100 unambiguous planar faces",
            )
        _, _, mesh_setup = self.repository.mesh_setup(owner, analysis, expected)
        planning = estimate(analysis, expected, geometry, display, mesh_setup)
        if planning.blockers:
            raise DomainError(422, "mesh_controls_blocked", " ".join(planning.blockers))
        snapshot = DeckSnapshot(
            analysis=current,
            geometry=geometry,
            materials=materials,
            loads=loads,
            mesh_setup=mesh_setup,
        )
        return snapshot, display

    @staticmethod
    def policy() -> dict[str, Any]:
        bubblewrap = shutil.which("bwrap")
        if bubblewrap is None:
            raise DomainError(503, "sandbox_unavailable", "Bubblewrap is required for deck export")
        policy = {
            "schema": 1,
            "gmsh": "4.15.2",
            "body_size": "explicit SI global/body/face minimum; legacy largest extent / 2",
            "mesh_quality": {
                "jacobian_m3": 1e-15,
                "mean_ratio": 0.05,
                "warning_ratio": 0.2,
                "method": "Bernstein",
                "max_subdivisions": 3,
            },
            "mesh_recovery_profiles": ["Delaunay", "Frontal", "Delaunay + Netgen optimization"],
            "max_elements": 3000,
            "wall_seconds": 60,
            "rss_mib": 1536,
            "output_mib": 192,
            "healing": False,
            "network": False,
            "mapping_area_m2": 1e-8,
            "mapping_coordinate_m": 1e-6,
            "load_area_m2": 1e-8,
            "load_force_n": 1e-8,
            "load_moment_nm": 1e-8,
            "fixed_force_n": 1e-10,
            "ccx_sha256": sha256(verified_tool("ccx")),
            "netdeny_sha256": sha256(verified_tool("netdeny")),
            "bubblewrap_sha256": sha256(Path(bubblewrap)),
            "gmsh_library_sha256": sha256(NATIVE / "venvs/mesh/lib/libgmsh.so.4.15"),
            "mesh_python_sha256": sha256((NATIVE / "venvs/mesh/bin/python").resolve()),
            "sources": {
                name: sha256(ROOT / name)
                for name in (
                    "services/worker/worker/meshing_native/build.py",
                    "services/worker/worker/deck_mesh.py",
                    "services/worker/worker/geometry.py",
                    "services/worker/worker/meshing.py",
                    "services/worker/worker/mesh_quality.py",
                    "services/api/app/domain/mesh.py",
                    "services/worker/worker/deck.py",
                    "services/api/app/domain/deck_service.py",
                    "services/api/app/domain/loads.py",
                    "services/api/app/domain/units.py",
                    "services/worker/worker/step_import.py",
                    "services/worker/worker/geometry_native/import_step.py",
                    "services/worker/environments/mesh/uv.lock",
                )
            },
        }
        return policy

    def mesh(
        self,
        snapshot: DeckSnapshot,
        display: GeometryDisplay,
        directory: Path,
        control: NativeControl | None = None,
    ) -> dict[str, Any]:
        inputs = directory / "inputs"
        inputs.mkdir(mode=0o700)
        geometry = snapshot.geometry
        current = snapshot.analysis
        fields = geometry.model_dump(mode="json")
        artifacts = fields["validation"]["artifacts"]
        bodies = []
        for index, body in enumerate(geometry.bodies, 1):
            name = f"body{index}.brep"
            bodies.append({"id": body.id, "path": name, "sha256": artifacts[name]["sha256"]})
        for name in ("geometry.brep", *(b["path"] for b in bodies)):
            (inputs / name).write_bytes(
                self.storage.read(current.project_id, artifacts[name]["sha256"])
            )
        catalog = {
            "revision": geometry.brep_sha256,
            "bodies": bodies,
            "faces": [
                {
                    "id": f.id,
                    "body": f.body_id,
                    "area": f.signature["area_m2"],
                    "center": f.signature["center_m"],
                    "bounds": f.signature["bounds_m"],
                    "neighbors": f.neighbors,
                }
                for f in geometry.faces
            ],
        }
        (inputs / "catalog.json").write_bytes(canonical(catalog))
        sizes, face_sizes, blockers = sizing(geometry, display, snapshot.mesh_setup)
        if blockers:
            raise DomainError(422, "mesh_controls_blocked", " ".join(blockers))
        return mesh_snapshot(
            inputs,
            directory / "output",
            sizes,
            control=control,
            face_sizes=face_sizes,
            curvature_elements=snapshot.mesh_setup.curvature_elements,
            recovery_enabled=snapshot.mesh_setup.recovery_enabled,
        )

    def generate(self, owner: UUID, analysis: UUID, expected: int) -> DeckExport:
        with (self.storage.root / "native-import.lock").open("a+b") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise DomainError(
                    429, "native_busy", "Another geometry or mesh operation is processing"
                ) from None
            snapshot, display = self.freeze(owner, analysis, expected)
            current, geometry = snapshot.analysis, snapshot.geometry
            policy = self.policy()
            digest = hashlib.sha256(
                canonical({"snapshot": snapshot.model_dump(mode="json"), "policy": policy})
            ).hexdigest()
            cached = self.repository.cached_export(owner, digest)
            if cached is not None:
                self.storage.read(current.project_id, cached.deck_sha256)
                self.storage.read(current.project_id, cached.mesh_sha256)
                self.storage.read(current.project_id, cached.snapshot_sha256)
                return cached
            identifier = uuid4()
            directory = self.storage.directory("exports", identifier)
            try:
                mesh = self.mesh(snapshot, display, directory)
                preview = load_state(current, geometry, snapshot.materials, snapshot.loads, display)
                deck, summary = deck_for(snapshot, mesh, preview)
            except ImportSandboxError:
                raise DomainError(
                    422, "mesh_failed", "Isolated preview mesh failed; no deck was published"
                ) from None
            except (ValueError, KeyError, TypeError, AssertionError):
                raise DomainError(
                    422,
                    "deck_validation",
                    "Mesh mapping or load validation failed; no deck was published",
                ) from None
            path = directory / "analysis.inp"
            path.write_text(deck)
            mesh_path = directory / "output/mesh.json"
            frozen = directory / "snapshot.json"
            frozen.write_bytes(
                canonical({"snapshot": snapshot.model_dump(mode="json"), "policy": policy})
            )
            for file in (path, mesh_path, frozen):
                self.storage.save(current.project_id, file, sha256(file))
            metadata = DeckExport(
                id=identifier,
                analysis_id=analysis,
                analysis_revision=expected,
                geometry_revision_id=geometry.id,
                snapshot_sha256=digest,
                deck_sha256=sha256(path),
                mesh_sha256=sha256(mesh_path),
                summary=summary,
            )
            self.repository.save_export(owner, metadata, snapshot)
            return metadata

    def artifact(self, owner: UUID, identifier: UUID, kind: str) -> bytes:
        metadata, snapshot = self.repository.export(owner, identifier)
        digest = metadata.deck_sha256 if kind == "input" else metadata.snapshot_sha256
        return self.storage.read(snapshot.analysis.project_id, digest)
