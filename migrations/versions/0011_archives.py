"""Owned downloadable bundles and inert imported provenance; never executable jobs."""

from alembic import op

revision = "0011_archives"
down_revision = "0010_word_exports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("portable_bundles", "archive_imports"):
        op.execute(
            f"CREATE TABLE {table} (id TEXT PRIMARY KEY, project_id TEXT NOT NULL "
            f"REFERENCES projects(id), record_json TEXT NOT NULL)"
        )
        for operation in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER {table}_no_{operation.lower()} BEFORE {operation} "
                f"ON {table} BEGIN SELECT RAISE(ABORT,'immutable archive record'); "
                f"END"
            )


def downgrade() -> None:
    op.execute("DROP TABLE archive_imports")
    op.execute("DROP TABLE portable_bundles")
