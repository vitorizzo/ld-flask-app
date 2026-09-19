"""Reference company cards by id from expense payments."""
from alembic import op
import sqlalchemy as sa

revision = "i3c4d5e6f7a8"
down_revision = "i2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("cash_expense_payments", sa.Column("pos_card_id", sa.Integer(), nullable=True))
    op.create_index("ix_cash_expense_payments_pos_card_id", "cash_expense_payments", ["pos_card_id"])
    op.create_foreign_key(
        "fk_cash_expense_payments_pos_card_id_company_credit_cards",
        "cash_expense_payments",
        "company_credit_cards",
        ["pos_card_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.execute(sa.text(
        "UPDATE cash_expense_payments p SET pos_card_id = c.id "
        "FROM company_credit_cards c "
        "WHERE p.pos_card_label = c.name AND p.pos_card_label <> 'Carta personale'"
    ))


def downgrade():
    op.drop_constraint("fk_cash_expense_payments_pos_card_id_company_credit_cards", "cash_expense_payments", type_="foreignkey")
    op.drop_index("ix_cash_expense_payments_pos_card_id", table_name="cash_expense_payments")
    op.drop_column("cash_expense_payments", "pos_card_id")
