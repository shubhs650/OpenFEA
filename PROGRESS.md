# Progress and handoff

Updated: 2026-10-13 (Asia/Calcutta)
Current state: HEALTH BOOTSTRAP + REAL SYNTHETIC CAD/MESH/SOLVE/STRESS/BOND/CLEANUP/RESOURCE DIAGNOSTICS
Current milestone: M0 — EXIT REVIEW NO-GO; two software findings, owner/formulation and target-hardware acceptance open
Next action: correct M0-R1 approval handling and M0-R2 failed-stage graduation, then owner/target-hardware acceptance; T007 remains blocked

## Current objective

Fully working, validated LOCAL prototype through M4/T030. AWS deployment, Google authentication, commercial billing and beta operations remain outside this stage. T001/T002 are complete; T003–T006 development implementations/experiments are delivered with engineering acceptance deferred. Explicit T004/T005/T006 requests authorize bounded development while predecessor review remains open. T006 development is delivered; the subsequent M0 exit review remains NO-GO. No M1 implementation starts in this review.

## Implementation status

T001: COMPLETE
T002: COMPLETE
T003: IN PROGRESS
T004: IN PROGRESS
T005: IN PROGRESS
T006: IN PROGRESS
T007–T042: NOT STARTED
M0: EXIT REVIEW NO-GO — two software findings plus engineering and target-hardware acceptance open.
M1–M6 exit gates: NOT RUN.
B01/B02: DEVELOPMENT PASS on two meshes each; owner-signed acceptance pending.
B09: DEVELOPMENT PASS; engineering-owner review pending.
B07: Native *TIE candidate REJECTED; experimental mortar DEVELOPMENT PASS; owner review pending.
B03–B06, B08, B10–B14: NOT RUN.
AWS price fit: NOT VERIFIED; outside this stage.
Project license: DEFERRED pending dependency/native review.

## What now works

The React/Vite page and FastAPI health API remain operational. T002 provisions CPU CCX and isolated CAD/mesh/post environments. T003 provides real synthetic SI STEP→BREP→face-labelled triangles→Gmsh→C3D10/load/deck→CCX diagnostics. T004 adds raw DAT integration-point stress/COORD extraction, canonical tensors with source/entity/frame/material provenance, separately labelled native averaged FRD, element-owned extrapolation/probes, von Mises/principals, native VTK export and an interactive standalone material-jump fixture. `make benchmark CASE=B01 DEVELOPMENT=1` (or B02/B09) runs actual diagnostics; unsigned acceptance fails closed. No application worker service, queue, user CAD/mesh/solve workflow, project persistence or reports exist.

T005 adds a limited real mortar connection experiment using CCX *EQUATION and native coordinate audits. Native *TIE failed the patch and is not a validated fallback. `make benchmark CASE=B07 DEVELOPMENT=1` passes both role cases within the planar unit/65-node scope, retaining all failed-candidate and negative evidence.

Root/native dependencies are separately locked. Source/deb/wheel/runtime hashes and upstream license notices are recorded. Native processes receive a minimal environment, no network sockets, single-thread settings and resource limits. Full hostile-upload/filesystem isolation is not implemented. See [native setup](docs/NATIVE_TOOLS.md), [ADR-010](docs/adr/ADR-010.md) and the [dependency matrix](docs/DEPENDENCIES.md). Final public license remains deferred.

## M0 exit-gate review

Reviewed commit `bc6af0041d8a6ef51b1ae5b100c3420708bd704d`, 2026-10-13 Asia/Calcutta. **NO-GO**. [Full review](docs/validation/M0-exit-review.md) and [retained review artifacts](docs/validation/results/M0/index.json) record source findings, current checks, manifest packet, analytical-reference assessment and exit actions. This is not engineering-owner approval; statuses remain authoritative.

- `make doctor check test-native build smoke test-integration test-e2e`: exit 0; **123 passed, 0 failed, 0 skipped** (74 Python, 7 TS, 34 native, 4 lifecycle, 4 Chromium). Build/startup/contracts/static/docs checks pass. Two extra real retained-data resource-browser replays pass; renderer is SwiftShader, not target GPU.
- M0-R1 (P1): approval means “not prefixed PENDING”. An empty in-memory B01 sign-off permits real non-development execution and a `PASS` label. No reviewer/date/approval exists; actual frozen files are unchanged. The ordinary PENDING guards work, but invalid/rejected/stale approval handling needs a shared fail-closed validator and regressions. Probe results are never acceptance evidence.
- M0-R2 (P2): failed preparation/solve/post stops the stage loop but later workload meshes still start. Controlled real native exit-7 preparation reproduced all three nominal workload attempts using tiny meshes. Stop the entire ladder, persist failure and test that later jobs are not launched. No tolerance/native-limit change or automatic coarsening.
- **1,090** inventory/runtime/library/license/lock hashes, **29** key retained/current-manifest/source hashes and **99** T006 artifact byte counts/hashes pass. Four independent reference calculations match B01/B02/B07-mortar/B09; proposed acceptance still requires owner/date/criteria-hash records and approved reruns.
- F1/inventory and limited F6 feasibility supported; F2/F3/F5 development-only; F4 alternative-formulation/scope review open; F7 needs software correction plus actual WSL2 conservative capacity/headed integrated-GPU evidence. 100k solve is unrun by policy, not a forced M0 capacity guarantee. Resolve the F4 zero-gap-versus-T019/B08 boundary explicitly with the owner.

This review records the two code defects; it does **not** implement their fixes, invent approval, close T003–T006/M0 or start T007. Public license, later release/security/report/hosted CI and AWS/beta are separate unexecuted/deferred gates. Saved startup instructions retain the NO-GO outcome without publication.

## T006 executed validation

Native implementation `d18901a3c2c6bfa4867dc0e3803cdeaddf318409`; child-reaping/browser provenance refinement `c490b21c4035bcb5e337e3c357140d09d3b2113a`. [T006 evidence](docs/validation/T006.md) retains measurements, raw sources, compressed artifacts, hashes, explicit omissions and the F1–F7 review. [ADR-014](docs/adr/ADR-014.md) records material scope/resource decisions.

- Real OCCT selected through-hole and single-edge fillet removal on deep copies produces valid new preview BREP/catalog/tessellation revisions. Analytic volume deltas pass; source hashes are unchanged on success and stale/unsupported selections. Each preview remeshes with six new face references and actual C3D10 elements. General cleanup/apply/undo/remapping remains T013.
- `make check`: 74 Python + 7 TS pass. `make test-native`: 34 pass, 0 failures/skips; changed cleanup/watchdog cases rerun after lifecycle correction also pass. Distinct unit/native total **115**. Doctor, static/docs/root-lock and artifact-integrity checks pass. No dependency/solver changes.
- `make feasibility MESHES=1`: actual 4,891/27,155/99,198-element meshes. Small and medium patches solve 15,219/93,978 free equations with unchanged B01 criteria: max U error ~5e-10 m, tensor error 3.846 Pa. Medium solve 49.858 s/792.12 MiB native maxRSS. Large meshing 19.287 s/501.16 MiB; large solve is NOT RUN due to explicit admission cap, with no automatic coarsening.
- Actual allocation/disk probes verify guarded stops, recorded sampling overshoot, nonzero exits and no host OOM. Cloud `/proc` child discovery and orderly reaping were corrected; native hard limits remain intact.
- Two actual exterior WebGL/native-field checks pass with 60 rotations, field switches and inspected screenshots. Renderer is SwiftShader; 27,155-cell mesh draws 18,544 exterior triangles with median animation interval 42.4 ms. Integrated-GPU/Windows and total browser RSS acceptance remain unrun.
- F1–F7 reviewed. Limited F6 scope is explicit. Highest cloud patch solve does not establish a laptop cap or arbitrary 30k-model capacity; start target calibration conservatively at ≤5k cells. F4/physical-gap/formulation and earlier owner reviews remain open. No M0 closure or milestone exception.

T006 CLI development work is delivered; formal status stays IN PROGRESS for target hardware and owner review. T007 is next, not started. No application workflow, deployment, push or merge was added.

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

M0 exit decision is **NO-GO**. First correct **M0-R1** invalid benchmark approval handling and **M0-R2** graduated workload failure sequencing with focused regressions. Preserve all physical criteria, actual native semantics and limits. The implementation/evidence reviewed remains useful within its declared synthetic scope; current passing suites do not establish a passed milestone.

Then obtain engineering-owner B01/B02/B09/B07-mortar and formulation/scope acceptance with owner/date/criteria hash, including an explicit disposition of the F4 small-gap overview versus planned T019/B08. Reproduce resource/headed display on the existing 16 GiB WSL2 laptop/integrated GPU and choose a conservative measured cap. No 100k solve or arbitrary-model capacity promise is required. Rerun approved acceptance cases after records exist and repeat the gate decision, or record a specific product-approved scope exception with disabled features/deferred deliverables.

Next implementation task is **T007**, still NOT STARTED and blocked by M0. Review request does not authorize milestone advancement. Native *TIE remains rejected; general/physical-gap/scalable assembly behavior, product editing, full viewer and later release/security/report features remain unvalidated.

All reviewed frozen manifests/locks/native binaries remain unchanged. Hosted CI, target-hardware acceptance and final public redistribution approval are unexecuted/deferred. No AWS, production secrets, private CAD, deployment, push or merge. Cloud startup review draft is saved but not published; live processes are not retained.
