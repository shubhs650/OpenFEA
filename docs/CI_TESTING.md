# Command and CI contract

The root Makefile now ships the T001 bootstrap commands. Each exits nonzero on a genuine failure. Missing required dependencies are reported as blocked, never silently skipped in a required job. The table retains the full target behavior to implement over subsequent tasks.

T001 supplies health API/UI; T002 provisions native tools. T003–T006 and the M0 defect fixes extend test-unit to 90 Python cases and test-native to 42 real tool/mesh/stress/bond/cleanup/resource tests. T007 adds 28 Python metadata/access/migration cases (118 total), one integration restart (5 total) and one Chromium/Vite project flow (5 total); see [T007 evidence](validation/T007.md). Native suites are unchanged and were not rerun for this metadata slice. Selected B01/B02/B07/B09 benchmarks execute the actual pipeline with DEVELOPMENT=1 while exact-criteria review is pending. B07 uses limited experimental mortar; failed native *TIE, uncovered nodes, singular assembly and adjustment diagnostics are retained. Hosted CI passed on PR #2. Full release/security/report gates remain blocked. T006 measured native workloads and two standalone software WebGL checks; target-laptop acceptance is deferred to M4/T030 by the [owner decision](validation/M0-owner-decision.md). See [T006 evidence](validation/T006.md), [native commands](NATIVE_TOOLS.md) and [T005 evidence](validation/T005.md).

| Command | Required behavior |
|---|---|
| make setup | Install/reconcile locked dev dependencies using documented provisioning path |
| make doctor | Report versions, platform and missing native capabilities |
| make dev | Start local web/API/worker with filesystem storage and loopback auth |
| make lint | Frontend/backend static checks and formatting validation |
| make typecheck | TypeScript and chosen Python static type checks |
| make test-unit | Pure math, domain, API helper and ledger tests without native solvers |
| make check | lint + typecheck + unit + contract checks, not all expensive benchmarks |
| make test-native | Tiny real import/mesh/CCX/parser tests with licensed synthetic fixtures |
| make test-e2e | Playwright core browser flows; distinguish mock UI tests from real solve flow |
| make benchmark CASE=B02 | Reproducible selected reference case with explicit versions/errors |
| make benchmark-all | Required release benchmark set; list unavailable external cases |
| make test-security | Owner isolation, archive parsing, auth, caps and lease-race cases |
| make test-reports | Generate reports; inspect text plus rendered-page/screenshot evidence |
| make docs-check | Internal links, task graph and declared status consistency |

## Test organization and gates

Unit/contract tests run on every relevant code PR. Browser UI tests use deterministic fixtures; at least one end-to-end flow uses a real solver before M1 closure. Math/solver/mesh changes trigger applicable native cases. Deployment code uses mocked SDK contracts and IaC validate/plan with no real apply. Release candidate runs full required benchmark suite on the recorded pinned environment.
Require regressions for each fixed numerical bug. Avoid tests solely asserting CSS class names or private method calls. On changes to output transformations compare physical values at defined coordinates, not just screenshots. Goldens are reviewed numerical fixtures, not snapshots overwritten automatically.

## CI limits

Set timeouts, concurrency cancellation, path filtering and short artifact retention. No entire OS/tool rebuild on every commit: cache by lockfile/native-tool hash. Avoid duplicate push+PR pipelines for the same revision. Avoid relying on persistent runner disk or secret access from forks. Record compute minutes to decide whether a future self-hosted runner is warranted; no CI platform migration is required now.

## Evidence format

Commit, task, command, platform, versions, passed/failed/skipped counts, benchmark expected/actual/error/tolerance, resource metrics and links. Screenshots alone cannot prove numerical correctness. A failed/blocked native gate remains open even if frontend tests pass.
