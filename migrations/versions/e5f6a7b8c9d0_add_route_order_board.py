"""add route order board

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-20 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "route_order_board_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("route_id", sa.Integer(), nullable=False),
        sa.Column("registry_id", sa.Integer(), nullable=False),
        sa.Column("board_date", sa.Date(), nullable=False),
        sa.Column("planned_delivery_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("order_note", sa.Text(), nullable=True),
        sa.Column("list_done", sa.Boolean(), nullable=False),
        sa.Column("slack_channel_id", sa.String(length=50), nullable=True),
        sa.Column("slack_message_ts", sa.String(length=50), nullable=True),
        sa.Column("slack_thread_ts", sa.String(length=50), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(
            ["registry_id"],
            ["business_registries.id"],
            name=op.f("fk_route_order_board_entries_registry_id_business_registries"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["route_id"],
            ["delivery_routes.id"],
            name=op.f("fk_route_order_board_entries_route_id_delivery_routes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_route_order_board_entries")),
        sa.UniqueConstraint("route_id", "registry_id", "board_date", name="uq_route_order_board_entry"),
    )
    with op.batch_alter_table("route_order_board_entries", schema=None) as batch_op:
        batch_op.create_index("ix_route_order_board_entries_planned", ["route_id", "planned_delivery_at"], unique=False)
        batch_op.create_index("ix_route_order_board_entries_route_board", ["route_id", "board_date"], unique=False)
        batch_op.create_index(batch_op.f("ix_route_order_board_entries_board_date"), ["board_date"], unique=False)
        batch_op.create_index(batch_op.f("ix_route_order_board_entries_planned_delivery_at"), ["planned_delivery_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_route_order_board_entries_registry_id"), ["registry_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_route_order_board_entries_route_id"), ["route_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_route_order_board_entries_status"), ["status"], unique=False)

    op.create_table(
        "business_registry_alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("registry_id", sa.Integer(), nullable=False),
        sa.Column("message", sa.String(length=255), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(
            ["registry_id"],
            ["business_registries.id"],
            name=op.f("fk_business_registry_alerts_registry_id_business_registries"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_business_registry_alerts")),
    )
    with op.batch_alter_table("business_registry_alerts", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_business_registry_alerts_end_date"), ["end_date"], unique=False)
        batch_op.create_index(batch_op.f("ix_business_registry_alerts_is_active"), ["is_active"], unique=False)
        batch_op.create_index(batch_op.f("ix_business_registry_alerts_registry_id"), ["registry_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_business_registry_alerts_start_date"), ["start_date"], unique=False)


def downgrade():
    with op.batch_alter_table("business_registry_alerts", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_business_registry_alerts_start_date"))
        batch_op.drop_index(batch_op.f("ix_business_registry_alerts_registry_id"))
        batch_op.drop_index(batch_op.f("ix_business_registry_alerts_is_active"))
        batch_op.drop_index(batch_op.f("ix_business_registry_alerts_end_date"))
    op.drop_table("business_registry_alerts")

    with op.batch_alter_table("route_order_board_entries", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_route_order_board_entries_status"))
        batch_op.drop_index(batch_op.f("ix_route_order_board_entries_route_id"))
        batch_op.drop_index(batch_op.f("ix_route_order_board_entries_registry_id"))
        batch_op.drop_index(batch_op.f("ix_route_order_board_entries_planned_delivery_at"))
        batch_op.drop_index(batch_op.f("ix_route_order_board_entries_board_date"))
        batch_op.drop_index("ix_route_order_board_entries_route_board")
        batch_op.drop_index("ix_route_order_board_entries_planned")
    op.drop_table("route_order_board_entries")
