"""add check event expense link and backfill

Revision ID: 60718293a4b5
Revises: 5f60718293a4
Create Date: 2026-07-20
"""
from alembic import op
import sqlalchemy as sa


revision = "60718293a4b5"
down_revision = "5f60718293a4"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("cash_check_events") as batch_op:
        batch_op.add_column(sa.Column("cash_expense_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_cash_check_events_cash_expense_id_cash_expenses",
            "cash_expenses",
            ["cash_expense_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_cash_check_events_cash_expense_id", ["cash_expense_id"], unique=False)

    op.execute(sa.text("""
        INSERT INTO cash_check_events (
            check_id, from_status, to_status, event_date, created_at,
            created_by_user_id, note, amount_spese, customer_charge_amount, cash_expense_id
        )
        SELECT
            checks.id,
            NULL,
            checks.status,
            COALESCE(checks.received_date, CURRENT_DATE),
            COALESCE(checks.created_at, CURRENT_TIMESTAMP),
            NULL,
            'Backfill tecnico: stato corrente precedente all''attivazione della cronologia completa',
            0,
            0,
            NULL
        FROM cash_checks AS checks
        WHERE NOT EXISTS (
            SELECT 1 FROM cash_check_events AS events WHERE events.check_id = checks.id
        )
    """))


def downgrade():
    op.execute(sa.text("""
        DELETE FROM cash_check_events
        WHERE note = 'Backfill tecnico: stato corrente precedente all''attivazione della cronologia completa'
          AND cash_expense_id IS NULL
          AND amount_spese = 0
          AND customer_charge_amount = 0
    """))
    with op.batch_alter_table("cash_check_events") as batch_op:
        batch_op.drop_index("ix_cash_check_events_cash_expense_id")
        batch_op.drop_constraint("fk_cash_check_events_cash_expense_id_cash_expenses", type_="foreignkey")
        batch_op.drop_column("cash_expense_id")
