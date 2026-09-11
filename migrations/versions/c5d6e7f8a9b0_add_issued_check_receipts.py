"""add issued check receipt attachments

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-09-11
"""
from alembic import op
import sqlalchemy as sa


revision = "c5d6e7f8a9b0"
down_revision = "b4c5d6e7f8a9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("cash_issued_checks", sa.Column("receipt_scan_path", sa.String(length=500), nullable=True))
    op.add_column("cash_issued_checks", sa.Column("receipt_scan_mime", sa.String(length=100), nullable=True))
    op.add_column("cash_issued_checks", sa.Column("receipt_scan_original_name", sa.String(length=255), nullable=True))
    op.add_column("cash_issued_checks", sa.Column("receipt_received_by", sa.String(length=160), nullable=True))
    op.add_column("cash_issued_checks", sa.Column("receipt_uploaded_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("cash_issued_checks", "receipt_uploaded_at")
    op.drop_column("cash_issued_checks", "receipt_received_by")
    op.drop_column("cash_issued_checks", "receipt_scan_original_name")
    op.drop_column("cash_issued_checks", "receipt_scan_mime")
    op.drop_column("cash_issued_checks", "receipt_scan_path")
