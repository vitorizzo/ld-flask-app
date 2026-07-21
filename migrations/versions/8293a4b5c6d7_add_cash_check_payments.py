"""add cash check payments

Revision ID: 8293a4b5c6d7
Revises: 718293a4b5c6
Create Date: 2026-07-21
"""

from alembic import op
import sqlalchemy as sa


revision = "8293a4b5c6d7"
down_revision = "718293a4b5c6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cash_check_payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("check_id", sa.Integer(), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("method", sa.String(20), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["check_id"], ["cash_checks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cash_check_payments_check_id", "cash_check_payments", ["check_id"])
    op.create_index("ix_cash_check_payments_payment_date", "cash_check_payments", ["payment_date"])


def downgrade():
    op.drop_index("ix_cash_check_payments_payment_date", table_name="cash_check_payments")
    op.drop_index("ix_cash_check_payments_check_id", table_name="cash_check_payments")
    op.drop_table("cash_check_payments")
