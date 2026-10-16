"""Bounded infrastructure attempts and immutable, fenced stage checkpoints."""

from datetime import datetime, timedelta

from alembic import op
from sqlalchemy import text

revision = "0012_job_attempts"
down_revision = "0011_archives"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE local_jobs ADD COLUMN attempt_number INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE local_jobs ADD COLUMN deadline_at TEXT")
    op.execute("""CREATE TABLE local_job_attempts (
        job_id TEXT NOT NULL REFERENCES local_jobs(id), number INTEGER NOT NULL CHECK(number BETWEEN 1 AND 2),
        token TEXT NOT NULL UNIQUE, started_at TEXT NOT NULL, finished_at TEXT,
        status TEXT NOT NULL, reason_code TEXT, artifacts_json TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY(job_id,number)
    )""")
    # Retain pre-migration active/terminal execution identity without restarting it.
    op.execute("""INSERT INTO local_job_attempts
        SELECT id,1,attempt_token,started_at,finished_at,status,reason_code,artifacts_json
        FROM local_jobs WHERE attempt_token IS NOT NULL""")
    # Terminal jobs cannot be updated. Their attempt count is read from the ledger.
    connection = op.get_bind()
    for row in (
        connection.execute(
            text("SELECT id,started_at FROM local_jobs WHERE status IN ('running','cancelling')")
        )
        .mappings()
        .all()
    ):
        connection.execute(
            text("UPDATE local_jobs SET attempt_number=1,deadline_at=:deadline WHERE id=:id"),
            {
                "id": row["id"],
                "deadline": (
                    datetime.fromisoformat(row["started_at"]) + timedelta(seconds=180)
                ).isoformat(),
            },
        )
    op.execute("""CREATE TRIGGER local_job_attempts_terminal BEFORE UPDATE ON local_job_attempts
        WHEN OLD.finished_at IS NOT NULL
        BEGIN SELECT RAISE(ABORT, 'finished attempt is immutable'); END""")
    op.execute("""CREATE TABLE local_job_checkpoints (
        job_id TEXT PRIMARY KEY REFERENCES local_jobs(id), token TEXT NOT NULL,
        input_sha256 TEXT NOT NULL, manifest_json TEXT NOT NULL, execution_json TEXT NOT NULL
    )""")
    for table in ("local_job_attempts", "local_job_checkpoints"):
        op.execute(
            f"CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table} "
            "BEGIN SELECT RAISE(ABORT, 'job history is retained'); END"
        )
    op.execute("""CREATE TRIGGER local_job_checkpoints_no_update BEFORE UPDATE
        ON local_job_checkpoints BEGIN SELECT RAISE(ABORT, 'checkpoint is immutable'); END""")


def downgrade() -> None:
    op.execute("DROP TABLE local_job_checkpoints")
    op.execute("DROP TABLE local_job_attempts")
    op.execute("ALTER TABLE local_jobs DROP COLUMN deadline_at")
    op.execute("ALTER TABLE local_jobs DROP COLUMN attempt_number")
