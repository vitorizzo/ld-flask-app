"""add ticket message read state

Revision ID: 2c3d4e5f6071
Revises: 1b2c3d4e5f60
Create Date: 2026-07-13 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "2c3d4e5f6071"
down_revision = "1b2c3d4e5f60"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("support_ticket_messages", sa.Column("read_by_user_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("support_ticket_messages", sa.Column("read_by_support_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        sa.text(
            "UPDATE support_ticket_messages "
            "SET read_by_user_at = CURRENT_TIMESTAMP, read_by_support_at = CURRENT_TIMESTAMP"
        )
    )
    op.create_index(
        "ix_support_ticket_messages_read_by_user_at",
        "support_ticket_messages",
        ["read_by_user_at"],
        unique=False,
    )
    op.create_index(
        "ix_support_ticket_messages_read_by_support_at",
        "support_ticket_messages",
        ["read_by_support_at"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_support_ticket_messages_read_by_support_at", table_name="support_ticket_messages")
    op.drop_index("ix_support_ticket_messages_read_by_user_at", table_name="support_ticket_messages")
    op.drop_column("support_ticket_messages", "read_by_support_at")
    op.drop_column("support_ticket_messages", "read_by_user_at")
