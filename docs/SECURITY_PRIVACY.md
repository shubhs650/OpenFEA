# Security and privacy requirements

## Trust boundaries

Browser inputs are untrusted; server owns authorization, geometry validity, costs and jobs. Native CAD/meshing/solver parsers process hostile bytes in isolated low-privilege subprocesses/containers with bounded CPU/RAM/disk/time and no general network. Control-plane compromise is distinct from numerical invalidity.

## Controls

- Google OIDC: verify issuer/audience/signature/expiry, state/nonce and verified email; exact email allowlist plus stable subject binding. Rate-limit login and uploads. Revoke sessions when allowlist is removed. No public registration.
- Secure HttpOnly SameSite cookies, TLS, CSRF defense for cookie-authenticated writes; session expiry/logout. No tokens in localStorage.
- Every project, job, artifact, report, event stream and export lookup checks owner. Signed links are short-lived and issued only after current ownership check; avoid putting bearer URLs in logs.
- Uploaded STEP files have byte, entity-count and processing-time limits. Ignore original path names. Internal IDs determine storage paths. No shell=True or string-built native command lines.
- Archives: reject absolute/traversal paths, symlinks, oversized expansion, excess file count, recursive archives, undeclared files and hash mismatch. Parse metadata through a strict versioned schema; never deserialize pickle or execute bundled scripts.
- Solver jobs read generated allowlisted files only. No arbitrary *INCLUDE paths; recursively constrain any internally generated includes to the sandbox. No user raw-input execution.
- Mask secrets and redact geometry coordinates/filenames from shared logs by default. Diagnostics preview inclusion choices; do not auto-upload to support.
- Store encryption keys/secrets outside git. AWS roles instead of embedded long-lived credentials. Restrict operator region/resource rights and audit provisioning.
- Private data never enters Codex Cloud, public git, CI screenshots or third-party error telemetry. Use generated fixtures for development/review.

## Retention and deletion

Results expire 30 days after completion. Proposed in-app notices at 7 days and 1 day remaining; no automated email required. Expiry removes access immediately; physical object deletion follows documented lifecycle and backups. Retain geometry/setup/run summaries until project deletion or quota policy. Propose per-user quota during beta cost calibration; block uploads/new output when quota cannot fit, never silently purge setups.
Daily encrypted backups of metadata and immutable geometry references; proposed 7 daily backup generations within India. Project deletion produces tombstone/purge record so restores do not resurrect deleted projects; backups age out within disclosed window. On restore, reapply deletion ledger and validate artifact ownership. No claim of immediate deletion from all backups.

## Threat tests

Cross-user ID enumeration; path traversal; ZIP bomb; malformed STEP; command injection in names; solver include escape; stale signed URL; OAuth replay; auth bypass flag in beta; stale worker token; double-spend race; instance metadata access from solver subprocess. Beta cannot launch with unresolved critical isolation or ownership failures.

T029 result parsing uses a private networkless Bubblewrap/netdeny subprocess with readonly frozen inputs/raw outputs and no project-store/SQLite mount. The controller supervises RSS, scratch, time, logs and live disk reserve while heartbeating. Token/heartbeat/deadline checks gate checkpoints/publication; retry additionally requires confirmed execution fencing and the inherited native flock. Two attempts share one deadline and aggregate retained-byte/scratch limits. Unknown exits and corrupt checkpoints fail for review. See [ADR-035](adr/ADR-035.md).
