# Local STEP import and face selection — T008

Run `make setup`, `make doctor`, `make check`, `make test-native`, then `make dev`. Open the loopback web port (default 5173). Create or open a project, choose a STEP file, and select **Upload and inspect**. The browser displays actual upload progress and the native inspection stage. Source filenames are not used as server storage paths.

Review the detected source length unit, size **in metres** and solid/face counts. If STEP metadata omits length units, choose metres, millimetres or inches explicitly and inspect again. Mixed/unsupported unit metadata and a choice conflicting with declared units are rejected. Check **I confirm the dimensions and body count**, then **Accept geometry**. This server acknowledgement creates an immutable geometry revision; inspection alone does not modify the project geometry. Failed/stale inspection or confirmation retains previously accepted geometry.

The shared vtk.js viewport renders actual face-labelled native tessellation. Drag to rotate, scroll to zoom, use Fit/Front/Isometric, and click faces to select/remove them. Hover and selection have separate highlights, and selected face counts/removable items provide non-color cues. The body tree provides keyboard-accessible face choices plus hide/isolate/show-all controls for occluded faces. Coarse/Fine changes display detail; selection references survive LOD and camera changes. Display triangles are not a solver mesh. Imported project geometry survives service/browser restart; the currently selected project and ephemeral face selection can be chosen again after reload. Engineering assignments are not implemented by this task.

## Supported import and limits

This slice supports solid STEP, 1–10 bodies, recognized metre/millimetre/inch length units or an explicit missing-unit decision. Invalid/surface-only/mixed free geometry is rejected with an actionable message. Optional repair/healing is disabled; general cleanup belongs to T013. Curved-face tessellation is supported and tested with a cylinder; this does not validate meshing or solving arbitrary curved parts.

Limits are 16 MiB uploaded bytes, 200,000 STEP entities, 2,000 faces and 120,000 triangles per display LOD. Native import has bounded wall/CPU/memory/output policies described in [ADR-016](adr/ADR-016.md). Oversized models stop rather than silently deleting geometry, coarsening settings or widening a tolerance. One application import executes at a time; another request gets 429 and can be retried deliberately after completion. Missing native tools, namespaces or sandbox support are blockers. There is no unconfined parse fallback.

Bubblewrap is a Linux runtime prerequisite (`bwrap`). Install your distribution's maintained package alongside the [native prerequisites](NATIVE_TOOLS.md), then run `make doctor`, which now executes a real sandboxed STEP import. The current cloud runtime uses Bubblewrap 0.12.0; each inspection records its actual executable hash/version. User namespaces must be enabled/permitted; Windows/WSL2 target setup is tested at M4, not assumed. No Docker daemon or privileged application process is required. Hosted CI installs the distro package explicitly; its actual execution still needs to pass.

Use synthetic/public fixtures in Codex Cloud. Real local data belongs in a durable operator-managed `FEA_DATA_ROOT` outside the checkout; the existing `/tmp` default can be removed by OS cleanup. See [persistence](PERSISTENCE.md), [security](SECURITY_PRIVACY.md) and [validation evidence](validation/T008.md). Full quota/retention, purge, restore and hardened hosted operations remain later gates; this task's byte/process limits are not those product guarantees.

## Real API path

Use the T007 local session cookie and CSRF token, with the current project's quoted ETag:

| Route | Implemented behavior |
|---|---|
| POST `/projects/{id}/geometry-uploads` | `{size_bytes,sha256}` → owned pending upload ticket |
| PUT `/geometry-uploads/{id}/content` | Raw bytes with Content-Length; stream, hash/size check, immutable original |
| GET `/geometry-uploads/{id}` | Owned ticket state |
| POST `/projects/{id}/geometry-imports` | `{upload_id,source_length_unit?}` plus If-Match → bounded native inspection |
| GET `/geometry-imports/{id}` | Persisted processing/needs_units/ready/failed/committed state |
| POST `/geometry-imports/{id}/confirm` | `{dimensions_confirmed:true}` plus If-Match → verified immutable geometry |
| GET `/geometry/{id}/display?lod=coarse|fine` | Authorized, hash-checked metre-coordinate display with stable body/face IDs |

An inspection can return 201 with a failed/needs_units record; inspect its status/error fields. It is not a successful geometry import until confirmed. Original hashes, canonical/per-body BREP, two display artifacts, tool provenance and warnings are retained under the private data root. Import records/artifacts stay owned and inaccessible after project tombstoning. Reopening an API session after restart retains the persistent local owner. There are no automatic retries; startup marks interrupted incomplete operations failed.

Next is T009: unit/material editing against these immutable body references. T011 introduces the real durable mesh/solve queue and complete run snapshots; T013 introduces geometry edits/reference invalidation. Existing analyses remain pinned to their earlier geometry.
