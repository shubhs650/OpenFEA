"""Local ownership, project tombstones, immutable geometry and analysis revisions."""

from alembic import op

revision = "0001_local_projects"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    statements = [
        """CREATE TABLE users (
            id TEXT PRIMARY KEY, local_identity TEXT UNIQUE, created_at TEXT NOT NULL
        )""",
        """CREATE TABLE projects (
            id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id),
            name TEXT NOT NULL CHECK(length(trim(name)) BETWEEN 1 AND 200),
            revision INTEGER NOT NULL CHECK(revision > 0),
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deleted_at TEXT
        )""",
        "CREATE INDEX projects_owner ON projects(owner_id, deleted_at, created_at, id)",
        """CREATE TABLE geometry_revisions (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
            parent_id TEXT, metadata_json TEXT NOT NULL,
            created_at TEXT NOT NULL, UNIQUE(project_id, id),
            FOREIGN KEY(project_id, parent_id) REFERENCES geometry_revisions(project_id, id)
        )""",
        """CREATE TABLE analyses (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
            head_revision INTEGER NOT NULL CHECK(head_revision > 0),
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(id, project_id)
        )""",
        "CREATE INDEX analyses_project ON analyses(project_id, created_at, id)",
        """CREATE TABLE analysis_revisions (
            analysis_id TEXT NOT NULL, project_id TEXT NOT NULL,
            revision INTEGER NOT NULL CHECK(revision > 0),
            name TEXT NOT NULL CHECK(length(trim(name)) BETWEEN 1 AND 200),
            geometry_revision_id TEXT, created_at TEXT NOT NULL,
            PRIMARY KEY(analysis_id, revision),
            FOREIGN KEY(analysis_id, project_id) REFERENCES analyses(id, project_id),
            FOREIGN KEY(project_id, geometry_revision_id)
                REFERENCES geometry_revisions(project_id, id)
        )""",
    ]
    for statement in statements:
        op.execute(statement)
    for table in ("geometry_revisions", "analysis_revisions"):
        for operation in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER {table}_no_{operation.lower()} BEFORE {operation} ON {table} "
                "BEGIN SELECT RAISE(ABORT, 'immutable revision'); END"
            )


def downgrade() -> None:
    # Explicit operator action on a disposable/backup-restored DB, never on API startup.
    for table in ("analysis_revisions", "geometry_revisions"):
        for operation in ("update", "delete"):
            op.execute(f"DROP TRIGGER {table}_no_{operation}")
    for table in ("analysis_revisions", "analyses", "geometry_revisions", "projects", "users"):
        op.execute(f"DROP TABLE {table}")
