"""Durable constrained uploads and inspected STEP preview lifecycle."""

from alembic import op

revision = "0002_step_imports"
down_revision = "0001_local_projects"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE geometry_uploads (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
        size_bytes INTEGER NOT NULL CHECK(size_bytes > 0 AND size_bytes <= 16777216),
        sha256 TEXT NOT NULL, status TEXT NOT NULL
        CHECK(status IN ('pending','uploading','complete','failed')),
        created_at TEXT NOT NULL, UNIQUE(project_id,id)
    )""")
    op.execute("""CREATE TABLE geometry_imports (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
        upload_id TEXT NOT NULL,
        project_revision INTEGER NOT NULL, status TEXT NOT NULL
        CHECK(status IN ('processing','needs_units','ready','failed','committed')),
        source_unit TEXT, preview_json TEXT, geometry_revision_id TEXT, error_code TEXT,
        error_message TEXT, created_at TEXT NOT NULL,
        FOREIGN KEY(project_id,upload_id) REFERENCES geometry_uploads(project_id,id),
        FOREIGN KEY(project_id,geometry_revision_id) REFERENCES geometry_revisions(project_id,id)
    )""")


def downgrade() -> None:
    op.execute("DROP TABLE geometry_imports")
    op.execute("DROP TABLE geometry_uploads")
