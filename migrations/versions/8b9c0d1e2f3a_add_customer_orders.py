"""add customer orders

Revision ID: 8b9c0d1e2f3a
Revises: 7a8b9c0d1e2f
Create Date: 2026-07-06 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "8b9c0d1e2f3a"
down_revision = "7a8b9c0d1e2f"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("user", sa.Column("customer_registry_id", sa.Integer(), nullable=True))
    op.create_index("ix_user_customer_registry_id", "user", ["customer_registry_id"], unique=False)
    op.create_foreign_key("fk_user_customer_registry_id", "user", "business_registries", ["customer_registry_id"], ["id"])

    op.create_table(
        "customer_order_delivery_options",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("requires_value", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("value_label", sa.String(length=80), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_customer_order_delivery_options_code"),
    )
    op.create_index(
        "ix_customer_order_delivery_options_active_sort",
        "customer_order_delivery_options",
        ["is_active", "sort_order"],
        unique=False,
    )

    op.create_table(
        "customer_orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("registry_id", sa.Integer(), nullable=False),
        sa.Column("route_id", sa.Integer(), nullable=True),
        sa.Column("delivery_option_id", sa.Integer(), nullable=True),
        sa.Column("delivery_option_value", sa.String(length=160), nullable=True),
        sa.Column("order_text", sa.Text(), nullable=True),
        sa.Column("attachments", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="received"),
        sa.Column("route_board_entry_id", sa.Integer(), nullable=True),
        sa.Column("slack_order_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["delivery_option_id"], ["customer_order_delivery_options.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["registry_id"], ["business_registries.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["route_board_entry_id"], ["route_order_board_entries.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["route_id"], ["delivery_routes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["slack_order_id"], ["slack_orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_customer_orders_created", "customer_orders", ["created_at"], unique=False)
    op.create_index("ix_customer_orders_registry_status", "customer_orders", ["registry_id", "status"], unique=False)
    op.create_index("ix_customer_orders_route_id", "customer_orders", ["route_id"], unique=False)
    op.create_index("ix_customer_orders_user_id", "customer_orders", ["user_id"], unique=False)

    op.create_table(
        "customer_order_revisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("change_type", sa.String(length=30), nullable=False, server_default="addition"),
        sa.Column("order_text", sa.Text(), nullable=True),
        sa.Column("attachments", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("delivery_option_id", sa.Integer(), nullable=True),
        sa.Column("delivery_option_value", sa.String(length=160), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["delivery_option_id"], ["customer_order_delivery_options.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["order_id"], ["customer_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_customer_order_revisions_order_created", "customer_order_revisions", ["order_id", "created_at"], unique=False)

    op.bulk_insert(
        sa.table(
            "customer_order_delivery_options",
            sa.column("code", sa.String),
            sa.column("label", sa.String),
            sa.column("requires_value", sa.Boolean),
            sa.column("value_label", sa.String),
            sa.column("sort_order", sa.Integer),
            sa.column("is_active", sa.Boolean),
        ),
        [
            {"code": "prossimo_giro", "label": "Con il prossimo giro", "requires_value": False, "value_label": None, "sort_order": 10, "is_active": True},
            {"code": "prima_possibile", "label": "Prima possibile", "requires_value": False, "value_label": None, "sort_order": 20, "is_active": True},
            {"code": "urgente", "label": "Urgente", "requires_value": False, "value_label": None, "sort_order": 30, "is_active": True},
            {"code": "data_consegna", "label": "Data consegna", "requires_value": True, "value_label": "Data richiesta", "sort_order": 40, "is_active": True},
            {"code": "entro_giorno", "label": "Entro un giorno X", "requires_value": True, "value_label": "Giorno richiesto", "sort_order": 50, "is_active": True},
        ],
    )


def downgrade():
    op.drop_index("ix_customer_order_revisions_order_created", table_name="customer_order_revisions")
    op.drop_table("customer_order_revisions")
    op.drop_index("ix_customer_orders_user_id", table_name="customer_orders")
    op.drop_index("ix_customer_orders_route_id", table_name="customer_orders")
    op.drop_index("ix_customer_orders_registry_status", table_name="customer_orders")
    op.drop_index("ix_customer_orders_created", table_name="customer_orders")
    op.drop_table("customer_orders")
    op.drop_index("ix_customer_order_delivery_options_active_sort", table_name="customer_order_delivery_options")
    op.drop_table("customer_order_delivery_options")
    op.drop_constraint("fk_user_customer_registry_id", "user", type_="foreignkey")
    op.drop_index("ix_user_customer_registry_id", table_name="user")
    op.drop_column("user", "customer_registry_id")
