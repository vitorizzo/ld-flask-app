"""add customer payment instructions

Revision ID: c4d5e6f7a0b1
Revises: b3c4d5e6f9a0
Create Date: 2026-08-26 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "c4d5e6f7a0b1"
down_revision = "b3c4d5e6f9a0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "customer_payment_instructions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("label", sa.String(length=120), nullable=False, server_default="Bonifico bancario"),
        sa.Column("account_holder", sa.String(length=255), nullable=False),
        sa.Column("iban", sa.String(length=34), nullable=False),
        sa.Column("bank_name", sa.String(length=160), nullable=True),
        sa.Column("bic_swift", sa.String(length=16), nullable=True),
        sa.Column("beneficiary_address", sa.String(length=255), nullable=True),
        sa.Column("payment_reason_template", sa.String(length=500), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["user.id"], ondelete="SET NULL"),
    )


def downgrade():
    op.drop_table("customer_payment_instructions")
