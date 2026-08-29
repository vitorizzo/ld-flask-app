"""convert PayByLink placeholders to generic online checkout

Revision ID: a8b9c0d1e3f5
Revises: f7a8b9c0d2e4
Create Date: 2026-08-29 12:00:00.000000
"""
from alembic import op


revision = "a8b9c0d1e3f5"
down_revision = "f7a8b9c0d2e4"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("UPDATE customer_payment_cases SET case_type = 'online_payment' WHERE case_type = 'paybylink'")
    op.execute("UPDATE customer_payment_cases SET status = 'creating_checkout' WHERE status = 'creating_link'")
    op.execute("UPDATE customer_payment_cases SET status = 'checkout_ready' WHERE status = 'link_active'")
    op.execute("UPDATE customer_accounting_item_states SET status = 'creating_checkout' WHERE status = 'creating_link'")
    op.execute("UPDATE customer_accounting_item_states SET status = 'checkout_ready' WHERE status = 'link_active'")


def downgrade():
    op.execute("UPDATE customer_accounting_item_states SET status = 'link_active' WHERE status = 'checkout_ready'")
    op.execute("UPDATE customer_accounting_item_states SET status = 'creating_link' WHERE status = 'creating_checkout'")
    op.execute("UPDATE customer_payment_cases SET status = 'link_active' WHERE status = 'checkout_ready'")
    op.execute("UPDATE customer_payment_cases SET status = 'creating_link' WHERE status = 'creating_checkout'")
    op.execute("UPDATE customer_payment_cases SET case_type = 'paybylink' WHERE case_type = 'online_payment'")
