# Cloud FEA prototype — development starter kit

Planning baseline: 12 October 2026. Working title only; no product name or domain has been chosen.
This repository contains a real STEP import/vtk.js geometry workspace, a persistent local project/analysis metadata API and real synthetic CAD/mesh/load/CCX/stress/bond diagnostics. T005 rejects a failed native tie candidate and proves an experimental consistent mortar connection on a limited planar patch. B01/B02/B09/B07 development evidence exists; T006 adds limited immutable native cleanup and measured cloud meshes/solves/display. The owner approved M0 progression with exact benchmark and laptop validation deferred. T008 provides real unit-confirmed solid import, private artifacts and stable face picking; the complete engineering analysis workflow remains future work.
The current objective is the validated LOCAL prototype through M4/T030. AWS deployment, Google authentication, commercial billing and beta operations are outside this stage.

## Run the bootstrap

See [development setup](docs/DEVELOPMENT.md), [local project API](docs/PERSISTENCE.md) and [native setup](docs/NATIVE_TOOLS.md). Run `make setup`, `make check`, `make test-native`, then `make dev`. The UI now creates/opens projects and imports selectable solid STEP. See the [import guide](docs/STEP_IMPORT.md); material editing is available in the [materials/units guide](docs/MATERIALS_UNITS.md); [saved face loads and checked coarse deck export](docs/LOADS_DECKS.md) are available; [durable local mesh/solve jobs](docs/LOCAL_JOBS.md) are available; [core calculated result views](docs/CORE_RESULTS.md) are available. `make benchmark CASE=B01 DEVELOPMENT=1` (or B02/B07/B09) runs real diagnostics. B07 uses declared experimental mortar *EQUATION with scope limits and retains the failed native *TIE candidate; [T005 evidence](docs/validation/T005.md) explains the decision. B09 retains VTK/HTML stress diagnostics. `make feasibility` runs native cleanup; `MESHES=1` measures bounded workloads, and `make resource-browser OUTPUT=<directory>` checks real exterior field display. See [T006 evidence](docs/validation/T006.md). Signed/full release/security/report gates remain blocked.

## Start here

1. Read [PRD.md](PRD.md), [ARCHITECTURE.md](ARCHITECTURE.md), and [AGENTS.md](AGENTS.md).
2. Follow [Codex Cloud setup](docs/CODEX_CLOUD.md) to create a development environment with synthetic fixtures only.
3. Review T001–T011 evidence in the [task index](TASKS.md), the historical [M0 NO-GO review](docs/validation/M0-exit-review.md), and the later [owner progression decision](docs/validation/M0-owner-decision.md). PR #2 fixed both reproduced software defects. T007–T018 are COMPLETE and T019/M3 is next; benchmark sign-offs and local laptop acceptance remain pending.
4. Record evidence in [PROGRESS.md](PROGRESS.md). Pass the M0 feasibility gate before implementing the complete product.
5. Use [session prompts](docs/SESSION_PROMPTS.md) for focused coding, review, and handoffs.

The canonical agent instruction filename is **AGENTS.md**. [Agent.md](Agent.md) is a human-facing pointer, not a second competing policy.

T009 adds real [unit/material editing](docs/MATERIALS_UNITS.md): create/open a geometry-pinned analysis, assign source-backed examples or custom properties per body, confirm assumptions and save immutable revisions. The three display presets preserve canonical SI and source snapshots exactly. Missing density/yield leave gravity/yield-factor prerequisites unavailable. [T009 evidence](docs/validation/T009.md) records its 234 passing distinct cases.

T010 adds saved fixed faces, signed planar pressure and global total distributed force with actual viewport arrows/resultants and [immutable checked deck downloads](docs/LOADS_DECKS.md). A bounded isolated Gmsh bridge produces real coarse affine C3D10 connectivity and checks the written CCX loads. [T010 evidence](docs/validation/T010.md) records 281 passing distinct cases; durable asynchronous mesh/solve/results remain T011–T012.

T011 adds a durable local FIFO queue, actual mesh preview, frozen CCX solve inputs, stage/heartbeat status, confirmed cancellation and immutable raw output downloads. [T011 evidence](docs/validation/T011.md) records 316 passing distinct cases, actual native errors/cancellation, process restart and browser-close checks. T012 adds actual core result views; formal laptop/owner acceptance stays deferred.

T012 adds real displacement/von Mises contours, deformation scale, raw extrema, corrected fixed-support reactions and frozen per-body yield factors. [Core results](docs/CORE_RESULTS.md) explains native/derived locations and zero/missing yield; [evidence](docs/validation/T012.md) records 349 passing distinct cases, actual bracket/axial/two-body references and durable result history. [M1 technical exit](docs/validation/M1-exit-review.md) passes within the coarse planar local scope; signed benchmark and target-laptop obligations remain later gates. T013 cleanup, T014 mesh controls, T015 essential loads/equilibrium and T016 geometry directions/symmetry are complete; T017 workspace checklist/themes/safe edits is complete; T018 is complete; T019/M3 is next.

## Document map

| Document | Purpose |
|---|---|
| PRD.md | User-approved scope and numbered requirements |
| ARCHITECTURE.md | Proposed implementation and boundaries |
| AGENTS.md | Rules for Codex sessions and reviews |
| PLAN.md / TASKS.md | Milestones, gates, ordered small tasks |
| PROGRESS.md | Truthful implementation status and next handoff |
| docs/DECISIONS.md | Settled choices and evidence-dependent decisions |
| docs/FEASIBILITY.md | Early experiments and stop criteria |
| docs/UX_SPEC.md | Workspace, interactions, failure messages |
| docs/DOMAIN_MODEL.md / API_CONTRACT.md | Data invariants and service contracts |
| docs/ENGINEERING_SPEC.md | Units, elements, loads, ties, result semantics |
| docs/VALIDATION.md / validation/BENCHMARKS.md | Verification matrix and acceptance protocol |
| docs/SECURITY_PRIVACY.md | Data ownership, isolation, untrusted files |
| docs/COST_MODEL.md / AWS_BETA.md | Accounting, cost control, India deployment |
| docs/REPORTS_EXPORTS.md / OPERATIONS.md | Reports, archives, backup, recovery |
| docs/DEPENDENCIES.md / SOURCES.md | Dependency decisions and primary references |
| docs/CI_TESTING.md / RELEASE_CHECKLIST.md | Required tests and release evidence |
| docs/adr/ | Architecture decision records |
| docs/plan/ / docs/tasks/ | Milestone instructions and session-sized work |

The command runner and native tools exist. The full product layout remains a plan; project metadata is persistent, with a real local mesh/solve worker and browser controls; core calculated results are available; broader engineering inspection/assemblies/reporting remain later tasks.

T013 adds real [geometry cleanup preview/apply/undo](docs/GEOMETRY_EDITS.md) for the two validated M0 features. Before/after native tessellations and volume changes are reviewable; changed assignments block compute until explicit face reselection. Immutable old runs remain viewable after cleanup/undo. [Evidence](docs/validation/T013.md) records actual native, restart and browser checks. T014 adds [saved SI global/body/face/curvature sizing, actual quadratic quality and bounded recovery](docs/MESH_CONTROLS.md). [Evidence](docs/validation/T014.md) records 414 distinct verified passes, genuine curved mesh previews and retained failed recovery diagnostics. Solving retains the validated affine/planar path; no silent coarsening or widened numerical/native limits. T015 adds [global component supports, body gravity and frozen external force/moment equilibrium](docs/ESSENTIAL_LOADS.md). [Evidence](docs/validation/T015.md) records 464 distinct verified passes and actual B03–B05 on two meshes with unchanged declared tolerances and pending engineering-owner acceptance. T016 adds [native signed directions and planar symmetry](docs/GEOMETRY_DIRECTIONS.md), including visible right-handed bases, shared-node constraint consistency and frozen global solver outputs. [Evidence](docs/validation/T016.md) records 492 distinct passing cases and B06 rotation references on both declared meshes. T017 is complete; T018 is complete; T019/M3 is next; owner/laptop acceptance remains pending.

T017 adds the connected [model checklist, themes, keyboard selection and safe edit flow](docs/WORKSPACE_EDITS.md), acknowledged autosave, guarded session undo and conflict-only recovery copies. [Evidence](docs/validation/T017.md) records 512 distinct verified passes including actual restored setup/CCX and immutable raw history. T018 now supplies general saved setup duplication; Windows Chrome/Edge/owner-laptop acceptance remains deferred.

T018 adds [independent saved/historical setup duplication and exact compatible project mesh reuse](docs/ANALYSES.md), with independent variant solves and immutable original histories. [Evidence](docs/validation/T018.md) records 538 distinct passes; [M2 technical exit](docs/validation/M2-exit-review.md) passes within the declared local bounds and preserves owner/laptop/Windows obligations. T019/M3 is next.

T019 provides [native bond candidates, manual pairs and explicit gap review](docs/CONNECTIONS.md). Saved setups retain independent provenance/history; body volume overlaps block computation and saved bonds cannot be ignored by product deck/solve admission. [B08](tests/benchmarks/B08.json) is a declared development axial-gap experiment; general bonded assembly solving follows T020 constraint validation. [Evidence](docs/validation/T019.md) retains the exact limits and pending owner/laptop acceptance.
