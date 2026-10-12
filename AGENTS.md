# Repository instructions for Codex

## Mission and authority

Build the prototype described in PRD.md, using ARCHITECTURE.md and accepted ADRs. This is initially a documentation-only repository. Never claim the application or a benchmark works until executed evidence exists.
Read README.md, PROGRESS.md, TASKS.md and the selected task; then read the relevant specification/ADR. User instructions override this file. PRD controls product scope; accepted ADRs control technical choices. Proposed ADRs require their stated experiment, not automatic implementation as fact.

## Work one bounded task at a time

Choose the first unblocked task or the task explicitly requested. Inspect current files and git diff before editing. Implement the smallest complete slice; preserve unrelated changes. A task may be split into recorded child tasks if it exceeds one session. Do not jump to later milestones to avoid a failed gate. Routine reversible implementation choices are authorized; record reasons without repeatedly asking permission. Ask only for a genuine product trade-off or external action not already authorized.
Do not spawn parallel agents unless explicitly requested. Do not create cloud resources, publish, send email, merge, or change production data merely because an implementation task mentions them.

## Engineering invariants

- SI canonical model; explicit dimensions and unit conversions at boundaries.
- C3D10 only, with tested connectivity and face ordering. Never treat midside nodes as linear corners.
- Face selections use immutable geometry revision references; never persist only screen triangle IDs or transient Gmsh tags.
- No silent stabilization, geometry healing, force redistribution, bond approval, tolerance widening, or result averaging across discontinuities.
- Generated solver deck is deterministic and downloadable. Do not accept user-authored executable inputs.
- Preserve raw solver outputs, stress location semantics, binary hashes, settings and warnings in each run snapshot.
- Tests against analytical/reference data are required for numerical changes. Never loosen tolerances to obtain a pass.
- A missing native dependency, skipped benchmark or mocked solve is not passing numerical validation.

## Security and spending

Use synthetic/publicly licensed fixtures only. No private user CAD, reports, OAuth secrets, AWS keys or production database copies in Codex Cloud, git, CI artifacts or prompts. Local development auth is loopback-only and must fail closed when beta mode is enabled.
Treat uploads, archives and solver logs as untrusted data. Sandboxed subprocesses, allowlisted paths, size limits and no shell interpolation. No network for solver/CAD jobs. Use synthetic cloud adapters in tests.
Server owns prices, reservations, ownership and state transitions. A browser timer is never a spending control. Never auto-retry a failed job beyond documented limits.

## Commands and verification

T001 must implement the root Makefile command contract in docs/CI_TESTING.md. Before it exists, use documented direct commands and say the runner is not bootstrapped. Afterwards use make check for fast gates and targeted make test-native / make test-e2e when affected. Use locked dependencies; no unpinned curl-to-shell installers.
Do not assume Docker or privileged execution in Codex Cloud. Native Linux subprocess fallback must exist; run environment checks first. Large benchmarks run on WSL2 or an explicitly authorized runner and remain pending until evidence is committed.
Tests must assert meaningful behavior, not mirror internals. No full benchmark suite on every docs change. No placeholder return-success scripts or fake completion flags.

## Completion and handoff

Update task status in TASKS.md and task file, PROGRESS.md, any changed contract/ADR and evidence paths. Record commands, pass/fail/skip counts, numerical errors, limitations, and next task. Evidence must include commit and tool versions; avoid checking in bulky outputs.
Open or prepare a reviewable PR if the environment supports it; do not merge without authorization. Describe problem, change, validation and limitations. A clean git state is not proof of correctness.

## Code Review Rules

Flag stale geometry mappings, incorrect units/load resultant, unsupported stress claims, mutable run inputs, missing owner checks, duplicate execution/charging, unbounded retries, results credited as successful despite solver errors, and budget/residency violations as release blockers. Flag unsupported material or failure criteria as product defects. Cosmetic changes cannot justify relaxing engineering gates.
