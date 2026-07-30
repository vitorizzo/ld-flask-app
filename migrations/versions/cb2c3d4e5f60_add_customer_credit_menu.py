"""add customer credit administration menu

Revision ID: cb2c3d4e5f60
Revises: ca1b2c3d4e5f
Create Date: 2026-07-30
"""

from alembic import op
import sqlalchemy as sa


revision = "cb2c3d4e5f60"
down_revision = "ca1b2c3d4e5f"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(sa.text("""
        INSERT INTO menus (name, weight, sort_order, parent_id, route, is_active, is_visible, item_type)
        SELECT
            'Situazioni contabili clienti',
            40,
            COALESCE((SELECT MAX(child.sort_order) + 1 FROM menus AS child WHERE child.parent_id = parent.id), 1),
            parent.id,
            '/administration/customer-credit',
            true,
            true,
            'link'
        FROM menus AS parent
        WHERE lower(parent.name) = lower('Amministrazione')
          AND parent.parent_id IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM menus WHERE route = '/administration/customer-credit'
          )
        ORDER BY parent.id
        LIMIT 1
    """))


def downgrade():
    op.execute("DELETE FROM menus WHERE route = '/administration/customer-credit'")
