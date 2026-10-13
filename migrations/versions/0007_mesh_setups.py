"""Append-only analysis mesh settings, preserving legacy default coarse behavior."""

from alembic import op

revision = "0007_mesh_setups"
down_revision = "0006_geometry_edits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE analysis_mesh_setups (
        analysis_id TEXT NOT NULL, revision INTEGER NOT NULL, setup_json TEXT NOT NULL,
        PRIMARY KEY(analysis_id,revision),
        FOREIGN KEY(analysis_id,revision) REFERENCES analysis_revisions(analysis_id,revision)
    )""")
    for operation in ("UPDATE", "DELETE"):
        op.execute(
            f"CREATE TRIGGER mesh_setups_no_{operation.lower()} BEFORE {operation} "
            "ON analysis_mesh_setups BEGIN SELECT RAISE(ABORT, 'immutable mesh setup'); END"
        )


def downgrade() -> None:
    op.execute("DROP TABLE analysis_mesh_setups")
