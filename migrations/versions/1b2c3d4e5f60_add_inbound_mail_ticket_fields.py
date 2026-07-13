"""add inbound mail and ticket correlation fields

Revision ID: 1b2c3d4e5f60
Revises: 0a1b2c3d4e5f
Create Date: 2026-07-13 12:00:00.000000

"""
import secrets

from alembic import op
import sqlalchemy as sa


revision = "1b2c3d4e5f60"
down_revision = "0a1b2c3d4e5f"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("email_accounts", sa.Column("imap_server", sa.String(length=255), nullable=True))
    op.add_column("email_accounts", sa.Column("imap_port", sa.Integer(), nullable=False, server_default="993"))
    op.add_column("email_accounts", sa.Column("imap_use_tls", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("email_accounts", sa.Column("imap_use_ssl", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("email_accounts", sa.Column("imap_username", sa.String(length=255), nullable=True))
    op.add_column("email_accounts", sa.Column("imap_password_encrypted", sa.String(length=2048), nullable=True))
    op.add_column("email_accounts", sa.Column("imap_folder", sa.String(length=120), nullable=False, server_default="INBOX"))
    op.add_column("email_accounts", sa.Column("imap_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))

    op.add_column("support_tickets", sa.Column("public_token", sa.String(length=64), nullable=True))
    tickets = sa.table(
        "support_tickets",
        sa.column("id", sa.Integer()),
        sa.column("public_token", sa.String(length=64)),
    )
    connection = op.get_bind()
    for ticket_id in connection.execute(sa.select(tickets.c.id)).scalars():
        connection.execute(
            tickets.update().where(tickets.c.id == ticket_id).values(public_token=secrets.token_urlsafe(32))
        )
    op.alter_column("support_tickets", "public_token", existing_type=sa.String(length=64), nullable=False)
    op.create_index("ix_support_tickets_public_token", "support_tickets", ["public_token"], unique=True)

    op.add_column("support_ticket_messages", sa.Column("source", sa.String(length=30), nullable=False, server_default="web"))
    op.add_column("support_ticket_messages", sa.Column("external_message_id", sa.String(length=500), nullable=True))
    op.add_column("support_ticket_messages", sa.Column("in_reply_to", sa.String(length=500), nullable=True))
    op.create_index(
        "ix_support_ticket_messages_external_message_id",
        "support_ticket_messages",
        ["external_message_id"],
        unique=True,
    )
    op.create_index("ix_support_ticket_messages_in_reply_to", "support_ticket_messages", ["in_reply_to"], unique=False)


def downgrade():
    op.drop_index("ix_support_ticket_messages_in_reply_to", table_name="support_ticket_messages")
    op.drop_index("ix_support_ticket_messages_external_message_id", table_name="support_ticket_messages")
    op.drop_column("support_ticket_messages", "in_reply_to")
    op.drop_column("support_ticket_messages", "external_message_id")
    op.drop_column("support_ticket_messages", "source")

    op.drop_index("ix_support_tickets_public_token", table_name="support_tickets")
    op.drop_column("support_tickets", "public_token")

    op.drop_column("email_accounts", "imap_enabled")
    op.drop_column("email_accounts", "imap_folder")
    op.drop_column("email_accounts", "imap_password_encrypted")
    op.drop_column("email_accounts", "imap_username")
    op.drop_column("email_accounts", "imap_use_ssl")
    op.drop_column("email_accounts", "imap_use_tls")
    op.drop_column("email_accounts", "imap_port")
    op.drop_column("email_accounts", "imap_server")
