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

T007 adds SQLAlchemy **2.1.4** (MIT), Alembic **1.20.0** (MIT), Mako **1.4.3** (MIT) and MarkupSafe **3.0.4** (BSD-3-Clause) to the root lock and inventory. Existing root/native/browser versions remain unchanged; actual reversible SQLite migrations and local API behavior are tested in [T007 evidence](validation/T007.md). This is not a final redistribution approval.

## T002 pinned native matrix

Native availability is now executed evidence. Historical T001 wheel downloads remain an ABI probe; actual installation pins are the three worker environment uv locks and `scripts/native/toolchain-lock.json`. [ADR-010](adr/ADR-010.md), [native setup](NATIVE_TOOLS.md) and [T002 results](validation/T002.md) describe the tested configuration.

| Component | Exact version / backend | License evidence / limit |
|---|---|---|
| CCX CPU | 2.23, 32-bit integers, GNU 14.2.0 | GPLv2-family source headers; entrypoint/header wording differs, retain complete source and review before redistribution |
| SPOOLES | 2.2 serial; official CCX 2.23 I2Ohash correction | Upstream public-domain release; correction comes from CCX's GPL source distribution |
| ARPACK-NG | Debian 3.9.1-6, static archive | BSD-3-Clause, Debian copyright notice |
| Netlib BLAS/LAPACK | Debian 3.12.1-6, static archives | BSD-3-Clause and bundled notices; no Intel MKL |
| GNU compiler/runtime | Debian 14.2.0-19 | Compiler GPLv3-family; runtime exception and component notices recorded |
| OCP binding | 8.0.1.1.0; proxy same version | Apache-2.0, exact upstream tag license |
| CAD OCCT | 8.0.1 (bundled library SONAME) | LGPL-2.1 with version-matched upstream exception |
| CAD VTK | 9.6.2 required by OCP wheel | BSD family; separate from post interpreter |
| Gmsh | 4.15.2, OCCT 7.8.1 in build info | GPL-2.0-or-later plus upstream linking exception; bundled component review still required |
| Post VTK | 9.7.1 | Version-matched BSD-3-Clause copyright notice |
| NumPy | 2.5.4 in each interpreter | BSD-3-Clause/0BSD/MIT/Zlib/CC0 plus wheel/native runtime notices; OpenBLAS wheel backend is separate from CCX |
| Base runtime | Debian 13, glibc 2.41, host GCC 14.2.0 | Base-image/system-library licenses also apply; Ubuntu CI/other WSL distributions not yet executed |

The [machine inventory](validation/native-dependencies.json) records 14 CAD, 2 mesh and 12 post installed packages, matching wheel URLs/SHA-256 pins, installed shared-library hashes and license metadata. The OCP wheel's bundled-component SBOM is preserved; its absent per-component license fields require source/notice review before public distribution. [License sources](validation/native-licenses/sources.json) pin version-matched OCCT/OCP/VTK notices. Gmsh and Debian numerical/runtime notices are copied from verified artifacts. Setup does not regenerate tracked reports; `make native-report` does so only as an explicit review operation.

This satisfies the T002 development inventory and real native smoke requirement. It does not choose a public project license, assert legal compatibility of the combined distribution, or waive source/relinking/attribution obligations. ADR-006 remains deferred.

## T008 import and browser additions

The browser pins `@kitware/vtk.js` **37.4.2** (BSD-3-Clause) with 57 new npm registry entries; prior package versions are unchanged. The root inventory now has 34 Python / 250 npm entries. Native OCP/mesh/post/CCX locks and binaries are unchanged. Linux STEP import additionally requires the distribution Bubblewrap executable (cloud **0.12.0**, LGPL-2.1-or-later; upstream https://github.com/containers/bubblewrap). Its actual executable hash/version is recorded per inspection along with the CAD binding/python, worker, seccomp filter and CAD lock. Runtime availability/namespaces are verified by doctor and native tests; there is no unconfined fallback. CI explicitly installs the system package. [ADR-016](adr/ADR-016.md) describes this system-runtime boundary; final project redistribution approval is still deferred.

T025 reuses the existing locked Playwright 1.64.0 and its matching Chromium headless-shell revision 1248 for offline A4 rendering; no registry/native locks change. DejaVu Sans (`fonts-dejavu-core`, permissive Bitstream Vera/DejaVu font notices) is required as a system report font; its actual regular-font SHA-256 is retained. Chromium retains its upstream BSD/third-party notices in the existing installed browser. Poppler (`poppler-utils`, GPL family) is used only by report verification for text, A4 bounds and rendered-page review; it is not linked into the application. CI installs the font and verification tools as system packages. Actual versions/hashes and remaining redistribution review are in [T025 evidence](validation/T025.md); no public-distribution license decision is implied.

T026 explicitly adds python-docx 1.2.0 (MIT) and pins its lxml dependency to 6.0.2 (BSD; bundled XML/XSLT notices remain applicable). `uv.lock` retains exact wheel/sdist hashes and the [inventory](validation/dependencies.json) is regenerated. Existing npm and native toolchain locks/binaries are unchanged. The production Word worker reuses locked Chromium/DejaVu and needs no office suite. Actual DOCX-to-PDF verification additionally requires LibreOffice Writer (MPL/LGPL and bundled notices), installed as a system QA dependency in CI; cloud and CI versions are recorded rather than claimed identical. No public redistribution approval is supplied here; see [T026 evidence](validation/T026.md).
