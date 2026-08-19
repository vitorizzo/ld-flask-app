"""add order history menu

Revision ID: a2b3c4d5e6f8
Revises: f1a2b3c4d5e6
Create Date: 2026-08-19 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "a2b3c4d5e6f8"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    parent_id = conn.execute(sa.text("""
        SELECT id FROM menus
        WHERE lower(name) = lower('Magazzino') AND parent_id IS NULL
        ORDER BY id LIMIT 1
    """)).scalar()
    if parent_id is None:
        parent_id = conn.execute(sa.text("""
            INSERT INTO menus (name, weight, sort_order, parent_id, route, is_active, is_visible, item_type)
            VALUES ('Magazzino', 30, 4, NULL, NULL, true, true, 'link')
            RETURNING id
        """)).scalar()

    sort_order = conn.execute(
        sa.text("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM menus WHERE parent_id = :parent_id"),
        {"parent_id": parent_id},
    ).scalar()
    existing = conn.execute(
        sa.text("SELECT id FROM menus WHERE route = '/route-orders/history' ORDER BY id LIMIT 1")
    ).scalar()
    values = {"parent_id": parent_id, "sort_order": sort_order}
    if existing:
        values["id"] = existing
        conn.execute(sa.text("""
            UPDATE menus SET name='Storico ordini', weight=30, sort_order=:sort_order,
                parent_id=:parent_id, is_active=true, is_visible=true, item_type='link'
            WHERE id=:id
        """), values)
    else:
        conn.execute(sa.text("""
            INSERT INTO menus (name, weight, sort_order, parent_id, route, is_active, is_visible, item_type)
            VALUES ('Storico ordini', 30, :sort_order, :parent_id, '/route-orders/history', true, true, 'link')
        """), values)


def downgrade():
    op.execute("DELETE FROM menus WHERE route = '/route-orders/history'")
