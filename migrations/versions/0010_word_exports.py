"""Append Word artifacts without rewriting earlier immutable PDF report records."""

from alembic import op

revision = "0010_word_exports"
down_revision = "0009_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE report_word_exports (
        id TEXT PRIMARY KEY, report_id TEXT NOT NULL REFERENCES reports(id),
        record_json TEXT NOT NULL
    )""")
    op.execute("CREATE INDEX word_exports_report ON report_word_exports(report_id)")
    for operation in ("UPDATE", "DELETE"):
        op.execute(
            f"CREATE TRIGGER word_exports_no_{operation.lower()} BEFORE {operation} "
            "ON report_word_exports BEGIN SELECT RAISE(ABORT,'word exports are immutable'); END"
        )


def downgrade() -> None:
    op.execute("DROP TABLE report_word_exports")
