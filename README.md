# Cloud FEA prototype — development starter kit

Planning baseline: 12 October 2026. Working title only; no product name or domain has been chosen.
This repository contains a health-only React/FastAPI bootstrap, isolated native tools and real synthetic CAD/mesh/load/CCX/stress diagnostics. T004 preserves raw integration tensors and material-side values. B01/B02/B09 pass development checks; owner-signed acceptance, the application workflow and capacity remain open.
The current objective is the validated LOCAL prototype through M4/T030. AWS deployment, Google authentication, commercial billing and beta operations are outside this stage.

## Run the bootstrap

See [development setup](docs/DEVELOPMENT.md) and [native setup](docs/NATIVE_TOOLS.md). Run `make setup`, `make check`, `make test-native`, then `make dev`. UI/API still provide health only. Run `make benchmark CASE=B01 DEVELOPMENT=1` (or B02/B09) for development diagnostics. B09 generates raw stress JSON, VTK and an offline interactive HTML fixture under `.local/native/benchmarks/B09/`; [evidence](docs/validation/T004.md) explains raw/derived semantics. Signed acceptance/full release benchmarks/security/reports remain blocked.

## Start here

1. Read [PRD.md](PRD.md), [ARCHITECTURE.md](ARCHITECTURE.md), and [AGENTS.md](AGENTS.md).
2. Follow [Codex Cloud setup](docs/CODEX_CLOUD.md) to create a development environment with synthetic fixtures only.
3. Review [T001](docs/tasks/T001.md), [T002](docs/tasks/T002.md), [T003](docs/tasks/T003.md) and [T004](docs/tasks/T004.md) evidence, then follow [TASKS.md](TASKS.md). T003/T004 owner review is pending; next implementation task: T005.
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
