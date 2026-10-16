# Local development — bootstrap and project persistence

The application implements the bounded local STEP/material/load/mesh/CCX/results/report/archive workflow. See [current acceptance instructions](LOCAL_ACCEPTANCE.md) and [README](../README.md) for supported scope and pending laptop/owner/human gates. Hosted authentication, accounting and operations remain later scope.

## Supported environment and tools

Linux x86_64 / WSL2, Node **24.19.0** (LTS), npm **11.9.0**, Python **3.12.14**, uv **0.12.23**, Bash and GNU Make. Version pins are in `.node-version`, `.nvmrc`, `.python-version`, `.uv-version` and `package.json`. Setup rejects wrong Node/npm/uv versions, and uv locates or provisions the exact Python version. Docker and privileged execution are unnecessary for the bootstrap.

Install these prerequisites through trusted sources. If nvm is already installed, `nvm install` and `nvm use` select `.nvmrc` and retain nvm's archive checksum verification. To install uv in a separate tools virtual environment, use `python3 -m venv /tmp/openfea-tools`, then `/tmp/openfea-tools/bin/python -m pip install --only-binary=:all: --require-hashes -r scripts/ci/tool-requirements.txt` and add `/tmp/openfea-tools/bin` to your shell PATH. The hashed wheel requirements pin uv without a curl-to-shell installer. To reconcile npm with the Node distribution, use `npm install --global npm@11.9.0` in your user-managed Node installation. Project dependencies always use the committed locks.

T001's [wheel probe](validation/wheel-probe.json) is historical ABI availability evidence. T002's actual isolated pins and executed capabilities are in [native setup](NATIVE_TOOLS.md); OCP's required VTK differs from the old probe candidate. OCP and Gmsh remain in separate processes. The validated tiny solve does not imply face mapping or release benchmark acceptance.

## Setup and commands

From the repository root:

```sh
make setup
make doctor
make check
make test-native
make build
make smoke
make test-integration
make test-e2e
make dev
```

`make setup` installs locked root/browser dependencies, then the pinned native source build and three separate locked interpreters, and runs required native checks. All six locks remain unchanged. Native files stay under ignored `.local/native/`; no system installation is performed. The browser installer retains TLS validation; Linux shared-library prerequisites must be available. The prepared Codex instance passed browser/native checks without privileged installation. See [native platform prerequisites](NATIVE_TOOLS.md); GCC 14.2.0 is now required.

Caches, virtual environments, logs and browser binaries are ignored. Make and shell scripts set repository-local writable cache directories under `.local/`, avoiding read-only home directories. Python dependencies reside in `.venv/`; npm dependencies in `node_modules/`; web build outputs in `apps/web/dist/`. No installation or startup command rewrites application source, tests or dependency declarations.

`make dev` runs the real API and Vite processes on **127.0.0.1**, API port **8000** and web port **5173**. It waits for the health JSON directly and through the Vite proxy, and checks the web HTML entry point. Logs are in `.local/logs/`. API and frontend support hot reload. Ctrl-C/SIGTERM terminates the child process groups; an unexpected child exit fails the supervisor and stops its sibling. Occupied ports cause a failure before services are launched; existing processes are never reused or stopped. API lifespan starts and supervises the durable single-job local worker. `make smoke` performs the same startup/readiness checks then shuts down.

The health page fetches `/api/v1/health`; it shows “API connected” only after validating the real response and reports “API unavailable” on a failed request. This means bootstrap connectivity, not FEA readiness. Project/session routes and their usage are described in [PERSISTENCE.md](PERSISTENCE.md). The Vite proxy preserves Host for Origin checks, and Uvicorn proxy headers are disabled. API schema/docs are under `/api/v1/openapi.json` and `/api/v1/docs`. Use `make contracts` to regenerate the checked-in OpenAPI and TypeScript types; `make contracts-check` fails on drift. The client compiles against the generated health response type.

Startup prints `SUPERVISOR pid=...` and the owned API/web process IDs. In a real terminal, Ctrl-C signals the foreground group and stops the services. This cloud tool's terminal-session interruption may disconnect without signaling the running Make/supervisor processes; if that occurs, send `kill -TERM` to the exact supervisor PID recorded for the session you started. The supervisor handles SIGINT, SIGTERM and SIGHUP, terminates its child groups, and removes surviving reload descendants. Check the ports are released; never infer shutdown merely from a closed tool session.

Optional settings are documented in `.env.example`. Scripts **do not automatically load `.env`**; export desired settings in the shell. `FEA_ENV` accepts `local` or `test`, `FEA_AUTH_MODE` accepts only `local`, and `FEA_BIND_HOST` must be `127.0.0.1`. Other modes, including beta, fail before startup. `FEA_DATA_ROOT` must be an absolute writable directory outside the checkout; the default is `/tmp/openfea-data`, which is temporary and not a persistence guarantee. API/web port overrides are `FEA_API_PORT` and `FEA_WEB_PORT`. API startup now migrates SQLite under this root and persists local owner/project/analysis metadata. Choose a durable directory for ordinary local use; no private CAD or production secrets belong in this cloud workspace. Local session secrets remain in memory and reset on restart.

## Verification and unavailable gates

`make check` runs Python/TypeScript lint, formatting, static types, non-native unit tests, API contract drift and documentation links/task-graph/status checks. `make build` compiles the client. `make test-e2e` launches isolated services on dedicated ports 8001/5174 and runs real full-workflow Chromium coverage, including deliberate error and native failure paths. These Linux headless results are regression evidence, not Windows Chrome/Edge or human acceptance. [The separate Windows configuration](../playwright.local.config.ts) runs installed headed browsers against a separately started WSL2 backend; see [the packet](LOCAL_ACCEPTANCE.md).

`make test-integration` checks actual service termination/restart, sibling cleanup after a child exits, and refusal of occupied ports without disturbing the listener. Scripts activate `.venv/bin` for each invocation; shell activation is not assumed to persist. `make doctor` honors a configured `FEA_CCX_PATH` but marks an executable's presence as unvalidated until native checks exist.

`.venv/bin/python scripts/ci/failure_probes.py` introduces six temporary failing inputs to prove Python and TypeScript lint/type/unit failures reach Make. It refuses to overwrite existing files, removes probes in `finally`, and stores logs under `.local/failure-probes/`. Run it after the baseline checks pass, without concurrent edits in those paths.

Native availability is mandatory for complete setup. `make doctor` verifies pinned hashes and real CAD/mesh/VTK prerequisites; setup runs the full native suite through `bash scripts/codex/check.sh --require-native`. `make test-native` runs all native regression cases, including missing/tampered binary/network refusals. `make test-reports` exercises real PDF/DOCX content/layout/conversion. `make benchmark-m4 DEVELOPMENT=1 OUTPUT=<fresh-directory>` replays all fourteen frozen cases; `make m4-review` prints exact pending approvals. Default M4 acceptance refuses without them. Legacy `benchmark-all` and `test-security` are still fail-closed broader-release placeholders; local security cases run in unit/native/process/browser/report suites. Neither placeholder is a passing full-security certification.

The GitHub workflow uses pinned actions/runtime versions and runs early Word QA, full native plus fast/build/smoke/failure-propagation coverage, and independent integration/browser/report coverage. Consult the PR's latest-head checks for actual hosted outcomes. No cloud resources are provisioned.

For T025 PDF generation, the locked setup's Node/Playwright/Chromium and Bubblewrap must be present, with the system DejaVu Sans font (`fonts-dejavu-core` on Debian/Ubuntu). `make test-reports` additionally requires Poppler `pdftotext`/`pdftoppm` for content/layout review (`poppler-utils`). It runs actual CAD/mesh/CCX and isolated Chromium rather than mocking a successful export. Raw PDFs/model/HTML and layout audit are written under `.local/reports/T025/`; no private model belongs in committed evidence. The renderer does not download dependencies on demand.

T026 Word generation requires the root locked python-docx/lxml packages (`uv sync --locked` or normal `make setup`) and existing Node/Chromium/Bubblewrap/DejaVu runtime. `make test-reports` additionally requires LibreOffice Writer (`libreoffice-writer` on Debian/Ubuntu). QA resolves the system installation or managed runtime's bundled `soffice`, uses a private profile/network namespace, and fails if actual conversion is unavailable. Generated DOCX/counterpart PDFs/conversion PDFs and audits are under `.local/reports/T026/`. Only synthetic examples may be committed.
