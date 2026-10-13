# Progress and handoff

Updated: 2026-10-13 UTC
Current state: DURABLE LOCAL MESH/SOLVE QUEUE + FROZEN RUN INPUTS/RAW OUTPUTS + ACTUAL MESH PREVIEW + REVISIONED FACE LOADS + IMMUTABLE CHECKED C3D10 DECK EXPORT + REAL SI UNIT/MATERIAL EDITOR + STEP IMPORT + SELECTABLE vtk.js WORKSPACE + PERSISTENT LOCAL PROJECT API + REAL SYNTHETIC CAD/MESH/SOLVE/STRESS/BOND/CLEANUP/RESOURCE DIAGNOSTICS
Current milestone: M1 — T007–T011 COMPLETE; M0 owner-approved progression and later validation obligations preserved
Next action: T012 — core results vertical slice; M4/T030 retains local laptop and benchmark acceptance obligations

## Current objective

Fully working, validated LOCAL prototype through M4/T030. Develop and test M1–M4 in Codex Cloud with synthetic/public fixtures; validate the completed local workflow on the owner's laptop at the M4 gate. AWS deployment, Google authentication, commercial billing and beta operations remain outside this stage. T001–T006 development deliverables are complete under the [owner's M0 progression exception](docs/validation/M0-owner-decision.md). Formal engineering benchmark sign-offs and target-laptop performance evidence remain deferred. That owner decision added no M1 implementation; T007 was subsequently implemented and tested as recorded below.

## Implementation status

T001: COMPLETE
T002: COMPLETE
T003: COMPLETE
T004: COMPLETE
T005: COMPLETE
T006: COMPLETE
T007: COMPLETE
T008: COMPLETE
T009: COMPLETE
T010: COMPLETE
T011: COMPLETE
T012–T042: NOT STARTED
M0: OWNER APPROVED FOR M1 PROGRESSION — explicit benchmark/laptop deferrals; historical technical NO-GO and fixes retained.
M1: T007–T011 COMPLETE; exit gate NOT RUN.
M2–M6 exit gates: NOT RUN.
B01/B02: DEVELOPMENT PASS on two meshes each; owner-signed acceptance pending.
B09: DEVELOPMENT PASS; engineering-owner review pending.
B07: Native *TIE candidate REJECTED; experimental mortar DEVELOPMENT PASS; owner review pending.
B03–B06, B08, B10–B14: NOT RUN.
AWS price fit: NOT VERIFIED; outside this stage.
Project license: DEFERRED pending dependency/native review.

## T011 completed — durable local mesh and solve jobs

The browser submits durable mesh jobs, previews actual quadratic boundary connectivity, reviews a completed mesh and submits isolated CCX solves. Inputs, material/load provenance, warnings, tool/runtime/source hashes and limits are frozen before admission. Editing and browser closure cannot alter or cancel admitted work. Strict raw DAT/FRD finite/coverage/topology/frame/material validation and complete hashed manifests precede success; downloads retain their original snapshot.

Atomic FIFO claim, attempt fencing, a unique active-job index and OS worker/native leases allow one heavy operation at a time. Native children retain the execution flock through sandbox shutdown. Pending jobs survive restart; interrupted processes are fenced before pending work starts, partial diagnostics are retained and no automatic retry occurs. Cancel remains pending until process death. Tombstones hide access/request cancellation atomically. Duplicate keys replay, changed payload conflicts and stale attempts cannot publish.

Doctor, fast/build/smoke, full native regression plus changed-native replay, integration and browser checks pass: **315 distinct cases, 0 failed/skipped** (185 Python unit, 18 TS, 90 native, 9 integration, 13 Chromium). Actual axial/multi-material queued solves meet fixed 1e-13 m / 0.01 Pa / 0.001 N criteria: displacement error below 5e-16 m, raw tensor error 3.65e-12 Pa, two-body reaction error below 1.01e-5 N. Actual cancellation, CCX error, corrupt/missing output, namespace/symlink denials, API SIGKILL/restart and browser closure are tested. [Evidence](docs/validation/T011.md), [ADR-019](docs/adr/ADR-019.md) and [guide](docs/LOCAL_JOBS.md) retain hashes, commands, screenshot and limits.

T011 is complete for bounded local queue/mesh/solve. Calculated contours/deformation/extrema/FoS remain T012; sizing/recovery/equilibrium/general assembly behavior remain later work. Current caps: 100 planar faces/3,000 affine C3D10 elements; 60 seconds/1,536 MiB RSS/192 MiB scratch per native stage; 180 seconds per job; 20 pending/active jobs. No dependency/native lock, binary build, frozen benchmark criterion or owner disposition changed. Laptop/GPU and owner acceptance remain deferred. Create the T011 PR; do not merge or start T012.

## T010 completed — face loads and deterministic deck

Saved fixed faces, positive-inward/negative-outward planar pressure and global total distributed force now use immutable analysis/geometry references and canonical SI/source copies. Selections deduplicate, overlapping distinct loads require explicit combination, and the viewport shows actual native directions/fixed glyphs and a signed CAD resultant/moment. Material/unit/name edits carry loads forward. Unit switches clear unsaved load numbers instead of reinterpreting them.

A bounded synchronous bridge creates an actual isolated Gmsh affine C3D10 mesh and full downloadable CalculiX deck. Export freezes inputs, validates mapping/area/resultant/moment and the decimal-written deck, then rechecks owner/tombstone/head before publishing immutable hash-verified deck/mesh/snapshot blobs. Old downloads survive later edits and real API-process restart. Force on fixed DOFs refuses without redistribution; coarse planar independent-body limits remain explicit. Native checks exposed and fixed copied-face orientation loss and CCX material-set line overflow.

`make doctor`, `make check build smoke`, `make test-native`, `make test-integration`, `make test-e2e` and final changed-native replays pass: **281 distinct cases, 0 failures/skips** (168 Python unit, 18 TS, 77 native, 7 integration, 11 Chromium). Downloaded decks pass twelve signed pressure references across all six orientations and a two-body 1,000 N force/reaction case. Unit-only revisions retain identical deck bytes. [T010 evidence](docs/validation/T010.md), [ADR-018](docs/adr/ADR-018.md) and [guide](docs/LOADS_DECKS.md) record criteria, measured errors, hashes and limits.

T010 is complete within this bounded export slice. Durable asynchronous mesh/solve jobs, cancellation, status, run snapshots and calculated results remain T011–T012. No dependency/native lock, binary build, frozen benchmark criterion or owner disposition changed. Windows/laptop/GPU and engineering-owner acceptance remain deferred. Create the T010 PR; do not merge or start T011 in this task.

## Owner M0 decision and development sequence

On 2026-10-13 Asia/Calcutta, the product owner explicitly approved M0 and directed that development through M4 occur in Codex Cloud, with local laptop validation at the end of M4. [Decision record](docs/validation/M0-owner-decision.md) quotes the instruction and records the exception. The owner described an i5 10th-generation-equivalent gaming laptop with a 1650-class 4 GB GPU; this is context, not measured OpenFEA capacity. The earlier NO-GO remains historical evidence at its reviewed commit. M0-R1/M0-R2 were corrected in [merged PR #2](https://github.com/shubhs650/OpenFEA/pull/2), whose hosted checks passed. The local development task statuses T003–T006 are now COMPLETE under the bounded owner exception, and at that decision T007 was unblocked but NOT STARTED; its subsequent completion is recorded below.

The exception does not approve B01/B02/B07-mortar/B09 exact assumptions/tolerances: their manifests remain `PENDING` and previous runs remain development-only. Formal hash-bound owner review and reruns are still required before accepted benchmark claims; the M3 assembly gate retains bond-specific evidence and M4/T030 must close the local numerical/workflow gate. Existing mortar support is the limited planar zero-gap unit patch with at most 65 trace nodes per side. Native `*TIE` stays rejected, physical gaps stay disabled until T019/B08, and cloud capacity numbers cannot be advertised as laptop capacity. Current native/admission limits remain. No AWS resources are provisioned; AWS backend work is a later M5 stage after its own cost/security gates.

Decision-record verification: `make doctor check` passed in the current Codex Cloud checkout (90 Python unit and 7 TypeScript unit cases, 0 failed/skipped; lint, format, types, contracts and 105-document/42-task graph checks passed). `git diff --check` passed; benchmark manifests, numerical code and dependency locks were not changed. The merged PR #2 already passed its full hosted native/bootstrap check. Cloud startup instructions were saved as an updated review draft reflecting this decision; saving does not publish or activate that draft.

## T009 executed validation — 2026-10-13

The real browser now creates/opens analyses pinned to accepted geometry and assigns confirmed source-backed or custom materials to each body. E/yield use Pa and density kg/m³; the three presets derive density from force/length/seconds. Unit-only revisions copy every SI/source quantity exactly. Numeric drafts retain SI across display changes. Missing density/yield leave saved gravity/yield-factor prerequisites unavailable. Sources, grade/condition, temperature, assumptions, original source values/units and sample version are frozen; changed reviewed library versions refuse and existing snapshots survive library edits.

- Implementation `5f58480`, base merged T008 `a2a493f`. `make doctor`; fast/build/native/smoke/integration/browser gates and final targeted native replay: **234 distinct cases passed, 0 failed, 0 skipped** (148 Python unit, 11 TS unit, 59 native, 6 integration, 10 Chromium). Thirty-four are new. Source/artifact/tool hashes and command logs are in [T009 evidence](docs/validation/T009.md).
- Independent E/density/acceleration/length/force references pass; repeated actual unit-only saves preserve physical/source snapshots exactly. Real API restart retains native imported geometry, material provenance, history and unit preference. Tests cover invalid/unsupported ν, nonfinite/overflow, confirmation, body/owner/tombstone/revision checks, competing writes and populated legacy migration/reversal.
- Nine native C3D10 axial compatibility solves at ν=0,0.3,0.45 across all presets meet fixed 1e-11 m / 10 Pa criteria: maximum errors **4.95737e-13 m / 2.237502e-7 Pa**. No old benchmark criterion/approval, solver assumption, native lock/binary or dependency changed. This is limited development compatibility, not certification of arbitrary-model material behavior.
- Chromium checks actual native multibody import and real independent sample/custom body saves, source/confirmation, missing-property blockers, SI draft/cancel and preset changes, reload, conflict refusal/reload, new geometry and restored older analysis. Screenshot inspected. [ADR-017](docs/adr/ADR-017.md), [operator guide](docs/MATERIALS_UNITS.md) and generated contracts describe the real path.

T009 is COMPLETE for units/material editing. Material setup rows are append-only per analysis revision; actual run freezing is T011. Load/deck wiring and product solve/results are T010–T012; actual gravity loading is T015. No calculated FoS or certified allowable is shown. Custom global library/undo/duplication, complete archive/restore/fault suites, Windows/Edge/laptop/GPU and full M1/M4 acceptance remain scheduled/unexecuted; the owner exception is preserved. Hosted status is on the T009 PR. Stop after T009 and its PR; **T010** is next.

## T008 executed validation — 2026-10-13

PR #5 hosted run `38392031074` failed during `make setup` at the synthetic namespace-isolated STEP doctor probe; test stages did not execute. Bounded doctor diagnostics in `3d29956` exposed `bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted` on run `38410679299`. CI now loads a `/usr/bin/bwrap`-specific AppArmor user-namespace profile and performs a trusted namespace preflight before native provisioning. Global runner policy and application sandbox restrictions are preserved. Local `make check doctor` passes (124 Python unit and 7 TS unit, no failures/skips). Final head `e1c1bc7` passed [hosted run 38411622227](https://github.com/shubhs650/OpenFEA/actions/runs/38411622227), all 200 cases and failure-propagation checks; the owner merged PR #5 to main `a2a493f` before T009.

The Ubuntu `bubblewrap_0.9.0-1ubuntu0.3_amd64.deb` executable was extracted into ignored scratch storage and used through a command-local PATH for `make doctor` and `.venv/bin/python -m pytest tests/native/test_step_import.py`: actual import probe and all 14 native import/API/security cases pass (0 failed/skipped). This checks launcher-version compatibility in the cloud host, not the Ubuntu AppArmor policy; the hosted preflight remains the policy verification.

The browser now creates/opens real projects, uploads STEP bytes with actual progress, runs isolated OCCT inspection, requires missing-unit/dimensions/body-count confirmation, and renders saved immutable multi-body geometry with vtk.js. Face picks resolve to the catalog within the geometry revision, survive camera/LOD changes, and work with body hide/isolate/tree controls. Invalid/surface/free-wire models, contradictory units, stale confirmations and corrupt artifacts refuse without modifying accepted geometry.

- `make doctor`; `make check test-native build smoke test-integration test-e2e`; final changed-native `make check test-native`: **200 distinct cases passed, 0 failed, 0 skipped** (124 Python unit, 7 TS unit, 56 native, 5 integration, 8 Chromium). Twenty-three cases are new. Full native regressions pass; repeat runs are not added to counts.
- Actual metre/millimetre/inch metadata and explicit missing-unit choices meet fixed analytical dimensions/volumes with 1e-9 m / 1e-10 m³ absolute criteria and no relative tolerance. A cylinder proves different tessellation detail with the same face IDs. Real canvas picks are checked against native body IDs and face centroids after camera/LOD/isolation; the screenshot was inspected.
- Uploads are size/hash bounded. Namespace/readonly mounts, dropped capabilities, no-network launcher, fork/namespace restrictions, native hard limits and a sampled resource watchdog protect parsing. Host read/write, source write, network and fork probes refuse. Publication/download reads use regular no-follow files and hashes, with an owner/revision-guarded atomic promotion. An OS lock serializes application imports; interrupted states fail without retry.
- vtk.js 37.4.2 adds 57 locked npm entries; existing versions and all native locks/binaries/criteria stay unchanged. Bubblewrap is required and explicitly provisioned in hosted CI; actual executable/binding/python/filter/worker/lock hashes and settings are retained per inspection. [Evidence](docs/validation/T008.md), [ADR-016](docs/adr/ADR-016.md), [import guide](docs/STEP_IMPORT.md) and generated contracts document the actual paths and limits.

T008 is COMPLETE for its tested import/viewport scope. Inspection is synchronous/bounded with persisted lifecycle, not the T011 durable queue. Face selections are ephemeral viewport state, not saved engineering assignments. Windows/Edge/target GPU, hosted CI and formal benchmark/M1/M4 acceptance remain unexecuted/deferred. Materials, mesh/solve, cleanup and reports are later tasks. Stop after T008; **T009** is next.

## T007 executed validation — 2026-10-13

The real API now persists owner-scoped projects, project tombstones, immutable geometry metadata and independent draft analysis revisions in SQLite WAL. API startup applies reversible Alembic migrations. ETags/If-Match guard saves, immutable DB triggers preserve history, and owner/project foreign keys prevent cross-project geometry references. Loopback sessions, CSRF, Host/Origin checks, bounded request bytes and redacted errors are wired through the real API. Vite preserves Host for browser mutations. Beta/production still reject local bypass.

- `make doctor` and final `make contracts check build smoke test-integration test-e2e` pass. **135 distinct automated cases passed, 0 failed, 0 skipped**: 118 Python unit, 7 TypeScript unit, 5 real-process integration, 5 Chromium. The 30 new cases include reversible/populated and failed-rollback migrations, competing edits, foreign ownership, immutable revisions, one real three-process restart and one browser/Vite CRUD flow. Repeat runs are not counted again.
- Real HTTP restart preserves local owner, project/analysis history and deletion tombstones. Local session tokens reset on restart; reopening a session retains ownership. Browser writes without CSRF fail, valid writes pass, stale saves return 409 and deleted children disappear. The browser test found Vite's shorthand Host rewrite; the explicit proxy preserves Host instead of weakening the same-origin check.
- SQLAlchemy 2.1.4 and Alembic 1.20.0 plus Mako 1.4.3/MarkupSafe 3.0.4 are pinned/locked and inventoried. Native tools, physical criteria and benchmark manifests are unchanged. Native/benchmark suites and target Windows hardware were not rerun for this metadata task. Existing Chromium stress-fixture regressions use a real diagnostic solve; they do not prove an application solve workflow.
- [T007 evidence](docs/validation/T007.md), [ADR-015](docs/adr/ADR-015.md), [local persistence guide](docs/PERSISTENCE.md) and generated OpenAPI/TS contracts describe the concrete implementation. Geometry registration is internal for a future verified CAD adapter; browser geometry reads exist, but there is no import endpoint or artifact validity claim. The browser UI remains health-only; project operations are actual API paths.

T007 is COMPLETE for its metadata/access scope under the recorded M0 owner progression decision. Exact benchmark and target-laptop acceptance remain deferred to the scheduled M3/M4 gates. T008 is the next bounded task. T007 adds no worker, solver UI, analysis duplication, report or hosted authentication.

## What now works

The React/Vite geometry workspace and FastAPI health/project/import APIs are operational. T002 provisions CPU CCX and isolated CAD/mesh/post environments. T003 provides real synthetic SI STEP→BREP→face-labelled triangles→Gmsh→C3D10/load/deck→CCX diagnostics. T004 adds raw DAT integration-point stress/COORD extraction, canonical tensors with source/entity/frame/material provenance, separately labelled native averaged FRD, element-owned extrapolation/probes, von Mises/principals, native VTK export and an interactive standalone material-jump fixture. `make benchmark CASE=B01 DEVELOPMENT=1` (or B02/B09) runs actual diagnostics; unsigned acceptance fails closed. There is a real STEP import/display and bounded durable local mesh/solve workflow. Calculated result views and reports remain later work.

T005 adds a limited real mortar connection experiment using CCX *EQUATION and native coordinate audits. Native *TIE failed the patch and is not a validated fallback. `make benchmark CASE=B07 DEVELOPMENT=1` passes both role cases within the planar unit/65-node scope, retaining all failed-candidate and negative evidence.

Root/native dependencies are separately locked. Source/deb/wheel/runtime hashes and upstream license notices are recorded. Native processes receive a minimal environment, no network sockets, single-thread settings and resource limits. Full hostile-upload/filesystem isolation is not implemented. See [native setup](docs/NATIVE_TOOLS.md), [ADR-010](docs/adr/ADR-010.md) and the [dependency matrix](docs/DEPENDENCIES.md). Final public license remains deferred.

## M0 exit-gate review

Reviewed commit `bc6af0041d8a6ef51b1ae5b100c3420708bd704d`, 2026-10-13 Asia/Calcutta. **NO-GO**. [Full review](docs/validation/M0-exit-review.md) and [retained review artifacts](docs/validation/results/M0/index.json) record source findings, current checks, manifest packet, analytical-reference assessment and exit actions. This is not engineering-owner approval; statuses remain authoritative.

- `make doctor check test-native build smoke test-integration test-e2e`: exit 0; **123 passed, 0 failed, 0 skipped** (74 Python, 7 TS, 34 native, 4 lifecycle, 4 Chromium). Build/startup/contracts/static/docs checks pass. Two extra real retained-data resource-browser replays pass; renderer is SwiftShader, not target GPU.
- M0-R1 (P1): approval means “not prefixed PENDING”. An empty in-memory B01 sign-off permits real non-development execution and a `PASS` label. No reviewer/date/approval exists; actual frozen files are unchanged. The ordinary PENDING guards work, but invalid/rejected/stale approval handling needs a shared fail-closed validator and regressions. Probe results are never acceptance evidence.
- M0-R2 (P2): failed preparation/solve/post stops the stage loop but later workload meshes still start. Controlled real native exit-7 preparation reproduced all three nominal workload attempts using tiny meshes. Stop the entire ladder, persist failure and test that later jobs are not launched. No tolerance/native-limit change or automatic coarsening.
- **1,090** inventory/runtime/library/license/lock hashes, **29** key retained/current-manifest/source hashes and **99** T006 artifact byte counts/hashes pass. Four independent reference calculations match B01/B02/B07-mortar/B09; proposed acceptance still requires owner/date/criteria-hash records and approved reruns.
- F1/inventory and limited F6 feasibility supported; F2/F3/F5 development-only; F4 alternative-formulation/scope review open; F7 needs software correction plus actual WSL2 conservative capacity/headed integrated-GPU evidence. 100k solve is unrun by policy, not a forced M0 capacity guarantee. Resolve the F4 zero-gap-versus-T019/B08 boundary explicitly with the owner.

At that historical review, the two defects were recorded but not fixed; no approval, T003–T006/M0 closure or T007 work was claimed. Public license, later release/security/report/hosted CI and AWS/beta were separate unexecuted/deferred gates. Startup instructions then retained the NO-GO outcome without publication; a later draft now reflects the owner's decision.

## M0-R1/M0-R2 follow-up — 2026-10-13

At the software-fix follow-up, before the owner's later progression decision, the two reproduced defects had focused fixes without changing frozen B01/B02/B07/B09/T006 manifests, physical tolerances, native limits or owner dispositions. M0 was still **NO-GO** at that point. The subsequent owner exception is recorded above.

- M0-R1: one validator requires an explicit `APPROVED` disposition, nonempty owner, ISO review date and a SHA-256 binding to every benchmark criterion except the approval field. Empty, whitespace, pending, rejected, malformed and stale records refuse before creating a job across B01/B02/B07/B09. An explicit development run remains labelled development-only even if an approved record is supplied. The positive bound-record unit case is synthetic test metadata, **not** owner approval; all committed manifests remain PENDING. B09's successful non-development status now follows the same approval rule.
- M0-R2: the declared native ladder stops after any mesh/prepare/solve/post stage failure or resource stop, saves the failed stage and marks all later workloads `NOT RUN`. A prelaunch resource error is saved as `stage_error`; invalid expected mesh/display artifacts fail the run. A successful mesh rejected by the explicit solve cap remains a separate admission/coarsening outcome. Focused native regressions used tiny real Gmsh meshes, actual exit-7 children, the real RSS watchdog and a real cleanup/CLI exit-2 case. They are sequencing checks, not capacity or physics benchmarks.
- Executed `make doctor check test-native build smoke test-integration test-e2e`: exit 0, **147 distinct automated cases passed, 0 failed, 0 skipped** (90 Python unit, 7 TypeScript unit, 42 native, 4 lifecycle integration, 4 Chromium). Doctor, lint, types, API contracts, documentation graph, build and real HTTP startup/proxy smoke passed. This includes 16 new approval units and 8 new native sequencing cases. No new accepted benchmark or target GPU/laptop result is claimed.
- Hosted PR #2 CI first reached 41/42 passing native cases, then found that the new CLI sequencing test exposed an existing assumption that `/sys/fs/cgroup/cpu.max` and `memory.max` always exist. The feasibility report now records `null` when either cgroup v2 metric is unavailable; the same real CLI failure test explicitly simulates their absence. Reran `make check test-native` locally: 90 Python unit, 7 TypeScript unit and 42 native passed. Hosted CI on this correction must pass before treating the PR as checked.
- Previous [M0 review evidence](docs/validation/M0-exit-review.md) remains historical proof of the defects at commit `bc6af004`; its reproduction scripts should not be read as current expected behavior. [Validation policy](docs/VALIDATION.md) now states the approval-record hash contract. PR #1 previously merged the T001–T006 work and original review into `main`; these follow-up fixes are subsequent work.

## T006 executed validation

Native implementation `d18901a3c2c6bfa4867dc0e3803cdeaddf318409`; child-reaping/browser provenance refinement `c490b21c4035bcb5e337e3c357140d09d3b2113a`. [T006 evidence](docs/validation/T006.md) retains measurements, raw sources, compressed artifacts, hashes, explicit omissions and the F1–F7 review. [ADR-014](docs/adr/ADR-014.md) records material scope/resource decisions.

- Real OCCT selected through-hole and single-edge fillet removal on deep copies produces valid new preview BREP/catalog/tessellation revisions. Analytic volume deltas pass; source hashes are unchanged on success and stale/unsupported selections. Each preview remeshes with six new face references and actual C3D10 elements. General cleanup/apply/undo/remapping remains T013.
- `make check`: 74 Python + 7 TS pass. `make test-native`: 34 pass, 0 failures/skips; changed cleanup/watchdog cases rerun after lifecycle correction also pass. Distinct unit/native total **115**. Doctor, static/docs/root-lock and artifact-integrity checks pass. No dependency/solver changes.
- `make feasibility MESHES=1`: actual 4,891/27,155/99,198-element meshes. Small and medium patches solve 15,219/93,978 free equations with unchanged B01 criteria: max U error ~5e-10 m, tensor error 3.846 Pa. Medium solve 49.858 s/792.12 MiB native maxRSS. Large meshing 19.287 s/501.16 MiB; large solve is NOT RUN due to explicit admission cap, with no automatic coarsening.
- Actual allocation/disk probes verify guarded stops, recorded sampling overshoot, nonzero exits and no host OOM. Cloud `/proc` child discovery and orderly reaping were corrected; native hard limits remain intact.
- Two actual exterior WebGL/native-field checks pass with 60 rotations, field switches and inspected screenshots. Renderer is SwiftShader; 27,155-cell mesh draws 18,544 exterior triangles with median animation interval 42.4 ms. Integrated-GPU/Windows and total browser RSS acceptance remain unrun.
- F1–F7 reviewed. Limited F6 scope is explicit. Highest cloud patch solve does not establish a laptop cap or arbitrary 30k-model capacity; start target calibration conservatively at ≤5k cells. F4/physical-gap/formulation and earlier owner reviews remain open. No M0 closure or milestone exception.

At the T006 handoff its CLI implementation was delivered, formal acceptance was open and T007 had not started. The later owner decision closes bounded T006 development and defers exact benchmark/laptop acceptance; subsequent T007 completion is recorded above. No application workflow, deployment, push or merge was added.

## T005 executed validation

Implementation commit `698bb06e9524992e4a9087490692e3636dbe616b`. Restored native tools/locks reused; no dependency or solver-source change.

- `make doctor` passed real isolated operations and binary/library integrity. `make check test-native`: **111 passed, 0 failed, 0 skipped** (74 Python, 7 TS, 30 native); static checks, contracts and docs pass.
- `make benchmark CASE=B07 DEVELOPMENT=1` passes monolithic and both independently meshed mortar role cases. Unsigned B07 correctly exits 2. `uv lock --check`, final lint/docs/diff and retained artifact hashes pass.
- Native node-to-face *TIE,ADJUST=NO failed the original frozen axial patch despite full coverage: max stress error 183,365 Pa. Failure is retained; original manifest/tolerances are unchanged.
- A second predeclared formulation integrates quadratic interface virtual work and emits CCX *EQUATION. Same geometry/references/loads/sampling/tolerances pass both orientations: 231/423 independent body nodes, 37/65 interface nodes, no merging/fusing, 284 total C3D10 versus a separate 266-element monolith.
- Max mortar displacement/stress error 4.989e-13 m/9.439e-7 Pa; MPC residual≤1.21e-12 m. End ux=9.52381e-6 m in all printed cases. External force/moment balance passes; internal MPC forces are excluded from support reactions.
- Native-double binary geometry audits measure zero coordinate change in both role cases. Diagnostic 10 µm gap shows default native *TIE adjustment and zero with ADJUST=NO; supported preflight rejects the gap, so B08 is not claimed.
- Partial native surface leaves 61 nodes uncovered. Untied CCX returned exit 0/Job finished with ~9.79e9 m displacement; the supported path rejects detached bodies before solving. No stabilization is added. Actual nonzero CCX failures retain complete transcripts.

[T005 evidence](docs/validation/T005.md) and [ADR-013](docs/adr/ADR-013.md) retain frozen manifests, compressed inputs/outputs/meshes and the scientific decision. Experimental mortar is limited to zero-gap planar unit interfaces and ≤65 trace nodes per side; native *TIE remains an unsupported failed candidate. Owner B07/formulation acceptance is pending. T006 subsequently proceeded by explicit request, preserving these pending acceptance gates.

## T004 historical validation

Implementation commit `47d18b9f06df2bb85b373ebc450b2b0f7b3c0a6b`, same pinned native tools; no dependency/lock change.

- `make check test-native test-e2e`: **96 passed, 0 failed, 0 skipped** (58 Python unit, 7 TS, 27 native, 4 Chromium). Static types/format/lint, generated contracts and documentation graph pass.
- `make benchmark CASE=B09 DEVELOPMENT=1`: actual two-material C3D10 solve and VTK/HTML artifacts pass; unsigned B09 exits 2 as required. No repeated cases added to counts.
- Raw DAT retains 210/70 MPa across the shared interface; native FRD averages to 139.999 MPa. Element-side tensors have max error 4.46e-7 Pa. VTK duplicates 6 interface nodes (20 element-owned points/14 global nodes) and preserves 8 IPs and exact tensors/positions.
- Hydrostatic, pure shear and spatially varying shear validate full tensor order, IP locations/numbering, extrapolation, probes and invariants. Native-text max tensor errors: 0, 2.31 Pa, 3.76 Pa respectively; frozen tolerances unchanged.
- Corrupted/truncated/duplicate/incomplete DAT/FRD, invalid orders/positions/topology, nonfinite tensors and stale mesh/ownership fail. An initial repeated-eigenvalue error was fixed with scaled Jacobi; original unit tolerances remain intact.
- Chromium uses a fresh real solve, verifies separate values/colors and source/location labels, and exercises field/node selections. Screenshot was inspected. `uv lock --check`, final lint/docs/diff and retained-source hash checks pass.

[T004 evidence](docs/validation/T004.md), [ADR-012](docs/adr/ADR-012.md) and committed raw outputs/VTK/HTML/screenshot provide the review record. B09 is development-only; engineering review and formal T004/F5 closure remain pending. T005 subsequently proceeded by explicit request, preserving pending acceptance.

## T003 historical validation

Code commit `0dd94178d197c46d54f4762a36303395d4991101`; same pinned Debian 13/Python 3.12.14/native tools as T002. No dependency/lock changes or mocked solver behavior.

- `make check test-native`: 30 Python unit + 7 TypeScript unit + 23 native = **60 passed, 0 failed, 0 skipped**. Lint/format, static types, generated contracts and documentation graph pass.
- `make benchmark CASE=B01 DEVELOPMENT=1` and B02: both exit 0, two meshes (231/100 and 423/184 nodes/elements). These duplicate native cases and are not added to test count.
- B01 max displacement/stress error 5e-10 m/3.85 Pa; B02 4.99e-13 m/1.82e-7 Pa. Every component met its frozen development criterion. Raw DAT/decks/logs, input/output hashes and versions are retained in [T003 evidence](docs/validation/T003.md).
- 6 cube, 8 bracket and 12 two-body faces map correctly after all Gmsh tags change; positive/negative CCX pressure on all 4 tetra faces matches consistent loads. Actual two-face total-force solve balances resultants/moments, including applied loads on support nodes.
- Unsigned `make benchmark CASE=B01` correctly exits 2; a unit test prevents accepting it. `uv lock --check` and diff checks pass. Final documentation/format checks also pass.

The owner selected **development-only; review later** for B01/B02. Formal T003 and F2/F3 acceptance remain open. [ADR-011](docs/adr/ADR-011.md) records planar synthetic geometry, affine C3D10/full-domain determinant bounds, frozen mapping thresholds and later curved/edited-geometry limitations. T004 subsequently proceeded by explicit request without claiming predecessor acceptance.

## T002 historical validation

Native implementation tested at `e104bf89684af994b73c2b75a4ac9da9c1edfbc0`, after T001 local commit `ed389d1`. Debian 13 x86_64; GCC/Fortran 14.2.0; Python 3.12.14; Node 24.19.0; npm 11.9.0; uv 0.12.23.

- Full `make setup` twice: exit 0; all six locks unchanged; verified native build reused.
- `make check`: lint, formatting, static types, 9 Python + 7 TypeScript unit tests, generated contract comparison and documentation links/task/status graph passed.
- `make build` and `make smoke`: compiled client and real HTTP startup checks passed.
- `make test-integration`: 4 passed; SIGTERM/restart, child failure/sibling cleanup, occupied-port refusal.
- `make test-e2e`: 2 Chromium health tests passed; real API connection and deliberate health-request abort.
- Required-native doctor / `make test-native`: 9 passed; three real native capabilities, three denied-network cases, missing/tampered solver failures and actual solve.
- `make native-report`: generated exact installed artifact/library/license inventory. Actual small DAT, transcript and result JSON are retained for review.
- T001's 6 failure-propagation probes remain historical evidence. Benchmarks/full security/reports remain BLOCKED and unrun.

Applicable T002/regression tests: **31 passed, 0 failed, 0 skipped**. Repeated runs are not added. CCX solved one free equation: ux2=0.001 m, sigma_xx=210 MPa at all four integration points, transverse stresses ~1.79e-7 Pa maximum and reaction residual ~1.04e-9 N. These pass unchanged, predeclared smoke tolerances; no release benchmark acceptance is claimed. [T002 evidence](docs/validation/T002.md) records the code commit, actual output, failures/corrections and limits. [T001 evidence](docs/validation/T001.md) remains historical.

## Handoff

M0 was **approved by the owner for M1 progression with explicit deferrals** after the historical NO-GO and PR #2 software fixes. Preserve all frozen criteria, native semantics and limits. The next gate work is exact benchmark/formulation review, M3 assembly validation and M4 local laptop/end-to-end acceptance. Current passing development suites do not establish those later acceptances.

Obtain engineering-owner B01/B02/B09/B07-mortar and formulation/scope acceptance with owner/date/criteria hash before claiming accepted benchmarks. Keep physical gaps unsupported until T019/B08. At M4/T030 reproduce conservative resource and headed browser measurements on the actual laptop and choose a supported cap; the reported 1650-class GPU does not remove that test. No 100k solve or arbitrary-model capacity promise is required. Rerun approved acceptance cases after records exist and close the M4 local gate only with actual evidence.

T007/T008 are COMPLETE with retained persistence and [real import/viewport evidence](docs/validation/T008.md). T009–T011 are now COMPLETE as recorded above. Next implementation is **T012**, NOT STARTED: core calculated result views. This session stops after the T011 PR. Native *TIE remains rejected; general/physical-gap/scalable assembly behavior, product editing, full viewer and later release/security/report features remain unvalidated.

All reviewed frozen manifests/locks/native binaries remain unchanged. Hosted CI passed on merged PR #1 before these follow-up fixes; target-hardware acceptance and final public redistribution approval remain unexecuted/deferred. No AWS, production secrets, private CAD or deployment. Cloud startup review draft was saved but not published; live processes are not retained.
