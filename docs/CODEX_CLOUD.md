# Developing this project in Codex Cloud

Codex Cloud develops the repository; it does not host this FEA service or replace numerical validation on the target laptop. This kit contains no runnable app yet.

## Initial repository and environment

1. Extract this kit at a new repository root. Commit documentation to a private repository while licensing is unresolved. Keep AGENTS.md at root.
2. Connect/select that repository in your Codex Cloud environment. Current official guidance describes creating an environment, letting setup inspect/install/test, reviewing it, and publishing it. Account interfaces may differ; use the available environment flow.
3. Start with T001 to bootstrap manifests, command runner and scripts. Ask setup to provision the pinned toolchain from those committed files. Do not configure commands that do not exist yet and call setup successful.
4. Test a fresh task from the prepared environment. Confirm dependencies and a tiny real CCX job using T002. Do not infer native solver availability from a successful Python import.

## Environment contract to implement in T001/T002

scripts/codex/setup.sh installs locked JS/Python dependencies, approved native tools with checksums, and browser test dependencies. scripts/codex/check.sh prints versions and tests writable scratch, native command availability and loopback networking. scripts/codex/start.sh starts local dev API/worker/UI and waits for health checks. They must be idempotent, fail on missing mandatory dependencies and contain no deployment credentials.
Support native Linux subprocess operation without Docker; Docker Compose remains the WSL2 reference path. If environment policy cannot install a dependency, document the blocked native tests and run those on WSL2 before closing their gate. Do not weaken sandbox rules or download unknown substitute binaries.

Provision package access during allowed setup: trusted OS repositories, chosen package registries and exact upstream source locations. Store no production secrets in the environment. Agent-phase network can stay restricted once dependencies are installed. If the account uses the legacy environment interface, point its setup/maintenance configuration to the same committed scripts; do not assume a setup shell export persists to coding sessions.

## Runtime profiles

- cloud-dev: synthetic fixtures, loopback/local auth, filesystem objects, local queue, no AWS.
- wsl-local: same contracts, larger native tests, optional containers, entire workflow offline after provisioning.
- beta: Google verification, regional private artifacts, worker roles, cost admission. Never activate in Codex Cloud.

## First task prompt

Read AGENTS.md, README.md, PROGRESS.md, PLAN.md and docs/tasks/T001.md. Implement T001 only. This is a documentation-only starting repository. Create the real command runner and dependency manifests; do not fabricate application features or passing solver tests. Run the applicable checks, update the task record and PROGRESS.md, and prepare a reviewable change. Do not deploy or advance to T002 automatically.

## Subsequent sessions

Use a task ID and acceptance criteria, not “build everything.” Read existing evidence, implement one bounded task, run targeted tests, update progress and leave a clean explanation. Use separate review sessions for numerical/bonding/metering changes. Save outcomes in git, not only chat. If a task is too large, add child tasks with explicit dependencies and keep parent incomplete.

## WSL2 handoff

Keep repo in the Linux filesystem for native tooling; open UI from Windows Chrome/Edge. Begin with a conservative worker memory budget (for example 6 GiB) leaving RAM for Windows/browser; calibrate in T006 rather than assuming all 16 GB is usable. Limit threads to avoid oversubscription. Commit only small nonprivate evidence. The 100k-element capacity target is subject to this measurement.

## Cloud CI cost discipline

Use focused fast checks on normal PRs. Native benchmarks are path-triggered or manually requested; cancel superseded runs. Do not launch full native benchmarks after every doc edit. No live AWS provisioning in default PR checks. Keep synthetic artifacts small and short-lived.
