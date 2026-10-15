# Verification and validation strategy

The product owner acts as engineering reviewer. Coding agents implement tests but cannot invent reference results or approve their own adjusted tolerances after failure.

## Layers

1. Pure math: dimensional conversion, tensor invariants, shape functions, load resultants, currency ledger, geometry-reference validity.
2. Native integration: real CAD import -> real mesh -> real CCX -> parsed output. Do not substitute mock numbers.
3. Benchmarks: analytical solutions and appropriately licensed/referenced CalculiX, Code_Aster and ANSYS verification cases.
4. Application behavior: model revision, permissions, job failure/retry, cap, cancellation, retention, report/archive round trip.
5. Human usability: bracket setup after tutorial, bonded example, 3–5 testers, timed with compute excluded.

## Predeclare acceptance

Each benchmark manifest defines source/revision, geometry, material, units, exact load/supports, element formulation, mesh sequence, quantity and physical sample location, expected number/analytic formula, absolute and relative tolerances, exclusions, reason and reviewer sign-off before execution. A manifest hash and owner review record accompany accepted results. Values below are proposed starting limits, not approved or measured accuracy.
Change a tolerance only with a documented scientific reason and reviewer decision, rerunning affected suite. Model differences between ANSYS/Code_Aster and CCX must be explained; agreement between two solvers alone is not proof.

For B01/B02/B07-mortar/B09, non-development execution requires `reviewer_signoff` to be an object with `disposition: "APPROVED"`, a nonempty engineering-owner `reviewer`, an ISO `reviewed_on` date, and `criteria_sha256`. The hash is SHA-256 of the canonical JSON of every manifest field except `reviewer_signoff` (`sort_keys=True`, compact separators, no NaN). A pending string, empty/rejected/malformed record or hash mismatch refuses before creating a job. Record the actual owner's decision only after reviewing the exact criteria; the object is review metadata, not a cryptographic signature. Explicit `DEVELOPMENT=1` always labels output development-only, including when a valid review record exists. T024 subsequently records the actual owner approval of the exact B01–B09/B11/M3 packet and reruns acceptance; [approval/evidence](validation/T024-acceptance.md) retains that decision. Pending/rejected/stale records still refuse; historical development outputs are not relabeled.

## Proposed initial acceptance examples

- Dimensional conversions: relative error <=1e-12 for representative values and appropriate absolute tolerance near zero.
- Tensor derivation: <=1e-10 relative for well-scaled analytical tensors; symmetric eigenvalue ordering verified.
- Constant-strain patch: central stress/displacement <=0.1% after matching exact boundary conditions; numerical residuals scaled.
- Axial block: displacement and central stress <=1% vs analytical values away from constraints.
- Slender cantilever: tip displacement <=2% against an explicitly chosen beam theory after convergence; stress samples away from root singularity <=5%.
- Force/moment equilibrium: <=0.5% normalized residual with separately defined absolute floor; tighten where justified.
- Bonded vs monolithic reference: displacement <=2%, interior stress <=5%, and no missing intended tie nodes; interface-edge peaks excluded only by predeclared location, not hidden after testing.

These limits become executable fixtures during M0/M3 after assumptions are reviewed. Every release summary reports passed, failed, skipped and not-run cases. Skipped is never passed.

## Required adversarial cases

Missing/invalid material; zero-area selection; reversed pressure; force on two faces; unsupported STEP surfaces; tiny sliver; invalid BREP; duplicate faces; ambiguous face remap; overlapping bodies; too-large bond gap; unsupported constraint combination; detached body; singular solve; negative/NaN Jacobian; worker kill; duplicate queue claim; stale heartbeat; price change; expired estimate; resource/cap stop; browser closure; corrupted FRD/DAT; archive traversal/bomb; unauthorized object ID; expired artifact token; restore old backup after deletion; report from expired results.

## Evidence storage

Small synthetic fixtures and numerical summaries in tests/benchmarks and docs/validation/results. Large generated files ignored; attach only nonprivate artifacts to controlled CI storage when needed. Reports identify code commit, dependency hashes, backend, CPU/RAM, thread count, mesh nodes/elements and parser version. Freeze fixtures and run benchmark subset on every numerical change; full suite at milestone gates.

## M3 assembly gate command

`make benchmark-m3 DEVELOPMENT=1` runs the complete frozen B01–B09/B11 development subset sequentially. [M3 criteria](../tests/benchmarks/M3.json) bind all required benchmark criteria and formulation contracts; [T024](validation/T024.md) records actual errors/raw sources. A failure/resource stop preserves diagnostics and leaves later cases NOT RUN. Fresh output directories and source/manifest/tool identities are mandatory. Default acceptance execution (`make benchmark-m3 OUTPUT=<fresh-directory>`) requires valid exact-criteria owner records for every required case and the M3 scope before starting; DEVELOPMENT never becomes acceptance, even with approvals. Product regression review remains a separate exit requirement. See the [owner packet](validation/M3-owner-review.md) and [current exit disposition](validation/M3-exit-review.md). No agent-created sign-off or automatic milestone progression is permitted.
