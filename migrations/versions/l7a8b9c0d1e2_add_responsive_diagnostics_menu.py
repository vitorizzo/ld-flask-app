"""Add Developer responsive diagnostics command."""
from alembic import op
import sqlalchemy as sa

revision = "l7a8b9c0d1e2"
down_revision = "k6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade():
    menus = sa.table("menus", sa.column("id", sa.Integer), sa.column("name", sa.String),
                     sa.column("weight", sa.Integer), sa.column("sort_order", sa.Integer),
                     sa.column("parent_id", sa.Integer), sa.column("route", sa.String),
                     sa.column("is_active", sa.Boolean), sa.column("is_visible", sa.Boolean),
                     sa.column("item_type", sa.String))
    conn = op.get_bind()
    parent = conn.execute(sa.select(menus.c.id).where(
        sa.func.lower(menus.c.name) == "developer", menus.c.parent_id.is_(None)
    ).order_by(menus.c.id).limit(1)).scalar()
    if parent is None:
        sort = conn.execute(sa.select(sa.func.coalesce(sa.func.max(menus.c.sort_order), 0)).where(
            menus.c.parent_id.is_(None))).scalar()
        parent = conn.execute(menus.insert().values(name="Developer", weight=999,
            sort_order=int(sort or 0) + 1, parent_id=None, route=None,
            is_active=True, is_visible=True, item_type="link").returning(menus.c.id)).scalar()
    item = conn.execute(sa.select(menus.c.id).where(
        menus.c.route == "/developer/responsive").order_by(menus.c.id).limit(1)).scalar()
    values = dict(name="Diagnostica responsive", weight=999, sort_order=2,
                  parent_id=parent, route="/developer/responsive", is_active=True,
                  is_visible=True, item_type="link")
    if item is None:
        conn.execute(menus.insert().values(**values))
    else:
        conn.execute(menus.update().where(menus.c.id == item).values(**values))


def downgrade():
    op.execute(sa.text("DELETE FROM menus WHERE route = '/developer/responsive'"))
