"""add customer entry accounting relevance

Revision ID: cc3d4e5f6071
Revises: cb2c3d4e5f60
Create Date: 2026-07-30
"""

from alembic import op
import sqlalchemy as sa


revision = "cc3d4e5f6071"
down_revision = "cb2c3d4e5f60"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("customer_account_entries", sa.Column("accounting_reason", sa.String(length=8), nullable=True))
    op.add_column("customer_account_entries", sa.Column("accounting_reference", sa.String(length=16), nullable=True))
    op.add_column(
        "customer_account_entries",
        sa.Column("is_balance_relevant", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.create_index(
        "ix_customer_account_entries_accounting_reason",
        "customer_account_entries",
        ["accounting_reason"],
    )
    op.create_index(
        "ix_customer_account_entries_is_balance_relevant",
        "customer_account_entries",
        ["is_balance_relevant"],
    )


def downgrade():
    op.drop_index("ix_customer_account_entries_is_balance_relevant", table_name="customer_account_entries")
    op.drop_index("ix_customer_account_entries_accounting_reason", table_name="customer_account_entries")
    op.drop_column("customer_account_entries", "is_balance_relevant")
    op.drop_column("customer_account_entries", "accounting_reference")
    op.drop_column("customer_account_entries", "accounting_reason")
