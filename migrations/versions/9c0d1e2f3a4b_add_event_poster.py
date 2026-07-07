"""add event poster

Revision ID: 9c0d1e2f3a4b
Revises: 8b9c0d1e2f3a
Create Date: 2026-07-07 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "9c0d1e2f3a4b"
down_revision = "8b9c0d1e2f3a"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("events", sa.Column("poster_path", sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column("events", "poster_path")
