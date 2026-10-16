"""Owned portable setup round trips, inert history and deliberate diagnostic bundles."""

import fcntl
import hashlib
import json
import platform
import shutil
import time
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import text

from app.domain.archive_validation import review_hash, validate_physics
from app.domain.archives import (
    ArchiveAnalysis,
    ArchiveManifest,
    ArchiveOptions,
    BundleRecord,
    DiagnosticOptions,
    FileEntry,
    HistoricalItem,
    ImportedArchive,
    PortableProject,
)
from app.domain.directions import DirectionSelection, resolve_direction
from app.domain.errors import DomainError, not_found
from app.domain.import_service import validate_display
from app.domain.jobs import JobInput, LocalJob
from app.domain.models import AnalysisCreate, GeometryMetadata, GeometryRevision
from app.domain.reports import ReportModel, ReportRecord
from app.domain.words import WordExport
from app.jobs.service import JobService
from app.persistence.repository import now
from app.storage.archives import (
    descriptor,
    json_bytes,
    nested_archive,
    read_archive,
    strict_json,
    write_archive,
)
from worker.reports.docx import validate_docx
from worker.runtime import ROOT, sha256
from worker.step_import import ImportSandboxError, inspect_step

NOTICE = (
    "Includes private engineering data. Historical inputs are downloads only; "
    "import never executes them."
)


def geometry_artifacts(geometry: Any) -> dict[str, FileEntry]:
    return TypeAdapter(dict[str, FileEntry]).validate_python(geometry.validation["artifacts"])


def job_files(job: LocalJob) -> dict[str, str]:
    return {
        "snapshot.json": job.input_sha256,
        **{k: v.sha256 for k, v in job.artifacts.items()},
        **{
            f"execution-{a.number}-{name}": artifact.sha256
            for a in job.attempts
            for name, artifact in a.artifacts.items()
        },
    }


def invalid(message: str) -> DomainError:
    return DomainError(422, "invalid_archive", message)


class ArchiveService:
    def __init__(self, jobs: JobService) -> None:
        self.jobs, self.projects, self.storage = jobs, jobs.decks.repository, jobs.storage

    def tools(self) -> dict[str, str]:
        return {
            "python": platform.python_version(),
            "archive_schema": "1",
            "native_lock_sha256": sha256(ROOT / "scripts/native/toolchain-lock.json"),
            "python_lock_sha256": sha256(ROOT / "uv.lock"),
        }

    def collect(
        self, owner: UUID, project_id: UUID, options: ArchiveOptions
    ) -> tuple[PortableProject, dict[str, bytes]]:
        files: dict[str, bytes] = {}

        def object_file(raw: bytes) -> str:
            digest = hashlib.sha256(raw).hexdigest()
            files[f"objects/{digest}"] = raw
            if sum(map(len, files.values())) > 60 * 1024**2:
                raise invalid("Project exceeds 64 MiB archive limit; omit outputs")
            return digest

        def retained(digest: str) -> str:
            object_file(self.storage.read(project_id, digest))
            return digest

        with self.projects.database.engine.connect() as connection, connection.begin():
            project = self.projects._project(connection, owner, project_id)
            geometry_ids = (
                connection.execute(
                    text(
                        "SELECT id FROM geometry_revisions WHERE project_id=:id "
                        "ORDER BY created_at,id LIMIT 9"
                    ),
                    {"id": str(project_id)},
                )
                .scalars()
                .all()
            )
            if len(geometry_ids) > 8:
                raise invalid("Archive v1 supports at most eight geometry revisions")
            geometries = [self.projects._geometry(connection, owner, UUID(g)) for g in geometry_ids]
            for geometry in geometries:
                artifacts = geometry.validation.get("artifacts")
                if not isinstance(artifacts, dict):
                    raise invalid("Geometry lacks portable native artifacts")
                for artifact in geometry_artifacts(geometry).values():
                    retained(artifact.sha256)
            revisions = connection.execute(
                text(
                    "SELECT analysis_id,revision FROM analysis_revisions WHERE "
                    "project_id=:id ORDER BY analysis_id,revision LIMIT 257"
                ),
                {"id": str(project_id)},
            ).all()
            if len(revisions) > 256:
                raise invalid("Archive v1 supports at most 256 analysis revisions")
            analyses = [
                ArchiveAnalysis(
                    analysis=self.projects._analysis(connection, owner, UUID(a), r),
                    materials=self.projects._material_setup(connection, UUID(a), r),
                    loads=self.projects._load_setup(connection, UUID(a), r),
                    mesh=self.projects._mesh_setup(connection, UUID(a), r),
                    bonds=self.projects._bond_setup(connection, UUID(a), r),
                )
                for a, r in revisions
            ]
            history = []
            job_ids = (
                connection.execute(
                    text(
                        "SELECT id FROM local_jobs WHERE project_id=:id "
                        "ORDER BY queued_at,id LIMIT 101"
                    ),
                    {"id": str(project_id)},
                )
                .scalars()
                .all()
            )
            if len(job_ids) > 100:
                raise invalid("Archive v1 supports at most 100 historical records")
            for identifier in job_ids:
                job = self.jobs.repository.get(owner, UUID(identifier))
                if job.status not in ("succeeded", "failed", "cancelled", "interrupted"):
                    raise DomainError(
                        409,
                        "archive_busy",
                        "Wait for active jobs to finish or cancel before exporting",
                    )
                item = HistoricalItem(
                    id=job.id,
                    source_id=job.id,
                    kind="job",
                    analysis_id=job.analysis_id,
                    geometry_revision_id=job.geometry_revision_id,
                    related_ids=[job.mesh_job_id] if job.mesh_job_id else [],
                )
                item.files["record.json"] = object_file(json_bytes(job.model_dump(mode="json")))
                candidates = job_files(job)
                self.collect_history(item, candidates, options.include_outputs, retained)
                history.append(item)
            reports = (
                connection.execute(
                    text(
                        "SELECT r.record_json FROM reports r JOIN local_jobs j ON "
                        "j.id=r.job_id WHERE j.project_id=:id LIMIT 101"
                    ),
                    {"id": str(project_id)},
                )
                .scalars()
                .all()
            )
            if len(reports) + len(history) > 100:
                raise invalid("Archive v1 supports at most 100 historical records")
            for raw in reports:
                record = ReportRecord.model_validate_json(raw)
                job = self.jobs.repository.get(owner, record.job_id)
                item = HistoricalItem(
                    id=record.id,
                    source_id=record.id,
                    kind="report",
                    analysis_id=job.analysis_id,
                    geometry_revision_id=job.geometry_revision_id,
                    related_ids=[record.job_id],
                )
                item.files["record.json"] = object_file(raw.encode())
                self.collect_history(
                    item,
                    {
                        "model.json": record.model_sha256,
                        "report.pdf": record.pdf_sha256,
                        "preview.html": record.html_sha256,
                    },
                    options.include_outputs,
                    retained,
                )
                history.append(item)
            words = (
                connection.execute(
                    text(
                        "SELECT w.record_json FROM report_word_exports w JOIN "
                        "reports r ON r.id=w.report_id JOIN local_jobs j ON "
                        "j.id=r.job_id WHERE j.project_id=:id LIMIT 101"
                    ),
                    {"id": str(project_id)},
                )
                .scalars()
                .all()
            )
            if len(words) + len(history) > 100:
                raise invalid("Archive v1 supports at most 100 historical records")
            for raw in words:
                word = WordExport.model_validate_json(raw)
                job = self.jobs.repository.get(owner, word.job_id)
                item = HistoricalItem(
                    id=word.id,
                    source_id=word.id,
                    kind="word",
                    analysis_id=job.analysis_id,
                    geometry_revision_id=job.geometry_revision_id,
                    related_ids=[word.report_id, word.job_id],
                )
                item.files["record.json"] = object_file(raw.encode())
                self.collect_history(
                    item, {"report.docx": word.docx_sha256}, options.include_outputs, retained
                )
                history.append(item)
            # Keep prior inert provenance portable on repeated round trips.
            previous = (
                connection.execute(
                    text("SELECT record_json FROM archive_imports WHERE project_id=:id"),
                    {"id": str(project_id)},
                )
                .scalars()
                .all()
            )
            for raw in previous:
                imported = ImportedArchive.model_validate_json(raw)
                for old in imported.history:
                    item = old.model_copy(deep=True)
                    for name, digest in list(item.files.items()):
                        if name in ("record.json", "snapshot.json") or options.include_outputs:
                            try:
                                retained(digest)
                            except DomainError as error:
                                if error.code != "artifact_unavailable":
                                    raise
                                del item.files[name]
                                item.omitted[name] = "unavailable"
                        else:
                            del item.files[name]
                            item.omitted[name] = "not_selected"
                    history.append(item)
        if len(history) > 100:
            raise invalid("Archive v1 supports at most 100 historical records")
        portable = PortableProject(
            name=project.name,
            source_project_id=project.id,
            geometries=geometries,
            analyses=analyses,
            history=history,
        )
        files["project.json"] = json_bytes(portable.model_dump(mode="json"))
        files["tools.json"] = json_bytes(self.tools())
        self.projects.get_project(owner, project_id)
        return portable, files

    @staticmethod
    def collect_history(
        item: HistoricalItem, candidates: dict[str, str], outputs: bool, retained: Any
    ) -> None:
        for name, digest in candidates.items():
            if name != "snapshot.json" and not outputs:
                item.omitted[name] = "not_selected"
                continue
            try:
                item.files[name] = retained(digest)
            except DomainError as error:
                if error.code != "artifact_unavailable":
                    raise
                item.omitted[name] = "unavailable"

    @contextmanager
    def bundle_slot(self, name: str = "archive-build.lock") -> Iterator[None]:
        if name not in ("archive-build.lock", "archive-upload.lock"):
            raise ValueError("Unknown archive lock")
        with (self.storage.root / name).open("a+b") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise DomainError(
                    429, "archive_busy", "Another archive operation is processing"
                ) from None
            yield

    def export(self, owner: UUID, project: UUID, options: ArchiveOptions) -> BundleRecord:
        self.projects.get_project(owner, project)
        with self.bundle_slot():
            return self._export(owner, project, options)

    def diagnostics(self, owner: UUID, project: UUID, options: DiagnosticOptions) -> BundleRecord:
        self.projects.get_project(owner, project)
        with self.bundle_slot():
            return self._diagnostics(owner, project, options)

    def _export(self, owner: UUID, project: UUID, options: ArchiveOptions) -> BundleRecord:
        portable, files = self.collect(owner, project, options)
        omissions = [
            f"{h.id}/{name}: {reason}"
            for h in portable.history
            for name, reason in h.omitted.items()
        ]
        labels = {
            "project.json": "Versioned geometry/setup/history references",
            "tools.json": "Tool and lock identities",
        }
        for g in portable.geometries:
            for name, item in geometry_artifacts(g).items():
                labels[f"objects/{item.sha256}"] = "Geometry: " + name
        for h in portable.history:
            for name, digest in h.files.items():
                labels[f"objects/{digest}"] = f"Historical {h.kind}: {name}"
        return self.publish(owner, project, "project", files, omissions, NOTICE, labels)

    def _diagnostics(self, owner: UUID, project: UUID, options: DiagnosticOptions) -> BundleRecord:
        self.projects.get_project(owner, project)
        files: dict[str, bytes] = {}
        labels = {"diagnostic.json": "Redacted job states, choices and log omission notice"}
        with self.projects.database.engine.connect() as connection, connection.begin():
            self.projects._project(connection, owner, project)
            rows = (
                connection.execute(
                    text(
                        "SELECT kind,status,stage,reason_code FROM local_jobs "
                        "WHERE project_id=:id ORDER BY queued_at DESC LIMIT 100"
                    ),
                    {"id": str(project)},
                )
                .mappings()
                .all()
            )
            # No project/analysis names, IDs, coordinates, original filenames, arbitrary
            # messages, environment, policy dictionaries or raw log lines enter defaults.
            summary = [{k: row[k] for k in ("kind", "status", "stage")} for row in rows]
        files["diagnostic.json"] = json_bytes(
            {
                "schema_version": 1,
                "job_sample": "Most recent 100 jobs maximum",
                "jobs": summary,
                "logs": "Raw log text omitted; use owned solver downloads for local investigation.",
                "choices": options.model_dump(),
            }
        )
        if options.include_geometry or options.include_results:
            portable, all_files = self.collect(
                owner, project, ArchiveOptions(include_outputs=options.include_results)
            )
            selected: set[str] = set()
            if options.include_geometry:
                selected.update(
                    d.sha256 for g in portable.geometries for d in geometry_artifacts(g).values()
                )
            if options.include_results:
                selected.update(
                    digest
                    for h in portable.history
                    for name, digest in h.files.items()
                    if name in ("mesh.json", "analysis.dat", "analysis.frd")
                )
            for digest in selected:
                files[f"objects/{digest}"] = all_files[f"objects/{digest}"]
                labels[f"objects/{digest}"] = "Explicitly included engineering data (coordinates)"
                for g in portable.geometries:
                    for name, artifact in geometry_artifacts(g).items():
                        if artifact.sha256 == digest:
                            labels[f"objects/{digest}"] = "Geometry: " + name
                for h in portable.history:
                    for name, artifact_hash in h.files.items():
                        if artifact_hash == digest:
                            labels[f"objects/{digest}"] = "Results: " + name
        return self.publish(
            owner,
            project,
            "diagnostic",
            files,
            [
                "Raw logs, credentials, names, setup and report metadata always omitted",
                *([] if options.include_geometry else ["Geometry excluded"]),
                *([] if options.include_results else ["Results excluded"]),
            ],
            "Review exact files before downloading. Geometry/results may reveal "
            "coordinates. Nothing is uploaded or sent to support.",
            labels,
        )

    def publish(
        self,
        owner: UUID,
        project: UUID,
        kind: Literal["project", "diagnostic"],
        files: dict[str, bytes],
        omitted: list[str],
        notice: str,
        labels: dict[str, str] | None = None,
    ) -> BundleRecord:
        identifier = uuid4()
        manifest = ArchiveManifest(
            kind=kind,
            created_at=datetime.now(UTC),
            files={},
            tools=self.tools(),
            omitted=omitted,
            labels=labels or {},
        )
        try:
            raw = write_archive(manifest, files)
        except ValueError as error:
            raise invalid(str(error)) from None
        digest = hashlib.sha256(raw).hexdigest()
        record = BundleRecord(
            id=identifier,
            project_id=project,
            kind=kind,
            created_at=manifest.created_at,
            sha256=digest,
            size_bytes=len(raw),
            manifest=manifest,
            notice=notice,
        )
        parent = self.storage.directory("exports", identifier)
        try:
            path = parent / "bundle.zip"
            path.write_bytes(raw)
            self.storage.save(project, path, digest, limit=64 * 1024**2)
            with self.projects.write() as connection:
                self.projects._project(connection, owner, project)
                connection.execute(
                    text("INSERT INTO portable_bundles VALUES (:id,:project,:record)"),
                    {
                        "id": str(identifier),
                        "project": str(project),
                        "record": record.model_dump_json(),
                    },
                )
        finally:
            shutil.rmtree(parent, ignore_errors=True)
        return record

    def bundle(self, owner: UUID, identifier: UUID) -> BundleRecord:
        return BundleRecord.model_validate_json(self.lookup(owner, identifier, "portable_bundles"))

    def imported(self, owner: UUID, identifier: UUID) -> ImportedArchive:
        return ImportedArchive.model_validate_json(
            self.lookup(owner, identifier, "archive_imports")
        )

    def lookup(self, owner: UUID, identifier: UUID, table: str) -> str:
        if table not in ("portable_bundles", "archive_imports"):
            raise ValueError("Invalid table")
        with self.projects.database.engine.connect() as connection, connection.begin():
            row = connection.execute(
                text(f"SELECT project_id,record_json FROM {table} WHERE id=:id"),
                {"id": str(identifier)},
            ).one_or_none()
            if row is None:
                raise not_found()
            self.projects._project(connection, owner, UUID(row[0]))
            return str(row[1])

    def download(self, owner: UUID, identifier: UUID) -> bytes:
        record = self.bundle(owner, identifier)
        raw = self.storage.read_fixed(
            self.storage.blob_path(record.project_id, record.sha256),
            record.sha256,
            limit=64 * 1024**2,
        )
        self.bundle(owner, identifier)
        return raw

    def history_file(self, owner: UUID, identifier: UUID, item_id: UUID, name: str) -> bytes:
        record = self.imported(owner, identifier)
        item = next((h for h in record.history if h.id == item_id), None)
        if item is None or name not in item.files:
            raise not_found()
        raw = self.storage.read(record.project.id, item.files[name])
        self.imported(owner, identifier)
        return raw

    def import_archive(self, owner: UUID, raw: bytes) -> ImportedArchive:
        with (self.storage.root / "native-import.lock").open("a+b") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise DomainError(
                    429, "import_busy", "Another geometry/archive import is processing"
                ) from None
            try:
                manifest, files = read_archive(raw)
                if manifest.kind != "project" or "project.json" not in files:
                    raise ValueError("Diagnostics are not project archives")
                portable = PortableProject.model_validate(strict_json(files["project.json"]))
                self.validate_project(portable, files)
                return self.restore(owner, raw, portable, files)
            except (
                ValueError,
                KeyError,
                TypeError,
                RecursionError,
                zipfile.BadZipFile,
                ValidationError,
            ) as error:
                raise invalid(
                    "Archive schema, references, paths, limits or hashes failed validation"
                ) from error
            except ImportSandboxError:
                raise invalid(
                    "Archived CAD failed isolated validation; no project was imported"
                ) from None

    def validate_project(self, portable: PortableProject, files: dict[str, bytes]) -> None:
        ids = [str(portable.source_project_id), *(str(g.id) for g in portable.geometries)]
        analysis_ids = {str(a.analysis.id) for a in portable.analyses}
        ids += sorted(analysis_ids) + [str(h.id) for h in portable.history]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate identities")
        geometries = {g.id: g for g in portable.geometries}
        seen = set()
        for geometry in portable.geometries:
            if geometry.project_id != portable.source_project_id or (
                geometry.parent_id is not None and geometry.parent_id not in seen
            ):
                raise ValueError("Invalid geometry ancestry")
            seen.add(geometry.id)
            descriptors = geometry_artifacts(geometry)
            allowed = {
                "geometry.brep",
                "source.step",
                "display-coarse.json",
                "display-fine.json",
                *(f"body{i}.brep" for i in range(1, len(geometry.bodies) + 1)),
            }
            if set(descriptors) != allowed:
                raise ValueError("Invalid geometry artifact names")
            if (
                descriptors["geometry.brep"].sha256 != geometry.brep_sha256
                or descriptors["source.step"].sha256 != geometry.source_sha256
            ):
                raise ValueError("Geometry identity mismatch")
            for d in descriptors.values():
                data = files[f"objects/{d.sha256}"]
                if descriptor(data) != d:
                    raise ValueError("Invalid CAD artifact descriptor")
        revisions: dict[UUID, list[int]] = {}
        for a in portable.analyses:
            analysis = a.analysis
            revisions.setdefault(analysis.id, []).append(analysis.revision)
            if analysis.project_id != portable.source_project_id or (
                analysis.geometry_revision_id and analysis.geometry_revision_id not in geometries
            ):
                raise ValueError("Foreign analysis reference")
            self.validate_selections(a, geometries)
            validate_physics(a, geometries)
        if any(sorted(rs) != list(range(1, len(rs) + 1)) for rs in revisions.values()):
            raise ValueError("Noncontiguous analysis revisions")
        history_ids = {h.id for h in portable.history}
        docx_hashes = set()
        for h in portable.history:
            if (
                h.analysis_id not in revisions
                or h.geometry_revision_id not in geometries
                or not set(h.related_ids) <= history_ids
            ):
                raise ValueError("Foreign historical reference")
            historical_names = {
                "record.json",
                "snapshot.json",
                "model.json",
                "report.pdf",
                "preview.html",
                "report.docx",
                "mesh.json",
                "analysis.inp",
                "analysis.dat",
                "analysis.frd",
                "results.json",
                "mesh.log",
                "solve.log",
                "solver.log",
                "resources.json",
                "validation-resources.json",
                "validation.log",
                "mesh-resources.json",
                "solve-resources.json",
                "recovery.json",
                "assembly.json",
                *(
                    f"mesh-attempt-{i}{suffix}"
                    for i in range(1, 4)
                    for suffix in (".log", "-resources.json")
                ),
            }
            allowed_names = historical_names | {
                f"execution-{number}-{name}"
                for number in (1, 2)
                for name in historical_names - {"record.json"}
            }
            for name, digest in h.files.items():
                if name not in allowed_names:
                    raise ValueError("Unsupported historical file")
                if hashlib.sha256(files[f"objects/{digest}"]).hexdigest() != digest:
                    raise ValueError("Historical checksum mismatch")
                if name == "report.docx":
                    validate_docx(files[f"objects/{digest}"])
                    docx_hashes.add(digest)
            original = strict_json(files[f"objects/{h.files['record.json']}"])
            model_type: Any = {"job": LocalJob, "report": ReportRecord, "word": WordExport}[h.kind]
            record = model_type.model_validate(original)
            if record.id != h.source_id:
                raise ValueError("Historical provenance ID mismatch")
            expected_files: dict[str, str]
            if h.kind == "job":
                expected_files = job_files(record)
                source_related = [record.mesh_job_id] if record.mesh_job_id else []
            elif h.kind == "report":
                expected_files = {
                    "model.json": record.model_sha256,
                    "report.pdf": record.pdf_sha256,
                    "preview.html": record.html_sha256,
                }
                source_related = [record.job_id]
            else:
                expected_files = {"report.docx": record.docx_sha256}
                source_related = [record.report_id, record.job_id]
            originals = {item.source_id: item.id for item in portable.history}
            if [originals[identifier] for identifier in source_related] != h.related_ids:
                raise ValueError("Historical relationships disagree")
            if any(
                name != "record.json" and expected_files.get(name) != digest
                for name, digest in h.files.items()
            ):
                raise ValueError("Historical record/artifact hashes disagree")
            if "snapshot.json" in h.files:
                snapshot = JobInput.model_validate(
                    strict_json(files[f"objects/{h.files['snapshot.json']}"])
                )
                if (
                    snapshot.snapshot.analysis.id != record.analysis_id
                    or snapshot.snapshot.analysis.project_id != record.project_id
                    or snapshot.snapshot.geometry.id != record.geometry_revision_id
                ):
                    raise ValueError("Historical snapshot identities disagree")
            if "model.json" in h.files:
                model = ReportModel.model_validate(
                    strict_json(files[f"objects/{h.files['model.json']}"])
                )
                if (
                    model.id != record.id
                    or model.source.job_id != record.job_id
                    or model.project_id != record.project_id
                ):
                    raise ValueError("Historical report model identities disagree")
        referenced = {d.sha256 for g in portable.geometries for d in geometry_artifacts(g).values()}
        referenced.update(d for h in portable.history for d in h.files.values())
        if set(files) != {"project.json", "tools.json", *(f"objects/{d}" for d in referenced)}:
            raise ValueError("Unreferenced archive payload")
        TypeAdapter(dict[str, str]).validate_python(strict_json(files["tools.json"]))
        for name, data in files.items():
            if (
                name.startswith("objects/")
                and nested_archive(data)
                and name.split("/")[1] not in docx_hashes
            ):
                raise ValueError("Recursive archive objects forbidden")

    @staticmethod
    def validate_selections(a: ArchiveAnalysis, geometries: dict[Any, Any]) -> None:
        bodies = {b.id for g in geometries.values() for b in g.bodies}
        faces = {f.id for g in geometries.values() for f in g.faces}
        if any(m.body_id not in bodies for m in a.materials.assignments):
            raise ValueError("Unknown material body")
        for load in a.loads.assignments:
            if (
                load.geometry_revision_id not in geometries
                or not set(load.face_ids + load.review_faces) <= faces
                or not set(load.body_ids + load.review_bodies) <= bodies
            ):
                raise ValueError("Unknown load reference")
        if (
            a.mesh.geometry_revision_id is not None
            and a.mesh.geometry_revision_id not in geometries
        ):
            raise ValueError("Unknown mesh geometry")
        if any(
            s.entity_id not in (bodies if s.kind == "body" else faces) for s in a.mesh.local_sizes
        ):
            raise ValueError("Unknown mesh target")
        for bond in a.bonds.assignments:
            if (
                bond.geometry_revision_id not in geometries
                or bond.master_face_id not in faces
                or bond.slave_face_id not in faces
            ):
                raise ValueError("Unknown bond target")

    def restore(
        self, owner: UUID, raw: bytes, portable: PortableProject, files: dict[str, bytes]
    ) -> ImportedArchive:
        mapping = {str(portable.source_project_id): uuid4()}
        mapping.update({str(g.id): uuid4() for g in portable.geometries})
        for a in portable.analyses:
            mapping.setdefault(str(a.analysis.id), uuid4())
            for assignment_id in [
                *(v.id for v in a.loads.assignments),
                *(v.id for v in a.bonds.assignments),
            ]:
                mapping.setdefault(str(assignment_id), uuid4())
        mapping.update({str(h.id): uuid4() for h in portable.history})

        def remap(value: Any, field: str = "") -> Any:
            if isinstance(value, str):
                return (
                    str(mapping.get(value, value))
                    if field
                    in {
                        "id",
                        "project_id",
                        "geometry_revision_id",
                        "analysis_id",
                        "parent_id",
                        "related_ids",
                    }
                    else value
                )
            if isinstance(value, list):
                return [remap(v, field) for v in value]
            if isinstance(value, dict):
                return {k: remap(v, k) for k, v in value.items()}
            return value

        project_id = mapping[str(portable.source_project_id)]
        parent = self.storage.directory("imports", uuid4())
        published = False
        try:
            started = time.monotonic()
            verified_geometries: dict[UUID, GeometryRevision] = {}
            trusted_objects: dict[str, bytes] = {}
            for i, geometry in enumerate(portable.geometries):
                source = parent / f"geometry-{i}.brep"
                source.write_bytes(files[f"objects/{geometry.brep_sha256}"])
                metadata = parent / f"metadata-{i}.json"
                metadata.write_bytes(json_bytes(geometry.model_dump(mode="json")))
                remaining = 120 - (time.monotonic() - started)
                if remaining <= 0:
                    raise ValueError("Archive CAD validation exceeded aggregate budget")
                output = parent / f"verified-{i}"
                inspected = inspect_step(
                    source, output, archive_metadata=metadata, wall_seconds=remaining
                )
                native = GeometryMetadata.model_validate(inspected["metadata"])
                if native.brep_sha256 != geometry.brep_sha256 or native.bodies != geometry.bodies:
                    raise ValueError("Archived canonical geometry identity/topology disagrees")
                for field in ("faces", "edges", "vertices"):
                    incoming = getattr(geometry, field)
                    rebuilt = getattr(native, field)
                    structural = ("id", "body_id", "neighbors", "face_ids", "vertex_ids")
                    if len(incoming) != len(rebuilt) or any(
                        any(getattr(old, k, None) != getattr(new, k, None) for k in structural)
                        for old, new in zip(incoming, rebuilt, strict=True)
                    ):
                        raise ValueError("Archived native catalog topology disagrees")
                fields = native.model_dump(mode="json")
                fields["validation"]["artifacts"]["source.step"] = geometry_artifacts(geometry)[
                    "source.step"
                ].model_dump()
                fields["validation"]["archive_derived_artifacts"] = (
                    "Regenerated from exact retained canonical BREP; incoming derived "
                    "metrics/artifacts are not trusted"
                )
                fields["edit_recipe"] = geometry.edit_recipe
                verified_geometries[geometry.id] = GeometryRevision(
                    **fields,
                    id=geometry.id,
                    project_id=geometry.project_id,
                    parent_id=geometry.parent_id,
                    created_at=geometry.created_at,
                )
                for name, expected in geometry_artifacts(verified_geometries[geometry.id]).items():
                    if name != "source.step":
                        data = (output / name).read_bytes()
                        if descriptor(data) != expected:
                            raise ValueError("Native CAD artifact failed its hash/size check")
                        trusted_objects[expected.sha256] = data
                saved_bonds = [
                    b
                    for a in portable.analyses
                    for b in a.bonds.assignments
                    if b.geometry_revision_id == geometry.id
                ]
                if saved_bonds:
                    remaining = 120 - (time.monotonic() - started)
                    if remaining <= 0:
                        raise ValueError("Archive CAD review exceeded aggregate budget")
                    review = inspect_step(
                        source, parent / f"review-{i}", bond_review=metadata, wall_seconds=remaining
                    )
                    from app.domain.connections import BondReport

                    fresh_report = BondReport.model_validate(review["report"])
                    if any(
                        b.review_report.pairs != fresh_report.pairs
                        or b.review_report.overlaps != fresh_report.overlaps
                        for b in saved_bonds
                    ):
                        raise ValueError("Saved bond measurements disagree with native geometry")
                for lod in ("coarse", "fine"):
                    validate_display((output / f"display-{lod}.json").read_bytes(), native)
            verified_analyses = []
            for analysis in portable.analyses:
                assignments = []
                for load in analysis.loads.assignments:
                    changes: dict[str, Any] = {}
                    if not load.review_direction:

                        def rebuild(direction: Any, flags: dict[str, Any] = changes) -> Any:
                            current = resolve_direction(
                                verified_geometries[direction.geometry_revision_id],
                                DirectionSelection.model_validate(
                                    {
                                        k: getattr(direction, k)
                                        for k in ("kind", "reference_id", "reverse")
                                    }
                                ),
                            )
                            if (
                                current.vector != direction.vector
                                or current.basis != direction.basis
                            ):
                                # Do not silently change physical force/constraint axes.
                                flags["review_direction"] = True
                                return direction
                            return current

                        if load.direction:
                            changes["direction"] = rebuild(load.direction)
                        changes["symmetry_directions"] = {
                            k: rebuild(v) for k, v in load.symmetry_directions.items()
                        }
                    assignments.append(load.model_copy(update=changes))
                rebuilt = analysis.model_copy(
                    update={"loads": analysis.loads.model_copy(update={"assignments": assignments})}
                )
                validate_physics(rebuilt, verified_geometries)
                verified_analyses.append(rebuilt)
            required_originals = {d for h in portable.history for d in h.files.values()}
            required_originals.update(g.source_sha256 for g in portable.geometries)
            for digest in required_originals:
                trusted_objects[digest] = files[f"objects/{digest}"]
            for digest, data in trusted_objects.items():
                path = parent / "object"
                path.write_bytes(data)
                self.storage.save(project_id, path, digest)
            timestamp = now()
            with self.projects.write() as connection:
                connection.execute(
                    text("INSERT INTO projects VALUES (:id,:owner,:name,1,:time,:time,NULL)"),
                    {
                        "id": str(project_id),
                        "owner": str(owner),
                        "name": portable.name,
                        "time": timestamp,
                    },
                )
                for original in portable.geometries:
                    geometry = verified_geometries[original.id]
                    fields = remap(geometry.model_dump(mode="json"))
                    connection.execute(
                        text(
                            "INSERT INTO geometry_revisions VALUES "
                            "(:id,:project,:parent,:metadata,:time)"
                        ),
                        {
                            "id": fields.pop("id"),
                            "project": fields.pop("project_id"),
                            "parent": fields.pop("parent_id"),
                            "metadata": json.dumps(
                                {k: v for k, v in fields.items() if k != "created_at"}
                            ),
                            "time": fields["created_at"],
                        },
                    )
                for analysis_id in sorted({a.analysis.id for a in portable.analyses}, key=str):
                    revisions = sorted(
                        [a for a in verified_analyses if a.analysis.id == analysis_id],
                        key=lambda a: a.analysis.revision,
                    )
                    identifier = mapping[str(analysis_id)]
                    connection.execute(
                        text("INSERT INTO analyses VALUES (:id,:project,:head,:time,:time)"),
                        {
                            "id": str(identifier),
                            "project": str(project_id),
                            "head": len(revisions),
                            "time": timestamp,
                        },
                    )
                    for a in revisions:
                        transformed_fields = remap(a.model_dump(mode="json"))
                        for bond, original_bond in zip(
                            transformed_fields["bonds"]["assignments"],
                            a.bonds.assignments,
                            strict=True,
                        ):
                            bond["review_sha256"] = review_hash(
                                UUID(bond["geometry_revision_id"]), original_bond.review_report
                            )
                        transformed = ArchiveAnalysis.model_validate(transformed_fields)
                        self.projects._insert_analysis_revision(
                            connection,
                            identifier,
                            project_id,
                            a.analysis.revision,
                            AnalysisCreate(
                                name=a.analysis.name,
                                geometry_revision_id=transformed.analysis.geometry_revision_id,
                            ),
                            timestamp,
                            transformed.materials,
                            transformed.loads,
                            transformed.mesh,
                            transformed.bonds,
                        )
                history = []
                for h in portable.history:
                    fields = remap(h.model_dump(mode="json"))
                    fields["source_id"] = str(h.source_id)
                    history.append(HistoricalItem.model_validate(fields))
                result = ImportedArchive(
                    id=uuid4(),
                    project=self.projects._project(connection, owner, project_id),
                    archive_sha256=hashlib.sha256(raw).hexdigest(),
                    id_map=mapping,
                    history=history,
                )
                connection.execute(
                    text("INSERT INTO archive_imports VALUES (:id,:project,:record)"),
                    {
                        "id": str(result.id),
                        "project": str(project_id),
                        "record": result.model_dump_json(),
                    },
                )
            published = True
            return result
        finally:
            shutil.rmtree(parent, ignore_errors=True)
            if not published:
                shutil.rmtree(self.storage.root / "artifacts" / str(project_id), ignore_errors=True)
