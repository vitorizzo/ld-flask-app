"""add business registries

Revision ID: c1d2e3f4a5b6
Revises: b7e4d2c9a8f1
Create Date: 2026-05-19 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "c1d2e3f4a5b6"
down_revision = "b7e4d2c9a8f1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "business_registries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("source_company_code", sa.String(length=16), nullable=True),
        sa.Column("source_record_type", sa.String(length=8), nullable=True),
        sa.Column("source_code", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("legal_name", sa.String(length=255), nullable=True),
        sa.Column("vat_number", sa.String(length=32), nullable=True),
        sa.Column("tax_code", sa.String(length=32), nullable=True),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("zip_code", sa.String(length=16), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("province", sa.String(length=8), nullable=True),
        sa.Column("country", sa.String(length=4), nullable=True),
        sa.Column("source_payload", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_business_registries")),
        sa.UniqueConstraint("kind", "source", "source_code", name="uq_business_registry_kind_source_code"),
    )
    with op.batch_alter_table("business_registries", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_business_registries_city"), ["city"], unique=False)
        batch_op.create_index(batch_op.f("ix_business_registries_display_name"), ["display_name"], unique=False)
        batch_op.create_index("ix_business_registry_kind_display", ["kind", "display_name"], unique=False)
        batch_op.create_index(batch_op.f("ix_business_registries_is_active"), ["is_active"], unique=False)
        batch_op.create_index(batch_op.f("ix_business_registries_kind"), ["kind"], unique=False)
        batch_op.create_index(batch_op.f("ix_business_registries_legal_name"), ["legal_name"], unique=False)
        batch_op.create_index(batch_op.f("ix_business_registries_province"), ["province"], unique=False)
        batch_op.create_index(batch_op.f("ix_business_registries_source"), ["source"], unique=False)
        batch_op.create_index(batch_op.f("ix_business_registries_source_code"), ["source_code"], unique=False)
        batch_op.create_index(batch_op.f("ix_business_registries_tax_code"), ["tax_code"], unique=False)
        batch_op.create_index(batch_op.f("ix_business_registries_vat_number"), ["vat_number"], unique=False)
        batch_op.create_index(batch_op.f("ix_business_registries_zip_code"), ["zip_code"], unique=False)

    op.create_table(
        "business_registry_contacts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("registry_id", sa.Integer(), nullable=False),
        sa.Column("contact_type", sa.String(length=20), nullable=False),
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=True),
        sa.Column("source_column", sa.String(length=16), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["registry_id"],
            ["business_registries.id"],
            name=op.f("fk_business_registry_contacts_registry_id_business_registries"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_business_registry_contacts")),
        sa.UniqueConstraint("registry_id", "contact_type", "value", name="uq_business_registry_contact_value"),
    )
    with op.batch_alter_table("business_registry_contacts", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_business_registry_contacts_contact_type"), ["contact_type"], unique=False)
        batch_op.create_index(batch_op.f("ix_business_registry_contacts_registry_id"), ["registry_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_business_registry_contacts_value"), ["value"], unique=False)


def downgrade():
    with op.batch_alter_table("business_registry_contacts", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_business_registry_contacts_value"))
        batch_op.drop_index(batch_op.f("ix_business_registry_contacts_registry_id"))
        batch_op.drop_index(batch_op.f("ix_business_registry_contacts_contact_type"))
    op.drop_table("business_registry_contacts")

    with op.batch_alter_table("business_registries", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_business_registries_zip_code"))
        batch_op.drop_index(batch_op.f("ix_business_registries_vat_number"))
        batch_op.drop_index(batch_op.f("ix_business_registries_tax_code"))
        batch_op.drop_index(batch_op.f("ix_business_registries_source_code"))
        batch_op.drop_index(batch_op.f("ix_business_registries_source"))
        batch_op.drop_index(batch_op.f("ix_business_registries_province"))
        batch_op.drop_index(batch_op.f("ix_business_registries_legal_name"))
        batch_op.drop_index(batch_op.f("ix_business_registries_kind"))
        batch_op.drop_index(batch_op.f("ix_business_registries_is_active"))
        batch_op.drop_index("ix_business_registry_kind_display")
        batch_op.drop_index(batch_op.f("ix_business_registries_display_name"))
        batch_op.drop_index(batch_op.f("ix_business_registries_city"))
    op.drop_table("business_registries")
