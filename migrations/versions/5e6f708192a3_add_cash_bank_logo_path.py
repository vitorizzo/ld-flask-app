"""add cash bank logo path

Revision ID: 5e6f708192a3
Revises: 4d5e6f708192
Create Date: 2026-06-19 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = "5e6f708192a3"
down_revision = "4d5e6f708192"
branch_labels = None
depends_on = None


def _has_column(bind, table_name, column_name):
    inspector = inspect(bind)
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade():
    bind = op.get_bind()
    if not _has_column(bind, "cash_banks", "logo_path"):
        op.add_column("cash_banks", sa.Column("logo_path", sa.String(length=255), nullable=True))


def downgrade():
    bind = op.get_bind()
    if _has_column(bind, "cash_banks", "logo_path"):
        op.drop_column("cash_banks", "logo_path")
