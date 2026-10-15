"""Immutable report outputs; ownership remains tied to the original project/run."""

from alembic import op

revision = "0009_reports"
down_revision = "0008_bond_setups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE reports (
        id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES local_jobs(id),
        record_json TEXT NOT NULL
    )""")
    op.execute("CREATE INDEX reports_job ON reports(job_id)")
    for operation in ("UPDATE", "DELETE"):
        op.execute(
            f"CREATE TRIGGER reports_no_{operation.lower()} BEFORE {operation} "
            "ON reports BEGIN SELECT RAISE(ABORT,'reports are immutable'); END"
        )


def downgrade() -> None:
    op.execute("DROP TABLE reports")
