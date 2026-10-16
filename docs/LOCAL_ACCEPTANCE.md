# Local acceptance packet — T030

The review packet is executable; **M4 exit is BLOCKED**. On 16 October 2026 the owner instructed: “No—prepare the packet with those checks pending.” Actual Windows/WSL2 laptop results and consented human trials have not been supplied. Cloud/Linux Chromium evidence cannot satisfy them. Exact B10/B12/B13/B14 and M4 scope review also remain pending. The [M0 exception](validation/M0-owner-decision.md) is still open for these obligations. See [T030 evidence](validation/T030.md) and the [release checklist](RELEASE_CHECKLIST.md).

## Freeze and run the Linux gates

Use only the supplied synthetic/public fixtures. On the target laptop, use a Linux-filesystem WSL2 checkout, not a shared Windows `node_modules` or `.venv`. Install the pinned prerequisites in [development setup](DEVELOPMENT.md), including native Linux dependencies, fonts, Poppler and LibreOffice for report QA. Record `git rev-parse HEAD`, `git status --short`, tool versions and all failures. Resolve modified engineering sources before recording acceptance; retain each attempt rather than overwriting it.

```sh
make setup
make doctor
make check
make test-native
make test-integration
make test-e2e
make test-reports
make build
make smoke
mkdir -p work/t030-laptop
make m4-review > work/t030-laptop/review-packet.json
make local-profile OUTPUT=work/t030-laptop/profile-before.json SCRATCH=/tmp
make benchmark-m4 DEVELOPMENT=1 OUTPUT=work/t030-laptop/development-benchmarks
make local-profile OUTPUT=work/t030-laptop/profile-after.json SCRATCH=/tmp
```

Do not run setup while other checks are using its environments. `make check` is fast/static/unit/contracts/docs; native, process, browser and report suites are separate mandatory gates. `make test-e2e` uses isolated ports/data and Linux headless Chromium; it is regression coverage, not Windows evidence. `benchmark-all` and `test-security` remain fail-closed legacy placeholders for broader release/hosted scope; they are not credited as passing tests. Actual local ownership, malformed input/archive, offline sandbox, resource/cancellation/retry and report security cases run in the required suites above. M5 hosted access/accounting/operations remain outside local acceptance.

`m4-review` prints 14 case records plus M3/M4 scope records. Existing ten M3 approvals remain unchanged. Review the [new exact criteria](validation/M4-owner-review.md), analytical/reference provenance, exclusions and measured errors. After an engineering owner explicitly approves those exact hashes, record identity, date and decision using the existing [approval contract](../services/worker/worker/approval.py) and rerun in a **fresh** directory:

```sh
make m4-review > work/t030-laptop/approved-review-packet.json
make benchmark-m4 OUTPUT=work/t030-laptop/acceptance-benchmarks
```

This command currently refuses before native execution/output creation because five approvals are pending. Never edit a signoff merely to make the command run. Development passes do not become acceptance passes retrospectively. Even an approved numerical pass leaves `m4_exit_status` blocked until the separate laptop, browser, human and final owner review are recorded. B11 passes by correctly refusing an invalid model. B07 means approved mortar, not rejected native `*TIE`. B08 is only an offline axial idealization, not enabled physical-gap product solving. B10 is an offline straight-sided fillet approximation, separate from the sharp planar UI tutorial. B12–B14 compare independently authored CCX models to published values; no fresh Code_Aster/ANSYS execution is claimed.

## Actual installed Windows Chrome and Edge

Use a second clean checkout at the **same full commit** on the Windows filesystem with Windows Node 24.19.0/npm 11.9.0. Its `node_modules` must be separate from WSL. Create a fresh byte-preserving checkout with `git clone --config core.autocrlf=false https://github.com/shubhs650/OpenFEA.git OpenFEA-windows`, then check out the recorded full commit. Tutorial STEP and retained evidence paths also explicitly disable Git line-ending conversion; do not rewrite fixture bytes. Install Chrome and Edge normally. Do not substitute Playwright Chromium, Linux browsers, WSLg or headless mode. Keep the WSL backend console open. Start it with a new, dedicated, synthetic-only directory outside the checkout (choose a fresh path on repeat runs):

```sh
export FEA_ENV=test
export FEA_AUTH_MODE=local
export FEA_BIND_HOST=127.0.0.1
export FEA_DATA_ROOT="$(mktemp -d /tmp/openfea-t030-browser-XXXXXXXX)"
make dev
```

The backend/API and Vite bind only loopback (8000/5173). From Windows, open `http://127.0.0.1:5173` and verify API connected; if WSL localhost forwarding is unavailable, fix the local WSL configuration and record the blocker. Do not expose the application on a public bind address. Then run from Windows PowerShell in its checkout:

```powershell
git rev-parse HEAD
git status --short
node --version
npm --version
npm ci
$env:FEA_ACCEPTANCE_BASE_URL = 'http://127.0.0.1:5173'
$env:FEA_REFERENCE_DIR = Join-Path (Get-Location) 'work/t030-windows-ui'
npm exec -- playwright test --config playwright.local.config.ts
```

The dedicated configuration runs nine browser-only real API/UI cases in each installed browser, headed, sequentially, with no retry or fallback. It includes bracket/bond native solve/refinement/probe/section/report, archive round-trip, PDF/Word export, themes and safe edits. Linux process-control tests remain in WSL's full suite. The config refuses on Linux; the Windows execution itself is **NOT RUN** here. Preserve `.local/windows-acceptance-results.json`, `.local/windows-acceptance-artifacts/`, screenshot PNG/JSON pairs and backend logs. Stop the backend with Ctrl-C when finished. Repeat a failed run with fresh evidence/data, preserving the failure.

Screenshots record actual user agent, host platform, theme, viewport, canvas renderer, source commit and PNG SHA-256. A software renderer must be labeled as such. Browser source and WSL backend commits must match; the browser cannot attest the backend commit automatically. Record both manually.

## Resource, renderer and capacity worksheet

`local-profile` records CPU, WSL-visible memory/swap, cgroup memory limit and free scratch disk. On WSL it attempts a bounded PowerShell query for physical RAM/CPU/GPU names only. It excludes usernames, machine names and serials; unavailable Windows interop remains an explicit observation error. Before/after free-memory snapshots are **not peak usage** and GPU model/VRAM are **not capacity evidence**.

For each actual bracket and bonded workload, retain downloaded `mesh.json`, original deck/DAT/FRD, result/comparison JSON and each execution's resource/diagnostic records. Record mesh elements/nodes, native wall time, sampled process-tree RSS, aggregate scratch peak, free-disk minimum, failures and cancellation/recovery outcomes. Sample Windows Task Manager and WSL memory/disk during the run, including report export, with timestamps; distinguish host from native-job memory. Native samples can miss short peaks and watchdogs can overshoot. State that limitation, the observation interval and competing workloads.

In **each headed Windows browser**, inspect the actual result canvas renderer from screenshot metadata and a DevTools Performance recording while rotating, zooming, changing stress component/body visibility, probing and applying a volume section. Retain browser version, display scaling/resolution, WebGL renderer, workload size, recording duration, frame-time/FPS observations, interaction stalls and errors. Use actual result rendering, not a disconnected WebGL demo. Observe at 1366×768 and 1920×1080 in both themes; manually check focus, clipping and report readability. Export a PDF and DOCX, open both locally, edit/reopen a Word paragraph and table cell, and compare original model units/warnings/captions. Office/driver rendering remains unverified until this check.

Start with the shipped fixtures. Do not attempt a 100k-element solve: current product admission is **3,000 elements**, affine/planar C3D10; curved meshes are preview-only. Native call limits remain 60 s, job deadline 180 s, tree RSS 1,536 MiB and aggregate scratch 192 MiB, with one eligible infrastructure retry inside the original budget. Bonded solving remains two bodies, one full axis-aligned zero-gap unit-square interface, at most 65 trace nodes per side. Record only the highest workload actually completed within these limits with sufficient measured headroom. An owner must approve a conservative supported capacity; do not extrapolate from GPU model, ANSYS history or cloud speed. Larger/general physics require a separate reviewed scope change.

| Actual laptop field | Observation / evidence |
|---|---|
| Full backend/browser commit; Windows/WSL/kernel/browser versions | PENDING |
| CPU; physical RAM; WSL allocation; scratch filesystem/free disk | PENDING |
| Fixture, mesh elements/nodes; elapsed/native times; peak RSS/scratch | PENDING |
| Chrome renderer/recording/frame times; light/dark/manual checks | PENDING |
| Edge renderer/recording/frame times; light/dark/manual checks | PENDING |
| PDF/DOCX local open/edit/reopen; archive restore/download hashes | PENDING |
| Measured supported capacity and owner rationale | PENDING |

## Consented human usability trials

Recruit **3–5** consenting people who understand mechanics but have little FEA experience. Give the same [written tutorials](TUTORIALS.md), fixture and clean local start; no live assistance during the scored bracket attempt. Explain that learning logs contain notes/timing/browser details, are voluntary local files, and should use pseudonyms (P01–P05), no personal CAD or identities. Get consent before observation and retain the consent decision locally. Do not invite users through this coding task or upload identifying participant records.

The timer excludes observed compute and manual pauses; keep the same analysis open, pause breaks, and record reloads because they reset timing. Independently note start/end/compute intervals, errors and assistance; checked steps are self-report, not proof. Success requires actual bracket setup/solve/inspection/refinement/report without live help and **≤30 minutes excluding compute**. A helped, abandoned, failed or >30-minute attempt is not a success. Keep failures in the denominator. Require **≥80%**: all three, all four, or at least four of five. Run the bonded exercise separately and record bond-review errors/learning observations; do not substitute automated timing for participants.

| Participant | Consent | Bracket setup minutes (compute excluded) | Independent completion / help / errors | Bond observations | Result |
|---|---|---|---|---|---|
| P01 | PENDING | PENDING | PENDING | PENDING | NOT RUN |
| P02 | PENDING | PENDING | PENDING | PENDING | NOT RUN |
| P03 | PENDING | PENDING | PENDING | PENDING | NOT RUN |
| P04 (if recruited) | PENDING | PENDING | PENDING | PENDING | NOT RUN |
| P05 (if recruited) | PENDING | PENDING | PENDING | PENDING | NOT RUN |

Retain the downloaded local learning JSON and an anonymized observer worksheet per attempt. Report actual participant count, numerator/denominator, timing and all failures. Automated Playwright learning logs count only as regression evidence.

## Final review

Review [requirement coverage and limits](validation/M4-owner-review.md), all retained failures/not-run checks and any proposed convenience deferral. PDF, editable Word, archive and tutorial features are implemented; no new convenience deferral is used to bypass them. General/curved/gap/capacity restrictions are engineering boundaries, not convenience exceptions. If a required core check fails, fix and rerun its affected evidence; do not widen tolerances or call it cosmetic. Close the M0 exception and mark T030/M4 complete only when exact approval/reruns, actual target-laptop workflows/resources/headed performance, successful human trial and final owner engineering exit decision are all recorded. T031/M5 stays blocked meanwhile.
