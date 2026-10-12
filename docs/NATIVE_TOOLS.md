# Native development toolchain — T002

This prepares native library/solver availability, not an application analysis feature. The API/UI remain health-only. No queue, user-authored deck execution, production worker or solve screen exists.

## Provisioning and isolation

Validated on **Debian 13, Linux x86_64, glibc 2.41**, with GCC 14.2.0 and Python 3.12.14. Bash, Make, gcc, ar, dpkg-deb and pinned uv are prerequisites. Other WSL2/Linux distributions have not been validated; the CI workflow prepares GCC 14 on Ubuntu but has not run on GitHub. Missing/wrong prerequisites fail clearly. No Docker daemon, root writes or extra credentials are required in Codex.

Run `make setup` for the complete locked environment, or `make setup-native` after bootstrap dependencies exist. Native installation uses `scripts/native/toolchain-lock.json` and three committed uv locks. Source archives are pinned from versioned official HTTPS downloads; upstream provides no separate source checksum, so the initially reviewed SHA-256 pins are enforced thereafter. Debian package pins were checked against Packages metadata authenticated by the signed trixie InRelease. Subsequent direct package downloads must match those reviewed hashes. TLS, signatures and checksums were never disabled.

All artifacts live under ignored `.local/native/`: `downloads/`, `sysroot/`, `build/`, `bin/`, `lib/`, `venvs/` and `validation/`. No system packages are changed. CCX builds use four jobs; SPOOLES uses one because recursive makes update a shared archive. `build.json` records source/toolchain/installer inputs and output hashes. A second setup reuses the build only when these hashes match. Changing build inputs triggers a rebuild. Cached checksum mismatches fail, rather than changing the expected hash.

| Role | Environment/tool | Actual native versions |
|---|---|---|
| CAD | `.local/native/venvs/cad/bin/python` | OCP 8.0.1.1.0, bundled OCCT 8.0.1, required VTK 9.6.2 |
| Mesh | `.local/native/venvs/mesh/bin/python` | Gmsh 4.15.2 with bundled OCCT 7.8.1 |
| Postprocessing | `.local/native/venvs/post/bin/python` | VTK 9.7.1 |
| Shared array dependency | separately locked in each environment | NumPy 2.5.4 |
| CPU solver | `.local/native/bin/ccx` | CCX 2.23, serial SPOOLES 2.2 + official correction; ARPACK-NG 3.9.1, Netlib BLAS/LAPACK 3.12.1, 32-bit solver integers |

Never activate OCP and Gmsh in one interpreter. OCP's VTK dependency remains in CAD; postprocessing has its own version. T003 now exchanges immutable synthetic SI BREP/catalog files between CAD and meshing processes, with verified face mapping and C3D10/load export; see [ADR-011](adr/ADR-011.md). NumPy wheel OpenBLAS components do not replace CCX's explicitly linked Netlib/SPOOLES libraries.

## Commands and native process boundary

`make doctor` verifies native binary/library hashes and performs real CAD/mesh/VTK operations in separate processes. `bash scripts/codex/check.sh --require-native` also runs all 23 native tests. `make test-native` includes the original nine toolchain checks plus three synthetic mapping cases, eight pressure-face/sign cases, two analytical development cases and a two-face total-force solve.

`make benchmark CASE=B01 DEVELOPMENT=1` (or B02) runs two meshes through the actual synthetic STEP/CAD/mesh/deck/CCX workflow. Outputs are under `.local/native/benchmarks/<case>/`. Without development mode, unsigned acceptance fails with exit 2. The owner deferred B01/B02 engineering review; [T003 evidence](validation/T003.md) retains frozen manifests, actual decks/DAT/transcripts and measured errors. General curved geometry/elements, ties and production stress output remain later work.

`worker.runtime` is an internal development primitive. It verifies the workspace CCX/launcher/library hashes, closes inherited descriptors, passes a minimal environment without proxy/authentication variables, and launches the owned process group through the compiled `netdeny` helper. Optional `FEA_CCX_PATH` must resolve to the pinned workspace executable so the verified runtime libraries remain the loaded ones. Foreign binaries are rejected.

Linux network namespaces are unavailable in this cloud host (`unshare` cannot write uid_map). The fallback applies `no_new_privs` and an inherited seccomp filter denying all socket/socketpair creation, including IPv4 TCP/UDP and IPv6. Actual denial is tested in all three interpreters. Native subprocesses are limited to 60 CPU seconds, 4 GiB address space, 64 MiB per regular output file, 64 descriptors, no core files, one thread setting, and a 90-second wall timeout; owned descendants are retired on completion. Installation networking remains available; no network is needed or permitted during the solve.

This is **not** a complete hostile-upload/filesystem sandbox. It does not claim a total per-job disk quota or bounded captured pipe logs; no untrusted user files/jobs are accepted. Filesystem access/caps and production isolation require later implementations and security gates. Do not expose the internal launcher as an arbitrary executable/deck API.

## Solver fixture and evidence

`tests/fixtures/native/smoke.inp` is a project-authored SI affine field on one manually ordered C3D10 tetrahedron. Twenty-nine displacements are prescribed; node 2's axial DOF is free. CCX must assemble/factor one equation. Isotropic Hooke law predicts ux=0.001 m and sigma_xx=210 MPa, with other stresses zero. Expected values and unchanged tolerances are in `smoke.json`, declared before the first solve. This is a development availability smoke, not an engineering-owner-approved release benchmark or proof of Gmsh connectivity/stress provenance/ties.

`make test-native` stores the latest passed synthetic result, probe versions, DAT and transcript under `.local/native/validation/`. [Committed T002 evidence](validation/T002.md) records the tested code commit and small actual output. `make native-report` explicitly regenerates the tracked [dependency inventory](validation/native-dependencies.json) and upstream license copies; it uses PyPI access and is a review operation, **not** an installation/startup step. Setup never rewrites tracked evidence or manifests.

Modern GNU compatibility flags are recorded in `build.json`: C `-fcommon` and `-Wno-error=return-mismatch`; Fortran `-fallow-argument-mismatch`. These preserve upstream source semantics while handling old common-symbol/return/argument conventions. The documented SPOOLES drawTree/draw filename correction and official I2Ohash correction affect only extracted build copies. No numerical source or tolerance was altered. CCX's embedded upstream executable-date text is retained from the source archive; it is not our build date. Use the actual built binary hash and evidence, not that string, as identity.

## License handoff

The [inventory](validation/native-dependencies.json), [version-matched license source list](validation/native-licenses/sources.json) and [dependency matrix](DEPENDENCIES.md) record licenses and hashes. CCX/SPOOLES, ARPACK/BLAS/LAPACK and GNU runtime provenance are explicit; no MKL/PARDISO/proprietary backend is enabled. Wheel metadata and the OCP bundled-component SBOM do not establish complete redistribution compliance. Final project license and bundled attribution/source/relinking review remain deferred under ADR-006. No public release is authorized by this task.
