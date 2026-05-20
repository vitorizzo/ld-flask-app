"""add registry contacts and route customers

Revision ID: d4e5f6a7b8c9
Revises: c1d2e3f4a5b6
Create Date: 2026-05-20 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "d4e5f6a7b8c9"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "registry_contacts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_registry_contacts")),
    )
    with op.batch_alter_table("registry_contacts", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_registry_contacts_display_name"), ["display_name"], unique=False)
        batch_op.create_index(batch_op.f("ix_registry_contacts_is_active"), ["is_active"], unique=False)

    op.create_table(
        "registry_contact_points",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("contact_id", sa.Integer(), nullable=False),
        sa.Column("contact_type", sa.String(length=20), nullable=False),
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(
            ["contact_id"],
            ["registry_contacts.id"],
            name=op.f("fk_registry_contact_points_contact_id_registry_contacts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_registry_contact_points")),
        sa.UniqueConstraint("contact_id", "contact_type", "value", name="uq_registry_contact_point_value"),
    )
    with op.batch_alter_table("registry_contact_points", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_registry_contact_points_contact_id"), ["contact_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_registry_contact_points_contact_type"), ["contact_type"], unique=False)
        batch_op.create_index(batch_op.f("ix_registry_contact_points_value"), ["value"], unique=False)

    op.create_table(
        "business_registry_contact_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("registry_id", sa.Integer(), nullable=False),
        sa.Column("contact_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=120), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(
            ["contact_id"],
            ["registry_contacts.id"],
            name=op.f("fk_business_registry_contact_links_contact_id_registry_contacts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["registry_id"],
            ["business_registries.id"],
            name=op.f("fk_business_registry_contact_links_registry_id_business_registries"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_business_registry_contact_links")),
        sa.UniqueConstraint("registry_id", "contact_id", name="uq_business_registry_contact_link"),
    )
    with op.batch_alter_table("business_registry_contact_links", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_business_registry_contact_links_contact_id"), ["contact_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_business_registry_contact_links_is_active"), ["is_active"], unique=False)
        batch_op.create_index(batch_op.f("ix_business_registry_contact_links_registry_id"), ["registry_id"], unique=False)

    op.create_table(
        "delivery_route_customers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("route_id", sa.Integer(), nullable=False),
        sa.Column("registry_id", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(
            ["registry_id"],
            ["business_registries.id"],
            name=op.f("fk_delivery_route_customers_registry_id_business_registries"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["route_id"],
            ["delivery_routes.id"],
            name=op.f("fk_delivery_route_customers_route_id_delivery_routes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_delivery_route_customers")),
        sa.UniqueConstraint("route_id", "registry_id", name="uq_delivery_route_customer"),
    )
    with op.batch_alter_table("delivery_route_customers", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_delivery_route_customers_is_active"), ["is_active"], unique=False)
        batch_op.create_index(batch_op.f("ix_delivery_route_customers_registry_id"), ["registry_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_delivery_route_customers_route_id"), ["route_id"], unique=False)


def downgrade():
    with op.batch_alter_table("delivery_route_customers", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_delivery_route_customers_route_id"))
        batch_op.drop_index(batch_op.f("ix_delivery_route_customers_registry_id"))
        batch_op.drop_index(batch_op.f("ix_delivery_route_customers_is_active"))
    op.drop_table("delivery_route_customers")

    with op.batch_alter_table("business_registry_contact_links", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_business_registry_contact_links_registry_id"))
        batch_op.drop_index(batch_op.f("ix_business_registry_contact_links_is_active"))
        batch_op.drop_index(batch_op.f("ix_business_registry_contact_links_contact_id"))
    op.drop_table("business_registry_contact_links")

    with op.batch_alter_table("registry_contact_points", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_registry_contact_points_value"))
        batch_op.drop_index(batch_op.f("ix_registry_contact_points_contact_type"))
        batch_op.drop_index(batch_op.f("ix_registry_contact_points_contact_id"))
    op.drop_table("registry_contact_points")

    with op.batch_alter_table("registry_contacts", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_registry_contacts_is_active"))
        batch_op.drop_index(batch_op.f("ix_registry_contacts_display_name"))
    op.drop_table("registry_contacts")
