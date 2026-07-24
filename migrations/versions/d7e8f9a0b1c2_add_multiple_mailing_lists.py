"""add multiple mailing lists

Revision ID: d7e8f9a0b1c2
Revises: c6d7e8f9a0b1
Create Date: 2026-07-24
"""

from alembic import op
import sqlalchemy as sa


revision = "d7e8f9a0b1c2"
down_revision = "c6d7e8f9a0b1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mailing_lists",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("source_type", sa.String(length=30), nullable=False, server_default="manual"),
        sa.Column("filter_config", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", name="uq_mailing_lists_name"),
    )
    op.create_index("ix_mailing_lists_source_type", "mailing_lists", ["source_type"])
    op.create_index("ix_mailing_lists_is_active", "mailing_lists", ["is_active"])

    op.create_table(
        "mailing_list_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("mailing_list_id", sa.Integer(), sa.ForeignKey("mailing_lists.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subscriber_id", sa.Integer(), sa.ForeignKey("mailing_subscribers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", sa.String(length=30), nullable=False, server_default="manual"),
        sa.Column("source_entity_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("mailing_list_id", "subscriber_id", name="uq_mailing_list_member"),
    )
    op.create_index("ix_mailing_list_members_mailing_list_id", "mailing_list_members", ["mailing_list_id"])
    op.create_index("ix_mailing_list_members_subscriber_id", "mailing_list_members", ["subscriber_id"])
    op.create_index("ix_mailing_list_members_list_active", "mailing_list_members", ["mailing_list_id", "is_active"])

    with op.batch_alter_table("mailing_campaigns") as batch_op:
        batch_op.add_column(sa.Column("mailing_list_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_mailing_campaigns_mailing_list_id",
            "mailing_lists",
            ["mailing_list_id"],
            ["id"],
        )
        batch_op.create_index("ix_mailing_campaigns_mailing_list_id", ["mailing_list_id"])

    op.execute(
        """
        INSERT INTO mailing_lists
            (name, source_type, filter_config, is_system, is_active, created_at, updated_at)
        VALUES
            ('Clienti', 'customers', '{}', true, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            ('Utenti APP', 'users', '{}', true, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
    )


def downgrade():
    with op.batch_alter_table("mailing_campaigns") as batch_op:
        batch_op.drop_index("ix_mailing_campaigns_mailing_list_id")
        batch_op.drop_constraint("fk_mailing_campaigns_mailing_list_id", type_="foreignkey")
        batch_op.drop_column("mailing_list_id")
    op.drop_table("mailing_list_members")
    op.drop_table("mailing_lists")
