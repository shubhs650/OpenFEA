# Developing this project in Codex Cloud

Codex Cloud develops and tests M1–M4; it does not host the eventual FEA service. The [M0 owner decision](validation/M0-owner-decision.md) defers completed-workflow laptop acceptance to M4/T030. T001 provides a runnable health-only API/UI bootstrap. The current objective ends at the validated local prototype through M4/T030; AWS, Google authentication, billing and beta operations are outside this stage.

## Initial repository and environment

1. Extract this kit at a new repository root. Commit documentation to a private repository while licensing is unresolved. Keep AGENTS.md at root.
2. Connect/select that repository in your Codex Cloud environment. Current official guidance describes creating an environment, letting setup inspect/install/test, reviewing it, and publishing it. Account interfaces may differ; use the available environment flow.
3. Follow [development setup](DEVELOPMENT.md) and run `make setup` using the pinned tools and committed locks. Use the existing isolated checkout; do not create a worktree unless explicitly requested. T001's real scripts now exist; no later feature command is considered implemented merely because its Make target exists.
4. Test a fresh task from the prepared environment. Confirm dependencies and a tiny real CCX job using T002. Do not infer native solver availability from a successful Python import.

## Environment contract to implement in T001/T002

The actual `scripts/codex/setup.sh` provisions locked root/browser dependencies, pinned CCX source/numerical libraries and three separate native Python environments. It runs doctor and all 42 native checks after the M0-R1/M0-R2 corrections, including development-only B01/B02/B07/B09 and native tensor/bond diagnostics. Missing/mismatched native tools fail. `scripts/codex/start.sh` still starts only the health API/UI; no worker service exists. Native probes/synthetic CAD-mesh-solve jobs are bounded, network-denied ephemeral processes. See [native setup](NATIVE_TOOLS.md). No deployment credentials belong in these scripts.
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

## M4 laptop handoff

At M4/T030, keep the repo in the WSL2 Linux filesystem for native tooling and open the UI from Windows Chrome/Edge. Measure actual RAM, CPU and browser/solver headroom first; the owner reported i5 10th-generation-equivalent CPU and a 1650-class GPU with 4 GB VRAM, but did not verify RAM or OpenFEA throughput. Begin with a conservative worker budget leaving headroom for Windows/browser, and limit threads to avoid oversubscription. Commit only small nonprivate evidence. T006 measured 99,198 cloud mesh cells, but deliberately did not solve that size. The highest measured cloud patch solve is 27,155 cells; default diagnostic budgets are 1.5 GiB RSS/256 MiB scratch with existing native hard limits. Start conservatively (e.g. ≤5k cells) until target WSL2 measurements exist; no validated laptop cap is claimed. Reproduce [T006 diagnostics](validation/T006.md) and complete end-to-end workflows, then open headed browser artifacts on the target Windows/GPU stack. The GPU model or smooth ANSYS use does not certify OpenFEA performance.

## Cloud CI cost discipline

Use focused fast checks on normal PRs. Native benchmarks are path-triggered or manually requested; cancel superseded runs. Do not launch full native benchmarks after every doc edit. No live AWS provisioning in default PR checks. Keep synthetic artifacts small and short-lived.
