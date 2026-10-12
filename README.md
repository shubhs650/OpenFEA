# Cloud FEA prototype — development starter kit

Planning baseline: 12 October 2026. Working title only; no product name or domain has been chosen.
This repository contains the specifications and a health-only local React/FastAPI bootstrap from T001. No analysis workflow, numerical validation or AWS cost-fit claim has been made.
The current objective is the validated LOCAL prototype through M4/T030. AWS deployment, Google authentication, commercial billing and beta operations are outside this stage.

## Run the bootstrap

See [development setup](docs/DEVELOPMENT.md) for pinned tools and configuration. From the repository root run `make setup`, `make check`, `make build`, then `make dev`. The UI and API bind to loopback; the page verifies API connectivity. `make smoke` checks startup and shuts down; `make test-e2e` runs the real health page in Chromium. Native and later feature gates remain unavailable and fail explicitly.

## Start here

1. Read [PRD.md](PRD.md), [ARCHITECTURE.md](ARCHITECTURE.md), and [AGENTS.md](AGENTS.md).
2. Follow [Codex Cloud setup](docs/CODEX_CLOUD.md) to create a development environment with synthetic fixtures only.
3. Review [T001](docs/tasks/T001.md) and its evidence, then follow the dependency-ordered [task index](TASKS.md). The next implementation task is T002.
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

The root command runner now exists. [Development setup](docs/DEVELOPMENT.md) distinguishes implemented bootstrap commands from blocked future gates. The architecture's full product layout remains an implementation plan; only the health slice exists.
