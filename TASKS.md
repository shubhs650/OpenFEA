# Task index

T001–T006 development deliverables are COMPLETE under the [M0 owner decision](docs/validation/M0-owner-decision.md), which approves progression to M1 and defers formal benchmark and target-laptop acceptance. The earlier [M0 exit review](docs/validation/M0-exit-review.md) remains historical NO-GO evidence; PR #2 corrected M0-R1/M0-R2. T007 persistence, T008 STEP import/viewport, T009 units/materials and T010 face loads/checked deck export are COMPLETE. T011 durable local mesh/solve is COMPLETE. T012 core results is COMPLETE, closing the bounded M1 technical path; T013 bounded geometry cleanup/reference invalidation is COMPLETE; T014 mesh sizing/quality/bounded recovery is COMPLETE; T015 essential loads/equilibrium is COMPLETE; T016 geometry directions/symmetry is COMPLETE; T017 workspace checklist/themes/safe edits is COMPLETE; T018 independent analyses/exact mesh reuse is COMPLETE; M2 bounded technical exit PASS. T019–T042 remain NOT STARTED and T019 is next. M1–M4 development runs in Codex Cloud; local laptop acceptance occurs at M4/T030. AWS backend work starts only in its later milestone.

| Task | Milestone | Goal | Depends on | Status |
|---|---|---|---|---|
| [T001](docs/tasks/T001.md) | M0 | Bootstrap repository and command contracts | none | COMPLETE |
| [T002](docs/tasks/T002.md) | M0 | Provision native tools and license inventory | T001 | COMPLETE |
| [T003](docs/tasks/T003.md) | M0 | Prove face mapping and quadratic element export | T002 | COMPLETE |
| [T004](docs/tasks/T004.md) | M0 | Prove raw stress extraction and display semantics | T003 | COMPLETE |
| [T005](docs/tasks/T005.md) | M0 | Prove independently meshed bonded connection | T003 | COMPLETE |
| [T006](docs/tasks/T006.md) | M0 | Cleanup and resource feasibility review | T004,T005 | COMPLETE |
| [T007](docs/tasks/T007.md) | M1 | Persist projects and local ownership | T006 | COMPLETE |
| [T008](docs/tasks/T008.md) | M1 | STEP import and selectable viewport | T007 | COMPLETE |
| [T009](docs/tasks/T009.md) | M1 | Units and material editor | T008 | COMPLETE |
| [T010](docs/tasks/T010.md) | M1 | Basic face loads and deterministic deck | T009 | COMPLETE |
| [T011](docs/tasks/T011.md) | M1 | Local mesh and asynchronous solve pipeline | T010 | COMPLETE |
| [T012](docs/tasks/T012.md) | M1 | Core results vertical slice | T011,T004 | COMPLETE |
| [T013](docs/tasks/T013.md) | M2 | Geometry edit preview and reference invalidation | T012 | COMPLETE |
| [T014](docs/tasks/T014.md) | M2 | Mesh sizing, quality and bounded recovery | T013 | COMPLETE |
| [T015](docs/tasks/T015.md) | M2 | Complete essential loads and equilibrium | T014 | COMPLETE |
| [T016](docs/tasks/T016.md) | M2 | Geometry-based directions and symmetry | T015 | COMPLETE |
| [T017](docs/tasks/T017.md) | M2 | Hybrid checklist, themes and edit flow | T016 | COMPLETE |
| [T018](docs/tasks/T018.md) | M2 | Multiple analyses and setup duplication | T017 | COMPLETE |
| [T019](docs/tasks/T019.md) | M3 | Bond suggestions, review and gap policy | T018,T005 | NOT STARTED |
| [T020](docs/tasks/T020.md) | M3 | Assembly constraint preflight | T019 | NOT STARTED |
| [T021](docs/tasks/T021.md) | M3 | Full result fields and averaging controls | T020 | NOT STARTED |
| [T022](docs/tasks/T022.md) | M3 | Probes and authoritative section cuts | T021 | NOT STARTED |
| [T023](docs/tasks/T023.md) | M3 | Mesh refinement comparison and assumption warnings | T022 | NOT STARTED |
| [T024](docs/tasks/T024.md) | M3 | Assembly engineering gate | T023 | NOT STARTED |
| [T025](docs/tasks/T025.md) | M4 | Shared report model and PDF | T024 | NOT STARTED |
| [T026](docs/tasks/T026.md) | M4 | Editable Word output | T025 | NOT STARTED |
| [T027](docs/tasks/T027.md) | M4 | Portable archives and diagnostic bundles | T026 | NOT STARTED |
| [T028](docs/tasks/T028.md) | M4 | Reference suite and guided tutorials | T027 | NOT STARTED |
| [T029](docs/tasks/T029.md) | M4 | Resource limits and local fault resilience | T028 | NOT STARTED |
| [T030](docs/tasks/T030.md) | M4 | Local prototype acceptance review | T029 | NOT STARTED |
| [T031](docs/tasks/T031.md) | M5 | OIDC allowlist and owner isolation | T030 | NOT STARTED |
| [T032](docs/tasks/T032.md) | M5 | Usage ledger, estimates and reservations | T031 | NOT STARTED |
| [T033](docs/tasks/T033.md) | M5 | India AWS budget feasibility and IaC plan | T032 | NOT STARTED |
| [T034](docs/tasks/T034.md) | M5 | Remote worker and durable artifact adapter | T033 | NOT STARTED |
| [T035](docs/tasks/T035.md) | M5 | Spending watchdog and failure credits | T034 | NOT STARTED |
| [T036](docs/tasks/T036.md) | M5 | Retention, backup and recovery | T035 | NOT STARTED |
| [T037](docs/tasks/T037.md) | M5 | Operator controls and security hardening | T036 | NOT STARTED |
| [T038](docs/tasks/T038.md) | M5 | Authorized staging drill and beta readiness | T037 | NOT STARTED |
| [T039](docs/tasks/T039.md) | M6 | Invite beta and usability observation | T038 | NOT STARTED |
| [T040](docs/tasks/T040.md) | M6 | Triage beta defects and cost calibration | T039 | NOT STARTED |
| [T041](docs/tasks/T041.md) | M6 | Self-host and release documentation | T040 | NOT STARTED |
| [T042](docs/tasks/T042.md) | M6 | Beta exit and paid-service decision | T041 | NOT STARTED |
