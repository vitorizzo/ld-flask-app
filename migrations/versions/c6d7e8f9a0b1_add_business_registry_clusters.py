"""add business registry category clusters

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
Create Date: 2026-07-24
"""

from alembic import op
import sqlalchemy as sa


revision = "c6d7e8f9a0b1"
down_revision = "b5c6d7e8f9a0"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("business_registries") as batch_op:
        batch_op.add_column(sa.Column("category_code", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("category_description", sa.String(length=160), nullable=True))
        batch_op.add_column(sa.Column("subcategory_code", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("subcategory_description", sa.String(length=160), nullable=True))
        batch_op.create_index(
            "ix_business_registry_customer_cluster",
            ["kind", "category_code", "subcategory_code"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("business_registries") as batch_op:
        batch_op.drop_index("ix_business_registry_customer_cluster")
        batch_op.drop_column("subcategory_description")
        batch_op.drop_column("subcategory_code")
        batch_op.drop_column("category_description")
        batch_op.drop_column("category_code")
