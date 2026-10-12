# Decision register

## Settled product decisions

Mechanical engineers; single parts and bonded assemblies; linear static; 3D solids; STEP only; repair plus selected defeaturing with limited supported release acceptable; auto bond suggestions and review; approved small gaps, reject overlaps; quadratic tetrahedra and local sizing; essential face loads/supports plus gravity; isotropic library/custom materials; consistent selectable units; global/geometric directions; no face partitioning; hybrid workflow; desktop Chrome/Edge Windows; light/dark; inspectable stress contours and verification; PDF/Word; multiple analyses; autosave and immutable run snapshots; portable archives; generated solver download only.

Local fully working on Windows WSL2, existing 16 GB laptop. CalculiX fixed, only open-source components, final license deferred. Invite beta 3–5, private individual projects, Google allowlist, one queued job at a time, results expire after 30 days, daily backup/up to 24 h loss, India-only, 24/7 access with cold-start worker, non-interruptible compute, ₹3,000 total AWS target, individual allowances plus reserve. Platform failure credit/one retry; modeling failures charged. Mesh/solve cost approval and cap. Future itemized usage plus overhead/reserve; no paid-service build until evidence and three willing testers.

## Technical recommendations requiring evidence

| Decision | Owner / resolution point | Current status |
|---|---|---|
| Exact toolchain and binding versions | Developer, T001–T002 | T001/T002 pins and local availability accepted in ADR-009/ADR-010; mapping/stress/tie compatibility remains later gates |
| Face-remap algorithm and valid confidence criteria | Developer + engineering owner, T003/T013 | Synthetic planar one-to-one mapping proven in T003 diagnostics/ADR-011; arbitrary/edited geometry and owner acceptance open |
| CCX tie keywords/adjustment behavior | Engineering owner, T005/T019 | Native *TIE fails unstructured C3D10 patch; default adjustment measured. Experimental consistent *EQUATION mortar passes zero-gap B07 scope; owner/general/gap review open (ADR-013) |
| Raw element stress output path | Developer + engineering owner, T004 | Native DAT global S/COORD and element-owned extrapolation/probes proved diagnostically; FRD averages labelled separately; B09 review pending (ADR-012) |
| Material nu range, mesh quality and gap limits | Engineering owner, M0/M3 | Proposed, validate |
| Benchmark-specific tolerances/cases | Engineering owner, before each benchmark run | B01/B02/B09 and B07 mortar development cases pass; original B07 native tie is retained as failed. No tolerances widened; engineering review deferred; other cases unrun |
| Practical element/memory/runtime ceiling | Developer, T006 | Measure first |
| AWS capacity/rates/fixed-cost fit | Operator, T033 before deployment | Not priced |
| Region choice within India | Operator, T033 | ap-south-1 candidate |
| Final open-source license | Owner after audit, T002/ADR-006 | Deferred, public redistribution blocked |
| Working title / product branding | Owner before public launch | Not required for prototype |

## Change discipline

For the current development stage, the owner has authorized a fully validated LOCAL prototype through M4/T030. AWS deployment, Google authentication, commercial billing and beta operations are excluded. This does not remove those later product requirements; it bounds current implementation work. T001 uses the accepted [health bootstrap decision](adr/ADR-009.md).

Use ADRs for technical changes. Record product changes with rationale and affected requirement IDs. Convenience cuts are allowed directionally by the user, but document which features are deferred before declaring a release. Never remove numerical validation, private ownership or spending controls as convenience cuts.
