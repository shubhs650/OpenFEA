"""Escaped, light-only A4 HTML adapter; no remote assets, scripts or user HTML."""

from html import escape

from app.domain.reports import ReportModel
from worker.reports.content import (
    ATTRIBUTION,
    CLOSING,
    assumption,
    identity,
    overview,
    reproducibility,
    rows,
)

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
        f"<p>{escape(overview(model))}</p>",
        f'<p class="identity">{escape(identity(model))}</p>',
        "<h2>Scope, warnings and assumptions</h2>",
    ]
    for warning in model.warnings:
        parts.append('<p class="warning">' + escape(warning) + "</p>")
    for note in model.assumptions:
        parts.append(f"<p>{escape(assumption(note))}</p>")
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
        for row in rows(table):
            parts.append("<tr>" + "".join("<td>" + escape(c) + "</td>" for c in row) + "</tr>")
        parts.append("</tbody></table>")
    parts += [
        f"<h2>User-written conclusion</h2><p>{escape(ATTRIBUTION)}</p>",
        '<div class="conclusion">'
        + escape(model.request.user_conclusion or "No user conclusion supplied.")
        + "</div>",
        "<h2>Reproducibility IDs</h2>",
    ]
    for key, v in reproducibility(model).items():
        parts.append(f'<p class="identity">{escape(str(key))}: {escape(str(v))}</p>')
    parts.append(f"<p>{escape(CLOSING)}</p></body></html>")
    return "".join(parts)
