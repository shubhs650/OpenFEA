# M3 engineering-owner review packet

Prepared: 2026-10-15 (Asia/Calcutta). **Review PENDING; this is not an owner decision.** The [exit review](M3-exit-review.md) remains BLOCKED. The [machine packet](results/T024/owner-review-packet.json) includes full manifest/source identities; [T024 evidence](T024.md) provides per-mesh expected/actual/error/limit context and retained raw synthetic results.

The product owner is the engineering reviewer under [VALIDATION](../VALIDATION.md). T024 specifically requires owner review; [M3](../plan/M3.md) requires physical-assumption and tolerance review before progression. Coding agents cannot certify these decisions. The earlier cloud-development/laptop deferral does not approve exact criteria or M3's bond formulation.

## Scope to review

1. Existing B01–B09/B11 analytical/diagnostic definitions, materials, loads/supports, physical sample regions, mesh ladders, absolute/relative tolerances and exclusions remain unchanged. B03 is an explicitly disclosed slender-solid/Euler–Bernoulli approximation, not exact solid or cross-solver truth. B09 tests provenance/material jumps, not convergence. B11 requires invalid-setup refusal; its huge finite native output is never a valid result.
2. B07 uses consistent planar mortar `M_slave*u_slave=C_slave_master*u_master` emitted as deterministic global CCX EQUATION rows. Native TIE revision 1 remains rejected. Both role orientations and an independent monolithic continuum match the frozen criteria without moving nodes.
3. Supported product scope remains two independent bodies, one full axis-aligned planar **zero-gap unit-square interface**, at most **65 nodes per trace**. Existing independent material/face identities, complete coverage, necessary supports, native equation count, written-coefficient continuity, raw output and external force/moment checks are mandatory. Necessary rank is not a stability certificate. No weak springs, hidden force redistribution, coarsening, node dropping or automatic retries.
4. B08 validates only its ideal **10 µm axial displacement-continuity/zero-compliance experiment**. It does not validate adhesive/contact behavior or general rigid rotation/shear/bending across a void. Reviewed physical gaps remain blocked for product solves. General, curved, nonunit/partial, multiple-bond and transformed bonded constraints remain unsupported.
5. Full fields, body/material-partitioned smoothing, explicit physical-side probes, authoritative volume sections and comparisons retain warnings, physical coordinates and immutable raw/source identities. A stable point, declining peak, necessary preflight or successfully finished solve never proves convergence, accuracy, stability or design safety.
6. This is bounded Linux cloud development. Reports/archives, B10/B12 and external references, Windows/WSL2 target-laptop/headed GPU/performance/resource/usability and final M4 acceptance remain their scheduled obligations; no AWS/deployment/beta release is authorized.

The [M3 manifest](../../tests/benchmarks/M3.json) binds the full scope and exact referenced criteria/formulation documents. A review hash is SHA-256 of every manifest field except `reviewer_signoff`, using sorted compact canonical JSON with no NaN. Approval applies only to the listed frozen hashes, not future changed criteria.

## Exact criteria records

| Record | Frozen manifest and evidence | Canonical criteria SHA-256 | Owner disposition |
| --- | --- | --- | --- |
| B01 | [B01.json](../../tests/benchmarks/B01.json) · [result](results/T024/benchmarks/B01.json) · [raw](results/T024/B01-raw.tar.gz) | `5edf7fcbd1834fbca4133fe61d3b8bdee970dbed08523401f606927ba3b17bf5` | PENDING |
| B02 | [B02.json](../../tests/benchmarks/B02.json) · [result](results/T024/benchmarks/B02.json) · [raw](results/T024/B02-raw.tar.gz) | `8d427332489761f1f3404b33eb82c1868592b7f6411f94ea0d212b1e2c3baf1d` | PENDING |
| B03 | [B03.json](../../tests/benchmarks/B03.json) · [result](results/T024/benchmarks/B03.json) · [raw](results/T024/B03-raw.tar.gz) | `601ac8ab828d2733b990ce4478609d5b93b5c746bc23ae01af7d3a7738b0d465` | PENDING |
| B04 | [B04.json](../../tests/benchmarks/B04.json) · [result](results/T024/benchmarks/B04.json) · [raw](results/T024/B04-raw.tar.gz) | `04cac6e33e6618957a6e45cafa6cd89038f5051f7ea7947ff466b8187dc7bd46` | PENDING |
| B05 | [B05.json](../../tests/benchmarks/B05.json) · [result](results/T024/benchmarks/B05.json) · [raw](results/T024/B05-raw.tar.gz) | `3115b64cccb907353dc7d2331a9e520b875e5c2d85bedb9b0eaafeeec1b2c465` | PENDING |
| B06 | [B06.json](../../tests/benchmarks/B06.json) · [result](results/T024/benchmarks/B06.json) · [raw](results/T024/B06-raw.tar.gz) | `eb88f1e475f58b74f681e826a95a1d311c23e704b1f5cc44741e22b85065fed6` | PENDING |
| B07 | [B07-mortar.json](../../tests/benchmarks/B07-mortar.json) · [result](results/T024/benchmarks/B07.json) · [raw](results/T024/B07-raw.tar.gz) | `d68c15e77da9be3402a2248be93c2f3ee57a9487ac5704a5be8d8b9ce620d23d` | PENDING |
| B08 | [B08.json](../../tests/benchmarks/B08.json) · [result](results/T024/benchmarks/B08.json) · [raw](results/T024/B08-raw.tar.gz) | `657334c736934d5e3843ac170a25bb91f0429be9e853db73c9a8ad5817d31029` | PENDING |
| B09 | [B09.json](../../tests/benchmarks/B09.json) · [result](results/T024/benchmarks/B09.json) · [raw](results/T024/B09-raw.tar.gz) | `5094fa2124b32d17e6f27fd864309779766071a2ffb5d6312cc30206faead65e` | PENDING |
| B11 | [B11.json](../../tests/benchmarks/B11.json) · [result](results/T024/benchmarks/B11.json) · [raw](results/T024/B11-raw.tar.gz) | `1590dbbb695b170f7d58b550853282864fa421135510c76be8f656a94468b7d4` | PENDING |
| M3 | [M3.json](../../tests/benchmarks/M3.json) · [suite](results/T024/benchmark-summary.json) | `908d1f323a5aac1ca65ee66bf15aaf43bf377f345d187e437e5b351a1b6e0843` | PENDING |

## Decision record required

After inspecting the scope, error tables and raw/source evidence, the actual engineering owner supplies a reviewer name, ISO date and APPROVED or REJECTED disposition for the listed exact criteria and M3 scope. Record a real decision using the existing `reviewer_signoff` object (`disposition`, `reviewer`, `reviewed_on`, `criteria_sha256`); do not copy synthetic unit-test reviewer records. If any assumption/limit is unacceptable, retain a blocker and define the required scientific correction rather than loosening criteria to obtain a pass.

After approval records exist, run `make benchmark-m3 OUTPUT=<fresh-directory>` without DEVELOPMENT. Record the acceptance results and complete the product exit review before closing T024/M3 or starting T025. Current diagnostic runs remain development-only even if a later record approves identical criteria. Merging this PR alone does not constitute that approval.
