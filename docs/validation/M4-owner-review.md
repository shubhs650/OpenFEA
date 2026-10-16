# M4 exact engineering review packet

Status: **PENDING**. Prepared at the owner's request; no approval or final acceptance is inferred. Existing [M3 exact owner approval and ten acceptance cases](T024-acceptance.md) remain unchanged. The new [M4 manifest](../../tests/benchmarks/M4.json) binds those records, four new reference criteria, ADR-035 resilience and the T028 source interpretations. `make m4-review` regenerates manifest/criteria/source hashes without launching native jobs.

| Record | Exact criteria SHA-256 (all fields except reviewer_signoff) | Owner disposition |
|---|---|---|
| B10 | `c294e683af0b82c23bce2fe2f657653b1f4723b70890f19d63525853154b559f` | PENDING |
| B12 | `7f88016857b446409c850cc3bb19dd775163d07f506f83de3d570490b118ffe0` | PENDING |
| B13 | `7b8e720ae1a9b15efb561b616f207e03c466e8b77b1e54fd11842a34bb3df481` | PENDING |
| B14 | `bf3bd3d0a5e5c526878ceb05c8371c092368f2249971c1b240a540e9b5c080e0` | PENDING |
| M4 | `0eb86b2890ab4c9cd79be434f292d8b7637e0f616c8370dbdb7cad1745717d73` | PENDING |

Review the complete manifest, not just this table. [T028 source interpretations/rights](T028-sources.md) and [measured numerical results](T028.md) explain the following:

- B10: three straight-sided fillet-approximation meshes; same physical tip/interior quantities; final-pair displacement/stress change ≤2%/5%, with unchanged equilibrium. No exact bracket peak target or curved product-solve claim.
- B12: Code_Aster SSLV001 affine continuum reconstructed in original C3D10; every nodal displacement/native tensor compared, 0.1% relative with declared absolute floors. External executable not run.
- B13: Code_Aster SSLV07 quadratic gravity/traction continuum; quarter-symmetry equivalence, published SI ambiguity and all-node/IP error floors explicitly reviewed. External executable not run.
- B14: ANSYS VM28 tapered square bar reconstruction; displacement ≤2%, interior stress ≤5%; changed element/mesh, sample ranges and published-value differences disclosed. No proprietary deck/manual redistribution or fresh ANSYS run.
- M4: retain bounded M3 physics, no new tolerance or native-budget change, explicit pending actual laptop/headed/capacity/human evidence and final owner exit review. Development numerical replays cannot grant acceptance.

Approval must name the actual engineering reviewer, date, exact criteria hash and disposition, followed by a fresh acceptance-mode replay. A merged PR or the owner's instruction to prepare a pending packet is not that approval. Do not change existing approved M3 manifests. The [local acceptance instructions](../LOCAL_ACCEPTANCE.md) describe the actual laptop/browser/human procedure and final exit decision.

## Requirement review

This maps implemented paths to evidence and restrictions; it does not mark the overall core gate complete while actual R01/R27/owner checks remain pending. No convenience deferral is newly requested. Existing accepted engineering restrictions remain prominent; they are not a claim that arbitrary PRD target capacity or general assemblies work.

| PRD requirement | Implemented local path / review evidence | Restriction or remaining acceptance |
|---|---|---|
| R01 | Themes, keyboard/workspace and full workflow Chromium tests, T017/T025–T030 | Actual Windows installed Chrome/Edge headed run and laptop renderer/performance PENDING |
| R02 | Guided checklist/model tree, [safe edits](../WORKSPACE_EDITS.md), blockers | Final human learnability trial PENDING |
| R03 | Confirmed native STEP units/dimensions/body topology, [import](../STEP_IMPORT.md) | Valid solid import; no claim of 1–10-body solved assembly capacity |
| R04 | [Cleanup](../GEOMETRY_EDITS.md), preview/apply/undo/reference invalidation | Only the declared simple hole/straight fillet cases |
| R05 | [Connections](../CONNECTIONS.md), [assembly preflight](../ASSEMBLY_PREFLIGHT.md), T019/T020/M3 | Two bodies, one full axis-aligned zero-gap unit-square interface, ≤65 trace nodes/side; gaps/general contact/multibond solves blocked |
| R06 | [Materials](../MATERIALS_UNITS.md), immutable per-body source snapshots | Isotropic linear elastic; examples require user confirmation; missing density/yield blocks dependent checks |
| R07–R08 | [Mesh controls](../MESH_CONTROLS.md), actual C3D10 quality/explicit bounded recovery | Product ≤3,000 elements affine/planar solve; curved preview only; 100k is not supported solve capacity; actual laptop capacity PENDING |
| R09–R10 | [Essential loads](../ESSENTIAL_LOADS.md), [directions](../GEOMETRY_DIRECTIONS.md), B01–B06 | Face supports/pressure/force, gravity and declared geometric bases; uncertain mappings block |
| R11–R12 | Canonical SI/presets, generated deterministic CCX decks and native checks | Small-deformation static C3D10 only; no stabilization, nonlinear switch or arbitrary executable upload |
| R13–R14 | [Independent analyses](../ANALYSES.md), immutable history, autosave/conflict copies/undo | Undo is session bounded; geometry changes require explicit engineering reassignment |
| R15–R17 | [Results/verification](../CORE_RESULTS.md), T021–T024 tests and M3 acceptance | Raw node/IP extrema vs derived contour/smoothing explicit; no cross-body/material smoothing, automatic convergence or design-safety certification |
| R18 | [PDF and editable Word](../REPORTS_EXPORTS.md), T025/T026 native render/content/layout QA | Generated paragraphs/tables editable; figures embedded; actual laptop Office open/edit/reopen PENDING |
| R19 | T027 archive round-trip/native revalidation/privacy/security and original deck/log downloads | Imported original history inert; no arbitrary input execute; bounded archive sizes/counts |
| R20 | [Local jobs](../LOCAL_JOBS.md), real process/restart/cancel/retry tests T011/T029 | One active local job; 180 s original deadline, 60 s native limit, one eligible infrastructure retry; no unbounded retries |
| R21 | Hosted estimate/reservation/spending model deferred by explicit local-only objective | M5; no local billing/spending-control claim |
| R22 | T029 failure classification and bounded infrastructure retry | Hosted credits/fairness/operator review are M5; failures never imply successful engineering output |
| R23 | Local loopback sessions/ownership, private artifacts, deliberate diagnostic export | Google allowlist/hosted isolation acceptance are M5 |
| R24 | Persistent local records/restart and manual portable archives | Hosted 30-day expiry/backup/restore service remains M5; choose durable local data root and retain exports |
| R25 | No AWS resources or deployment in local objective | India regional operations/budget remain later gated scope |
| R26 | Locked open-source dependency inventory/native source build, self-hostable local source | Final redistribution license remains deferred; no public release declaration |
| R27 | [Both tutorials](../TUTORIALS.md), fourteen frozen analytical/reference cases | New four exact owner approvals and rerun, 3–5 consented-human trial, final engineering review PENDING |

## Exit record (to be completed from actual evidence)

| Required record | Current disposition |
|---|---|
| Existing ten M3 exact approvals | APPROVED historically; unchanged |
| New B10/B12/B13/B14 exact criteria and M4 scope | PENDING |
| Fresh all-required acceptance-mode replay after approvals | BLOCKED before native execution |
| Actual target-laptop WSL2 full gate and headed Windows Chrome/Edge | NOT RUN |
| Measured CPU/RAM/scratch/renderer and supported local capacity | NOT RUN |
| Consented human trial, bracket ≥80% success within 30 minutes excluding compute | NOT RUN |
| Engineering owner's final M4 decision / closure of M0 exception | PENDING; M4 NO-GO |
