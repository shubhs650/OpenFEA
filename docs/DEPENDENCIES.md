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

T001 selects supported Node LTS and Python version only after resolving binary wheel constraints (Python 3.11 is a conservative candidate). Commit lockfiles and a dependency report listing exact versions, hashes, upstream URLs, licenses and known limitations. No dependency upgrades silently during environment boot.

Isolation by subprocess is an engineering boundary, not a blanket exemption from license obligations. Do not publish an MIT/AGPL/GPL license file by guesswork. Record license review and owner selection in ADR-006 before public code/container release. Documentation kit is supplied for the user's project; this does not relicense third-party sources.
