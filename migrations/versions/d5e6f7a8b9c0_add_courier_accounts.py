"""add courier accounts

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-06-02 15:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "courier_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("courier_code", sa.String(length=30), nullable=False),
        sa.Column("account_type", sa.String(length=30), nullable=False, server_default="portal"),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("base_url", sa.String(length=255), nullable=True),
        sa.Column("username", sa.String(length=180), nullable=True),
        sa.Column("password_encrypted", sa.String(length=1024), nullable=True),
        sa.Column("extra_config", sa.JSON(), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("courier_code", "account_type", "name", name="uq_courier_accounts_code_type_name"),
    )
    op.create_index("ix_courier_accounts_account_type", "courier_accounts", ["account_type"])
    op.create_index("ix_courier_accounts_courier_code", "courier_accounts", ["courier_code"])
    op.create_index("ix_courier_accounts_courier_enabled", "courier_accounts", ["courier_code", "is_enabled"])
    op.create_index("ix_courier_accounts_is_enabled", "courier_accounts", ["is_enabled"])

    op.add_column("shipments", sa.Column("courier_account_id", sa.Integer(), nullable=True))
    op.create_index("ix_shipments_courier_account_id", "shipments", ["courier_account_id"])
    op.create_foreign_key(
        "fk_shipments_courier_account_id",
        "shipments",
        "courier_accounts",
        ["courier_account_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade():
    op.drop_constraint("fk_shipments_courier_account_id", "shipments", type_="foreignkey")
    op.drop_index("ix_shipments_courier_account_id", table_name="shipments")
    op.drop_column("shipments", "courier_account_id")

    op.drop_index("ix_courier_accounts_is_enabled", table_name="courier_accounts")
    op.drop_index("ix_courier_accounts_courier_enabled", table_name="courier_accounts")
    op.drop_index("ix_courier_accounts_courier_code", table_name="courier_accounts")
    op.drop_index("ix_courier_accounts_account_type", table_name="courier_accounts")
    op.drop_table("courier_accounts")
