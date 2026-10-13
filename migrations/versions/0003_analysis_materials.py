"""Append-only per-analysis-revision material and display-unit snapshots."""

from alembic import op

revision = "0003_analysis_materials"
down_revision = "0002_step_imports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE analysis_material_setups (
        analysis_id TEXT NOT NULL, revision INTEGER NOT NULL, setup_json TEXT NOT NULL,
        PRIMARY KEY(analysis_id, revision),
        FOREIGN KEY(analysis_id, revision) REFERENCES analysis_revisions(analysis_id, revision)
    )""")
    for operation in ("UPDATE", "DELETE"):
        op.execute(
            f"CREATE TRIGGER analysis_material_setups_no_{operation.lower()} "
            f"BEFORE {operation} ON analysis_material_setups "
            "BEGIN SELECT RAISE(ABORT, 'immutable material setup'); END"
        )


def downgrade() -> None:
    op.execute("DROP TABLE analysis_material_setups")
