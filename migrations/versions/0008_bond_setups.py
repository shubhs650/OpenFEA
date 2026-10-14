"""Append-only saved reviewed connection setups; legacy revisions have no bonds."""

from alembic import op

revision = "0008_bond_setups"
down_revision = "0007_mesh_setups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE analysis_bond_setups (
        analysis_id TEXT NOT NULL, revision INTEGER NOT NULL, setup_json TEXT NOT NULL,
        PRIMARY KEY(analysis_id,revision),
        FOREIGN KEY(analysis_id,revision) REFERENCES analysis_revisions(analysis_id,revision)
    )""")
    for operation in ("UPDATE", "DELETE"):
        op.execute(
            f"CREATE TRIGGER bond_setups_no_{operation.lower()} BEFORE {operation} "
            "ON analysis_bond_setups BEGIN SELECT RAISE(ABORT, 'immutable bond setup'); END"
        )


def downgrade() -> None:
    op.execute("DROP TABLE analysis_bond_setups")
