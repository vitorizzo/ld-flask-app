"""Organize checks and reports under Administration."""
from alembic import op
import sqlalchemy as sa

revision = "e7f8a9b0c1d2"
down_revision = "d6e7f8a9b0c1"
branch_labels = None
depends_on = None


def _parent(conn, name):
    return conn.execute(sa.text("""
        SELECT id FROM menus
        WHERE lower(name) = lower(:name) AND parent_id IS NULL
        ORDER BY id LIMIT 1
    """), {"name": name}).scalar()


def _ensure_parent(conn, administration_id, name, order):
    existing = conn.execute(sa.text("""
        SELECT id FROM menus WHERE lower(name) = lower(:name) AND parent_id = :parent_id LIMIT 1
    """), {"name": name, "parent_id": administration_id}).scalar()
    if existing:
        return existing, False
    return conn.execute(sa.text("""
        INSERT INTO menus (name, weight, sort_order, parent_id, route, is_active, is_visible, item_type)
        VALUES (:name, 40, :sort_order, :parent_id, NULL, true, true, 'link')
        RETURNING id
    """), {"name": name, "sort_order": order, "parent_id": administration_id}).scalar(), True


def _ensure_child(conn, parent_id, name, route, order):
    conn.execute(sa.text("""
        INSERT INTO menus (name, weight, sort_order, parent_id, route, is_active, is_visible, item_type)
        SELECT :name, 40, :sort_order, :parent_id, :route, true, true, 'link'
        WHERE NOT EXISTS (SELECT 1 FROM menus WHERE route = :route)
    """), {"name": name, "sort_order": order, "parent_id": parent_id, "route": route})


def upgrade():
    conn = op.get_bind()
    administration_id = _parent(conn, "Amministrazione")
    if not administration_id:
        return
    checks_id, _ = _ensure_parent(conn, administration_id, "Gestione assegni", 80)
    reports_id, _ = _ensure_parent(conn, administration_id, "Prospetti", 90)
    _ensure_child(conn, checks_id, "Assegni emessi", "/cassa/agenda/issued-checks", 10)
    _ensure_child(conn, checks_id, "Assegni clienti", "/cassa/agenda/checks", 20)
    _ensure_child(conn, reports_id, "Flusso di cassa", "/administration/cash-flow", 10)


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM menus WHERE route IN (:issued, :customer, :flow)"), {
        "issued": "/cassa/agenda/issued-checks", "customer": "/cassa/agenda/checks", "flow": "/administration/cash-flow",
    })
    conn.execute(sa.text("""
        DELETE FROM menus parent
        WHERE parent.parent_id IS NULL
          AND lower(parent.name) IN (lower('Gestione assegni'), lower('Prospetti'))
          AND NOT EXISTS (SELECT 1 FROM menus child WHERE child.parent_id = parent.id)
    """))
