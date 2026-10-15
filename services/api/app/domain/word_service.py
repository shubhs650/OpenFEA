"""Format an exact retained report model; never rebuild its facts from current setup."""

import fcntl
import hashlib
import json
import shutil
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import text

from app.domain.errors import DomainError, not_found
from app.domain.report_service import ReportService
from app.domain.reports import ReportModel, ReportRecord
from app.domain.words import WordExport
from worker.reports.docx import validate_docx, validate_text_tree
from worker.reports.render import render_word, word_generator


class WordService:
    def __init__(self, reports: ReportService) -> None:
        self.reports = reports
        self.jobs, self.projects, self.storage = reports.jobs, reports.projects, reports.storage

    def list(self, owner: UUID, report_id: UUID) -> list[WordExport]:
        report = self.reports.get(owner, report_id)
        with self.projects.database.engine.connect() as connection, connection.begin():
            self.jobs.repository.authorized(connection, owner, report.job_id)
            records = connection.execute(
                text(
                    "SELECT record_json FROM report_word_exports WHERE report_id=:id "
                    "ORDER BY rowid DESC LIMIT 100"
                ),
                {"id": str(report_id)},
            ).scalars()
            return [WordExport.model_validate_json(r) for r in records]

    def get(self, owner: UUID, identifier: UUID) -> WordExport:
        with self.projects.database.engine.connect() as connection, connection.begin():
            raw = connection.execute(
                text("SELECT record_json FROM report_word_exports WHERE id=:id"),
                {"id": str(identifier)},
            ).scalar_one_or_none()
            if raw is None:
                raise not_found()
            record = WordExport.model_validate_json(raw)
            self.jobs.repository.authorized(connection, owner, record.job_id)
            return record

    def artifact(self, owner: UUID, identifier: UUID) -> bytes:
        record = self.get(owner, identifier)
        raw = self.storage.read(record.project_id, record.docx_sha256)
        self.get(owner, identifier)
        return raw

    def retained(self, owner: UUID, report: ReportRecord, model: ReportModel) -> None:
        view = self.jobs.result_view(owner, report.job_id)
        if (
            model.id != report.id
            or model.project_id != report.project_id
            or model.source.job_id != report.job_id
            or any(
                getattr(model.source, k) != getattr(view, k)
                for k in (
                    "analysis_id",
                    "analysis_revision",
                    "geometry_revision_id",
                    "input_sha256",
                    "results_sha256",
                    "mesh_sha256",
                    "deck_sha256",
                    "dat_sha256",
                )
            )
        ):
            raise DomainError(
                503, "report_integrity", "Report and retained run identities disagree"
            )
        if model.comparison:
            other = self.jobs.result_view(owner, model.comparison.compared.source.job_id)
            if other.results_sha256 != model.comparison.compared.source.results_sha256:
                raise DomainError(503, "report_integrity", "Compared run identity disagrees")
        self.reports.artifact(owner, report.id, "pdf")

    def create(self, owner: UUID, report_id: UUID) -> WordExport:
        report = self.reports.get(owner, report_id)
        with (self.storage.root / "report.lock").open("a+b") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise DomainError(
                    429, "report_busy", "Another report is rendering; try again later"
                ) from None
            try:
                return self._create(owner, report)
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _create(self, owner: UUID, report: ReportRecord) -> WordExport:
        raw = self.reports.artifact(owner, report.id, "model")
        try:
            model = ReportModel.model_validate_json(raw)
        except ValidationError:
            raise DomainError(
                503, "report_integrity", "The saved report model is invalid"
            ) from None
        self.retained(owner, report, model)
        try:
            validate_text_tree(model.model_dump(mode="json"))
        except ValueError as error:
            raise DomainError(422, "word_text", str(error)) from None
        try:
            generator = word_generator()
        except (OSError, RuntimeError):
            raise DomainError(
                503, "word_unavailable", "Word rendering dependencies are unavailable"
            ) from None
        identifier = uuid4()
        parent = self.storage.directory("exports", identifier)
        try:
            with tempfile.TemporaryDirectory(dir=parent) as temporary:
                directory = Path(temporary)
                (directory / "model.json").write_bytes(raw)
                provenance = {
                    "report_id": str(report.id),
                    "source_model_sha256": report.model_sha256,
                    "original_pdf_sha256": report.pdf_sha256,
                    "word_export_id": str(identifier),
                    **generator,
                }
                (directory / "provenance.json").write_text(json.dumps(provenance))
                try:
                    renderer = render_word(directory)
                    output = directory / "report.docx"
                    data = self.storage.read_fixed(output, limit=16 * 1024**2)
                    validate_docx(data)
                except (OSError, RuntimeError, ValueError, zipfile.BadZipFile):
                    raise DomainError(
                        503,
                        "word_render_failed",
                        "Word generation failed or exceeded its budget; no export was saved",
                    ) from None
                self.retained(owner, report, model)
                digest = hashlib.sha256(data).hexdigest()
                self.storage.save(report.project_id, output, digest)
                result = WordExport(
                    id=identifier,
                    report_id=report.id,
                    job_id=report.job_id,
                    project_id=report.project_id,
                    created_at=datetime.now(UTC),
                    model_sha256=report.model_sha256,
                    pdf_sha256=report.pdf_sha256,
                    docx_sha256=digest,
                    generator=generator,
                    renderer=renderer,
                )
                with self.projects.write() as connection:
                    self.jobs.repository.authorized(connection, owner, report.job_id)
                    if model.comparison:
                        self.jobs.repository.authorized(
                            connection, owner, model.comparison.compared.source.job_id
                        )
                    connection.execute(
                        text(
                            "INSERT INTO report_word_exports (id,report_id,record_json) "
                            "VALUES (:id,:report,:record)"
                        ),
                        {
                            "id": str(result.id),
                            "report": str(report.id),
                            "record": result.model_dump_json(),
                        },
                    )
                return result
        finally:
            shutil.rmtree(parent, ignore_errors=True)
