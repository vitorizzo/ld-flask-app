"""add cash check scan

Revision ID: 93a4b5c6d7e8
Revises: 8293a4b5c6d7
Create Date: 2026-07-21
"""

from alembic import op
import sqlalchemy as sa


revision = "93a4b5c6d7e8"
down_revision = "8293a4b5c6d7"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("cash_checks") as batch_op:
        batch_op.add_column(sa.Column("scan_path", sa.String(500), nullable=True))
        batch_op.add_column(sa.Column("scan_mime", sa.String(100), nullable=True))
        batch_op.add_column(sa.Column("scan_original_name", sa.String(255), nullable=True))


def downgrade():
    with op.batch_alter_table("cash_checks") as batch_op:
        batch_op.drop_column("scan_original_name")
        batch_op.drop_column("scan_mime")
        batch_op.drop_column("scan_path")
