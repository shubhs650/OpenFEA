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

T011 adds 34 distinct cases: 17 Python unit, 13 native, 2 real-process integration and 2 Chromium. Final totals are 185 Python, 18 TS, 90 native, 9 integration, 13 Chromium (315 pass, 0 failed/skipped). Full native regression plus final changed-native replay covers actual queue/mesh/CCX, analytical references, process death/fencing, output faults, runtime/source fingerprints, warnings and symlink/network/fork/input-write denials. Browser/restart workflows use actual native execution and immutable bytes; lifecycle pauses/lease holds are explicitly separate from capacity evidence. See [T011 evidence](validation/T011.md). No frozen numerical/benchmark criterion, native build or dependency lock changes.

## Evidence format

T012 adds 33 distinct cases: 19 Python unit, 3 TypeScript, 8 native, 1 process restart and 2 Chromium. Final totals: 205 Python, 21 TS, 98 native, 10 integration, 15 Chromium (**349 passed, 0 failed/skipped**). Actual axial/bracket/two-body solves verify raw/derived results, fixed RF-minus-load reactions and frozen yields; actual zero-pressure cancellation/missing yield, corrupted sources, deletion at publication and result restart/browser history are covered. Full 97-case native regression plus final eight-case result replay accounts for the added race case; repetitions count once. [T012 evidence](validation/T012.md) and [M1 exit review](validation/M1-exit-review.md) retain hashes, numerical criteria and unexecuted owner/laptop gates. Final new browser workflows use the unchanged 15-second timeout; no numerical/native limit was relaxed.

T010 adds 47 distinct cases: 20 Python, 7 TS, 18 native, 1 restart, 1 Chromium. Final totals are 168 Python unit, 18 TS unit, 77 native, 7 integration and 11 Chromium (281 pass, 0 failed/skipped). Actual downloaded decks are solved for six pressure orientations/both signs and a two-body total-force reference. Native export/security tests use real namespaces/Gmsh; browser/restart cases use real imported geometry and saved/exported bytes. [T010 evidence](validation/T010.md) records fixed criteria, corrections, hashes and unexecuted gates. No dependency, native lock/build or frozen benchmark criterion changed.

T009 adds 34 distinct cases, bringing executed local totals to 148 Python unit, 11 TS unit, 59 native, 6 real-process integration and 10 Chromium (234 pass, 0 failures/skips). Native material cases execute nine actual axial solves using independent references; browser cases use native imported solids and real immutable saves. Tests also cover sample/version/provenance, exact unit-only copying, conflicts, migration/history and process restart. See [T009 evidence](validation/T009.md). No existing native/benchmark criterion or dependency changed.

Commit, task, command, platform, versions, passed/failed/skipped counts, benchmark expected/actual/error/tolerance, resource metrics and links. Screenshots alone cannot prove numerical correctness. A failed/blocked native gate remains open even if frontend tests pass.

T008 executed `make check test-native build smoke test-integration test-e2e`, plus doctor and changed-native checks: 124 Python unit, 7 TS unit, 56 native, 5 integration and 8 Chromium cases pass (200 distinct). Actual import/picking flows use native synthetic STEP, not mocked CAD. CI installs Bubblewrap explicitly; unsupported/missing namespaces remain a native gate failure. [T008 evidence](validation/T008.md) records versions/hashes and unexecuted Windows/hosted/engineering gates.

The ephemeral Ubuntu 24.04 CI runner loads a launcher-specific AppArmor `userns` profile for `/usr/bin/bwrap`, then checks namespace creation with a trusted `/usr/bin/true` before native provisioning. This targets the runner's private-loopback `RTM_NEWADDR: Operation not permitted` denial without changing global user-namespace policy. STEP jobs retain their private namespaces, readonly mounts, dropped capabilities and syscall/resource restrictions; no unconfined parsing fallback is added. This runner setup is not automatically applied to operator machines. Doctor prints at most the last 4,000 bytes of its synthetic STEP probe log on failure; public API errors remain redacted.
