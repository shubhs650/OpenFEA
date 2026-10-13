# Local development — bootstrap and project persistence

The React client now creates/opens projects and runs real T008 STEP inspection/confirmation/selection; FastAPI serves the persistent project/import/geometry APIs. See [STEP usage](STEP_IMPORT.md). See [local storage/API usage](PERSISTENCE.md). T002 adds the real native tools and smoke runner described in [NATIVE_TOOLS.md](NATIVE_TOOLS.md). STEP import/display works; the complete material/mesh/solve workflow, durable worker/queue, hosted authentication, billing and reports remain later tasks. The objective remains the validated local prototype through M4/T030; hosted operations are outside this stage.

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

`make dev` runs the real API and Vite processes on **127.0.0.1**, API port **8000** and web port **5173**. It waits for the health JSON directly and through the Vite proxy, and checks the web HTML entry point. Logs are in `.local/logs/`. API and frontend support hot reload. Ctrl-C/SIGTERM terminates the child process groups; an unexpected child exit fails the supervisor and stops its sibling. Occupied ports cause a failure before services are launched; existing processes are never reused or stopped. No worker is started because none is implemented. `make smoke` performs the same startup/readiness checks then shuts down.

The health page fetches `/api/v1/health`; it shows “API connected” only after validating the real response and reports “API unavailable” on a failed request. This means bootstrap connectivity, not FEA readiness. Project/session routes and their usage are described in [PERSISTENCE.md](PERSISTENCE.md). The Vite proxy preserves Host for Origin checks, and Uvicorn proxy headers are disabled. API schema/docs are under `/api/v1/openapi.json` and `/api/v1/docs`. Use `make contracts` to regenerate the checked-in OpenAPI and TypeScript types; `make contracts-check` fails on drift. The client compiles against the generated health response type.

Startup prints `SUPERVISOR pid=...` and the owned API/web process IDs. In a real terminal, Ctrl-C signals the foreground group and stops the services. This cloud tool's terminal-session interruption may disconnect without signaling the running Make/supervisor processes; if that occurs, send `kill -TERM` to the exact supervisor PID recorded for the session you started. The supervisor handles SIGINT, SIGTERM and SIGHUP, terminates its child groups, and removes surviving reload descendants. Check the ports are released; never infer shutdown merely from a closed tool session.

Optional settings are documented in `.env.example`. Scripts **do not automatically load `.env`**; export desired settings in the shell. `FEA_ENV` accepts `local` or `test`, `FEA_AUTH_MODE` accepts only `local`, and `FEA_BIND_HOST` must be `127.0.0.1`. Other modes, including beta, fail before startup. `FEA_DATA_ROOT` must be an absolute writable directory outside the checkout; the default is `/tmp/openfea-data`, which is temporary and not a persistence guarantee. API/web port overrides are `FEA_API_PORT` and `FEA_WEB_PORT`. API startup now migrates SQLite under this root and persists local owner/project/analysis metadata. Choose a durable directory for ordinary local use; no private CAD or production secrets belong in this cloud workspace. Local session secrets remain in memory and reset on restart.

## Verification and unavailable gates

`make check` runs Python/TypeScript lint, formatting, static types, non-native unit tests, API contract drift and documentation links/task-graph/status checks. `make build` compiles the client. `make test-e2e` launches its own services on dedicated ports 8001/5174 and runs Chromium against the real UI/API; its second case deliberately aborts the health request to test failure display. These are health tests, not solver tests or Windows Chrome/Edge product acceptance.

`make test-integration` checks actual service termination/restart, sibling cleanup after a child exits, and refusal of occupied ports without disturbing the listener. Scripts activate `.venv/bin` for each invocation; shell activation is not assumed to persist. `make doctor` honors a configured `FEA_CCX_PATH` but marks an executable's presence as unvalidated until native checks exist.

`.venv/bin/python scripts/ci/failure_probes.py` introduces six temporary failing inputs to prove Python and TypeScript lint/type/unit failures reach Make. It refuses to overwrite existing files, removes probes in `finally`, and stores logs under `.local/failure-probes/`. Run it after the baseline checks pass, without concurrent edits in those paths.

Native availability is now mandatory for complete setup. `make doctor` verifies CCX/library hashes and real CAD/mesh/VTK operations; `bash scripts/codex/check.sh --require-native` also runs nine native tests. `make test-native` performs the T002 availability smoke and explicit missing/tampered binary/network tests. Benchmark, full security and report targets remain BLOCKED; T007 local ownership/session/revision tests run in the fast unit suite. Health/startup guards remain in fast tests. See [T001 evidence](validation/T001.md) and [T002 evidence](validation/T002.md); neither closes the full engineering workflow.

The GitHub PR/manual workflow runs the same bootstrap checks with pinned action commits and runtime versions. It has not been executed on GitHub in this session. No cloud resources are provisioned.
