# Developing this project in Codex Cloud

Codex Cloud develops the repository; it does not host this FEA service or replace numerical validation on the target laptop. T001 now provides a runnable health-only API/UI bootstrap. The current objective ends at the validated local prototype through M4/T030; AWS, Google authentication, billing and beta operations are outside this stage.

## Initial repository and environment

1. Extract this kit at a new repository root. Commit documentation to a private repository while licensing is unresolved. Keep AGENTS.md at root.
2. Connect/select that repository in your Codex Cloud environment. Current official guidance describes creating an environment, letting setup inspect/install/test, reviewing it, and publishing it. Account interfaces may differ; use the available environment flow.
3. Follow [development setup](DEVELOPMENT.md) and run `make setup` using the pinned tools and committed locks. Use the existing isolated checkout; do not create a worktree unless explicitly requested. T001's real scripts now exist; no later feature command is considered implemented merely because its Make target exists.
4. Test a fresh task from the prepared environment. Confirm dependencies and a tiny real CCX job using T002. Do not infer native solver availability from a successful Python import.

## Environment contract to implement in T001/T002

T001's `scripts/codex/setup.sh` installs locked JS/Python development dependencies and the locked Playwright browser. `scripts/codex/check.sh` prints versions and tests writable scratch, native availability and loopback networking; missing native tools are explicitly optional for health-only work. `scripts/codex/start.sh` supervises the real local API/UI and checks HTTP behavior. No worker exists yet. T002 extends provisioning with verified native tools and a real solver check; mandatory native gates must fail if unavailable. No deployment credentials belong in these scripts.
Support native Linux subprocess operation without Docker; Docker Compose remains the WSL2 reference path. If environment policy cannot install a dependency, document the blocked native tests and run those on WSL2 before closing their gate. Do not weaken sandbox rules or download unknown substitute binaries.

Provision package access during allowed setup: trusted OS repositories, chosen package registries and exact upstream source locations. Store no production secrets in the environment. Agent-phase network can stay restricted once dependencies are installed. If the account uses the legacy environment interface, point its setup/maintenance configuration to the same committed scripts; do not assume a setup shell export persists to coding sessions.

## Runtime profiles

- cloud-dev: synthetic fixtures, loopback/local auth, filesystem objects, local queue, no AWS.
- wsl-local: same contracts, larger native tests, optional containers, entire workflow offline after provisioning.
- beta: Google verification, regional private artifacts, worker roles, cost admission. Never activate in Codex Cloud.

## First task prompt

Read AGENTS.md, README.md, PROGRESS.md, PLAN.md and the explicitly requested task. Inspect the checkout and recorded evidence before changes. T001 now provides the command runner and health-only app; do not overwrite it or infer numerical features exist. Implement one bounded task, run applicable checks, update evidence and prepare a reviewable change. Do not deploy or advance to a later task automatically.

## Subsequent sessions

Use a task ID and acceptance criteria, not “build everything.” Read existing evidence, implement one bounded task, run targeted tests, update progress and leave a clean explanation. Use separate review sessions for numerical/bonding/metering changes. Save outcomes in git, not only chat. If a task is too large, add child tasks with explicit dependencies and keep parent incomplete.

## WSL2 handoff

Keep repo in the Linux filesystem for native tooling; open UI from Windows Chrome/Edge. Begin with a conservative worker memory budget (for example 6 GiB) leaving RAM for Windows/browser; calibrate in T006 rather than assuming all 16 GB is usable. Limit threads to avoid oversubscription. Commit only small nonprivate evidence. The 100k-element capacity target is subject to this measurement.

## Cloud CI cost discipline

Use focused fast checks on normal PRs. Native benchmarks are path-triggered or manually requested; cancel superseded runs. Do not launch full native benchmarks after every doc edit. No live AWS provisioning in default PR checks. Keep synthetic artifacts small and short-lived.
