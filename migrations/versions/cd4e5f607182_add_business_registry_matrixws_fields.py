"""add business registry matrixws classification fields

Revision ID: cd4e5f607182
Revises: cc3d4e5f6071
Create Date: 2026-08-09
"""

from alembic import op
import sqlalchemy as sa


revision = "cd4e5f607182"
down_revision = "cc3d4e5f6071"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("business_registries") as batch_op:
        batch_op.add_column(sa.Column("area_code", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("area_description", sa.String(length=160), nullable=True))
        batch_op.add_column(sa.Column("zone_code", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("zone_description", sa.String(length=160), nullable=True))
        for index in range(1, 6):
            batch_op.add_column(sa.Column(f"statistical_code_{index}", sa.String(length=32), nullable=True))
            batch_op.add_column(sa.Column(f"statistical_description_{index}", sa.String(length=160), nullable=True))
        batch_op.create_index(
            "ix_business_registry_customer_action",
            ["kind", "statistical_code_2"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("business_registries") as batch_op:
        batch_op.drop_index("ix_business_registry_customer_action")
        for index in range(5, 0, -1):
            batch_op.drop_column(f"statistical_description_{index}")
            batch_op.drop_column(f"statistical_code_{index}")
        batch_op.drop_column("zone_description")
        batch_op.drop_column("zone_code")
        batch_op.drop_column("area_description")
        batch_op.drop_column("area_code")
