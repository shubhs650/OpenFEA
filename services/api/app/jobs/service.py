"""Owned admission, immutable mesh/run inputs and verified artifact access."""

import hashlib
import json
from typing import Any
from uuid import UUID, uuid4

from app.domain.deck_service import DeckService, canonical, deck_for
from app.domain.errors import DomainError, not_found
from app.domain.imports import FaceDisplay, GeometryDisplay
from app.domain.jobs import JobInput, LocalJob, MeshPreview, MeshSource
from app.domain.loads import load_state
from app.domain.materials import body_status
from app.domain.results import ResultData, ResultView
from app.persistence.jobs import JobRepository
from worker.mesh_quality import mesh_quality
from worker.postprocess.view import build_view
from worker.runtime import ROOT, sha256


class JobService:
    def __init__(self, repository: JobRepository, decks: DeckService) -> None:
        self.repository, self.decks, self.storage = repository, decks, decks.storage

    def policy(self) -> dict[str, Any]:
        policy = self.decks.policy()
        policy.update(
            job_schema=1,
            job_wall_seconds=180,
            max_queue=20,
            automatic_retries=0,
            calculix="2.23",
            stress_coordinates=True,
        )
        policy["native_build_manifest_sha256"] = sha256(ROOT / ".local/native/build.json")
        policy["runtime_libraries"] = {
            path: sha256(ROOT / ".local/native" / path)
            for path in json.loads((ROOT / ".local/native/build.json").read_bytes())[
                "outputs_sha256"
            ]
            if path.startswith("lib/")
        }
        for name in (
            "services/worker/worker/local_process.py",
            "services/worker/worker/local_solve.py",
            "services/worker/worker/calculix/results.py",
            "services/api/app/jobs/service.py",
            "services/api/app/jobs/runner.py",
            "services/worker/worker/postprocess/tensors.py",
            "services/worker/worker/runtime.py",
            "services/worker/worker/resources.py",
            "services/api/app/domain/jobs.py",
            "services/api/app/persistence/jobs.py",
        ):
            policy["sources"][name] = sha256(ROOT / name)
        return policy

    def admit(
        self, owner: UUID, analysis: UUID, expected: int, key: UUID, mesh_job: UUID | None = None
    ) -> LocalJob:
        # Check ownership even on an idempotent replay with an old revision.
        self.decks.repository.get_analysis(owner, analysis)
        request_hash = hashlib.sha256(
            canonical(
                {
                    "analysis": str(analysis),
                    "revision": expected,
                    "mesh_job_id": str(mesh_job) if mesh_job else None,
                }
            )
        ).hexdigest()
        existing = self.repository.existing(owner, key, request_hash)
        if existing is not None:
            return existing
        snapshot, display = self.decks.freeze(owner, analysis, expected, mesh_only=mesh_job is None)
        try:
            policy = self.policy()
        except (RuntimeError, OSError):
            raise DomainError(
                503, "native_unavailable", "Pinned native tools are unavailable"
            ) from None
        source, deck_hash = None, None
        if mesh_job is not None:
            mesh_state = self.repository.get(owner, mesh_job)
            if (
                mesh_state.kind != "mesh"
                or mesh_state.status != "succeeded"
                or mesh_state.analysis_id != analysis
                or mesh_state.geometry_revision_id != snapshot.geometry.id
            ):
                raise DomainError(
                    422, "incompatible_mesh", "Select a completed mesh for this analysis geometry"
                )
            previous = self.repository.inputs(owner, mesh_job)

            def physical(value: Any) -> dict[str, Any]:
                return {
                    "global_size_m": value.global_size_m,
                    "curvature_elements": value.curvature_elements,
                    "local_sizes": [(s.kind, s.entity_id, s.size_m) for s in value.local_sizes],
                }

            if physical(previous.snapshot.mesh_setup) != physical(snapshot.mesh_setup):
                raise DomainError(
                    422,
                    "incompatible_mesh_controls",
                    "Sizing or curvature changed. Generate a new mesh before solving",
                )
            if previous.policy != policy:
                raise DomainError(
                    409,
                    "tool_contract_changed",
                    "Regenerate the mesh with the current tool contract",
                )
            mesh_artifact = mesh_state.artifacts.get("mesh.json")
            if mesh_artifact is None:
                raise not_found()
            mesh = json.loads(self.storage.read(snapshot.analysis.project_id, mesh_artifact.sha256))
            preview = load_state(
                snapshot.analysis, snapshot.geometry, snapshot.materials, snapshot.loads, display
            )
            try:
                deck, _ = deck_for(snapshot, mesh, preview, stress_coordinates=True)
            except (ValueError, KeyError, TypeError, AssertionError):
                raise DomainError(
                    422, "deck_validation", "The selected mesh or generated loads failed validation"
                ) from None
            identifier = uuid4()
            directory = self.storage.directory("jobs", identifier)
            deck_path = directory / "analysis.inp"
            deck_path.write_text(deck)
            deck_hash = sha256(deck_path)
            self.storage.save(snapshot.analysis.project_id, deck_path, deck_hash)
            source = MeshSource(job_id=mesh_job, sha256=mesh_artifact.sha256)
        else:
            identifier = uuid4()
            directory = self.storage.directory("jobs", identifier)
        inputs = JobInput(
            kind="solve" if source else "mesh",
            snapshot=snapshot,
            display=display,
            policy=policy,
            mesh=source,
            deck_sha256=deck_hash,
            warnings=[
                warning
                for assignment in snapshot.materials.assignments
                for warning in body_status(assignment.body_id, assignment.material).warnings
            ]
            + load_state(
                snapshot.analysis, snapshot.geometry, snapshot.materials, snapshot.loads, display
            ).warnings,
        )
        path = directory / "snapshot.json"
        path.write_bytes(canonical(inputs.model_dump(mode="json")))
        input_hash = sha256(path)
        self.storage.save(snapshot.analysis.project_id, path, input_hash)
        return self.repository.enqueue(owner, key, request_hash, identifier, inputs, input_hash)

    def artifact(self, owner: UUID, identifier: UUID, name: str) -> tuple[bytes, str]:
        job = self.repository.get(owner, identifier)
        if name == "snapshot.json":
            return self.storage.read(job.project_id, job.input_sha256), "application/json"
        if name == "results.json" and job.status != "succeeded":
            raise not_found()
        descriptor = job.artifacts.get(name)
        if descriptor is None:
            raise not_found()
        data = self.storage.read(job.project_id, descriptor.sha256)
        if len(data) != descriptor.size_bytes:
            raise DomainError(503, "artifact_integrity", "Job artifact failed its size check")
        return data, descriptor.media_type

    def mesh_preview(self, owner: UUID, identifier: UUID) -> MeshPreview:
        job = self.repository.get(owner, identifier)
        if (
            job.status not in ("succeeded", "failed")
            or job.kind != "mesh"
            or "mesh.json" not in job.artifacts
        ):
            raise DomainError(409, "mesh_unavailable", "A checked mesh has not completed")
        inputs = self.repository.inputs(owner, identifier)
        mesh = json.loads(self.artifact(owner, identifier, "mesh.json")[0])
        if (
            mesh["revision"] != inputs.snapshot.geometry.brep_sha256
            or mesh["units"] != "m"
            or set(mesh["boundary"]) != {f.id for f in inputs.snapshot.geometry.faces}
        ):
            raise DomainError(503, "mesh_integrity", "Mesh identity or boundary mapping disagrees")
        quality = mesh_quality(mesh)
        quality_faces = []
        from worker.meshing import face_nodes

        grouped: dict[tuple[str, str], dict[str, Any]] = {}
        metrics = {str(c["element_id"]): c for c in quality["cells"]}
        for eid, connectivity in mesh["elements"].items():
            bucket = (
                "failed"
                if not metrics[eid]["accepted"]
                else "warning"
                if metrics[eid]["mean_ratio"] < 0.2
                else "passed"
            )
            body = mesh["owners"][eid]
            group = grouped.setdefault((body, bucket), {"points": [], "triangles": []})
            for face_number in range(1, 5):
                ns = face_nodes(connectivity, face_number)
                offset = len(group["points"])
                group["points"].extend(mesh["nodes"][str(n)] for n in ns)
                group["triangles"].extend(
                    tuple(offset + i for i in tri)
                    for tri in ((0, 3, 5), (3, 1, 4), (5, 4, 2), (3, 4, 5))
                )
        for (body, bucket), group in grouped.items():
            quality_faces.append(
                FaceDisplay(
                    id=f"quality:{body}:{bucket}",
                    body_id=body,
                    points_m=group["points"],
                    triangles=group["triangles"],
                )
            )
        # Subdivide every tri6 into four display triangles; midsides remain
        # real mesh nodes. Catalog face IDs are retained for picking and loads.
        faces = []
        for catalog in inputs.snapshot.geometry.faces:
            unique = sorted({n for f in mesh["boundary"][catalog.id] for n in f["nodes"]})
            indices = {n: i for i, n in enumerate(unique)}
            triangles = []
            for face in mesh["boundary"][catalog.id]:
                a, b, c, ab, bc, ca = [indices[n] for n in face["nodes"]]
                triangles.extend([(a, ab, ca), (ab, b, bc), (ca, bc, c), (ab, bc, ca)])
            faces.append(
                FaceDisplay(
                    id=catalog.id,
                    body_id=catalog.body_id,
                    points_m=[mesh["nodes"][str(n)] for n in unique],
                    triangles=triangles,
                )
            )
        self.repository.get(owner, identifier)
        return MeshPreview(
            job_id=identifier,
            analysis_id=job.analysis_id,
            geometry_revision_id=job.geometry_revision_id,
            nodes=len(mesh["nodes"]),
            elements=len(mesh["elements"]),
            quality=quality,
            quality_display=GeometryDisplay(
                brep_sha256=inputs.snapshot.geometry.brep_sha256,
                lod="coarse",
                bodies=inputs.display.bodies,
                faces=quality_faces,
            ),
            display=GeometryDisplay(
                brep_sha256=inputs.snapshot.geometry.brep_sha256,
                lod="coarse",
                bodies=inputs.display.bodies,
                faces=faces,
            ),
        )

    def result_view(self, owner: UUID, identifier: UUID) -> ResultView:
        job = self.repository.get(owner, identifier)
        if job.status != "succeeded" or job.kind != "solve":
            raise DomainError(409, "results_unavailable", "Select a completed validated solve")
        inputs = self.repository.inputs(owner, identifier)
        frozen = JobInput.model_validate_json(self.artifact(owner, identifier, "snapshot.json")[0])
        if frozen != inputs or inputs.mesh is None or inputs.deck_sha256 is None:
            raise DomainError(503, "artifact_integrity", "Frozen run inputs disagree")
        raw = json.loads(self.artifact(owner, identifier, "results.json")[0])
        mesh = json.loads(self.artifact(owner, identifier, "mesh.json")[0])
        deck = self.artifact(owner, identifier, "analysis.inp")[0].decode("ascii")
        # Verify retained native sources too, rather than trusting only links
        # inside the parsed artifact after on-disk corruption.
        self.artifact(owner, identifier, "analysis.dat")
        self.artifact(owner, identifier, "analysis.frd")
        try:
            if (
                raw["input_sha256"] != job.input_sha256
                or raw["mesh_sha256"] != inputs.mesh.sha256
                or raw["deck_sha256"] != inputs.deck_sha256
                or job.artifacts["mesh.json"].sha256 != inputs.mesh.sha256
                or job.artifacts["analysis.inp"].sha256 != inputs.deck_sha256
                or raw["dat"]["source_sha256"] != job.artifacts["analysis.dat"].sha256
                or any(
                    p["provenance"]["source_sha256"] != job.artifacts["analysis.frd"].sha256
                    for p in raw["frd"]
                )
            ):
                raise ValueError("Result source identities disagree")
            materials = {
                assignment.body_id: {
                    "material_id": f"M{i}",
                    "yield_strength_pa": assignment.material.properties.yield_strength_pa,
                    "name": assignment.material.provenance.name,
                }
                for i, body in enumerate(inputs.snapshot.geometry.bodies, 1)
                for assignment in inputs.snapshot.materials.assignments
                if assignment.body_id == body.id
            }
            view = ResultView(
                job_id=job.id,
                analysis_id=job.analysis_id,
                analysis_revision=job.analysis_revision,
                geometry_revision_id=job.geometry_revision_id,
                input_sha256=job.input_sha256,
                results_sha256=job.artifacts["results.json"].sha256,
                mesh_sha256=inputs.mesh.sha256,
                deck_sha256=inputs.deck_sha256,
                dat_sha256=job.artifacts["analysis.dat"].sha256,
                processor_sources={
                    name: sha256(ROOT / name)
                    for name in (
                        "services/worker/worker/postprocess/view.py",
                        "services/worker/worker/postprocess/fields.py",
                        "services/worker/worker/postprocess/tensors.py",
                        "services/worker/worker/meshing.py",
                        "services/worker/worker/actions.py",
                        "services/worker/worker/calculix/results.py",
                        "services/api/app/jobs/service.py",
                        "services/api/app/domain/results.py",
                    )
                },
                data=ResultData.model_validate(
                    build_view(
                        raw,
                        mesh,
                        materials,
                        deck,
                        load_state(
                            inputs.snapshot.analysis,
                            inputs.snapshot.geometry,
                            inputs.snapshot.materials,
                            inputs.snapshot.loads,
                            inputs.display,
                        ).model_dump(mode="json")
                        | {
                            "equilibrium_policy": inputs.policy.get(
                                "equilibrium",
                                {
                                    "version": 1,
                                    "relative": 0.005,
                                    "force_absolute_n": 1e-6,
                                    "moment_absolute_nm": 1e-6,
                                },
                            )
                        },
                    )
                ),
            )
            self.repository.get(owner, identifier)
            return view
        except (ValueError, KeyError, TypeError, AssertionError):
            raise DomainError(
                503, "result_integrity", "Frozen output or derived fields failed validation"
            ) from None
