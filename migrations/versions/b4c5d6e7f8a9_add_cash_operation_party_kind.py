"""add cash operation party kind

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-09-11
"""
from alembic import op
import sqlalchemy as sa


revision = "b4c5d6e7f8a9"
down_revision = "a3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "cash_sales",
        sa.Column("party_kind", sa.String(length=20), server_default="customer", nullable=False),
    )
    op.add_column(
        "cash_expenses",
        sa.Column("party_kind", sa.String(length=20), server_default="supplier", nullable=False),
    )


def downgrade():
    op.drop_column("cash_expenses", "party_kind")
    op.drop_column("cash_sales", "party_kind")
