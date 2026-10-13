"""Persistent bounded previews; immutable geometry/analysis history remains append-only."""

from alembic import op

revision = "0006_geometry_edits"
down_revision = "0005_local_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE geometry_edits (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
        record_json TEXT NOT NULL
    )""")


def downgrade() -> None:
    op.execute("DROP TABLE geometry_edits")
