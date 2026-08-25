"""add customer account portal foundations

Revision ID: b3c4d5e6f9a0
Revises: a2b3c4d5e6f8
Create Date: 2026-08-25 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "b3c4d5e6f9a0"
down_revision = "a2b3c4d5e6f8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "customer_registry_memberships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("registry_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="owner"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source", sa.String(length=40), nullable=False, server_default="manual"),
        sa.Column("approved_by_user_id", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["registry_id"], ["business_registries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["user.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("user_id", "registry_id", name="uq_customer_registry_membership_user_registry"),
    )
    op.create_index("ix_customer_registry_membership_user_status", "customer_registry_memberships", ["user_id", "status"])
    op.create_index("ix_customer_registry_membership_registry_status", "customer_registry_memberships", ["registry_id", "status"])
    op.create_index(
        "uq_customer_registry_membership_primary",
        "customer_registry_memberships",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("is_primary AND status = 'active'"),
    )

    op.execute(sa.text("""
        INSERT INTO customer_registry_memberships
            (user_id, registry_id, role, status, is_primary, source, approved_at, created_at, updated_at)
        SELECT u.id, u.customer_registry_id, 'owner', 'active', true, 'legacy_customer_registry',
               CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
          FROM "user" u
          JOIN business_registries b ON b.id = u.customer_registry_id
         WHERE u.customer_registry_id IS NOT NULL
           AND b.kind = 'customer'
        ON CONFLICT (user_id, registry_id) DO NOTHING
    """))

    op.create_table(
        "customer_payment_cases",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("public_id", sa.String(length=48), nullable=False),
        sa.Column("registry_id", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("case_type", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="EUR"),
        sa.Column("declared_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("payment_reference", sa.String(length=255), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=True),
        sa.Column("provider_reference", sa.String(length=160), nullable=True),
        sa.Column("payment_url", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["registry_id"], ["business_registries.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_customer_payment_cases_public_id", "customer_payment_cases", ["public_id"], unique=True)
    op.create_index("ix_customer_payment_cases_status", "customer_payment_cases", ["status"])
    op.create_index("ix_customer_payment_case_registry_status", "customer_payment_cases", ["registry_id", "status"])
    op.create_index("ix_customer_payment_case_creator_created", "customer_payment_cases", ["created_by_user_id", "created_at"])
    op.create_index("ix_customer_payment_cases_provider_reference", "customer_payment_cases", ["provider_reference"])

    op.create_table(
        "customer_payment_allocations",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("case_id", sa.BigInteger(), nullable=False),
        sa.Column("source_customer_code", sa.String(length=64), nullable=False),
        sa.Column("source_item_key", sa.String(length=160), nullable=False),
        sa.Column("current_entry_id", sa.Integer(), nullable=True),
        sa.Column("allocated_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("document_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["customer_payment_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["current_entry_id"], ["customer_account_entries.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("case_id", "source_item_key", name="uq_customer_payment_allocation_case_item"),
    )
    op.create_index("ix_customer_payment_allocations_case_id", "customer_payment_allocations", ["case_id"])
    op.create_index("ix_customer_payment_allocations_source_item_key", "customer_payment_allocations", ["source_item_key"])

    op.create_table(
        "customer_payment_evidence",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("case_id", sa.BigInteger(), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_path", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["case_id"], ["customer_payment_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["user.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_customer_payment_evidence_case_id", "customer_payment_evidence", ["case_id"])

    op.create_table(
        "customer_payment_events",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("case_id", sa.BigInteger(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=True),
        sa.Column("to_status", sa.String(length=32), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("event_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["case_id"], ["customer_payment_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["user.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_customer_payment_event_case_created", "customer_payment_events", ["case_id", "created_at"])

    op.create_table(
        "customer_accounting_item_states",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("registry_id", sa.Integer(), nullable=False),
        sa.Column("source_customer_code", sa.String(length=64), nullable=False),
        sa.Column("source_item_key", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payment_case_id", sa.BigInteger(), nullable=True),
        sa.Column("last_seen_entry_id", sa.Integer(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["registry_id"], ["business_registries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["payment_case_id"], ["customer_payment_cases.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["last_seen_entry_id"], ["customer_account_entries.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("registry_id", "source_item_key", name="uq_customer_accounting_item_state_registry_item"),
    )
    op.create_index("ix_customer_accounting_item_state_registry_status", "customer_accounting_item_states", ["registry_id", "status"])


def downgrade():
    op.drop_table("customer_accounting_item_states")
    op.drop_table("customer_payment_events")
    op.drop_table("customer_payment_evidence")
    op.drop_table("customer_payment_allocations")
    op.drop_table("customer_payment_cases")
    op.drop_table("customer_registry_memberships")
