# Command and CI contract

These commands are targets to create in T001/T002, not shipped scripts. Each must exit nonzero on a genuine failure. Missing required dependencies must be reported as blocked, not silently skipped in a required job.

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
