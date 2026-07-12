"""reorganize customer service menus

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-07-12 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "f5a6b7c8d9e0"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


menus = sa.table(
    "menus",
    sa.column("id", sa.Integer),
    sa.column("name", sa.String),
    sa.column("weight", sa.Integer),
    sa.column("sort_order", sa.Integer),
    sa.column("parent_id", sa.Integer),
    sa.column("route", sa.String),
    sa.column("is_active", sa.Boolean),
    sa.column("is_visible", sa.Boolean),
    sa.column("item_type", sa.String),
)


def _one(conn, where):
    return conn.execute(sa.select(menus.c.id).where(where).limit(1)).scalar()


def _max_root_order(conn):
    value = conn.execute(sa.select(sa.func.max(menus.c.sort_order)).where(menus.c.parent_id.is_(None))).scalar()
    return int(value or 0)


def _max_child_order(conn, parent_id):
    value = conn.execute(sa.select(sa.func.max(menus.c.sort_order)).where(menus.c.parent_id == parent_id)).scalar()
    return int(value or 0)


def _insert_menu(conn, *, name, route, weight, parent_id, sort_order):
    existing = _one(conn, menus.c.route == route) if route else _one(conn, sa.and_(menus.c.name == name, menus.c.parent_id == parent_id))
    if existing:
        conn.execute(
            menus.update()
            .where(menus.c.id == existing)
            .values(name=name, route=route, weight=weight, parent_id=parent_id, is_active=True, is_visible=True, item_type="link")
        )
        return existing
    result = conn.execute(
        menus.insert().values(
            name=name,
            route=route,
            weight=weight,
            parent_id=parent_id,
            sort_order=sort_order,
            is_active=True,
            is_visible=True,
            item_type="link",
        ).returning(menus.c.id)
    )
    return result.scalar()


def upgrade():
    conn = op.get_bind()
    strumenti_id = _one(conn, menus.c.name == "Strumenti")
    impostazioni_id = _one(conn, menus.c.name == "Impostazioni")
    if strumenti_id and impostazioni_id:
        base_order = _max_child_order(conn, strumenti_id)
        children = conn.execute(
            sa.select(menus.c.id).where(menus.c.parent_id == impostazioni_id).order_by(menus.c.sort_order.asc(), menus.c.id.asc())
        ).scalars().all()
        for offset, child_id in enumerate(children, start=1):
            conn.execute(menus.update().where(menus.c.id == child_id).values(parent_id=strumenti_id, sort_order=base_order + offset))
        conn.execute(menus.update().where(menus.c.id == impostazioni_id).values(is_active=False, is_visible=False))

    service_id = _one(conn, menus.c.name == "Servizio clienti")
    if not service_id:
        result = conn.execute(
            menus.insert().values(
                name="Servizio clienti",
                route=None,
                weight=40,
                parent_id=None,
                sort_order=_max_root_order(conn) + 1,
                is_active=True,
                is_visible=True,
                item_type="link",
            ).returning(menus.c.id)
        )
        service_id = result.scalar()
    else:
        conn.execute(menus.update().where(menus.c.id == service_id).values(weight=40, is_active=True, is_visible=True))

    _insert_menu(conn, name="Attivazioni Horeca", route="/settings/horeca-activations", weight=40, parent_id=service_id, sort_order=1)
    _insert_menu(conn, name="Assistenza LDApp", route="/settings/support-tickets", weight=900, parent_id=service_id, sort_order=2)


def downgrade():
    conn = op.get_bind()
    service_id = _one(conn, menus.c.name == "Servizio clienti")
    if service_id:
        conn.execute(menus.delete().where(menus.c.parent_id == service_id))
        conn.execute(menus.delete().where(menus.c.id == service_id))
    strumenti_id = _one(conn, menus.c.name == "Strumenti")
    impostazioni_id = _one(conn, menus.c.name == "Impostazioni")
    if strumenti_id and impostazioni_id:
        conn.execute(menus.update().where(menus.c.id == impostazioni_id).values(is_active=True, is_visible=True))
