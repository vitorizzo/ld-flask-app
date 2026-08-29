"""add administration PayByLink workflow

Revision ID: b9c0d1e2f4a6
Revises: a8b9c0d1e3f5
Create Date: 2026-08-29 15:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

from tools.crypto import EncryptedString


revision = "b9c0d1e2f4a6"
down_revision = "a8b9c0d1e3f5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "administration_payment_links",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("public_id", sa.String(length=48), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_order_id", sa.String(length=18), nullable=True),
        sa.Column("provider_reference", sa.String(length=160), nullable=True),
        sa.Column("provider_operation_id", sa.String(length=160), nullable=True),
        sa.Column("provider_security_token", EncryptedString(length=512), nullable=True),
        sa.Column("provider_last_event_id", sa.String(length=80), nullable=True),
        sa.Column("payment_url", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_order_id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index("ix_administration_payment_link_public_id", "administration_payment_links", ["public_id"])
    op.create_index("ix_administration_payment_link_provider_order_id", "administration_payment_links", ["provider_order_id"])
    op.create_index("ix_administration_payment_link_provider_reference", "administration_payment_links", ["provider_reference"])
    op.create_index("ix_administration_payment_link_provider_operation_id", "administration_payment_links", ["provider_operation_id"])
    op.create_index("ix_administration_payment_link_provider_last_event_id", "administration_payment_links", ["provider_last_event_id"])
    op.create_index("ix_administration_payment_link_status", "administration_payment_links", ["status"])
    op.create_index("ix_administration_payment_link_status_created", "administration_payment_links", ["status", "created_at"])
    op.create_index("ix_administration_payment_link_creator_created", "administration_payment_links", ["created_by_user_id", "created_at"])

    op.create_table(
        "administration_payment_link_deliveries",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("payment_link_id", sa.BigInteger(), nullable=False),
        sa.Column("requested_by_user_id", sa.Integer(), nullable=True),
        sa.Column("recipient_type", sa.String(length=24), nullable=False),
        sa.Column("recipient_user_id", sa.Integer(), nullable=True),
        sa.Column("recipient_registry_id", sa.Integer(), nullable=True),
        sa.Column("recipient_name", sa.String(length=255), nullable=True),
        sa.Column("recipient_email", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["payment_link_id"], ["administration_payment_links.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["recipient_registry_id"], ["business_registries.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_administration_payment_link_delivery_status", "administration_payment_link_deliveries", ["status"])
    op.create_index("ix_administration_payment_link_delivery_link_created", "administration_payment_link_deliveries", ["payment_link_id", "created_at"])

    op.execute(sa.text("""
        INSERT INTO menus (name, weight, sort_order, parent_id, route, is_active, is_visible, item_type)
        SELECT
            'Manda un link di pagamento',
            40,
            COALESCE((SELECT MAX(child.sort_order) + 1 FROM menus AS child WHERE child.parent_id = parent.id), 1),
            parent.id,
            '/administration/payment-links',
            true,
            true,
            'link'
        FROM menus AS parent
        WHERE lower(parent.name) = lower('Amministrazione')
          AND parent.parent_id IS NULL
          AND NOT EXISTS (SELECT 1 FROM menus WHERE route = '/administration/payment-links')
        ORDER BY parent.id
        LIMIT 1
    """))


def downgrade():
    op.execute("DELETE FROM menus WHERE route = '/administration/payment-links'")
    op.drop_index("ix_administration_payment_link_delivery_link_created", table_name="administration_payment_link_deliveries")
    op.drop_index("ix_administration_payment_link_delivery_status", table_name="administration_payment_link_deliveries")
    op.drop_table("administration_payment_link_deliveries")
    op.drop_index("ix_administration_payment_link_creator_created", table_name="administration_payment_links")
    op.drop_index("ix_administration_payment_link_status_created", table_name="administration_payment_links")
    op.drop_index("ix_administration_payment_link_status", table_name="administration_payment_links")
    op.drop_index("ix_administration_payment_link_provider_last_event_id", table_name="administration_payment_links")
    op.drop_index("ix_administration_payment_link_provider_operation_id", table_name="administration_payment_links")
    op.drop_index("ix_administration_payment_link_provider_reference", table_name="administration_payment_links")
    op.drop_index("ix_administration_payment_link_provider_order_id", table_name="administration_payment_links")
    op.drop_index("ix_administration_payment_link_public_id", table_name="administration_payment_links")
    op.drop_table("administration_payment_links")
