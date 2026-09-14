"""Add private receipt attachments to expense card payments."""
from alembic import op
import sqlalchemy as sa

revision = "d6e7f8a9b0c1"
down_revision = "c5d6e7f8a9b0"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("cash_expense_payments", sa.Column("receipt_scan_path", sa.String(500), nullable=True))
    op.add_column("cash_expense_payments", sa.Column("receipt_scan_mime", sa.String(100), nullable=True))
    op.add_column("cash_expense_payments", sa.Column("receipt_scan_original_name", sa.String(255), nullable=True))
    op.add_column("cash_expense_payments", sa.Column("receipt_uploaded_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    for name in ("receipt_uploaded_at", "receipt_scan_original_name", "receipt_scan_mime", "receipt_scan_path"):
        op.drop_column("cash_expense_payments", name)
