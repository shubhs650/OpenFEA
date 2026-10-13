"""Durable local queue, immutable admission snapshots and fenced event history."""

from alembic import op

revision = "0005_local_jobs"
down_revision = "0004_loads_decks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE local_jobs (
        id TEXT PRIMARY KEY, analysis_id TEXT NOT NULL, project_id TEXT NOT NULL,
        analysis_revision INTEGER NOT NULL, geometry_revision_id TEXT NOT NULL,
        kind TEXT NOT NULL CHECK(kind IN ('mesh','solve')), mesh_job_id TEXT,
        owner_id TEXT NOT NULL, idempotency_key TEXT NOT NULL, request_sha256 TEXT NOT NULL,
        input_sha256 TEXT NOT NULL, status TEXT NOT NULL,
        stage TEXT NOT NULL, queued_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
        heartbeat_at TEXT, cancel_requested INTEGER NOT NULL DEFAULT 0,
        attempt_token TEXT, worker_id TEXT, process_pid INTEGER, process_start TEXT,
        reason_code TEXT, reason_message TEXT,
        summary_json TEXT NOT NULL DEFAULT '{}', artifacts_json TEXT NOT NULL DEFAULT '{}',
        UNIQUE(owner_id,idempotency_key),
        FOREIGN KEY(analysis_id,analysis_revision)
          REFERENCES analysis_revisions(analysis_id,revision),
        FOREIGN KEY(project_id) REFERENCES projects(id),
        FOREIGN KEY(mesh_job_id) REFERENCES local_jobs(id)
    )""")
    op.execute(
        "CREATE UNIQUE INDEX local_jobs_one_active ON local_jobs((1)) "
        "WHERE status IN ('running','cancelling')"
    )
    op.execute("""CREATE TABLE local_job_inputs (
        job_id TEXT PRIMARY KEY REFERENCES local_jobs(id), input_json TEXT NOT NULL
    )""")
    op.execute("""CREATE TABLE local_job_events (
        job_id TEXT NOT NULL REFERENCES local_jobs(id), sequence INTEGER NOT NULL,
        status TEXT NOT NULL, stage TEXT NOT NULL, at TEXT NOT NULL, reason_code TEXT,
        PRIMARY KEY(job_id,sequence)
    )""")
    for table in ("local_job_inputs", "local_job_events"):
        for operation in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER {table}_no_{operation.lower()} "
                f"BEFORE {operation} ON {table} BEGIN "
                "SELECT RAISE(ABORT, 'immutable job input/event'); END"
            )
    op.execute("""CREATE TRIGGER local_jobs_frozen_inputs BEFORE UPDATE ON local_jobs
        WHEN NEW.id IS NOT OLD.id OR NEW.analysis_id IS NOT OLD.analysis_id
        OR NEW.project_id IS NOT OLD.project_id
        OR NEW.analysis_revision IS NOT OLD.analysis_revision
        OR NEW.geometry_revision_id IS NOT OLD.geometry_revision_id OR NEW.kind IS NOT OLD.kind
        OR NEW.mesh_job_id IS NOT OLD.mesh_job_id OR NEW.input_sha256 IS NOT OLD.input_sha256
        OR NEW.owner_id IS NOT OLD.owner_id OR NEW.idempotency_key IS NOT OLD.idempotency_key
        OR NEW.request_sha256 IS NOT OLD.request_sha256
        BEGIN SELECT RAISE(ABORT, 'immutable job identity'); END""")
    op.execute("""CREATE TRIGGER local_jobs_terminal BEFORE UPDATE ON local_jobs
        WHEN OLD.status IN ('cancelled','succeeded','failed','interrupted')
        BEGIN SELECT RAISE(ABORT, 'terminal job is immutable'); END""")
    op.execute(
        "CREATE TRIGGER local_jobs_no_delete BEFORE DELETE ON local_jobs "
        "BEGIN SELECT RAISE(ABORT, 'job history is retained'); END"
    )


def downgrade() -> None:
    op.execute("DROP TABLE local_job_events")
    op.execute("DROP TABLE local_job_inputs")
    op.execute("DROP TABLE local_jobs")
