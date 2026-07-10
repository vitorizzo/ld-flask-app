"""add event posters

Revision ID: b1c2d3e4f5a6
Revises: a0b1c2d3e4f5
Create Date: 2026-07-10 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "b1c2d3e4f5a6"
down_revision = "a0b1c2d3e4f5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "event_posters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("file_path", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=20), nullable=False, server_default="image"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_event_posters_event_id", "event_posters", ["event_id"], unique=False)
    op.create_index("ix_event_posters_event_sort", "event_posters", ["event_id", "sort_order"], unique=False)

    op.execute(
        """
        INSERT INTO event_posters (event_id, file_path, media_type, sort_order, created_at)
        SELECT id,
               poster_path,
               CASE
                   WHEN lower(poster_path) LIKE '%%.pdf' THEN 'pdf'
                   ELSE 'image'
               END,
               0,
               CURRENT_TIMESTAMP
        FROM events
        WHERE poster_path IS NOT NULL AND poster_path <> ''
        """
    )


def downgrade():
    op.drop_index("ix_event_posters_event_sort", table_name="event_posters")
    op.drop_index("ix_event_posters_event_id", table_name="event_posters")
    op.drop_table("event_posters")
