"""add supplier order matrix names

Revision ID: 4e5f60718293
Revises: 3d4e5f607182
Create Date: 2026-07-16
"""

from alembic import op
import sqlalchemy as sa


revision = "4e5f60718293"
down_revision = "3d4e5f607182"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "supplier_order_matrix_names",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("matrix_code", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["supplier_order_groups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_id", "matrix_code", name="uq_supplier_order_matrix_names_group_matrix"),
    )
    op.create_index("ix_supplier_order_matrix_names_group", "supplier_order_matrix_names", ["group_id"])


def downgrade():
    op.drop_index("ix_supplier_order_matrix_names_group", table_name="supplier_order_matrix_names")
    op.drop_table("supplier_order_matrix_names")
