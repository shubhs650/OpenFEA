# Operating the beta

## Daily checks

Review actual versus reserved usage, remaining fixed-cost forecast, worker state, stale leases, disk and S3 growth, error classes and last backup success. Stop admissions before forecasted budget exhaustion. Do not depend on users remembering to cancel jobs.

## Job failure runbook

1. Identify job/attempt, lease token, last heartbeat and provider instance state without opening project content.
2. Fence stale attempt; confirm process termination or stop the worker before retrying.
3. Classify model/platform/unknown; retain original cost event and add any credit separately.
4. Reuse validated completed stages; retry infrastructure failure at most once and only inside reserve.
5. Keep outputs inaccessible until complete manifest validation; clean orphan temporary files after safe retention period.

## Backup/restore drill

Use SQLite online backup, copy referenced immutable geometry and metadata manifests to private encrypted regional storage. Backups include tombstones and version/rate history. Restore into an isolated local/staging instance, verify hashes/ownership/migrations, replay deletion ledger, open a synthetic project and reproduce a tiny run. Record timestamps and observed loss window; never overwrite live data as a test. Large result fields are not part of the promised backup guarantee unless explicitly included within the budget.

## Retention

Send in-app expiry notices; mark expired outputs unavailable at deadline; purge eligible bytes, retaining small summaries and manifests with missing-file status. Running jobs and exports hold bounded leases to prevent mid-download deletion where practical. A restore must not reset result age or resurrect expired artifacts.

## Incident handling

Disable admission and revoke affected worker/session tokens. Preserve minimal evidence without copying private CAD externally. Inform affected users through an authorized channel; do not automatically send messages from coding agents. Diagnose with sanitized logs and user-selected diagnostic bundles. Restore only from verified clean backups. Document root cause and add a regression test before reopening.

## Observability

Structured request/job IDs, stage duration, peak RSS, input/output bytes, queue time, attempt count, stop reason, native tool version and cost categories. No raw geometry or input decks in central logs. Initially use bounded on-disk/regional logs and a simple operator screen; avoid a costly observability stack. Alert on orphan workers, cap guard failure, no backup, disk pressure and repeated parsing errors.
