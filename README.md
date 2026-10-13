# Cloud FEA prototype — development starter kit

Planning baseline: 12 October 2026. Working title only; no product name or domain has been chosen.
This repository contains a health-only React/FastAPI bootstrap and real synthetic CAD/mesh/load/CCX/stress/bond diagnostics. T005 rejects a failed native tie candidate and proves an experimental consistent mortar connection on a limited planar patch. B01/B02/B09/B07 development evidence exists; T006 adds limited immutable native cleanup and measured cloud meshes/solves/display. The owner approved M0 progression with exact benchmark and laptop validation deferred. The general application workflow remains future work.
The current objective is the validated LOCAL prototype through M4/T030. AWS deployment, Google authentication, commercial billing and beta operations are outside this stage.

## Run the bootstrap

See [development setup](docs/DEVELOPMENT.md) and [native setup](docs/NATIVE_TOOLS.md). Run `make setup`, `make check`, `make test-native`, then `make dev`. UI/API remain health only. `make benchmark CASE=B01 DEVELOPMENT=1` (or B02/B07/B09) runs real diagnostics. B07 uses declared experimental mortar *EQUATION with scope limits and retains the failed native *TIE candidate; [T005 evidence](docs/validation/T005.md) explains the decision. B09 retains VTK/HTML stress diagnostics. `make feasibility` runs native cleanup; `MESHES=1` measures bounded workloads, and `make resource-browser OUTPUT=<directory>` checks real exterior field display. See [T006 evidence](docs/validation/T006.md). Signed/full release/security/report gates remain blocked.

## Start here

1. Read [PRD.md](PRD.md), [ARCHITECTURE.md](ARCHITECTURE.md), and [AGENTS.md](AGENTS.md).
2. Follow [Codex Cloud setup](docs/CODEX_CLOUD.md) to create a development environment with synthetic fixtures only.
3. Review T001–T006 evidence in the [task index](TASKS.md), the historical [M0 NO-GO review](docs/validation/M0-exit-review.md), and the later [owner progression decision](docs/validation/M0-owner-decision.md). PR #2 fixed both reproduced software defects. T007 is unblocked; benchmark sign-offs and local laptop acceptance remain pending.
4. Record evidence in [PROGRESS.md](PROGRESS.md). Pass the M0 feasibility gate before implementing the complete product.
5. Use [session prompts](docs/SESSION_PROMPTS.md) for focused coding, review, and handoffs.

The canonical agent instruction filename is **AGENTS.md**. [Agent.md](Agent.md) is a human-facing pointer, not a second competing policy.

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

The command runner and native tools exist. The full product layout remains a plan; no worker service, project workflow or solver UI is implemented.
