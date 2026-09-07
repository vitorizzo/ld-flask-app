"""add manual customer accounting states

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-09-07
"""
from alembic import op
import sqlalchemy as sa


revision = "a3b4c5d6e7f8"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "customer_accounting_item_states",
        "registry_id",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.add_column(
        "customer_accounting_item_states",
        sa.Column("source", sa.String(length=32), server_default="customer_case", nullable=False),
    )
    op.add_column(
        "customer_accounting_item_states",
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "customer_accounting_item_states",
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "customer_accounting_item_states",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_foreign_key(
        "fk_customer_accounting_item_state_created_by",
        "customer_accounting_item_states", "user",
        ["created_by_user_id"], ["id"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_customer_accounting_item_state_updated_by",
        "customer_accounting_item_states", "user",
        ["updated_by_user_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index(
        "ix_customer_accounting_item_state_source_key",
        "customer_accounting_item_states",
        ["source_customer_code", "source_item_key"],
    )


def downgrade():
    op.drop_index(
        "ix_customer_accounting_item_state_source_key",
        table_name="customer_accounting_item_states",
    )
    op.drop_constraint(
        "fk_customer_accounting_item_state_updated_by",
        "customer_accounting_item_states",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_customer_accounting_item_state_created_by",
        "customer_accounting_item_states",
        type_="foreignkey",
    )
    op.drop_column("customer_accounting_item_states", "created_at")
    op.drop_column("customer_accounting_item_states", "updated_by_user_id")
    op.drop_column("customer_accounting_item_states", "created_by_user_id")
    op.drop_column("customer_accounting_item_states", "source")
    op.execute("DELETE FROM customer_accounting_item_states WHERE registry_id IS NULL")
    op.alter_column(
        "customer_accounting_item_states",
        "registry_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
