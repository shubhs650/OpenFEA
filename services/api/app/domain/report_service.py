"""Owner-scoped, append-only reports from retained validated historical runs."""

import fcntl
import hashlib
import json
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import text

from app.domain.deck_service import canonical
from app.domain.errors import DomainError, not_found
from app.domain.loads import load_state
from app.domain.reports import ReportFigure, ReportModel, ReportRecord, ReportRequest, ReportTable
from app.domain.results import ResultIdentity
from app.domain.units import PRESETS
from app.jobs.service import JobService
from worker.reports.figures import figure, legend
from worker.reports.html import report_html
from worker.reports.model import tables, value
from worker.reports.render import generator, render_pdf


class ReportService:
    def __init__(self, jobs: JobService) -> None:
        self.jobs = jobs
        self.projects = jobs.repository.projects
        self.storage = jobs.storage

    def list(self, owner: UUID, job_id: UUID) -> list[ReportRecord]:
        with self.projects.database.engine.connect() as connection, connection.begin():
            self.jobs.repository.authorized(connection, owner, job_id)
            records = connection.execute(
                text(
                    "SELECT record_json FROM reports WHERE job_id=:id ORDER BY rowid DESC LIMIT 100"
                ),
                {"id": str(job_id)},
            ).scalars()
            return [ReportRecord.model_validate_json(r) for r in records]

    def get(self, owner: UUID, report_id: UUID) -> ReportRecord:
        with self.projects.database.engine.connect() as connection, connection.begin():
            record = connection.execute(
                text("SELECT record_json FROM reports WHERE id=:id"), {"id": str(report_id)}
            ).scalar_one_or_none()
            if record is None:
                raise not_found()
            result = ReportRecord.model_validate_json(record)
            self.jobs.repository.authorized(connection, owner, result.job_id)
            return result

    def artifact(
        self, owner: UUID, report_id: UUID, kind: Literal["model", "html", "pdf"]
    ) -> bytes:
        record = self.get(owner, report_id)
        digest = {
            "model": record.model_sha256,
            "html": record.html_sha256,
            "pdf": record.pdf_sha256,
        }[kind]
        data = self.storage.read(record.project_id, digest)
        self.get(owner, report_id)
        return data

    def create(self, owner: UUID, job_id: UUID, request: ReportRequest) -> ReportRecord:
        self.jobs.repository.get(owner, job_id)
        # A process lock also bounds reports across API instances; never retry automatically.
        lock_path = self.storage.root / "report.lock"
        with lock_path.open("a+b") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise DomainError(
                    429, "report_busy", "Another report is rendering; try again later"
                ) from None
            try:
                return self._create(owner, job_id, request)
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _create(self, owner: UUID, job_id: UUID, request: ReportRequest) -> ReportRecord:
        view = self.jobs.result_view(owner, job_id)
        job = self.jobs.repository.get(owner, job_id)
        inputs = self.jobs.repository.inputs(owner, job_id)
        project = self.projects.get_project(owner, job.project_id)
        mesh = json.loads(self.jobs.artifact(owner, job_id, "mesh.json")[0])
        if job.mesh_job_id is None:
            raise DomainError(503, "artifact_integrity", "Frozen mesh job is unavailable")
        original_mesh = self.jobs.repository.get(owner, job.mesh_job_id)
        mesh["quality"] = original_mesh.summary.get("quality", {})
        loads = load_state(
            inputs.snapshot.analysis,
            inputs.snapshot.geometry,
            inputs.snapshot.materials,
            inputs.snapshot.loads,
            inputs.display,
            inputs.snapshot.bonds,
        )
        bodies = {b.id for b in inputs.snapshot.geometry.bodies}
        prepared = []
        data = view.data.model_dump(mode="json")
        preset = PRESETS[request.units]
        try:
            for definition in request.views:
                if not set(definition.visible_body_ids) <= bodies:
                    raise ValueError("A selected body does not belong to this frozen run")
                geometry = data
                if definition.section:
                    section = self.jobs.result_inspection(owner, job_id, definition.section)
                    geometry = section.model_dump(mode="json")
                field = next(f for f in view.data.fields if f.key == definition.field)
                unit = preset.length if field.unit == "m" else preset.stress
                mode = (
                    "Native DAT nodal displacement"
                    if field.unit == "m"
                    else (
                        view.data.smoothing_method
                        if definition.smoothed
                        else view.data.stress_method
                    )
                )
                location = (
                    "element-interpolated volume section "
                    + str(definition.section.model_dump(mode="json"))
                    if definition.section
                    else ("node boundary" if field.unit == "m" else "element-node boundary")
                )
                caption = (
                    f"{field.label}; global Cartesian; {location}; {mode}. "
                    f"Deformation ×{definition.deformation_scale:g}; "
                    f"visible bodies {', '.join(definition.visible_body_ids)}. "
                    "Flat triangle colour samples use the vertex-scalar mean; "
                    "no numerical extrema are read from pixels. "
                    "Camera and SI limits are retained in the report model."
                )
                prepared.append(
                    ReportFigure(
                        caption=caption,
                        svg=figure(view, definition, geometry)
                        + legend(field.label, unit.label, definition.range_si, unit.to_si),
                    )
                )
            setup = request.views[0].model_copy(
                update={"deformation_scale": 0, "visible_body_ids": sorted(bodies), "section": None}
            )
            prepared.insert(
                0,
                ReportFigure(
                    caption=(
                        "Frozen loads and supports on undeformed geometry. Arrows indicate"
                        " global direction only; squares indicate fixed supports. Marker "
                        "numbers resolve to the setup table; arrow lengths do not encode "
                        "magnitude."
                    ),
                    svg=figure(
                        view,
                        setup,
                        data,
                        markers=[m.model_dump(mode="json") for m in loads.markers],
                    ),
                ),
            )
            tool_identity = generator()
        except (ValueError, StopIteration, OverflowError) as error:
            raise DomainError(422, "invalid_report_view", str(error)) from None
        except RuntimeError:
            raise DomainError(
                503, "report_renderer_unavailable", "Report renderer prerequisites are unavailable"
            ) from None
        comparison = (
            self.jobs.compare_results(owner, job_id, request.comparison)
            if request.comparison
            else None
        )
        report_tables = tables(inputs, job, view, loads, mesh, request.units)
        warnings = list(dict.fromkeys(inputs.warnings + view.data.warnings))
        assumptions = list(view.data.assumptions)
        if comparison:
            unit = preset.length if comparison.unit == "m" else preset.stress
            warnings = list(
                dict.fromkeys(warnings + comparison.warnings + comparison.compared.warnings)
            )
            assumptions += comparison.compared.assumptions
            report_tables.append(
                ReportTable(
                    title="Physical refinement comparison — no convergence certification",
                    columns=[
                        "Sample / body / position (m)",
                        f"Reference / compared ({unit.label})",
                        "Signed / absolute change",
                        "Relative change",
                    ],
                    rows=[
                        [
                            r.sample.label
                            + " / "
                            + r.sample.body_id
                            + " / "
                            + value(r.sample.point_m),
                            value(r.change.reference, unit.to_si)
                            + " / "
                            + value(r.change.compared, unit.to_si),
                            value(r.change.signed_change, unit.to_si)
                            + " / "
                            + value(r.change.absolute_change, unit.to_si),
                            value(r.change.relative_change),
                        ]
                        for r in comparison.rows
                    ],
                )
            )
            report_tables.append(
                ReportTable(
                    title="Comparison provenance and moving raw peaks",
                    columns=["Fact", "Value"],
                    rows=[
                        ["Compared run", str(comparison.compared.source.job_id)],
                        ["Compared result SHA-256", comparison.compared.source.results_sha256],
                        ["Physics SHA-256", comparison.physics_sha256],
                        [
                            "Method / denominator floor",
                            comparison.method
                            + f"; {comparison.reference_floor:g} {comparison.unit}",
                        ],
                        [
                            "Reference / compared raw peaks",
                            value(comparison.reference.raw_peak.value, unit.to_si)
                            + " / "
                            + value(comparison.compared.raw_peak.value, unit.to_si),
                        ],
                        [
                            "Raw peak semantics",
                            (
                                "Native peaks may move between meshes; physical samples and moving"
                                " extrema remain separate."
                            ),
                        ],
                    ],
                )
            )
        if job.finished_at is None:
            raise DomainError(409, "results_unavailable", "A finished run is required")
        model = ReportModel(
            id=uuid4(),
            created_at=datetime.now(UTC),
            project_id=job.project_id,
            project_name=project.name,
            run_finished_at=job.finished_at,
            request=request,
            source=ResultIdentity.model_validate(view.model_dump(exclude={"data"})),
            frozen_input=inputs,
            generator=tool_identity,
            run_summary=job.summary,
            mesh_summary=original_mesh.summary,
            tables=report_tables,
            figures=prepared,
            warnings=warnings,
            assumptions=assumptions,
            comparison=comparison,
            limitations=[
                (
                    "Linear static, small-deformation and supplied material "
                    "assumptions apply. No automatic design-safety conclusion is "
                    "generated."
                ),
                (
                    "Yield assessment does not assess fatigue, brittle failure, "
                    "buckling or plasticity. Stress singularities require engineering "
                    "review."
                ),
                (
                    "Passing equilibrium does not establish convergence, stability or "
                    "physical validity. Target-laptop validation and remaining "
                    "external references are pending; bounded M3 approval "
                    "does not certify this design."
                ),
                (
                    "Figures are light report derivatives of retained verified data. "
                    "Hidden bodies, clipping, smoothing and deformation do not alter "
                    "all-body native extrema or warnings."
                ),
            ],
        )
        # Scratch is private and removed on every outcome, including renderer failure.
        parent = self.storage.directory("exports", model.id)
        try:
            with tempfile.TemporaryDirectory(dir=parent) as temporary:
                directory = Path(temporary)
                model_path, html_path, pdf_path = [
                    directory / f"report.{s}" for s in ("json", "html", "pdf")
                ]
                model_path.write_bytes(canonical(model.model_dump(mode="json")))
                html_path.write_text(report_html(model))
                if (
                    model_path.stat().st_size > 16 * 1024**2
                    or html_path.stat().st_size > 16 * 1024**2
                ):
                    raise DomainError(
                        422, "report_size", "Report exceeds the 16 MiB model/HTML limit"
                    )
                try:
                    renderer = render_pdf(directory)
                except (RuntimeError, OSError):
                    raise DomainError(
                        503,
                        "report_render_failed",
                        "PDF rendering failed or exceeded its budget; no report was saved",
                    ) from None
                pdf = self.storage.read_fixed(pdf_path, limit=16 * 1024**2)
                if not pdf.startswith(b"%PDF-"):
                    raise DomainError(503, "report_render_failed", "PDF output failed validation")
                # Revalidate all retained sources at publication; no expired-data fallback.
                self.jobs.result_view(owner, job_id)
                if comparison:
                    self.jobs.result_view(owner, comparison.compared.source.job_id)
                hashes = []
                for path in (model_path, html_path, pdf_path):
                    digest = hashlib.sha256(self.storage.read_fixed(path)).hexdigest()
                    self.storage.save(job.project_id, path, digest)
                    hashes.append(digest)
                record = ReportRecord(
                    id=model.id,
                    job_id=job_id,
                    project_id=job.project_id,
                    title=request.title,
                    created_at=model.created_at,
                    model_sha256=hashes[0],
                    html_sha256=hashes[1],
                    pdf_sha256=hashes[2],
                    renderer=renderer,
                )
                with self.projects.write() as connection:
                    self.jobs.repository.authorized(connection, owner, job_id)
                    if comparison:
                        self.jobs.repository.authorized(
                            connection, owner, comparison.compared.source.job_id
                        )
                    connection.execute(
                        text(
                            "INSERT INTO reports (id,job_id,record_json) VALUES (:id,:job,:record)"
                        ),
                        {
                            "id": str(record.id),
                            "job": str(job_id),
                            "record": record.model_dump_json(),
                        },
                    )
                return record
        finally:
            shutil.rmtree(parent, ignore_errors=True)
