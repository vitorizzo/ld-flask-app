"""add pwa share and push

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-05-21 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.Text(), nullable=False),
        sa.Column("auth", sa.Text(), nullable=False),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], name=op.f("fk_push_subscriptions_user_id_user"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_push_subscriptions")),
        sa.UniqueConstraint("endpoint", name="uq_push_subscriptions_endpoint"),
    )
    with op.batch_alter_table("push_subscriptions", schema=None) as batch_op:
        batch_op.create_index("ix_push_subscriptions_user_active", ["user_id", "is_active"], unique=False)
        batch_op.create_index(batch_op.f("ix_push_subscriptions_is_active"), ["is_active"], unique=False)
        batch_op.create_index(batch_op.f("ix_push_subscriptions_user_id"), ["user_id"], unique=False)

    op.create_table(
        "shared_order_intents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("files", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], name=op.f("fk_shared_order_intents_user_id_user"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shared_order_intents")),
    )
    with op.batch_alter_table("shared_order_intents", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_shared_order_intents_status"), ["status"], unique=False)
        batch_op.create_index(batch_op.f("ix_shared_order_intents_user_id"), ["user_id"], unique=False)


def downgrade():
    with op.batch_alter_table("shared_order_intents", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_shared_order_intents_user_id"))
        batch_op.drop_index(batch_op.f("ix_shared_order_intents_status"))
    op.drop_table("shared_order_intents")

    with op.batch_alter_table("push_subscriptions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_push_subscriptions_user_id"))
        batch_op.drop_index(batch_op.f("ix_push_subscriptions_is_active"))
        batch_op.drop_index("ix_push_subscriptions_user_active")
    op.drop_table("push_subscriptions")
