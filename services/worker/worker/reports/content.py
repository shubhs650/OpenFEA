"""Common report text and table continuation rules for PDF and editable Word."""

from collections.abc import Iterator
from itertools import zip_longest
from textwrap import wrap
from typing import Any

from app.domain.reports import ReportModel, ReportTable
from app.domain.results import AssumptionNote

ATTRIBUTION = "Attributed to the report author; this text is not a computed engineering finding."
CLOSING = (
    "Download the immutable report-model JSON for complete original inputs, view definitions, "
    "camera, quality and tool policy. Its SHA-256 and this PDF’s SHA-256 are in the report record."
)


def overview(model: ReportModel) -> str:
    return (
        f"Project: {model.project_name}\n"
        f"Analysis: {model.frozen_input.snapshot.analysis.name} · "
        f"frozen revision {model.source.analysis_revision}\n"
        f"Run completed: {model.run_finished_at.isoformat()}\n"
        f"Report generated: {model.created_at.isoformat()}\n"
        f"Display units: {model.request.units}"
    )


def identity(model: ReportModel) -> str:
    return (
        f"Report {model.id}\nRun {model.source.job_id}\nInput SHA-256 {model.source.input_sha256}"
    )


def assumption(note: AssumptionNote) -> str:
    status = (
        "unassessed"
        if note.triggered is None
        else ("triggered" if note.triggered else "not triggered")
    )
    return f"{note.code} · {note.body_id or 'all bodies'} · {status}: {note.message}"


def rows(table: ReportTable) -> Iterator[tuple[str, ...]]:
    for row in table.rows:
        cells = [
            wrap(c, width=350, replace_whitespace=False, drop_whitespace=False) or [""] for c in row
        ]
        yield from zip_longest(*cells, fillvalue="")


def reproducibility(model: ReportModel) -> dict[str, Any]:
    return {
        **model.source.model_dump(mode="json", exclude={"processor_sources"}),
        **model.source.processor_sources,
        **model.generator,
    }
