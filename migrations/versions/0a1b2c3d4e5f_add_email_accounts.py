"""add email accounts

Revision ID: 0a1b2c3d4e5f
Revises: f5a6b7c8d9e0
Create Date: 2026-07-13 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "0a1b2c3d4e5f"
down_revision = "f5a6b7c8d9e0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "email_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("smtp_server", sa.String(length=255), nullable=False),
        sa.Column("smtp_port", sa.Integer(), nullable=False, server_default="25"),
        sa.Column("use_tls", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("use_ssl", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("password_encrypted", sa.String(length=2048), nullable=True),
        sa.Column("default_sender", sa.String(length=255), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_email_accounts_code"),
    )
    op.create_index("ix_email_accounts_enabled", "email_accounts", ["is_enabled"], unique=False)


def downgrade():
    op.drop_index("ix_email_accounts_enabled", table_name="email_accounts")
    op.drop_table("email_accounts")
