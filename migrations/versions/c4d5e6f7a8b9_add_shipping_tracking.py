"""add shipping tracking

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-06-01 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "c4d5e6f7a8b9"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "courier_integrations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("base_url", sa.String(length=255), nullable=True),
        sa.Column("credentials", sa.JSON(), nullable=True),
        sa.Column("settings", sa.JSON(), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_courier_integrations_code"),
    )
    op.create_index("ix_courier_integrations_enabled", "courier_integrations", ["is_enabled"])

    op.create_table(
        "external_orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False, server_default="poleepo"),
        sa.Column("external_id", sa.String(length=120), nullable=False),
        sa.Column("order_number", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="imported"),
        sa.Column("customer_registry_id", sa.Integer(), nullable=True),
        sa.Column("customer_name", sa.String(length=255), nullable=True),
        sa.Column("recipient_name", sa.String(length=255), nullable=True),
        sa.Column("recipient_address", sa.Text(), nullable=True),
        sa.Column("order_total", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("ordered_at", sa.DateTime(), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["customer_registry_id"], ["business_registries.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "external_id", name="uq_external_orders_source_external_id"),
    )
    op.create_index("ix_external_orders_customer_registry_id", "external_orders", ["customer_registry_id"])
    op.create_index("ix_external_orders_order_number", "external_orders", ["order_number"])
    op.create_index("ix_external_orders_source", "external_orders", ["source"])
    op.create_index("ix_external_orders_source_status", "external_orders", ["source", "status"])
    op.create_index("ix_external_orders_status", "external_orders", ["status"])

    op.create_table(
        "shipments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("courier_code", sa.String(length=30), nullable=False),
        sa.Column("courier_name", sa.String(length=80), nullable=True),
        sa.Column("tracking_number", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="created"),
        sa.Column("status_label", sa.String(length=120), nullable=True),
        sa.Column("customer_registry_id", sa.Integer(), nullable=True),
        sa.Column("customer_name", sa.String(length=255), nullable=True),
        sa.Column("recipient_name", sa.String(length=255), nullable=True),
        sa.Column("recipient_address", sa.Text(), nullable=True),
        sa.Column("external_order_id", sa.String(length=120), nullable=True),
        sa.Column("source", sa.String(length=40), nullable=True),
        sa.Column("reference", sa.String(length=120), nullable=True),
        sa.Column("shipped_at", sa.DateTime(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("last_tracking_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["customer_registry_id"], ["business_registries.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("courier_code", "tracking_number", name="uq_shipments_courier_tracking"),
    )
    op.create_index("ix_shipments_courier_code", "shipments", ["courier_code"])
    op.create_index("ix_shipments_courier_status", "shipments", ["courier_code", "status"])
    op.create_index("ix_shipments_customer_registry_id", "shipments", ["customer_registry_id"])
    op.create_index("ix_shipments_external_order_id", "shipments", ["external_order_id"])
    op.create_index("ix_shipments_status", "shipments", ["status"])

    op.create_table(
        "shipment_tracking_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("shipment_id", sa.Integer(), nullable=False),
        sa.Column("event_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=80), nullable=True),
        sa.Column("location", sa.String(length=180), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["shipment_id"], ["shipments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_shipment_tracking_events_shipment_at", "shipment_tracking_events", ["shipment_id", "event_at"])
    op.create_index("ix_shipment_tracking_events_shipment_id", "shipment_tracking_events", ["shipment_id"])

    op.execute("""
        INSERT INTO courier_integrations (code, name, is_enabled)
        VALUES ('brt', 'BRT', false), ('gls', 'GLS', false), ('dhl', 'DHL', false), ('poleepo', 'Poleepo', false)
        ON CONFLICT (code) DO NOTHING
    """)
    op.execute("""
        INSERT INTO menus (name, weight, sort_order, parent_id, route, is_active, is_visible, item_type)
        SELECT 'Spedizioni', 30, 95, NULL, '/shipping', true, true, 'link'
        WHERE NOT EXISTS (SELECT 1 FROM menus WHERE route = '/shipping')
    """)


def downgrade():
    op.execute("DELETE FROM menus WHERE route = '/shipping'")
    op.drop_index("ix_shipment_tracking_events_shipment_id", table_name="shipment_tracking_events")
    op.drop_index("ix_shipment_tracking_events_shipment_at", table_name="shipment_tracking_events")
    op.drop_table("shipment_tracking_events")
    op.drop_index("ix_shipments_status", table_name="shipments")
    op.drop_index("ix_shipments_external_order_id", table_name="shipments")
    op.drop_index("ix_shipments_customer_registry_id", table_name="shipments")
    op.drop_index("ix_shipments_courier_status", table_name="shipments")
    op.drop_index("ix_shipments_courier_code", table_name="shipments")
    op.drop_table("shipments")
    op.drop_index("ix_external_orders_status", table_name="external_orders")
    op.drop_index("ix_external_orders_source_status", table_name="external_orders")
    op.drop_index("ix_external_orders_source", table_name="external_orders")
    op.drop_index("ix_external_orders_order_number", table_name="external_orders")
    op.drop_index("ix_external_orders_customer_registry_id", table_name="external_orders")
    op.drop_table("external_orders")
    op.drop_index("ix_courier_integrations_enabled", table_name="courier_integrations")
    op.drop_table("courier_integrations")
