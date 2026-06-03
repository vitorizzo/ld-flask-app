"""split shipping menu

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-06-03 11:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "f7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def _ensure_child(conn, parent_id, name, route, sort_order):
    existing = conn.execute(sa.text("SELECT id FROM menus WHERE route = :route"), {"route": route}).scalar()
    if existing:
        conn.execute(
            sa.text(
                """
                UPDATE menus
                SET name = :name,
                    weight = 30,
                    sort_order = :sort_order,
                    parent_id = :parent_id,
                    is_active = true,
                    is_visible = true,
                    item_type = 'link'
                WHERE id = :id
                """
            ),
            {"id": existing, "name": name, "sort_order": sort_order, "parent_id": parent_id},
        )
        return
    conn.execute(
        sa.text(
            """
            INSERT INTO menus (name, weight, sort_order, parent_id, route, is_active, is_visible, item_type)
            VALUES (:name, 30, :sort_order, :parent_id, :route, true, true, 'link')
            """
        ),
        {"name": name, "sort_order": sort_order, "parent_id": parent_id, "route": route},
    )


def upgrade():
    conn = op.get_bind()
    parent_id = conn.execute(sa.text("SELECT id FROM menus WHERE route = '/shipping' ORDER BY id LIMIT 1")).scalar()
    if not parent_id:
        parent_id = conn.execute(
            sa.text(
                """
                INSERT INTO menus (name, weight, sort_order, parent_id, route, is_active, is_visible, item_type)
                VALUES ('Spedizioni', 30, 95, NULL, '/shipping', true, true, 'link')
                RETURNING id
                """
            )
        ).scalar()
    else:
        conn.execute(
            sa.text(
                """
                UPDATE menus
                SET name = 'Spedizioni',
                    weight = 30,
                    sort_order = 95,
                    parent_id = NULL,
                    route = '/shipping',
                    is_active = true,
                    is_visible = true,
                    item_type = 'link'
                WHERE id = :parent_id
                """
            ),
            {"parent_id": parent_id},
        )

    _ensure_child(conn, parent_id, "Consultazione spedizioni", "/shipping/shipments", 10)
    _ensure_child(conn, parent_id, "Ordini Poleepo", "/shipping/orders", 20)
    _ensure_child(conn, parent_id, "Account corrieri", "/shipping/accounts", 30)


def downgrade():
    op.execute(
        """
        DELETE FROM menus
        WHERE route IN ('/shipping/shipments', '/shipping/orders', '/shipping/accounts')
        """
    )
