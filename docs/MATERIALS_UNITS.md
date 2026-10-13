# Local units and material editing — T009

Start with `make setup`, `make doctor`, then `make dev`. Import and accept solid STEP as described in [STEP import](STEP_IMPORT.md). Give the analysis a name and choose **Create analysis for this geometry**. Each analysis pins an immutable geometry revision. **Open analysis** restores that revision in the viewport; **Geometry preview (no analysis)** returns to the latest geometry loaded for the project. Importing a replacement does not transfer earlier materials to it. Analysis duplication remains T018.

Select **Material body**. Choose a manufacturer-backed example or enter custom properties, grade, condition, temperature applicability, source reference and assumptions. A source URL is optional; the server never fetches user URLs. Review the properties and select **I confirm the properties, condition and assumptions**, then **Apply material**. This appends an analysis revision. Saved means the server acknowledged it; failed/conflicting saves retain the earlier revision. **Reload saved analysis (discard edits)** explicitly reloads current state. **Cancel material edits** restores the selected body's saved copy. Changing body/analysis discards unapplied form edits.

Library examples are templates, not certified allowables or preconfirmed user materials. Sample requests include the reviewed library version; a changed version refuses until reviewed again. Opening a saved sample loads an editable copy of its frozen properties/provenance. Applying the current library requires a deliberate selection. There is no mutable personal library UI in this slice; custom entries persist per body/analysis revision.

## Quantities and presets

The API stores E/yield in Pa, density in kg/m³ and geometry in m. Display conversion factors come from the authenticated `/unit-presets` endpoint. Preset changes append only a display preference while copying every material SI and original source value exactly. Unapplied numeric edits keep a separate SI value; redisplay never parses rounded text back into physics. Values entered in a material form convert once at the server boundary. A finite boundary conversion may incur binary floating-point roundoff; display-only changes incur no physical drift.

| Display preset | E / yield | Density | Acceleration |
|---|---|---|---|
| mm–N–MPa | MPa | tonne/mm³ | mm/s² |
| m–N–Pa | Pa | kg/m³ | m/s² |
| inch–lbf–psi | psi | lbf·s²/inch⁴ | inch/s² |

The mass-density units are consistent with force, length and seconds. They are not kg/mm³ or lbm/inch³. One tonne/mm³ converts to 10¹² kg/m³. International inch is 0.0254 m; lbf is 0.45359237 kg × 9.80665 m/s² = 4.4482216152605 N. Stress and imperial density follow from force/length² and force·second²/length⁴. The API also provides length/force conversion factors for subsequent load editing. Acceleration conversion is tested; applying gravity loads remains T015.

## Material policy and examples

E must be finite and positive. Optional density and yield must be finite and positive when supplied, including after SI conversion; NaN, infinity, overflow and boolean properties refuse. The current development policy accepts **0 ≤ ν ≤ 0.45**, matching the existing multi-material deck guard. Auxetic and higher ratios remain blocked. Ratios ≥0.4 carry a displacement-tetrahedron locking warning. Tiny axial native tests at 0, 0.3 and 0.45 substantiate a limited compatibility check, not arbitrary-model near-incompressible validation or engineering acceptance.

Missing density leaves the saved body's gravity prerequisite unavailable. Missing yield leaves its yield-factor-of-safety prerequisite unavailable. No calculated factor or result is displayed here. A future yield factor applies only to ductile yielding, not brittle failure, fatigue or buckling. Materials, gravity and yield prerequisites must be checked again when later tasks freeze/execute a run.

The versioned examples use [Kaiser Aluminum's 6061 rod/bar technical data](https://online.kaiseraluminum.com/depot/PublicProductInformation/Document/1025/Kaiser_Aluminum_6061_Rod_and_Bar.pdf) and [Outokumpu's Core range physical properties](https://www.outokumpu.com/-/media/files/products/core/outokumpu-core-range-datasheet.pdf), inspected 2026-10-13. Source title/revision/page, URL, access date, condition, temperature, selected metric columns and assumptions are copied into assignments. Their Poisson ratios are explicitly project assumptions. The stainless example omits yield because product form/condition is unspecified. User confirmation does not turn typical/example values into certified allowables.

## API and storage

All routes retain loopback/session ownership, CSRF for writes, bounded metadata, redacted errors and tombstone checks. Material mutations and unit changes require the **analysis** ETag in If-Match and increment that analysis once. The project revision is unchanged.

| Method / route | Behavior |
|---|---|
| GET `/unit-presets` | Labels and explicit SI factors |
| GET `/material-library` | Versioned templates without user confirmation |
| GET `/analyses/{id}/materials` | Pinned geometry, saved setup and per-body prerequisites |
| GET `/analyses/{id}/revisions/{revision}/materials` | Immutable historical setup |
| PATCH `/analyses/{id}/display-units` | `{preset}`; preserve canonical snapshots |
| PUT `/analyses/{id}/materials/{body_id}` | `{material:{kind:"sample",sample_id,library_version,confirmed:true}}` or `{material:{kind:"custom",units,values,provenance,confirmed:true}}` |
| DELETE `/analyses/{id}/materials/{body_id}` | Remove only this body's assignment in a new revision |

Custom values are `young_modulus`, `poisson_ratio`, optional `density` and optional `yield_strength`, expressed in the submitted preset. Assignments must resolve in that analysis's pinned geometry. No geometry is repinned, no unsupported property is clamped, and no library lookup remains live in stored history. Alembic `0003_analysis_materials` adds append-only setup rows keyed by analysis/revision, with foreign keys and UPDATE/DELETE refusal triggers. Older revisions read as explicitly empty mm–N–MPa setups; name edits carry materials/units forward. Downgrading intentionally drops the material setups while retaining older metadata; use only an operator-authorized disposable/restored DB as described in [persistence](PERSISTENCE.md).

See [ADR-017](adr/ADR-017.md) and [T009 evidence](validation/T009.md). Loads, deterministic engineering deck wiring, asynchronous runs/results, undo/duplication, Windows/Edge/laptop validation and complete M1/M4 gates remain their scheduled tasks. Next: T010.
