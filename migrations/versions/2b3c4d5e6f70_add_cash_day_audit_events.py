"""add cash day audit events

Revision ID: 2b3c4d5e6f70
Revises: 1a2b3c4d5e6f
Create Date: 2026-06-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "2b3c4d5e6f70"
down_revision = "1a2b3c4d5e6f"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cash_day_audit_events",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("cash_day_id", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=True),
        sa.Column("action", sa.String(length=24), nullable=False),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["cash_day_id"], ["cash_days.id"], name=op.f("fk_cash_day_audit_events_cash_day_id_cash_days"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"], name=op.f("fk_cash_day_audit_events_created_by_user_id_user"), ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("cash_day_audit_events", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_cash_day_audit_events_cash_day_id"), ["cash_day_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_cash_day_audit_events_entity_type"), ["entity_type"], unique=False)
        batch_op.create_index(batch_op.f("ix_cash_day_audit_events_entity_id"), ["entity_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_cash_day_audit_events_action"), ["action"], unique=False)
        batch_op.create_index(batch_op.f("ix_cash_day_audit_events_created_at"), ["created_at"], unique=False)


def downgrade():
    with op.batch_alter_table("cash_day_audit_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_cash_day_audit_events_created_at"))
        batch_op.drop_index(batch_op.f("ix_cash_day_audit_events_action"))
        batch_op.drop_index(batch_op.f("ix_cash_day_audit_events_entity_id"))
        batch_op.drop_index(batch_op.f("ix_cash_day_audit_events_entity_type"))
        batch_op.drop_index(batch_op.f("ix_cash_day_audit_events_cash_day_id"))
    op.drop_table("cash_day_audit_events")
