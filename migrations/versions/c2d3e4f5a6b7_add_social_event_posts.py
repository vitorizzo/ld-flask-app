"""add social event posts

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-07-10 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "c2d3e4f5a6b7"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "social_event_posts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("caption", sa.Text(), nullable=False),
        sa.Column("public_url", sa.String(length=500), nullable=False),
        sa.Column("destinations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("status_message", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_social_event_posts_created_at", "social_event_posts", ["created_at"], unique=False)
    op.create_index("ix_social_event_posts_kind_period", "social_event_posts", ["kind", "period_start", "period_end"], unique=False)
    op.create_index("ix_social_event_posts_status", "social_event_posts", ["status"], unique=False)


def downgrade():
    op.drop_index("ix_social_event_posts_status", table_name="social_event_posts")
    op.drop_index("ix_social_event_posts_kind_period", table_name="social_event_posts")
    op.drop_index("ix_social_event_posts_created_at", table_name="social_event_posts")
    op.drop_table("social_event_posts")
