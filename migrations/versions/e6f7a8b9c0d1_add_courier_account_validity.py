"""add courier account validity

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-06-03 09:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "e6f7a8b9c0d1"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("courier_accounts", sa.Column("valid_from", sa.Date(), nullable=True))
    op.add_column("courier_accounts", sa.Column("valid_to", sa.Date(), nullable=True))
    op.create_index("ix_courier_accounts_valid_from", "courier_accounts", ["valid_from"])
    op.create_index("ix_courier_accounts_valid_to", "courier_accounts", ["valid_to"])


def downgrade():
    op.drop_index("ix_courier_accounts_valid_to", table_name="courier_accounts")
    op.drop_index("ix_courier_accounts_valid_from", table_name="courier_accounts")
    op.drop_column("courier_accounts", "valid_to")
    op.drop_column("courier_accounts", "valid_from")
