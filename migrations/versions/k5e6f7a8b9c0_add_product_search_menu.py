"""Add the warehouse product search menu."""
from alembic import op
import sqlalchemy as sa

revision = "k5e6f7a8b9c0"
down_revision = "j4d5e6f7a8b9"
branch_labels = None
depends_on = None


def _menu_id(conn, name, parent_id=None):
    if parent_id is None:
        return conn.execute(sa.text(
            "SELECT id FROM menus WHERE lower(name)=lower(:name) AND parent_id IS NULL ORDER BY id LIMIT 1"
        ), {"name": name}).scalar()
    return conn.execute(sa.text(
        "SELECT id FROM menus WHERE lower(name)=lower(:name) AND parent_id=:parent_id ORDER BY id LIMIT 1"
    ), {"name": name, "parent_id": parent_id}).scalar()


def _next_order(conn, parent_id):
    value = conn.execute(sa.text(
        "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM menus WHERE parent_id=:parent_id"
    ), {"parent_id": parent_id}).scalar()
    return int(value or 1)


def upgrade():
    conn = op.get_bind()
    strumenti_id = _menu_id(conn, "Strumenti")
    if not strumenti_id:
        return
    ricerche_id = _menu_id(conn, "Ricerche", strumenti_id)
    if not ricerche_id:
        ricerche_id = conn.execute(sa.text("""
            INSERT INTO menus (name, weight, sort_order, parent_id, route, is_active, is_visible, item_type)
            VALUES ('Ricerche', 40, :sort_order, :parent_id, NULL, true, true, 'link')
            RETURNING id
        """), {"sort_order": _next_order(conn, strumenti_id), "parent_id": strumenti_id}).scalar()
    existing = conn.execute(sa.text("SELECT id FROM menus WHERE route=:route LIMIT 1"),
                            {"route": "/search/elenco-prodotti"}).scalar()
    values = {"name": "Elenco prodotti", "weight": 40, "sort_order": _next_order(conn, ricerche_id),
              "parent_id": ricerche_id, "route": "/search/elenco-prodotti"}
    if existing:
        conn.execute(sa.text("""
            UPDATE menus SET name=:name, weight=:weight, sort_order=:sort_order, parent_id=:parent_id,
                is_active=true, is_visible=true, item_type='link' WHERE id=:id
        """), {**values, "id": existing})
    else:
        conn.execute(sa.text("""
            INSERT INTO menus (name, weight, sort_order, parent_id, route, is_active, is_visible, item_type)
            VALUES (:name, :weight, :sort_order, :parent_id, :route, true, true, 'link')
        """), values)


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM menus WHERE route='/search/elenco-prodotti'"))
    conn.execute(sa.text("""
        DELETE FROM menus parent
        WHERE lower(parent.name)=lower('Ricerche')
          AND parent.parent_id=(SELECT id FROM menus WHERE lower(name)=lower('Strumenti') AND parent_id IS NULL LIMIT 1)
          AND NOT EXISTS (SELECT 1 FROM menus child WHERE child.parent_id=parent.id)
    """))
