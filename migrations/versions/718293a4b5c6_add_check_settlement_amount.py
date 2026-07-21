"""add check settlement amount

Revision ID: 718293a4b5c6
Revises: 60718293a4b5
Create Date: 2026-07-21
"""

from alembic import op
import sqlalchemy as sa


revision = "718293a4b5c6"
down_revision = "60718293a4b5"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("cash_checks") as batch_op:
        batch_op.add_column(sa.Column("settlement_amount", sa.Numeric(12, 2), nullable=True))


def downgrade():
    with op.batch_alter_table("cash_checks") as batch_op:
        batch_op.drop_column("settlement_amount")
