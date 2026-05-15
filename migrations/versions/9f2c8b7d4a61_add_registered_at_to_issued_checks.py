"""add registered_at to issued checks

Revision ID: 9f2c8b7d4a61
Revises: 6c7693e36d37
Create Date: 2026-05-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "9f2c8b7d4a61"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("cash_issued_checks", schema=None) as batch_op:
        batch_op.add_column(sa.Column("registered_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_cash_issued_checks_registered_at"),
            ["registered_at"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("cash_issued_checks", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_cash_issued_checks_registered_at"))
        batch_op.drop_column("registered_at")
