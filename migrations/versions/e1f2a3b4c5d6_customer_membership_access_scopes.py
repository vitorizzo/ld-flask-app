"""normalize customer membership access scopes

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-09-04
"""
from alembic import op
import sqlalchemy as sa


revision = "e1f2a3b4c5d6"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(sa.text("""
        UPDATE customer_registry_memberships
        SET role = CASE
            WHEN role IN ('payments', 'viewer') THEN 'administration'
            WHEN role IN ('administration', 'management', 'both') THEN role
            ELSE 'both'
        END
    """))
    op.alter_column(
        "customer_registry_memberships",
        "role",
        existing_type=sa.String(length=20),
        server_default="both",
        existing_nullable=False,
    )


def downgrade():
    op.execute(sa.text("""
        UPDATE customer_registry_memberships
        SET role = CASE
            WHEN role = 'administration' THEN 'payments'
            ELSE 'owner'
        END
    """))
    op.alter_column(
        "customer_registry_memberships",
        "role",
        existing_type=sa.String(length=20),
        server_default=None,
        existing_nullable=False,
    )
