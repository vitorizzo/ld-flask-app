"""cancellazione constraint posdevice e poscircuit su CashSalePayment

Revision ID: e14a0e9f2c8b
Revises: 7c42eef454d5
Create Date: 2026-03-31 18:00:47.704640
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e14a0e9f2c8b'
down_revision = '7c42eef454d5'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE cash_sale_payments
        DROP CONSTRAINT IF EXISTS ck_cash_sale_payment_pos_requires_device_circuit
    """)

    op.execute("""
        ALTER TABLE cash_sale_payments
        DROP CONSTRAINT IF EXISTS cash_sale_payments_pos_device_id_fkey
    """)

    op.execute("""
        ALTER TABLE cash_sale_payments
        DROP CONSTRAINT IF EXISTS cash_sale_payments_pos_circuit_id_fkey
    """)

    op.execute("""
        ALTER TABLE cash_sale_payments
        DROP COLUMN IF EXISTS pos_device_id
    """)

    op.execute("""
        ALTER TABLE cash_sale_payments
        DROP COLUMN IF EXISTS pos_circuit_id
    """)


def downgrade():
    op.add_column(
        'cash_sale_payments',
        sa.Column('pos_device_id', sa.Integer(), nullable=True)
    )

    op.add_column(
        'cash_sale_payments',
        sa.Column('pos_circuit_id', sa.Integer(), nullable=True)
    )

    op.create_foreign_key(
        'cash_sale_payments_pos_device_id_fkey',
        'cash_sale_payments',
        'pos_devices',
        ['pos_device_id'],
        ['id']
    )

    op.create_foreign_key(
        'cash_sale_payments_pos_circuit_id_fkey',
        'cash_sale_payments',
        'pos_circuits',
        ['pos_circuit_id'],
        ['id']
    )

    op.create_check_constraint(
        'ck_cash_sale_payment_pos_requires_device_circuit',
        'cash_sale_payments',
        "(method <> 'pos') OR (pos_device_id IS NOT NULL AND pos_circuit_id IS NOT NULL)"
    )