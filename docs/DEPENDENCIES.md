# Dependencies, licenses and version locks

All component choices are open-source candidates. This document does not select the application's final license or assert legal compatibility. Audit source, binaries, Python wheels, fonts, JS bundles and transitive/native linear algebra libraries before redistribution.

| Component | Intended use | M0 action |
|---|---|---|
| CalculiX CCX | CPU linear static solver, candidate 2.23 | Official source/binary checksum; output/version tests; verify complete build license chain |
| Gmsh | Quadratic tetra meshes and physical groups | Pin stable release; inspect GPL/commercial terms and distribution obligations; open-source route only |
| OCCT + OCP binding | STEP, BREP, repair/defeaturing | Separate binding/kernel licenses; Linux wheel/build compatibility; track bundled kernel version |
| VTK / vtk.js | Authoritative volume transforms / browser rendering | Verify supported array/cell paths and license notices |
| React/Vite/TypeScript/Zustand/TanStack Query | UI tooling | Lock tested compatible releases; no latest tags in CI |
| FastAPI/Pydantic/SQLAlchemy/Alembic | API, schema, storage | Lock Python deps and migration behavior |
| NumPy, Jinja, python-docx, PDF renderer | Numerics and reports | Font license, headless Linux rendering, output QA |
| Authlib or equivalent maintained OIDC library | Google authentication | Choose one; verify token validation/cookie integration, do not handroll OAuth |
| OpenTofu, OCI runtime | Infrastructure/local isolation | Version and deployment compatibility; daemonless cloud-dev path |

T001 pins Node LTS 24.19.0, npm 11.9.0, Python 3.12.14 and uv 0.12.23; see [ADR-009](adr/ADR-009.md). Python 3.12 candidate wheel availability was checked before selecting the runtime; [wheel evidence](validation/wheel-probe.json) includes exact versions, upstream URLs and verified SHA-256 hashes. This does not select or validate the native toolchain: T002 must prove native compatibility and inventory distribution obligations.

`package-lock.json` and `uv.lock` record exact development dependencies and artifact integrity. The generated [dependency report](validation/dependencies.json) records every registry lock entry's versions, upstream URLs, hashes and license metadata (including installed wheel license text where metadata is absent). Regenerate explicitly with `.venv/bin/python scripts/ci/dependency_report.py`; this requires PyPI access and does not upgrade dependencies. uv bootstrap wheel hashes are in `scripts/ci/tool-requirements.txt`. The report is an inventory, not legal approval; native components and final project license remain deferred to T002/ADR-006. No dependency upgrades occur silently during environment boot.

Isolation by subprocess is an engineering boundary, not a blanket exemption from license obligations. Do not publish an MIT/AGPL/GPL license file by guesswork. Record license review and owner selection in ADR-006 before public code/container release. Documentation kit is supplied for the user's project; this does not relicense third-party sources.
