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

## Implemented local PDF workflow (T025)

Open a completed solve in **Engineering results**, choose the field/range/smoothing/deformation/section and camera, then use **Add current view to report** beneath the result viewport. Add up to four views. Enter a title and optional **User-written conclusion**; the report uses current display units throughout. A completed physical comparison can be included explicitly. **Generate A4 PDF** saves an immutable report, light HTML preview and shared-model JSON. The saved-report list is restored when that historical run is reopened. Later edits do not rewrite it.

All reports include frozen geometry/source units, sourced materials, supports/load targets and schematic direction arrows, bond/gap review, mesh quality/counts, solver identity, all-body native extrema, supplied-yield states, external reactions/equilibrium, original warnings, assumption explanations and reproducibility IDs. The model retains complete inputs/tool policy and view definitions; it is the common data source for the later T026 Word adapter. Camera coordinates use the model-centred metre frame. Vector figures disclose flat triangle colour sampling and differ from a vtk.js screenshot. Visibility/range/smoothing never filters raw summaries or warnings.

Generation requires all original retained numerical sources and checks them again before publication; a missing/corrupt source refuses. Existing PDF/model downloads remain available while their own bytes and owner/project access remain valid. Project deletion removes access. There is no expiry scheduler in this slice. No uploaded HTML, arbitrary image URL, executable content or user-authored deck is accepted. The renderer is isolated and resource-bounded; dependency failure is an explicit error, with no saved successful report. [ADR-032](adr/ADR-032.md) defines exact bounds and [T025](validation/T025.md) records executed checks. PDF/Word parity is not claimed until T026.

## Implemented editable Word workflow (T026)

Under any saved report, select **Generate editable Word**. The service consumes that report's original shared model and PDF identities, including reports saved before T026. **Download editable Word** returns a DOCX with editable headings, paragraphs, captions and tables; the figures and their legends are embedded images. **Word export provenance** exposes the original model/PDF hashes, generated DOCX hash and generator/resource audit. Exports survive reload and are append-only; editing the current analysis does not alter them.

The document retains the PDF's exact numerical table strings, units, warnings, assumptions and attributed conclusion. A separate provenance notice explains that later edits are outside the generated checksum and do not acquire engineering approval. Missing original numerical files block new generation; existing checked downloads remain available until project deletion or their own artifact loss. Invalid XML characters refuse with a clear error rather than being silently removed. No DOCX import or executable content is accepted.

Production export uses the existing isolated renderer and pinned python-docx/lxml, without requiring Word or LibreOffice. `make test-reports` additionally requires LibreOffice Writer for actual converted-page QA; [ADR-033](adr/ADR-033.md) and [T026 evidence](validation/T026.md) record parity, layout and limits. Exact page breaks across Word/LibreOffice installations and actual Windows-laptop acceptance remain T030.

## Implemented archives and diagnostics (T027)

Use **Portable archives** in the project workspace. **Preview project archive** includes all supported geometry/setup revisions and retained run snapshots. Select **Include available meshes, results and reports** to retain raw outputs, original PDF/model/Word and logs. The preview lists exact included contents and marks unselected/unavailable output; corrupt bytes refuse. **Download reviewed project archive** saves the ZIP. It contains private engineering data.

Choose a **Project archive ZIP**, then **Import project archive**. Import validates it and creates a new private project with new IDs. Supported source/SI values, materials, named selections, mesh controls, native bonds and geometry ancestry are retained; CAD previews/body artifacts are regenerated from exact canonical BREP bytes. A direction whose native vector/basis changes is explicitly marked for review instead of silently changing forces or constraints. Imported raw inputs/results/reports remain under **Imported read-only history**, with original bytes/IDs and owned downloads; they do not become executable jobs or certified current results. A new mesh/solve always uses current checked setup and tools. A second round trip preserves this inert history.

**Preview diagnostic bundle** defaults to anonymous job states, tool identities and a raw-log omission notice. Geometry and results are separate unchecked opt-ins, each disclosing coordinates. Exact filenames/purposes/sizes/hashes appear before **Download reviewed diagnostic bundle**. Names, raw logs, setup and reports are always excluded from diagnostics; nothing is sent to support. For local investigation, **Download job snapshot**, **Download analysis.inp** and **Download solver.log** remain in each original run's fixed-name downloads. Missing original files stay unavailable.

[ADR-034](adr/ADR-034.md) defines schema, sandbox and size/count/deadline bounds. Archives over v1 limits refuse instead of truncating setup/history. Unknown schema/migrations require a future explicit migration, not automatic parsing/execution. Bundles remain local immutable downloads; lifecycle/quota, target-laptop/Windows and full release security acceptance remain later gates. [T027 evidence](validation/T027.md) records executed checks and limitations.
