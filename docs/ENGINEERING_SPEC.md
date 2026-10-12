# Engineering semantics

This is an implementation contract, not a replacement for the pinned CalculiX manual. Confirm keyword/output details against that version before emitting decks.

## Units and materials

Store all physical quantities in SI: m, N, Pa, kg, s. Density is kg/m³, gravity m/s². A mm–N–MPa display never means storing density in kg/mm³ without conversion. Parse STEP length metadata and require dimension confirmation; missing/ambiguous units block solve until user confirmation. Display switching must round-trip internal values without repeated rounding.
Isotropic E > 0; -1 < nu < 0.5; density > 0 when gravity is used; yield > 0 when yield factor is requested. Warn on near-incompressibility with displacement tetrahedra and block outside the validated material range. Initial proposed tested range nu=0..0.45; auxetic or near-incompressible values require validation before enabling, rather than pretending all mathematically valid values are supported. Validate this policy in M0. Materials include provenance, grade/condition, applicable temperature note and user confirmation. Generic entries are examples, not certified allowables.

## Mesh and element identities

C3D10 only. Verify Gmsh-to-CCX permutation against a hand-built ten-node tetrahedron, including all six midside nodes and four oriented quadratic faces. Test positive determinant over the integration domain, not just corner volume. Preserve global node IDs, per-body ownership and CAD face membership. No remeshing after run snapshot creation.
Initial target 100,000 elements is not a hard capacity guarantee. Estimate nodes/DOFs and sparse-factorization memory from calibration; do not use a constant bytes-per-element promise. Detect disk limits as well as RAM. Offer a coarser mesh with explicit acceptance and invalidate prior mesh-dependent results.
Proposed mesh recovery: initial attempt plus at most two alternatives, deterministic sequence captured in logs. May modify algorithm/optimization settings within validated policy; do not coarsen user sizing without approval or alter geometry. Quality metrics and thresholds are frozen from M0 fixtures.

## Loads and constraints

Uniform pressure acts inward for positive compressive pressure; show arrows and test outward normal/sign for each element face. Negative values explicitly mean outward traction. Integrate over curved quadratic faces using a validated quadrature mapping.
Distributed face force is a total vector over the complete selected face set, not that total once per face. Convert to uniform traction F / total selected area, then consistent nodal loads; verify resultant and moment. Document uniform-traction semantics, since they differ from remote rigid coupling. Exclude unsupported remote moments and point loads.
Fixed support constrains translations. Directional displacement constrains a specified component in an orthonormal basis while leaving others free. Symmetry constrains normal displacement on a planar face. Reject ambiguous curved symmetry and contradictory constraints at shared nodes. Shared edges inherit face constraints; edge picking is for direction only, not load targets.
Gravity is acceleration and needs density. Deduplicate overlapping face selections, detect pressure/force duplication and let users intentionally combine distinct loads with a visible resultant summary. Do not silently cancel conflicting inputs.

## Bonding

Use a validated CCX tie formulation for independently meshed bodies. Review master/slave designation, tolerance, projected nodes, uncovered regions and redundant constraints. M0 determines exact supported keywords and whether the pinned tie formulation repositions slave nodes. Any solver-induced movement must be disabled where supported or made explicit, quantified and approved; it must never be hidden as geometry unchanged.
Candidate detection uses opposing normals, overlap area and separation, not bounding boxes alone. Reject body volume overlaps beyond declared geometric tolerance. Distinguish numerical coincidence tolerance from a user-approved physical gap. Check all intended interface nodes are tied and no unintended nodes are captured. Prevent ties from forcing an unsupported rigid connection across arbitrary gaps. Small-gap maximum is benchmark-derived and visible, not a universal number.
Preflight connected-body graph and support coverage are heuristics, not a proof of stiffness rank. Solver singularity detection is a second gate. Never auto-add weak springs.

## Stress and derived quantities

Keep all six tensor components with explicit order (xx, yy, zz, xy, yz, zx), frame, location type and stress units. Principal stresses are sorted eigenvalues of the symmetric tensor. Von Mises is sqrt(((sx-sy)^2+(sy-sz)^2+(sz-sx)^2)/2 + 3*(txy^2+tyz^2+tzx^2)). Test hydrostatic, uniaxial and pure-shear tensors independently.
Smoothed nodal stress is a documented derived field; unaveraged element-nodal stress and integration-point stress are distinct. Never mix body/material sides during smoothing. Probe returns entity, position, location convention, interpolation method and value. Element-associated contours duplicate vertices where needed to preserve jumps.
Yield factor = specified material yield / von Mises for ductile materials. Missing yield => unavailable; essentially zero stress => unbounded/undefined display, not a fabricated finite safe value. No fatigue, brittle failure, buckling or code checks implied. Minima near singularities retain warnings.

## Verification and model limitations

Force residual = norm(sum applied + sum external reactions) / max(sum magnitudes of applied loads, documented reference force). Use absolute tolerance for near-zero load. Include body loads and prescribed-displacement reactions; do not double-count internal ties as external reactions. Check moment residual about a documented origin similarly. In self-equilibrated loading, use sum of magnitudes rather than net applied force as denominator.
Mesh comparison matches physical locations/regions on the same geometry and loading, not nearest arbitrary node IDs. Report both absolute and relative changes; prevent division by near-zero values. Refinement of a singular peak may diverge; do not claim automatic convergence or silently discard peaks.
Warn when yield exceeded or displacement relative to a relevant dimension suggests small-deformation invalidity. A single global bounding box ratio cannot certify validity. Proposed warnings are heuristics, explained and retained in reports. No global “safe design” badge.
