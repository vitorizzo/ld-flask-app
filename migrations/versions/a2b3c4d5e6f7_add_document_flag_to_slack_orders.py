"""add document flag to slack orders

Revision ID: a2b3c4d5e6f7
Revises: f6a7b8c9d0e1
Create Date: 2026-05-23 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "a2b3c4d5e6f7"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("slack_orders", sa.Column("document_issued", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("slack_orders", sa.Column("document_issued_at", sa.DateTime(), nullable=True))
    op.create_index("ix_slack_orders_document_issued", "slack_orders", ["document_issued"])
    op.alter_column("slack_orders", "document_issued", server_default=None)
    op.add_column("route_order_board_entries", sa.Column("order_attachments", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("route_order_board_entries", "order_attachments")
    op.drop_index("ix_slack_orders_document_issued", table_name="slack_orders")
    op.drop_column("slack_orders", "document_issued_at")
    op.drop_column("slack_orders", "document_issued")
