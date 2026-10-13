# Product requirements — Cloud FEA prototype

Version 1.0 • 2026-10-12 • Product baseline agreed in interview.
Technical choices in ARCHITECTURE.md are recommendations to validate, not additional user promises.

## Purpose and users

Provide an approachable browser-based FEA workflow for mechanical engineers checking individual parts and simple bonded assemblies. Differentiate through understandable setup, inspectable engineering results, and eventually itemized usage pricing that covers infrastructure and an operating reserve. No assertion is made about competitors' current prices.
Primary users understand mechanics but have little FEA experience. Development is a lean solo effort using Codex Cloud through M4; the completed local application is validated at M4/T030 on the owner's Windows/WSL2 gaming laptop. The owner describes an i5 10th-generation-equivalent CPU and 1650-class GPU with 4 GB VRAM; exact RAM/SSD and OpenFEA performance require measurement. The local application must complete the full workflow without AWS or third-party accounts. AWS is a later backend direction subject to M5 gates.

## Delivery boundaries

- Local prototype: complete, validated engineering workflow; no billing or cloud dependency.
- Invite beta: 3–5 engineers, Google sign-in with explicit email allowlist, private individual projects, India-only application data storage and processing, ₹3,000 total monthly AWS budget target.
- Later paid service: itemized compute/storage/transfer plus disclosed platform margin; fund infrastructure and operating reserve, not an assumed salary or profit target. Payment collection is excluded from prototype/beta.
- Future direction, not commitment: thermal, nonlinear, shells, beams, broader CalculiX coverage.

## Requirements and acceptance

| ID | Requirement | Observable acceptance |
|---|---|---|
| R01 | Desktop Chrome/Edge on Windows; light default and dark option | Core workflow passes on both browsers; figures readable in light reports |
| R02 | Hybrid model tree and guided checklist | User can follow steps or revisit any valid setup; blockers explain next action |
| R03 | STEP solids, single or multi-body, target 1–10 bodies | Imported dimensions, units and body count shown for confirmation; surface-only inputs rejected clearly |
| R04 | Repair and user-selected hole/fillet removal | Preview, explicit apply, undo, validity checks; failed edit retains original; limited supported cases acceptable |
| R05 | Bond suggestions with review and manual face pairing | No bond active until confirmed; gap shown; overlaps rejected; small gaps require explicit tolerance approval |
| R06 | Isotropic linear elastic material library plus custom entries | Per-body E, nu, density; optional yield strength; sources and assumptions visible; invalid values rejected |
| R07 | Automatic quadratic tetrahedral meshes | Global and face/body local size, curvature refinement; quality feedback and resource estimate; target up to ~100,000 elements subject to measured memory |
| R08 | Bounded meshing recovery | At most two additional controlled attempts by proposed policy, within approved allowance; changes disclosed; no geometry deletion |
| R09 | Face-only loads/supports | Fixed, directional prescribed displacement, planar symmetry, uniform face pressure, distributed face force; body gravity |
| R10 | Direction controls | Global components or selected planar normal, straight edge, cylindrical axis; direction arrows and sign preview |
| R11 | Consistent selectable unit systems | mm–N–MPa, m–N–Pa, inch–lbf–psi presets; conversion changes display, not physical model |
| R12 | CalculiX linear static only | Small-deformation elastic solve; no automatic nonlinear switch, weak springs, or solver substitution |
| R13 | Multiple analyses per project | Shared immutable geometry revisions; independent materials, bonds, mesh and loading; analysis duplication |
| R14 | Safe edits and run history | Autosave with revision conflict handling, session undo; immutable run snapshots; uncertain geometry references invalidate setup |
| R15 | Engineering results inspection | Displacement/stress components, principal and von Mises stress, yield factor, reactions, extrema, deformation scale, probes, sections, contour ranges |
| R16 | Inspectable stress smoothing | Smoothed and unaveraged element-associated stresses identified correctly; no averaging across bodies/material discontinuities |
| R17 | Guided verification | Force/moment balance, mesh-refinement comparisons at defined locations; warnings for singularities, yielding and large displacement |
| R18 | PDF and editable Word reports | Same run and units, selected views, verification, warnings, user-written conclusions, snapshot identity |
| R19 | Portable archive and solver downloads | Export/import validated project archive; generated input and logs downloadable; no arbitrary input editing/upload-and-execute |
| R20 | Queued asynchronous compute | One mesh/solve execution at a time globally in beta; status persists across closed browser; cancellation |
| R21 | Estimate and spending approval | Mesh and solve each require estimate and max approval; reservation/watchdog enforced server-side; no cost approval for viewing/cleanup/reporting |
| R22 | Failure fairness | Modeling failures count as usage; platform failures credited; unclear causes reviewed; retry platform interruption once |
| R23 | Hosted access/privacy | Verified allowlisted Google identity; owner-scoped API and artifacts; no sharing/live collaboration; diagnostic bundle by deliberate user export |
| R24 | Retention and recovery | Large results expire 30 days after completion with warning/download opportunity; geometry/setup/run records remain; daily backups, up to 24 h data-loss target |
| R25 | Budget and residency | Individual allowances plus operator reserve; 24/7 project access with on-demand non-interruptible worker; India regional data including backups/logs |
| R26 | Open-source direction | Open-source components only; self-hostable; final distribution license deferred to dependency review |
| R27 | Learning and validation | Bracket tutorial; second bonded example; documented reference/analytical benchmarks with predeclared quantity-specific tolerances |

## First-use story

An engineer imports a bracket, confirms dimensions, assigns a sourced/custom material, selects mounting faces, applies a distributed force, previews a quadratic mesh, reviews checks, approves a solve, inspects displacement and stress away from singularities, refines the mesh, and exports a report. A short tutorial precedes the task. Target completion is about 30 minutes excluding computation and without live assistance. The second tutorial reviews and solves a bonded two-body support.

## Beta success and graduation

Required: benchmark suite passes predeclared tolerances; representative user models complete without unresolved critical errors; first-use task meets the 30-minute target; actual cost and runtime records support defensible estimates. Proposed measurement: at least 3 testers attempt the tutorial, record each result/time/help request, and at least 80% succeed (with 3–4 testers this requires all; with 5, at least 4). Product owner can revise this sampling rule before trials, not after seeing results.
Paid-service consideration requires all above plus at least three testers willing to pay the disclosed proposed rates. This is not authorization to build billing now.

## Non-goals

CFD; nonlinear contact/separation/sliding; plasticity; large-deformation analysis; thermal; dynamics/modal/buckling/fatigue; shell/beam/hex meshing; orthotropic materials; arbitrary CAD creation/face splitting; direct mesh editing; arbitrary CalculiX upload/execution; automatic design/code-compliance verdicts; phone/tablet support; collaboration; AI-generated engineering conclusions; automated parametric optimization; production SLA; commercial payment collection.

## Scope cuts and unresolved evidence

Preserve valid solving, bonded assemblies, core trustworthy results, privacy and cost controls. Defeaturing, Word output and advanced viewing controls may be explicitly deferred if required; record owner-visible scope exception before declaring release. The default plan still includes them. Do not silently reduce scope or label absent features complete.
License selection, exact validated dependency versions, reference-specific tolerances, memory/runtime limits, rates and AWS feasibility must be resolved through tasks. No fixed delivery date was agreed. See DECISIONS and FEASIBILITY.
