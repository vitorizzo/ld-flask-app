"""add customer route order reminders

Revision ID: d0e1f2a3b4c5
Revises: c0d1e2f3a5b7
Create Date: 2026-09-03
"""
from alembic import op
import sqlalchemy as sa


revision = "d0e1f2a3b4c5"
down_revision = "c0d1e2f3a5b7"
branch_labels = None
depends_on = None


TABLE = "customer_route_order_reminders"
REQUIRED_COLUMNS = {
    "id", "public_id", "user_id", "route_id", "registry_id", "delivery_date",
    "status", "action", "sent_at", "acted_at", "last_error", "created_at", "updated_at",
}


def _create_table():
    op.create_table(
        TABLE,
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("public_id", sa.String(length=48), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("route_id", sa.Integer(), nullable=False),
        sa.Column("registry_id", sa.Integer(), nullable=False),
        sa.Column("delivery_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("action", sa.String(length=24), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["registry_id"], ["business_registries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["route_id"], ["delivery_routes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
        sa.UniqueConstraint(
            "user_id", "route_id", "registry_id", "delivery_date",
            name="uq_customer_route_order_reminder_delivery",
        ),
    )


def _ensure_indexes(bind):
    inspector = sa.inspect(bind)
    existing = {
        tuple(index.get("column_names") or ())
        for index in inspector.get_indexes(TABLE)
    }
    definitions = (
        ("ix_customer_route_order_reminders_public_id", ("public_id",)),
        ("ix_customer_route_order_reminders_user_id", ("user_id",)),
        ("ix_customer_route_order_reminders_route_id", ("route_id",)),
        ("ix_customer_route_order_reminders_registry_id", ("registry_id",)),
        ("ix_customer_route_order_reminders_delivery_date", ("delivery_date",)),
        ("ix_customer_route_order_reminders_status", ("status",)),
        ("ix_customer_route_order_reminders_delivery_status", ("delivery_date", "status")),
    )
    for name, columns in definitions:
        if columns not in existing:
            op.create_index(name, TABLE, list(columns))
            existing.add(columns)


def upgrade():
    if op.get_context().as_sql:
        _create_table()
        return

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table(TABLE):
        existing = {column["name"] for column in inspector.get_columns(TABLE)}
        missing = sorted(REQUIRED_COLUMNS - existing)
        if missing:
            raise RuntimeError(f"La tabella preesistente {TABLE} e' incompleta; mancano: {', '.join(missing)}")
    else:
        _create_table()
    _ensure_indexes(bind)


def downgrade():
    op.execute(sa.text(f'DROP TABLE IF EXISTS "{TABLE}"'))
