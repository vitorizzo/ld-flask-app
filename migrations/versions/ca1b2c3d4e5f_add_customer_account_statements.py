"""add customer account statement imports

Revision ID: ca1b2c3d4e5f
Revises: f9a0b1c2d3e4
Create Date: 2026-07-30
"""

from alembic import op
import sqlalchemy as sa


revision = "ca1b2c3d4e5f"
down_revision = "f9a0b1c2d3e4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "customer_account_statement_imports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_file", sa.String(length=255), nullable=False),
        sa.Column("trace_file", sa.String(length=255), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("customer_count", sa.Integer(), nullable=False),
        sa.Column("matched_customer_count", sa.Integer(), nullable=False),
        sa.Column("unmatched_customer_count", sa.Integer(), nullable=False),
        sa.Column("imported_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_sha256"),
    )
    op.create_index(
        "ix_customer_account_statement_imports_imported_at",
        "customer_account_statement_imports",
        ["imported_at"],
    )
    op.create_index(
        "ix_customer_account_statement_imports_source_sha256",
        "customer_account_statement_imports",
        ["source_sha256"],
    )

    op.create_table(
        "customer_account_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("import_id", sa.Integer(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("registry_id", sa.Integer(), nullable=True),
        sa.Column("source_customer_code", sa.String(length=64), nullable=False),
        sa.Column("customer_name", sa.String(length=255), nullable=False),
        sa.Column("registration_date", sa.Date(), nullable=True),
        sa.Column("document_date", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("document_number", sa.String(length=64), nullable=True),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("additional_description", sa.String(length=255), nullable=True),
        sa.Column("accounting_side", sa.String(length=1), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("signed_amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("source_payload", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["import_id"],
            ["customer_account_statement_imports.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["registry_id"], ["business_registries.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("import_id", "row_number", name="uq_customer_account_entry_import_row"),
    )
    op.create_index("ix_customer_account_entries_import_id", "customer_account_entries", ["import_id"])
    op.create_index("ix_customer_account_entries_registry_id", "customer_account_entries", ["registry_id"])
    op.create_index("ix_customer_account_entries_due_date", "customer_account_entries", ["due_date"])
    op.create_index(
        "ix_customer_account_entries_source_customer_code",
        "customer_account_entries",
        ["source_customer_code"],
    )
    op.create_index(
        "ix_customer_account_entry_import_customer",
        "customer_account_entries",
        ["import_id", "registry_id"],
    )
    op.create_index(
        "ix_customer_account_entry_import_source",
        "customer_account_entries",
        ["import_id", "source_customer_code"],
    )


def downgrade():
    op.drop_table("customer_account_entries")
    op.drop_table("customer_account_statement_imports")
