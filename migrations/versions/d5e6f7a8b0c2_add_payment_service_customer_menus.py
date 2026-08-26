"""add payment service customer menus

Revision ID: d5e6f7a8b0c2
Revises: c4d5e6f7a0b1
Create Date: 2026-08-26 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "d5e6f7a8b0c2"
down_revision = "c4d5e6f7a0b1"
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


def _upsert_child(conn, parent_id, name, route, sort_order):
    existing = conn.execute(sa.select(menus.c.id).where(menus.c.route == route).limit(1)).scalar()
    values = {
        "name": name,
        "route": route,
        "weight": 40,
        "parent_id": parent_id,
        "sort_order": sort_order,
        "is_active": True,
        "is_visible": True,
        "item_type": "link",
    }
    if existing:
        conn.execute(menus.update().where(menus.c.id == existing).values(**values))
    else:
        conn.execute(menus.insert().values(**values))


def upgrade():
    conn = op.get_bind()
    service_id = conn.execute(
        sa.select(menus.c.id).where(sa.func.lower(menus.c.name) == "servizio clienti").limit(1)
    ).scalar()
    if not service_id:
        max_root_order = conn.execute(
            sa.select(sa.func.max(menus.c.sort_order)).where(menus.c.parent_id.is_(None))
        ).scalar() or 0
        service_id = conn.execute(
            menus.insert().values(
                name="Servizio clienti", weight=40, sort_order=int(max_root_order) + 1,
                parent_id=None, route=None, is_active=True, is_visible=True, item_type="link",
            ).returning(menus.c.id)
        ).scalar()

    max_child_order = conn.execute(
        sa.select(sa.func.max(menus.c.sort_order)).where(menus.c.parent_id == service_id)
    ).scalar() or 0
    _upsert_child(
        conn, service_id, "Comunicazioni di pagamento",
        "/customer-account/office/payment-communications", int(max_child_order) + 1,
    )
    _upsert_child(
        conn, service_id, "Contestazioni partite aperte",
        "/customer-account/office/payment-disputes", int(max_child_order) + 2,
    )


def downgrade():
    conn = op.get_bind()
    conn.execute(menus.delete().where(menus.c.route.in_((
        "/customer-account/office/payment-communications",
        "/customer-account/office/payment-disputes",
    ))))
