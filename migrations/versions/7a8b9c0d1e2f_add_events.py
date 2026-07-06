"""add events

Revision ID: 7a8b9c0d1e2f
Revises: 6f708192a3b4
Create Date: 2026-07-06 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "7a8b9c0d1e2f"
down_revision = "6f708192a3b4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("location", sa.String(length=180), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("contact_info", sa.String(length=180), nullable=True),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_events_published_starts_at", "events", ["is_published", "starts_at"], unique=False)


def downgrade():
    op.drop_index("ix_events_published_starts_at", table_name="events")
    op.drop_table("events")
