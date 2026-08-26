"""repair payment service customer menus

Revision ID: e6f7a8b9c1d3
Revises: d5e6f7a8b0c2
Create Date: 2026-08-26 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "e6f7a8b9c1d3"
down_revision = "d5e6f7a8b0c2"
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


MENU_ITEMS = (
    ("Comunicazioni di pagamento", "/customer-account/office/payment-communications"),
    ("Contestazioni partite aperte", "/customer-account/office/payment-disputes"),
)


def upgrade():
    conn = op.get_bind()
    service_id = conn.execute(
        sa.select(menus.c.id).where(sa.func.lower(menus.c.name) == "servizio clienti").limit(1)
    ).scalar()
    if service_id is None:
        max_root_order = conn.execute(
            sa.select(sa.func.max(menus.c.sort_order)).where(menus.c.parent_id.is_(None))
        ).scalar() or 0
        service_id = conn.execute(
            menus.insert().values(
                name="Servizio clienti", weight=40, sort_order=int(max_root_order) + 1,
                parent_id=None, route=None, is_active=True, is_visible=True, item_type="link",
            ).returning(menus.c.id)
        ).scalar()
    else:
        conn.execute(menus.update().where(menus.c.id == service_id).values(
            weight=40, is_active=True, is_visible=True,
        ))

    max_order = conn.execute(
        sa.select(sa.func.max(menus.c.sort_order)).where(menus.c.parent_id == service_id)
    ).scalar() or 0
    for offset, (name, route) in enumerate(MENU_ITEMS, start=1):
        existing_id = conn.execute(sa.select(menus.c.id).where(menus.c.route == route).limit(1)).scalar()
        values = {
            "name": name, "route": route, "weight": 40, "parent_id": service_id,
            "is_active": True, "is_visible": True, "item_type": "link",
        }
        if existing_id is None:
            conn.execute(menus.insert().values(sort_order=int(max_order) + offset, **values))
        else:
            conn.execute(menus.update().where(menus.c.id == existing_id).values(**values))


def downgrade():
    # La revisione precedente gestisce la creazione/rimozione delle stesse voci.
    pass
