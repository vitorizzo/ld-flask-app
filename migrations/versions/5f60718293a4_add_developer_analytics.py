"""add developer analytics

Revision ID: 5f60718293a4
Revises: 4e5f60718293
Create Date: 2026-07-20
"""
from alembic import op
import sqlalchemy as sa


revision = "5f60718293a4"
down_revision = "4e5f60718293"
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


def upgrade():
    op.create_table(
        "app_visitors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("visitor_hash", sa.String(length=64), nullable=False),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("visit_count", sa.BigInteger(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("visitor_hash", name="uq_app_visitors_visitor_hash"),
    )
    op.create_index("ix_app_visitors_last_seen", "app_visitors", ["last_seen"])

    conn = op.get_bind()
    developer_id = conn.execute(
        sa.select(menus.c.id).where(menus.c.name == "Developer", menus.c.parent_id.is_(None)).limit(1)
    ).scalar()
    if developer_id is None:
        max_order = conn.execute(
            sa.select(sa.func.coalesce(sa.func.max(menus.c.sort_order), 0)).where(menus.c.parent_id.is_(None))
        ).scalar()
        developer_id = conn.execute(
            menus.insert().values(
                name="Developer", weight=999, sort_order=int(max_order or 0) + 1,
                parent_id=None, route=None, is_active=True, is_visible=True, item_type="link",
            ).returning(menus.c.id)
        ).scalar()
    else:
        conn.execute(menus.update().where(menus.c.id == developer_id).values(weight=999, is_active=True, is_visible=True))

    dashboard_id = conn.execute(
        sa.select(menus.c.id).where(menus.c.route == "/developer/dashboard").limit(1)
    ).scalar()
    values = dict(
        name="Dashboard", weight=999, sort_order=1, parent_id=developer_id,
        route="/developer/dashboard", is_active=True, is_visible=True, item_type="link",
    )
    if dashboard_id is None:
        conn.execute(menus.insert().values(**values))
    else:
        conn.execute(menus.update().where(menus.c.id == dashboard_id).values(**values))


def downgrade():
    conn = op.get_bind()
    conn.execute(menus.delete().where(menus.c.route == "/developer/dashboard"))
    developer_id = conn.execute(
        sa.select(menus.c.id).where(menus.c.name == "Developer", menus.c.parent_id.is_(None)).limit(1)
    ).scalar()
    if developer_id is not None:
        child_count = conn.execute(
            sa.select(sa.func.count()).select_from(menus).where(menus.c.parent_id == developer_id)
        ).scalar()
        if not child_count:
            conn.execute(menus.delete().where(menus.c.id == developer_id))
    op.drop_index("ix_app_visitors_last_seen", table_name="app_visitors")
    op.drop_table("app_visitors")
