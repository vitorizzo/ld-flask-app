"""add registry contact vcard imports

Revision ID: ce5f60718293
Revises: cd4e5f607182
Create Date: 2026-08-16
"""

from alembic import op
import sqlalchemy as sa


revision = "ce5f60718293"
down_revision = "cd4e5f607182"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("registry_contacts") as batch_op:
        batch_op.add_column(sa.Column("photo_path", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("photo_mime", sa.String(length=80), nullable=True))

    op.create_table(
        "registry_contact_import_intents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("suggested_registry_id", sa.Integer(), nullable=True),
        sa.Column("source_filename", sa.String(length=255), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("phones", sa.JSON(), nullable=True),
        sa.Column("emails", sa.JSON(), nullable=True),
        sa.Column("photo_path", sa.String(length=500), nullable=True),
        sa.Column("photo_mime", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["suggested_registry_id"], ["business_registries.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_registry_contact_import_intents_user_id",
        "registry_contact_import_intents",
        ["user_id"],
    )
    op.create_index(
        "ix_registry_contact_import_intents_suggested_registry_id",
        "registry_contact_import_intents",
        ["suggested_registry_id"],
    )
    op.create_index(
        "ix_registry_contact_import_intents_status",
        "registry_contact_import_intents",
        ["status"],
    )


def downgrade():
    op.drop_index("ix_registry_contact_import_intents_status", table_name="registry_contact_import_intents")
    op.drop_index("ix_registry_contact_import_intents_suggested_registry_id", table_name="registry_contact_import_intents")
    op.drop_index("ix_registry_contact_import_intents_user_id", table_name="registry_contact_import_intents")
    op.drop_table("registry_contact_import_intents")
    with op.batch_alter_table("registry_contacts") as batch_op:
        batch_op.drop_column("photo_mime")
        batch_op.drop_column("photo_path")
