# Benchmark registry

B01/B02 have [T003](T003.md), B09 has [T004](T004.md), and B07 has [T005](T005.md) development evidence. B07 native *TIE revision 1 failed; separately predeclared mortar revision 2 passes identical physical criteria within its documented scope. Frozen manifests remain under `tests/benchmarks/`; owner/formulation acceptance is pending. B03–B05 have [T015](T015.md) two-mesh DEVELOPMENT PASS evidence; B03 revision 1 coarse stress failure remains retained and revision 2 explicitly refines without changing physical criteria. B06 has [T016](T016.md) exact continuum DEVELOPMENT PASS on both meshes at identity and rotated/translated placements. B08 has [T019](T019.md) DEVELOPMENT PASS evidence for both roles in a separately declared 10 µm unit-block axial displacement-continuity experiment, with complete node/equation coverage and zero native coordinate adjustment; owner acceptance and general gap/shear/bending behavior remain pending. B10–B14 are unexecuted. Never treat development evidence as signed release acceptance.

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
