"""add cash closure fiscal snapshot fields

Revision ID: 1a2b3c4d5e6f
Revises: c0d1e2f3a4b5
Create Date: 2026-06-13 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "1a2b3c4d5e6f"
down_revision = "c0d1e2f3a4b5"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("cash_closures", schema=None) as batch_op:
        batch_op.add_column(sa.Column("fiscal_snapshot_version", sa.Integer(), nullable=False, server_default="1"))
        batch_op.add_column(sa.Column("fiscal_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
        batch_op.add_column(sa.Column("fiscal_snapshot_created_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("fiscal_snapshot_stale", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("saldo_versabile_precedente", sa.Numeric(precision=12, scale=2), nullable=True))
        batch_op.add_column(sa.Column("versabile_giornata", sa.Numeric(precision=12, scale=2), nullable=True))
        batch_op.add_column(sa.Column("saldo_versabile_finale", sa.Numeric(precision=12, scale=2), nullable=True))

    with op.batch_alter_table("cash_closures", schema=None) as batch_op:
        batch_op.alter_column("fiscal_snapshot_version", server_default=None)
        batch_op.alter_column("fiscal_snapshot_stale", server_default=None)


def downgrade():
    with op.batch_alter_table("cash_closures", schema=None) as batch_op:
        batch_op.drop_column("saldo_versabile_finale")
        batch_op.drop_column("versabile_giornata")
        batch_op.drop_column("saldo_versabile_precedente")
        batch_op.drop_column("fiscal_snapshot_stale")
        batch_op.drop_column("fiscal_snapshot_created_at")
        batch_op.drop_column("fiscal_snapshot")
        batch_op.drop_column("fiscal_snapshot_version")
