# OpenFEA — bounded local FEA prototype

The local application implements STEP solid import, confirmed source-backed materials and SI units, face loads/supports, quadratic tetrahedral mesh, CalculiX linear static solve, engineering result inspection, immutable history, PDF/editable Word reports and portable project archives. Guided bracket and two-body bonded examples use the real workflow. No third-party account or AWS service is needed locally.

**Current status: T025–T029 complete; T030 IN PROGRESS; M4 acceptance BLOCKED.** The owner requested the acceptance packet with actual Windows/WSL2 laptop and consented human checks pending. Existing bounded M3 engineering approval is preserved; exact new reference-owner review, acceptance reruns, measured laptop capacity and final M4 review remain open. See [progress](PROGRESS.md), [local acceptance packet](docs/LOCAL_ACCEPTANCE.md) and [review/limitations](docs/validation/M4-owner-review.md). AWS, Google authentication, hosted billing/operations and deployment belong to later gated milestones.

## Run locally

Use Linux x86_64 or WSL2 with the pinned prerequisites in [development setup](docs/DEVELOPMENT.md) and [native setup](docs/NATIVE_TOOLS.md). From the root:

```sh
make setup
make check
make test-native
make test-integration
make test-e2e
make test-reports
make build
make smoke
make dev
```

Open `http://127.0.0.1:5173`. Choose a durable absolute `FEA_DATA_ROOT` outside the checkout for ordinary use; the default `/tmp/openfea-data` is temporary. Only synthetic/public fixtures belong in cloud/CI. The [tutorials](docs/TUTORIALS.md) explain deliberate import/setup/bond approval, mesh refinement, physical probes/sections and report export. The [acceptance packet](docs/LOCAL_ACCEPTANCE.md) includes separate actual installed Windows Chrome/Edge commands, hardware/renderer worksheets and human-trial instructions. Linux headless Chromium passes do not certify either Windows browser or human usability.

## Supported engineering scope

Small-deformation isotropic elastic static C3D10 only. Product solves admit at most **3,000 affine/planar elements**; curved meshes are preview-only. Bonded solves support two independent bodies and one full axis-aligned zero-gap unit-square mortar interface, with at most 65 trace nodes per side. General assemblies, physical-gap/contact solves and nonlinear analysis remain unavailable. Native `*TIE` was rejected; no automatic stabilization, healing, force redistribution or silent coarsening is used. Actual laptop workload capacity is unmeasured; a 100k-element solve is not supported.

Raw native stresses/extrema remain distinct from tensor-derived contours and optional partitioned smoothing. Refinement comparisons and yield factors do not certify a safe design. [Results](docs/CORE_RESULTS.md), [assembly preflight](docs/ASSEMBLY_PREFLIGHT.md) and the [exact M4 review](docs/validation/M4-owner-review.md) give the boundaries. Reports retain warnings, assumptions and source identities; imported original archive history is inert.

## Review and evidence

Read [AGENTS.md](AGENTS.md), [PRD.md](PRD.md), [ARCHITECTURE.md](ARCHITECTURE.md), the [task index](TASKS.md) and the current [M4 plan](docs/plan/M4.md). The [M0 progression exception](docs/validation/M0-owner-decision.md) and [M3 acceptance](docs/validation/T024-acceptance.md) retain the original decisions and exact scope. The canonical agent instruction filename is **AGENTS.md**; [Agent.md](Agent.md) is a pointer.

`make m4-review` prints exact pending criteria hashes. `make benchmark-m4 DEVELOPMENT=1 OUTPUT=<fresh-directory>` replays all fourteen required native cases as development evidence. Default acceptance execution refuses pending owner approvals. Numerical passes alone cannot close M4. Per-task execution/failure records are linked from [PROGRESS.md](PROGRESS.md); [T030 evidence](docs/validation/T030.md) records this review and real UI references.

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
