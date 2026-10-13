# Local project persistence — T007

The browser page still displays bootstrap health. The real `/api/v1` API now supports projects and draft analysis metadata. [ADR-015](adr/ADR-015.md) defines the storage/access decisions; [T007 evidence](validation/T007.md) records executed checks. STEP uploads, geometry import, engineering setup and solve remain later tasks.

## Data root and migrations

Set `FEA_DATA_ROOT` to an absolute writable directory outside the checkout before `make dev`. The API stores `metadata.sqlite3` there with WAL and foreign keys; the database file is created with mode 0600. Its local owner, projects, tombstones and revision history survive stopping/restarting the API. The existing default `/tmp/openfea-data` survives ordinary process restarts but can be removed by OS cleanup/reboot; choose a durable operator-managed directory for real local persistence. No private CAD belongs in this cloud development workspace.

Startup upgrades the schema to Alembic head before serving requests, and fails if migration fails. Explicit schema commands from the repository root:

```sh
PYTHONPATH=services/api .venv/bin/python scripts/dev/migrate.py upgrade head
```

Downgrades intentionally remove affected tables/data. Stop the API first and back up with SQLite's backup API; copying only the live main file omits WAL data. On a disposable or backup-restored database, reversal is:

```sh
PYTHONPATH=services/api .venv/bin/python scripts/dev/migrate.py downgrade base
```

T007 tests migration reversal and rollback, not a full backup/restore/deletion-ledger product. Large artifacts and jobs do not exist in this slice.

## Using the API

Use the loopback supervisor (`make dev`); manual Uvicorn starts must bind 127.0.0.1 and disable proxy headers. API docs are at `/api/v1/docs`. GET `/api/v1/session` sets `openfea_local_session` and returns `owner_id` and `csrf_token`. Reads require the cookie, and writes require `X-CSRF-Token` too. Session tokens are in memory and expire on API restart; reopen a session without changing the persisted owner. HTTP local cookies are not hosted authentication.

For a synthetic example, save the local cookie in ignored scratch storage and copy the response token into the subsequent request:

```sh
mkdir -p .local
curl -c .local/local-session.cookies http://127.0.0.1:8000/api/v1/session
curl -b .local/local-session.cookies \
  -H 'Content-Type: application/json' -H 'X-CSRF-Token: <csrf_token>' \
  -d '{"name":"Synthetic bracket"}' http://127.0.0.1:8000/api/v1/projects
```

Creation returns a UUID, owner, timestamps, revision 1, `ETag: "1"` and Location. GET/list return only own nondeleted projects. PATCH/DELETE require the quoted ETag in `If-Match`; a missing revision is 428, invalid format 422 and stale edit 409. DELETE returns 204 and immediately hides child analyses/geometry. It does not purge their bytes/metadata or implement job cancellation.

POST `/projects/{id}/analyses` requires the project's current ETag and creates an independent draft. An absent geometry reference is explicitly null; it is not a runnable analysis. Optional geometry must belong to this same owned project. GET/PATCH `/analyses/{id}` use the analysis ETag. PATCH currently edits only the name; GET `/analyses/{id}/revisions/{revision}` retrieves immutable history. Creating/editing an analysis does not advance the project's metadata revision.

Geometry registration is an internal trusted-adapter boundary for T008. It increments the project revision and optionally references a parent in that project. GET `/projects/{id}/geometry` and GET `/geometry/{id}` read the records; browser mutation/import endpoints are not implemented. Metadata fixtures do not constitute native CAD validation. Existing analyses keep their earlier geometry references.

Lists support `offset` (default 0) and `limit` (default 50, maximum 100) with stable creation-time/ID order and a total. Unknown input fields, empty/oversized names, and inaccessible/cross-project references are rejected. POST/PATCH/PUT metadata bodies require Content-Length and are bounded to 64 KiB before JSON parsing; chunked bodies receive 411. Errors return `code`, `message`, `field_errors`, `retryable` and `request_id`, without DB paths or SQL. Responses disable caching. Local mode rejects nonloopback peers/Hosts, foreign browser Origins and cross-site fetches; no CORS bypass or user-selectable owner is available.

## Next boundary

T008 must add bounded STEP upload/import, native validation, verified content-addressed artifacts and the selectable viewport. It must register the immutable metadata only after that validation and retain revision-bound body/face identities. Future setup changes must append typed analysis revisions rather than overwrite history. T011 adds guarded jobs/run snapshots and deletion coordination; T018 adds duplication. The [M0 owner progression decision](validation/M0-owner-decision.md) closes bounded M0 development; exact benchmark and laptop acceptance remain deferred to the scheduled M3/M4 gates in [PROGRESS.md](../PROGRESS.md).
