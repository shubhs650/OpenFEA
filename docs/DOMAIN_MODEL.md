# Domain model and persistence invariants

UUID identifiers; UTC timestamps; dimensional canonical SI values; integer minor currency units or fixed decimals, never binary floating-point currency. Schema versions are explicit and migrations tested.

| Entity | Key fields and invariants |
|---|---|
| User | id, OIDC subject, verified email, allowlist state; identity is subject, not mutable email alone |
| Project | owner_id, name, current revision; all access is owner scoped |
| GeometryRevision | source hash, canonical BREP hash, units decision, body/face catalog, parent, edit recipe, validation; immutable |
| FaceReference | revision_id, body_id, face_id; signature/adjacency supporting remap; never a viewer triangle ID |
| Analysis | project_id, geometry_revision_id, revision counter, status; editable with optimistic concurrency |
| MaterialSnapshot | E, nu, density, optional yield, provenance, source units; copied into each run |
| Assignment | typed material/bond/load/support/mesh control, face refs, basis, validity reason |
| MeshArtifact | geometry+settings hash, body/face sets, C3D10 connectivity, quality and tool digest; immutable |
| RunSnapshot | full frozen analysis, mesh hash, versions, deck hash, rate card, warning policy, approved limit |
| Job / Attempt | stage, status, owner, snapshot, lease token, heartbeat, retry category, resource caps, times |
| Artifact | key, hash, type, size, owner, run, created/expires; immutable bytes, access through authorized request |
| UsageEvent | unique event key, attempt, quantity, units, period, reason, rate version; append-only |
| Reservation | user/run limit, global reserved exposure, consumed, released; atomic admission |
| Credit | referenced usage event, amount, reason, operator review; no deleting original cost evidence |
| Report | run hash, selected views, generator version, warning set, user conclusion; immutable revision |
| AuditEvent | access/admin/retention state changes without geometry or secrets |

## Consistency rules

A changed analysis creates a new revision and cannot change a queued/running snapshot. New meshes invalidate dependent derived previews. A run can reuse a compatible mesh only if geometry and all mesh controls/tool contract hashes match. Material/load changes do not require remeshing unless their selections require changed geometry, but always create a new run snapshot.
Duplication creates independent analysis state referencing immutable geometry. Archive import assigns new owner-scoped IDs and revalidates references; incoming owner IDs, URLs or executable scripts are ignored/rejected. Old immutable run snapshots may refer to an earlier geometry while the editor displays a newer one; UI must identify both.
Delete project first tombstones access and cancels pending work; purge only after active processes terminate. Audit manifests preserve deletion timing without retaining model content forever. Backup retention and erasure deadlines are disclosed.
SQLite transactions handle job admission, reservation and claim. Use WAL and busy timeouts; one control service initially. Live DB backups use the database backup API, not an unsafe copy of only the main file. Remote artifacts published only after a verified manifest; partial blobs are unreferenced until committed.
