"""Append-only load setups and frozen, authorized deck-export records."""

from alembic import op

revision = "0004_loads_decks"
down_revision = "0003_analysis_materials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE analysis_load_setups (
        analysis_id TEXT NOT NULL, revision INTEGER NOT NULL, setup_json TEXT NOT NULL,
        PRIMARY KEY(analysis_id,revision),
        FOREIGN KEY(analysis_id,revision) REFERENCES analysis_revisions(analysis_id,revision)
    )""")
    op.execute("""CREATE TABLE deck_exports (
        id TEXT PRIMARY KEY, analysis_id TEXT NOT NULL, revision INTEGER NOT NULL,
        snapshot_sha256 TEXT NOT NULL UNIQUE,
        metadata_json TEXT NOT NULL, snapshot_json TEXT NOT NULL,
        FOREIGN KEY(analysis_id,revision) REFERENCES analysis_revisions(analysis_id,revision)
    )""")
    for table in ("analysis_load_setups", "deck_exports"):
        for operation in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER {table}_no_{operation.lower()} BEFORE {operation} ON {table} "
                "BEGIN SELECT RAISE(ABORT, 'immutable setup/export'); END"
            )


def downgrade() -> None:
    op.execute("DROP TABLE deck_exports")
    op.execute("DROP TABLE analysis_load_setups")
