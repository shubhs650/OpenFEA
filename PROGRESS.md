# Progress and handoff

Updated: 2026-10-12
Current state: HEALTH BOOTSTRAP + REAL SYNTHETIC CAD/MESH/LOAD/SOLVE PIPELINE
Current milestone: M0 — F1 availability passed; F2/F3 development evidence exists, engineering acceptance open
Next action: T003 engineering-owner benchmark review; next implementation task T004

## Current objective

Fully working, validated LOCAL prototype through M4/T030. AWS deployment, Google authentication, commercial billing and beta operations remain outside this stage. T001/T002 are complete; T003 implementation is delivered with development-only diagnostics, and its signed acceptance is deferred by the owner. This session stops at T003.

## Implementation status

T001: COMPLETE
T002: COMPLETE
T003: IN PROGRESS
T004–T042: NOT STARTED
All M0–M6 exit gates: NOT RUN.
B01/B02: DEVELOPMENT PASS on two meshes each; owner-signed acceptance pending.
B03–B14: NOT RUN.
AWS price fit: NOT VERIFIED; outside this stage.
Project license: DEFERRED pending dependency/native review.

## What now works

The React/Vite page and FastAPI health API remain operational. T002 provisions CPU CCX 2.23 and separate OCP/OCCT, Gmsh/OCCT and VTK environments. T003 adds a real internal synthetic STEP→BREP→face-labelled triangles→Gmsh→C3D10/load/deck→CCX diagnostic workflow. Face IDs survive changed tags; missing/ambiguous identity and unsupported curved elements fail. Distributed force/pressure orientation, midsides, total resultants and moments are exercised by real tests. `make benchmark CASE=B01 DEVELOPMENT=1` (or B02) runs actual analytical diagnostics; unsigned acceptance fails closed. No application worker service, queue, user CAD/mesh/solve workflow, project persistence or reports exist.

Root/native dependencies are separately locked. Source/deb/wheel/runtime hashes and upstream license notices are recorded. Native processes receive a minimal environment, no network sockets, single-thread settings and resource limits. Full hostile-upload/filesystem isolation is not implemented. See [native setup](docs/NATIVE_TOOLS.md), [ADR-010](docs/adr/ADR-010.md) and the [dependency matrix](docs/DEPENDENCIES.md). Final public license remains deferred.

## T003 executed validation

Code commit `0dd94178d197c46d54f4762a36303395d4991101`; same pinned Debian 13/Python 3.12.14/native tools as T002. No dependency/lock changes or mocked solver behavior.

- `make check test-native`: 30 Python unit + 7 TypeScript unit + 23 native = **60 passed, 0 failed, 0 skipped**. Lint/format, static types, generated contracts and documentation graph pass.
- `make benchmark CASE=B01 DEVELOPMENT=1` and B02: both exit 0, two meshes (231/100 and 423/184 nodes/elements). These duplicate native cases and are not added to test count.
- B01 max displacement/stress error 5e-10 m/3.85 Pa; B02 4.99e-13 m/1.82e-7 Pa. Every component met its frozen development criterion. Raw DAT/decks/logs, input/output hashes and versions are retained in [T003 evidence](docs/validation/T003.md).
- 6 cube, 8 bracket and 12 two-body faces map correctly after all Gmsh tags change; positive/negative CCX pressure on all 4 tetra faces matches consistent loads. Actual two-face total-force solve balances resultants/moments, including applied loads on support nodes.
- Unsigned `make benchmark CASE=B01` correctly exits 2; a unit test prevents accepting it. `uv lock --check` and diff checks pass. Final documentation/format checks also pass.

The owner selected **development-only; review later** for B01/B02. Formal T003 and F2/F3 acceptance remain open. [ADR-011](docs/adr/ADR-011.md) records planar synthetic geometry, affine C3D10/full-domain determinant bounds, frozen mapping thresholds and later curved/edited-geometry limitations. No T004 work was started.

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

T003's remaining blocker is engineering-owner manifest review and signed rerun, deferred by explicit user choice. Record owner/date and reviewed criteria hash, rerun B01/B02 without development-only status, and close T003 only then. T004 is the next implementation task. Separate OCCT 8.0.1/7.8.1 kernels must remain isolated. T004–T006 still own production stress semantics, ties, cleanup and capacity; arbitrary edited/curved face mapping remains T013. The ~100k-element target is unmeasured. F1 availability passes; full M0 does not.

Hosted GitHub CI and Windows Chrome/Edge acceptance were not executed; browser evidence is headless Linux Chromium health only. Public redistribution remains blocked by deferred project/native license review. No live AWS resources, production secrets, private engineering data, deployment or merge was used.

Next session: review [T003 manifests/evidence](docs/validation/T003.md) and close acceptance when authorized; then implement **T004 only** when requested. Reuse current provisioning/locks/evidence, preserving numerical gates. No later task, deployment, push or merge was performed.
