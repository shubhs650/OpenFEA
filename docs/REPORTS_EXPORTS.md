# Reports, solver downloads and portable archives

## Shared report model

Report generation consumes one immutable completed run and selected view definitions. Sections: title/project/run date; geometry dimensions and source units; assumptions; material table and provenance; bond review and gaps; mesh counts/quality; loads/supports with arrows; solver/version; selected stress/displacement figures; reaction/equilibrium checks; refinement comparison if present; limitations/warnings; user-written conclusions; reproducibility IDs.
PDF and DOCX share the same data model, field units and captions. Use A4, legible fonts, repeated table headers, unclipped legends and images. No automatic “design safe” conclusion. Warnings remain visible even if user selects only favorable views. User conclusions are clearly attributed and not mixed with numerical facts. Word is editable, so hash/run provenance references the generated version, not later user edits.
Capture figures with camera, field, location type, range, units, smoothing and deformation scale. Server validates view schema against run; never fetch arbitrary user-supplied image URLs. Browser-generated images are size-limited and treated as untrusted. Preview and inspect PDF plus rendered DOCX pages for missing legends or layout overflow.

## Solver downloads

Generated .inp, material/load snapshots, raw available outputs, logs and versions are exportable. Do not provide raw input editing/import execution. Distinguish solver-ready export from a project archive; including a deck does not make imported archives executable. Expired files are labeled unavailable rather than silently regenerated.

## Archive v1

ZIP with manifest.json; project.json; geometry/<hash>.step and canonical geometry when supported; analyses/<id>.json; runs/<id>/snapshot.json; optional meshes/results/reports; tool-version manifest; per-file SHA-256, size and schema version. Manifest declares omitted/expired results and required migrations. Never include session tokens, OAuth IDs, signed URLs, worker credentials or arbitrary local paths.
Import validates limits/hashes/schema before database commit. Create new project and IDs under current user; map all references atomically. Imported historical results are read-only until integrity checked and retain original provenance. Never trust embedded ownership/price credits. A re-solve creates a fresh current-tool run and estimate. Round-trip must preserve physical values, named selections, materials, supported views and immutable snapshot relationships.
