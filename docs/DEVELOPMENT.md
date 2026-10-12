# Local development — T001 bootstrap

The current application is a health-only React client and FastAPI service. There is no CAD import, worker, queue, mesher, solver, persistence, authentication service, billing or report implementation. The current objective is the validated local prototype through M4/T030. AWS, Google authentication, commercial billing and beta operations are outside this stage.

## Supported environment and tools

Linux x86_64 / WSL2, Node **24.19.0** (LTS), npm **11.9.0**, Python **3.12.14**, uv **0.12.23**, Bash and GNU Make. Version pins are in `.node-version`, `.nvmrc`, `.python-version`, `.uv-version` and `package.json`. Setup rejects wrong Node/npm/uv versions, and uv locates or provisions the exact Python version. Docker and privileged execution are unnecessary for the bootstrap.

Install these prerequisites through trusted sources. If nvm is already installed, `nvm install` and `nvm use` select `.nvmrc` and retain nvm's archive checksum verification. To install uv in a separate tools virtual environment, use `python3 -m venv /tmp/openfea-tools`, then `/tmp/openfea-tools/bin/python -m pip install --only-binary=:all: --require-hashes -r scripts/ci/tool-requirements.txt` and add `/tmp/openfea-tools/bin` to your shell PATH. The hashed wheel requirements pin uv without a curl-to-shell installer. To reconcile npm with the Node distribution, use `npm install --global npm@11.9.0` in your user-managed Node installation. Project dependencies always use the committed locks.

Onboarding confirmed Python 3.12 wheels for candidate OCP/Gmsh/VTK/NumPy packages, with PyPI artifact hash verification recorded in [wheel-probe.json](validation/wheel-probe.json). This establishes ABI availability only. The candidates were not installed, loaded together or accepted as native pins. T002 must test shared libraries, licensed native builds and a real CCX solve; OCP and Gmsh must remain in separate processes.

## Setup and commands

From the repository root:

```sh
make setup
make doctor
make check
make build
make smoke
make test-integration
make test-e2e
make dev
```

`make setup` uses `uv sync --locked` and `npm ci`, then installs the locked Playwright Chromium headless shell and checks scratch/loopback prerequisites. It must not change either lockfile. The browser installer retains upstream TLS validation and downloads the revision selected by the locked Playwright package. Linux browser shared libraries must be available; if a fresh WSL2 installation lacks them, follow the official Playwright Linux dependency instructions with appropriate OS installation authority. Setup does not run privileged package installation or assume Docker. The prepared Codex instance passed the browser test without additional OS packages.

Caches, virtual environments, logs and browser binaries are ignored. Make and shell scripts set repository-local writable cache directories under `.local/`, avoiding read-only home directories. Python dependencies reside in `.venv/`; npm dependencies in `node_modules/`; web build outputs in `apps/web/dist/`. No installation or startup command rewrites application source, tests or dependency declarations.

`make dev` runs the real API and Vite processes on **127.0.0.1**, API port **8000** and web port **5173**. It waits for the health JSON directly and through the Vite proxy, and checks the web HTML entry point. Logs are in `.local/logs/`. API and frontend support hot reload. Ctrl-C/SIGTERM terminates the child process groups; an unexpected child exit fails the supervisor and stops its sibling. Occupied ports cause a failure before services are launched; existing processes are never reused or stopped. No worker is started because none is implemented. `make smoke` performs the same startup/readiness checks then shuts down.

The health page fetches `/api/v1/health`; it shows “API connected” only after validating the real response and reports “API unavailable” on a failed request. This means bootstrap connectivity, not FEA readiness. API schema/docs are under `/api/v1/openapi.json` and `/api/v1/docs`. Use `make contracts` to regenerate the checked-in OpenAPI and TypeScript types; `make contracts-check` fails on drift. The client compiles against the generated health response type.

Startup prints `SUPERVISOR pid=...` and the owned API/web process IDs. In a real terminal, Ctrl-C signals the foreground group and stops the services. This cloud tool's terminal-session interruption may disconnect without signaling the running Make/supervisor processes; if that occurs, send `kill -TERM` to the exact supervisor PID recorded for the session you started. The supervisor handles SIGINT, SIGTERM and SIGHUP, terminates its child groups, and removes surviving reload descendants. Check the ports are released; never infer shutdown merely from a closed tool session.

Optional settings are documented in `.env.example`. Scripts **do not automatically load `.env`**; export desired settings in the shell. `FEA_ENV` accepts `local` or `test`, `FEA_AUTH_MODE` accepts only `local`, and `FEA_BIND_HOST` must be `127.0.0.1`. Other modes, including beta, fail before startup. `FEA_DATA_ROOT` must be an absolute writable directory outside the checkout; the default is `/tmp/openfea-data`, which is temporary and not a persistence guarantee. API/web port overrides are `FEA_API_PORT` and `FEA_WEB_PORT`. No project data or secrets are stored by the bootstrap.

## Verification and unavailable gates

`make check` runs Python/TypeScript lint, formatting, static types, non-native unit tests, API contract drift and documentation links/task-graph/status checks. `make build` compiles the client. `make test-e2e` launches its own services on dedicated ports 8001/5174 and runs Chromium against the real UI/API; its second case deliberately aborts the health request to test failure display. These are health tests, not solver tests or Windows Chrome/Edge product acceptance.

`make test-integration` checks actual service termination/restart, sibling cleanup after a child exits, and refusal of occupied ports without disturbing the listener. Scripts activate `.venv/bin` for each invocation; shell activation is not assumed to persist. `make doctor` honors a configured `FEA_CCX_PATH` but marks an executable's presence as unvalidated until native checks exist.

`.venv/bin/python scripts/ci/failure_probes.py` introduces six temporary failing inputs to prove Python and TypeScript lint/type/unit failures reach Make. It refuses to overwrite existing files, removes probes in `finally`, and stores logs under `.local/failure-probes/`. Run it after the baseline checks pass, without concurrent edits in those paths.

`make doctor` distinguishes optional missing native capabilities from required bootstrap prerequisites. `bash scripts/codex/check.sh --require-native` exits nonzero until real native validation exists. `make test-native`, `benchmark`, `benchmark-all`, `test-security` and `test-reports` deliberately exit nonzero with the missing implementation/gate named. Full ownership/archive/job security tests are future work; the local startup guard tests already run in `test-unit`. Do not count unavailable targets as passed or skipped numerical tests. See [T001 evidence](validation/T001.md).

The GitHub PR/manual workflow runs the same bootstrap checks with pinned action commits and runtime versions. It has not been executed on GitHub in this session. No cloud resources are provisioned.
