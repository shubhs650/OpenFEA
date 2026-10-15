"""Escaped, light-only A4 HTML adapter; no remote assets, scripts or user HTML."""

from html import escape
from itertools import zip_longest
from textwrap import wrap

from app.domain.reports import ReportModel

CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; img-src 'none'; "
    "font-src 'none'; base-uri 'none'; form-action 'none'"
)
STYLE = """
@page { size: A4; margin: 17mm 15mm 19mm; }
* { box-sizing: border-box; }
html { color-scheme: light; background: white; color: #172633; }
body { font: 10pt/1.4 'DejaVu Sans', Arial, sans-serif; margin: 0; }
h1 { font-size: 23pt; line-height: 1.2; overflow-wrap: anywhere; }
h2 { font-size: 14pt; margin-top: 8mm; break-after: avoid; }
p, td, th, li { overflow-wrap: anywhere; white-space: pre-wrap; }
p { orphans: 3; widows: 3; }
table { width: 100%; border-collapse: collapse; table-layout: fixed;
        font-size: 8.5pt; margin: 3mm 0 6mm; }
thead { display: table-header-group; }
tr { break-inside: avoid; }
th, td { border: .2mm solid #b5c3cd; padding: 2mm; vertical-align: top; }
th { background: #eaf0f5; text-align: left; }
figure { break-inside: avoid; margin: 6mm 0; }
figure svg { width: 100%; display: block; }
figcaption { font-size: 9pt; overflow-wrap: anywhere; white-space: pre-wrap; }
.warning { border-left: 1mm solid #9c5710; padding: 2mm 3mm; background: #fff7e9; }
.conclusion { white-space: pre-wrap; border: .3mm solid #8499aa; padding: 4mm; }
.identity { font-size: 8pt; overflow-wrap: anywhere; }
"""


def report_html(model: ReportModel) -> str:
    parts = [
        '<!doctype html><html lang="en"><head><meta charset="utf-8">',
        f'<meta http-equiv="Content-Security-Policy" content="{escape(CSP, quote=True)}">',
        f"<title>{escape(model.request.title)}</title><style>{STYLE}</style></head><body>",
        f"<h1>{escape(model.request.title)}</h1>",
        f"<p>Project: {escape(model.project_name)}\n"
        f"Analysis: {escape(model.frozen_input.snapshot.analysis.name)} · "
        f"frozen revision {model.source.analysis_revision}\n"
        f"Run completed: {model.run_finished_at.isoformat()}\n"
        f"Report generated: {model.created_at.isoformat()}\n"
        f"Display units: {model.request.units}</p>",
        f'<p class="identity">Report {model.id}\nRun {model.source.job_id}\n'
        f"Input SHA-256 {model.source.input_sha256}</p>",
        "<h2>Scope, warnings and assumptions</h2>",
    ]
    for warning in model.warnings:
        parts.append('<p class="warning">' + escape(warning) + "</p>")
    for note in model.assumptions:
        status = (
            "unassessed"
            if note.triggered is None
            else ("triggered" if note.triggered else "not triggered")
        )
        parts.append(
            f"<p>{escape(note.code)} · {escape(note.body_id or 'all bodies')} · "
            f"{status}: {escape(note.message)}</p>"
        )
    for limitation in model.limitations:
        parts.append("<p>" + escape(limitation) + "</p>")
    parts.append("<h2>Selected figures and setup</h2>")
    for index, figure in enumerate(model.figures, 1):
        parts.append(
            f"<figure>{figure.svg}<figcaption>Figure {index}. "
            f"{escape(figure.caption)}</figcaption></figure>"
        )
    for table in model.tables:
        parts.append("<h2>" + escape(table.title) + "</h2><table><thead><tr>")
        parts.extend("<th>" + escape(c) + "</th>" for c in table.columns)
        parts.append("</tr></thead><tbody>")
        for row in table.rows:
            # Bound row height while preserving EVERY character of long provenance/URLs.
            # Repeated thead remains visible on each A4 page.
            cells = [
                wrap(c, width=350, replace_whitespace=False, drop_whitespace=False) or [""]
                for c in row
            ]
            for continuation in zip_longest(*cells, fillvalue=""):
                parts.append(
                    "<tr>" + "".join("<td>" + escape(c) + "</td>" for c in continuation) + "</tr>"
                )
        parts.append("</tbody></table>")
    parts += [
        (
            "<h2>User-written conclusion</h2><p>Attributed to the report "
            "author; this text is not a computed engineering finding.</p>"
        ),
        '<div class="conclusion">'
        + escape(model.request.user_conclusion or "No user conclusion supplied.")
        + "</div>",
        "<h2>Reproducibility IDs</h2>",
    ]
    identities = {
        **model.source.model_dump(mode="json", exclude={"processor_sources"}),
        **model.source.processor_sources,
        **model.generator,
    }
    for key, v in identities.items():
        parts.append(f'<p class="identity">{escape(str(key))}: {escape(str(v))}</p>')
    parts.append(
        "<p>Download the immutable report-model JSON for complete original"
        " inputs, view definitions, camera, quality and tool policy. Its "
        "SHA-256 and this PDF’s SHA-256 are in the report "
        "record.</p></body></html>"
    )
    return "".join(parts)
