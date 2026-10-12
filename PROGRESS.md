# Progress and handoff

Updated: 2026-10-13 (Asia/Calcutta)
Current state: HEALTH BOOTSTRAP + REAL SYNTHETIC CAD/MESH/SOLVE/STRESS/BOND EXPERIMENTS
Current milestone: M0 — F1 passed; F2–F5 development evidence exists with scope limits and owner acceptance open
Next action: T003–T005 review (B01/B02/B09/B07 + experimental mortar); next implementation task T006

## Current objective

Fully working, validated LOCAL prototype through M4/T030. AWS deployment, Google authentication, commercial billing and beta operations remain outside this stage. T001/T002 are complete; T003–T005 development implementations/experiments are delivered with engineering acceptance deferred. Explicit T004/T005 requests authorize bounded development while predecessor review remains open. This session stops at T005.

## Implementation status

T001: COMPLETE
T002: COMPLETE
T003: IN PROGRESS
T004: IN PROGRESS
T005: IN PROGRESS
T006–T042: NOT STARTED
All M0–M6 exit gates: NOT RUN.
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

## T005 executed validation

Implementation commit `698bb06e9524992e4a9087490692e3636dbe616b`. Restored native tools/locks reused; no dependency or solver-source change.

- `make doctor` passed real isolated operations and binary/library integrity. `make check test-native`: **111 passed, 0 failed, 0 skipped** (74 Python, 7 TS, 30 native); static checks, contracts and docs pass.
- `make benchmark CASE=B07 DEVELOPMENT=1` passes monolithic and both independently meshed mortar role cases. Unsigned B07 correctly exits 2. `uv lock --check`, final lint/docs/diff and retained artifact hashes pass.
- Native node-to-face *TIE,ADJUST=NO failed the original frozen axial patch despite full coverage: max stress error 183,365 Pa. Failure is retained; original manifest/tolerances are unchanged.
- A second predeclared formulation integrates quadratic interface virtual work and emits CCX *EQUATION. Same geometry/references/loads/sampling/tolerances pass both orientations: 231/423 independent body nodes, 37/65 interface nodes, no merging/fusing, 284 total C3D10 versus a separate 266-element monolith.
- Max mortar displacement/stress error 4.989e-13 m/9.439e-7 Pa; MPC residual≤1.21e-12 m. End ux=9.52381e-6 m in all printed cases. External force/moment balance passes; internal MPC forces are excluded from support reactions.
- Native-double binary geometry audits measure zero coordinate change in both role cases. Diagnostic 10 µm gap shows default native *TIE adjustment and zero with ADJUST=NO; supported preflight rejects the gap, so B08 is not claimed.
- Partial native surface leaves 61 nodes uncovered. Untied CCX returned exit 0/Job finished with ~9.79e9 m displacement; the supported path rejects detached bodies before solving. No stabilization is added. Actual nonzero CCX failures retain complete transcripts.

[T005 evidence](docs/validation/T005.md) and [ADR-013](docs/adr/ADR-013.md) retain frozen manifests, compressed inputs/outputs/meshes and the scientific decision. Experimental mortar is limited to zero-gap planar unit interfaces and ≤65 trace nodes per side; native *TIE remains an unsupported failed candidate. Owner B07/formulation acceptance is pending. No T006 work started.

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

T003–T005 acceptance blockers are engineering-owner B01/B02/B09/B07 and mortar-formulation review. Record owner/date and reviewed criteria hashes; close formal tasks only after those gates. Next implementation task is T006 when requested: cleanup and measured resources. Keep OCCT 8.0.1/7.8.1 isolated. General/scalable interfaces, physical gaps and broader connection loading remain unvalidated; native *TIE failed the patch and is not a validated fallback. The ~100k-element target is unmeasured. F1 passes; full M0 does not.

Hosted GitHub CI and Windows Chrome/Edge acceptance were not executed; browser evidence is headless Linux Chromium health plus the actual native stress diagnostic fixture. Public redistribution remains blocked by deferred project/native license review. No live AWS resources, production secrets, private engineering data, deployment or merge was used.

Next session: inspect T003–T005 evidence and pending reviews; implement **T006 only** when requested, preserving open gates and current scope limits. Reuse provisioning/locks and actual evidence. No later task, deployment, push or merge was performed.
