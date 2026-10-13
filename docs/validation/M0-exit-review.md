# M0 exit-gate review — NO-GO

Date: **2026-10-13, Asia/Calcutta**. Reviewed repository commit: `bc6af0041d8a6ef51b1ae5b100c3420708bd704d`. Scope: local M0/T001–T006 feasibility, actual code, frozen manifests, retained native outputs and current-instance checks. This is a software/evidence review, not engineering-owner sign-off.

**Decision: M0 does not pass its exit gate.** Two reproducible software defects require correction. Engineering benchmark/formulation approval and target-laptop/integrated-GPU evidence remain missing. Keep T003–T006 IN PROGRESS and T007 NOT STARTED. No M1 advancement or product-approved scope exception is inferred from this review request.

## Findings, in priority order

### M0-R1 — P1: empty or rejected sign-off can authorize a benchmark

At [benchmark.py](../../services/worker/worker/benchmark.py#L76), approval is the negation of `reviewer_signoff.startswith("PENDING")`. An empty string, whitespace or a rejected disposition therefore qualifies as approved. [bond_fixture.py](../../services/worker/worker/bond_fixture.py#L262) repeats the rule. [stress_fixture.py](../../services/worker/worker/stress_fixture.py#L121) also permits non-development execution for those invalid values, although its summary continues to say development-only.

The review probe injected **only an empty in-memory sign-off** into the loaded B01 metadata and invoked `run_case(..., development=False)`. It executed the actual two-mesh CAD/Gmsh/CCX pipeline, created the job directory and returned **`status: PASS`**, without a reviewer, date or approval. All tracked manifests, physics, sampling and tolerances remained unchanged. The result is an intentionally invalid approval diagnostic, never accepted benchmark evidence. [Reproduction and result](results/M0/signoff-probe-result.json) record the violation. The normal pending manifests correctly refuse all four non-development commands before job creation; this narrower success does not cover invalid approval metadata.

Required resolution: one shared fail-closed approval validator with an explicit approved disposition, reviewer/date and a review record bound to the exact reviewed criteria hash. Pending, empty, rejected, malformed and stale approvals must refuse before creating a job; valid development diagnostics must stay labelled development-only. Do not fabricate an approval, change tolerances or promote the probe's `PASS` to acceptance. Add regressions for all rejection forms and the correctly bound approved path. Owner-approved acceptance runs must execute after their approval record exists, as required by [VALIDATION.md](../VALIDATION.md).

### M0-R2 — P2: resource graduation continues after a failed stage

At [feasibility.py](../../scripts/native/feasibility.py#L108), a preparation/solve/postprocessing failure breaks only the inner stage loop. The enclosing workload loop then starts the next mesh. Mesh-stage failure stops the outer loop correctly, so current tests of individual RSS/disk stops do not catch this distinction. It contradicts the frozen T006 policy: “Stop on stage failure; no retries or automatic coarsening.”

The controlled probe kept **real native Gmsh meshing** and replaced preparation with an actual bounded native child exiting 7. It used h=0.6 tiny meshes for all nominal directory labels to verify sequencing safely; it is **not** a 5k/25k/100k capacity experiment. After the first preparation failed, meshing and failing preparation ran for both later workload directories. The command eventually returned 2, so failure is not reported as success, but graduation still happened. [Actual call trace](results/M0/stop-probe-result.json) and [reproduction source](results/M0/stop_probe.py) preserve the evidence; no solver-result numbers were mocked or added as a feature.

Required resolution: persist the failed workload/transcript and stop the entire sequence on every native/resource stage failure. Later workloads must be recorded as not run. Add regressions for preparation, solve, postprocess and resource stops, ensuring no subsequent mesh job is launched and the command stays nonzero. Keep explicit coarsening/admission stops distinct from genuine stage failures. Do not loosen limits or silently retry.

## Gate-by-gate disposition

The [M0 contract](../plan/M0.md) requires F1–F5 native evidence, explicit F6 cleanup scope, measured F7 capacity and a license inventory. [Feasibility definitions](../FEASIBILITY.md) and task-specific acceptance also apply.

| Gate | Technical evidence reviewed | Exit disposition |
|---|---|---|
| F1 toolchain | Current doctor and native smoke pass; CCX/runtime hashes and separated CAD/mesh/post operations verified. Installed native/library/license/lock inventory: **1,090 hash checks, no mismatch**. | **PASS for local availability and inventory.** Public redistribution/project-license selection is a separate deferred gate. |
| F2 geometry identity | Cube, planar bracket and two separate bodies; revision-bound face catalog survives tessellation/import/tag reordering. Missing/ambiguous/stale mappings fail. | **Development pass in planar synthetic scope.** Owner acceptance remains pending; no claim for arbitrary/edited curved CAD. |
| F3 C3D10/traction | Independent midside/face permutation, full-domain Jacobian bound, real ±pressure on all four faces, selected-set force/moment and B01/B02 on two meshes pass. | **Development pass.** Formal benchmark acceptance blocked by absent owner review and M0-R1. |
| F4 independent bonding | Original native *TIE still fails unchanged B07 criteria. Experimental consistent mortar *EQUATION passes both roles against separate monolithic/analytical references, complete coverage and zero native coordinate movement. | **OPEN.** Owner must accept the alternative and exact zero-gap/unit/≤65-trace-node scope. General interfaces/loading/scalability and physical gaps are unvalidated. |
| F5 stress provenance | Full raw DAT S/COORD; canonical order; averaged FRD separately labelled; derived element-owned fields/probes; VTK round-trip and actual material-interface browser pass. | **Development pass.** B09 owner review and approval handling remain open. Product viewer/full application are later milestones. |
| F6 cleanup | Native OCCT deep-copy defeaturing of a simple through-hole and straight-edge fillet; valid preview, analytic volume deltas and unchanged source bytes on success/failure; remeshed new revisions. | **Limited feasibility requirement supported.** Only these synthetic features are proven. General cleanup/apply/undo/remapping is T013, not an implemented product feature. |
| F7 capacity/display | Retained actual 4,891/27,155/99,198-element meshes; first two real patch solves; real memory/disk stops; fresh small/medium exterior display replay classifies SwiftShader. | **INCOMPLETE.** Fix M0-R2; measure a conservative cap on the actual 16 GiB WSL2 laptop and run headed integrated-GPU/Windows display. Cloud success and software rendering cannot supply those results. |
| License inventory | Native component/source/backend/wheel/license records exist; runtime files match. Open-source-only choices, final redistribution obligations expressly deferred. | **Inventory requirement supported.** Do not make public licensing approval an invented M0 local-development prerequisite. |

The 100k **solve** remains unrun by deliberate admission policy. This is a limitation, not a requirement to force an OOM or guarantee 100k capacity: F7 explicitly permits a measured lower cap. The missing evidence is a justified **target-laptop** cap and target display, plus the failed-stage policy defect. No GPU device is available here; Chromium reports SwiftShader.

There is a scope ambiguity to resolve explicitly: F4's overview mentions an approved small-gap experiment, while T005 requires the zero-gap patch and B08 is scheduled for T019. Recommended disposition is to keep physical gaps disabled until T019/B08 and record the owner's acceptance of a zero-gap M0 proof, or perform the broader experiment if the owner requires it before exit. This review makes neither choice on the owner's behalf. Larger/general assemblies also require later validation; passing the present axial patch is not permission to enable them.

## Independent engineering assessment

The review recomputed the physical references independently from the manifests, without changing them:

- B01: symmetrized displacement gradient and isotropic Hooke law reproduce native-order `[210e6, 0, 0, 32.307692e6, -16.153846e6, 24.230769e6]` Pa. The prescribed exterior affine field leaves real interior equations free. A constant-strain patch does not require a singular-peak convergence claim.
- B02: F=1e6 N, A=1 m², E=210 GPa, L=1 m give σxx=1 MPa and end ux=4.7619047619e-6 m. Relaxed axial/three rigid-mode constraints allow lateral contraction, matching the reference instead of introducing clamped-end effects.
- B07-mortar: the separate L=2 m monolith gives end ux=9.5238095238e-6 m and σxx=1 MPa. Both independently meshed roles reproduce those smooth patch values. Full quadratic trace inclusion and virtual-work checks support this limited experiment; they do not establish bending, arbitrary gaps or scalable general assemblies.
- B09: εxx=0.001 with common ν=0.3 yields 210/70 MPa across the two materials. The interface normal is z, so the differing σxx is tangential and both interface tractions are zero. The continuous affine displacement with a stress jump is physically consistent; the fixture proves output semantics rather than mesh convergence.

Frozen componentwise tolerances, absolute floors and equilibrium definitions were inspected. No scientific inconsistency was found in these reference formulas for their stated scopes. This assessment supports presenting them to the engineering owner; it does not invent owner sign-off. These native reference fixtures use ν=0.3; the proposed general ν=0..0.45 material policy is not validated across that range by these tests and must not be advertised as accepted without further evidence/scope disposition. Fresh maximum errors remain B01 5e-10 m/3.846 Pa, B02 ~4.989e-13 m/~1.819e-7 Pa and B09 ~4.459e-7 Pa. The native tie candidate's ~183,365 Pa error versus 1 MPa is a retained failure. Proposed B01/B02 relative limits are 0.1%/1%; B07 mortar displacement/stress limits are 2%/5%, with 0.5% equilibrium and explicit absolute floors. They have not been widened.

Exact manifest hashes, scopes and current pending dispositions are in the [review summary](results/M0/summary.json). The owner should review these records and ADR-011/012/013/014, record accepted or rejected decisions with owner/date/hash, and rerun the selected acceptance cases after M0-R1 is fixed. Historical development results remain labelled development-only.

## Executed checks and evidence integrity

Command at the reviewed commit, exit 0:

```sh
make doctor check test-native build smoke test-integration test-e2e
```

**123 automated cases passed, 0 failed, 0 skipped:** 74 Python unit, 7 TypeScript unit, 34 native, 4 lifecycle integration and 4 Chromium cases. Native coverage includes B01/B02/B07/B09, retained rejected-candidate behavior, uncovered/singular/gap-adjustment cases, corrupted results and actual cleanup/watchdog stops. Rejected cases are asserted negative tests, not successful engineering solves. The build, real startup/proxy smoke, types/lint/format, API contracts and documentation graph also pass. [Transcript](results/M0/checks.log).

Two standalone resource-browser checks also pass on separately extracted **retained real native data**; no large solve was rerun. Both exercise rotation/field switching/source identity/pixel changes and have zero page errors. Fresh renderer: Chromium 156.0.8078.4 / ANGLE Vulkan SwiftShader. Small/medium median animation intervals are ~16.7/21.5 ms in this instance; these observations differ from historical cloud measurements and do not replace target-hardware acceptance. Screenshots were inspected. Browser reports/screenshots are retained without duplicating the bulky field payload already committed in T006.

Read-only evidence integrity:

- **1,090** native library/license/lock/source checks match the T002 inventory and current runtime; no inventory regeneration or dependency upgrade.
- **29** important retained B01/B02/B09/B07 manifest/deck/DAT/FRD/field checks match their summaries and current frozen manifest hashes.
- **99** T006 retained artifact byte counts/hashes pass after lossless decompression. Its **15** explicitly omitted workspace-only entries are not claimed as committed proof.
- Four independent analytical-reference calculations match the frozen values; four actual currently-pending non-development commands refuse before creating jobs. These checks do not conceal the invalid-sign-off finding.
- No tracked source, solver, manifest, tolerance or lock changes during review. Root lock validation and final docs/diff checks pass. Code fixes are **not implemented by this review**; the reproduced defects stay open. Startup instructions were saved as a review draft, not published.

Unrun or outside M0: target WSL2/Windows Chrome/Edge/integrated GPU, large solve, approved physical-gap benchmark, later B03–B06/B08/B10–B14, full application/security/report/release suites and hosted CI. Security checks applicable to the present bootstrap/native boundary executed; unsupported ownership/archive/report features are not marked passed. Full release benchmark/security/report Make targets remain explicitly blocked. AWS pricing/F8, deployment, auth, billing and beta are outside this local stage. Final public license remains deferred.

## Concrete exit actions

1. Correct M0-R1 and M0-R2 with focused regressions; preserve every frozen physical criterion and native limit. Do not begin T007 as a substitute for fixing the gate.
2. Obtain owner disposition of B01/B02/B09, the B07 mortar alternative and the supported F4/F6 scope, with owner/date/criteria-hash evidence. Keep the rejected native *TIE candidate rejected. Resolve the small-gap M0/T019 boundary explicitly.
3. Reproduce conservative resource and headed browser diagnostics on the existing laptop. Record available WSL2 RAM/CPU, node/DOF counts, per-stage RSS/runtime/scratch, failure/admission/coarsening behavior and actual GPU/browser renderer. Set a measured lower cap with headroom; no linear bytes-per-element promise or forced 100k solve.
4. Rerun affected diagnostics and the approved acceptance subset, verify retained evidence, and repeat the M0 decision. Only then close dependent tasks/M0, or record a specific owner-approved exception with deferred deliverables and disabled features.

Next implementation ID remains **T007**, blocked by M0. No later task, deployment, push, merge, private CAD or production secrets were used. Review findings, not a false completion flag, are the handoff.

## Subsequent software correction (2026-10-13)

This document records the original NO-GO review at `bc6af004`; its reproduced failures and retained artifacts are historical. M0-R1 and M0-R2 now have focused code fixes and regressions. Non-development benchmark execution requires an explicit owner/date/disposition record bound to the exact criteria hash; all committed records remain pending. The native workload ladder now persists a failed stage, marks later workloads not run and returns nonzero. Real bounded-child regressions cover mesh, prepare, solve, post and RSS stops. The full current local check command passed 147 distinct automated cases (90 Python unit, 7 TypeScript unit, 42 native, 4 lifecycle and 4 Chromium) with none failed or skipped. See [PROGRESS.md](../../PROGRESS.md) and [VALIDATION.md](../VALIDATION.md). **The M0 decision remains NO-GO** because engineering/formulation approval, target WSL2/integrated-GPU evidence and a repeated exit review are still pending.

## Subsequent owner decision (2026-10-13)

The product owner then [approved M0 progression under explicit deferrals](M0-owner-decision.md). This later decision supersedes the historical NO-GO for starting M1, while keeping exact benchmark sign-offs and M4 laptop validation pending. Nothing in the original review or its evidence was retroactively reclassified as accepted benchmark output.
