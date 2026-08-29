"""add online payment provider fields

Revision ID: f7a8b9c0d2e4
Revises: e6f7a8b9c1d3
Create Date: 2026-08-27 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "f7a8b9c0d2e4"
down_revision = "e6f7a8b9c1d3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("customer_payment_cases", sa.Column("provider_order_id", sa.String(length=18), nullable=True))
    op.add_column("customer_payment_cases", sa.Column("provider_operation_id", sa.String(length=160), nullable=True))
    op.add_column("customer_payment_cases", sa.Column("provider_security_token", sa.String(length=512), nullable=True))
    op.add_column("customer_payment_cases", sa.Column("provider_last_event_id", sa.String(length=80), nullable=True))
    op.create_index("ix_customer_payment_cases_provider_order_id", "customer_payment_cases", ["provider_order_id"], unique=True)
    op.create_index("ix_customer_payment_cases_provider_operation_id", "customer_payment_cases", ["provider_operation_id"])
    op.create_index("ix_customer_payment_cases_provider_last_event_id", "customer_payment_cases", ["provider_last_event_id"])


def downgrade():
    op.drop_index("ix_customer_payment_cases_provider_last_event_id", table_name="customer_payment_cases")
    op.drop_index("ix_customer_payment_cases_provider_operation_id", table_name="customer_payment_cases")
    op.drop_index("ix_customer_payment_cases_provider_order_id", table_name="customer_payment_cases")
    op.drop_column("customer_payment_cases", "provider_last_event_id")
    op.drop_column("customer_payment_cases", "provider_security_token")
    op.drop_column("customer_payment_cases", "provider_operation_id")
    op.drop_column("customer_payment_cases", "provider_order_id")
