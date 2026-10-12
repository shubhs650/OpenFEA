# Benchmark registry

B01/B02 have [real T003 development evidence](T003.md), with exact frozen manifests under `tests/benchmarks/`. The owner chose development-only and deferred review; signed acceptance remains pending. B03–B14 are not executed. Never treat the development result as a signed release pass.

| ID | Case and purpose | Reference / sampled quantities | Planned task |
|---|---|---|---|
| B01 | Constant-strain tetra/block patch | Analytic displacement and full stress tensor; orientation/permutation | T003 |
| B02 | Axially loaded 3D block | u=FL/AE, sigma=F/A away from constrained end | T003 |
| B03 | Slender solid cantilever | Declared Euler–Bernoulli or Timoshenko displacement; finite-width assumptions | T015 |
| B04 | Pressure-loaded symmetric solid | Analytic resultant/reactions; all face normals; avoid unvalidated thin-shell assumptions | T015 |
| B05 | Gravity-loaded block | Weight=rho*V*g, support reactions and displacement | T015 |
| B06 | Rotated supports/directional displacement | Rotational invariance and correct transformed constraints | T016 |
| B07 | Bonded two-block patch | Compare independently meshed tie with monolithic continuum | T005 |
| B08 | Bonded small-gap case | Explicit gap model, tie coverage, displacement adjustment and documented assumptions | T019 |
| B09 | Material jump at interface | Unaveraged fields retain discontinuity; no cross-material smoothing | T004 |
| B10 | Filleted mounting bracket | Tutorial convergence, selected interior samples; no analytical peak claim | T028 |
| B11 | Rigid-body/disconnected assembly | Must fail with actionable diagnosis, no stabilization | T020 |
| B12 | Public external verification case | Select compatible 3D linear-elastic case from official CalculiX suite | T028 |
| B13 | Code_Aster reference comparison | Identify exact public case and version; independently reconstruct where permitted | T028 |
| B14 | ANSYS reference comparison | Select applicable solid structural verification case; match assumptions | T028 |

B12–B14 case numbers are intentionally not invented. Selection, accessibility, permission, mathematical equivalence and quantity-specific tolerance are deliverables of T028. Do not convert a truss/beam benchmark into a solid benchmark without accounting for end effects and changed kinematics. Publicly viewable documentation does not automatically permit bundling its models or text.

Mandatory release evidence includes B01–B11 and B12. B13/B14 comparisons are desired supporting evidence; if unavailable or incompatible, record the reason and owner-approved replacement with a rigorous analytical/CalculiX case. Do not claim cross-solver validation without it.
