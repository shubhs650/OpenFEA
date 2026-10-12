# M0 feasibility and stop/go review

Status: F1 local native availability/tiny solve PASSED in [T002](validation/T002.md), with public license review still deferred. [T003](validation/T003.md) delivers F2/F3 development evidence for synthetic planar geometry/affine C3D10; B01/B02 signed acceptance is deferred by the owner. F4–F8 NOT RUN. Full M0 exit remains open; development passes are not release acceptance.

| Gate | Experiment | Required evidence | Failure response |
|---|---|---|---|
| F1 Native toolchain | Provision pinned CCX, Gmsh, OCCT binding, VTK in Linux; run tiny real solve | Versions, checksums, licenses, command transcript and numerical output | Fix build/dependencies; no fake solver adapter |
| F2 Geometry identity | Import synthetic bracket and two solids; tessellate, round-trip into Gmsh; apply face selections | One-to-one face correspondence or explicit unresolved flags; correct loaded face after reorder | Restrict supported geometry; never guess references |
| F3 C3D10 and traction | One element plus tensile block with pressure/force on each oriented face | Connectivity, midside mapping, resultants and moments against independent values | Block UI solve integration |
| F4 Ties | Two separately meshed blocks; compare zero-gap bond with monolithic model; test approved small gap | Coverage, stress/displacement continuity, no unintended node adjustment, reactions | Investigate formulation; assemblies remain blocked rather than replaced by fused solids |
| F5 Stress provenance | Request and parse smoothed and element-associated output | Raw location/ordering demonstrated; discontinuous test retained in viewer | Do not claim unaveraged contours; fix extraction or record scope exception |
| F6 Cleanup | Select and remove simple hole/fillet; test unsupported feature | Validity, preview, volume delta, unchanged original on failure | Limit cleanup as user-authorized fallback |
| F7 Resource and display | 5k/25k/100k C3D10 meshes, stopping before OOM; render fields on integrated GPU | Nodes, DOFs, RAM, runtime, artifact size, viewport performance | Set measured lower cap and offer coarsening; no capacity guarantee |
| F8 Cloud viability | Cost worksheet for Indian control host + idle disks + worker hours + overhead | Dated regional rates/taxes/FX assumptions, baseline below total cap with reserve | Return cost conflict with concrete options before deployment |

F1–F5 are core blockers for M1 engineering completion. F6 can be limited with explicit supported cases. F7 establishes capacity, not a requirement to crash-test the laptop. F8 must pass before beta infrastructure is provisioned; provisional architecture can be developed with mocks earlier.

Risk priority: face identity after edits (high), nonconforming C3D10 ties (high), stress output meaning (high), memory at 100k elements (high), India budget fit (high), UI polish (medium), report formatting (medium). Record experiments with source/commit/version, expected result before running, actual observation, decision and next task. Use docs/templates/EXPERIMENT.md.
