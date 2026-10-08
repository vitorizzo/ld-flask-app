"""Independent supplier order board, initial columns from Scarichi - Ufficio."""
from alembic import op
import sqlalchemy as sa

revision = "m8b9c0d1e2f3"
down_revision = "l7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade():
    columns = op.create_table("supplier_board_columns",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("order_index", sa.Integer, nullable=False),
        sa.Column("is_terminal", sa.Boolean, nullable=False, server_default=sa.false()))
    op.create_table("supplier_board_cards",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("column_id", sa.Integer, sa.ForeignKey("supplier_board_columns.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("supplier_id", sa.Integer, sa.ForeignKey("business_registries.id", ondelete="RESTRICT")),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("notes", sa.Text), sa.Column("reference", sa.String(160)),
        sa.Column("expected_date", sa.Date),
        sa.Column("is_archived", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()))
    op.create_index("ix_supplier_board_cards_column_id", "supplier_board_cards", ["column_id"])
    op.create_index("ix_supplier_board_cards_supplier_id", "supplier_board_cards", ["supplier_id"])
    names = ["In Arrivo", "In Attesa dei Lotti", "Da Caricare", "Caricamento in Magazzino",
             "Prezzi da inserire", "Anomalie da Gestire", "Ultimate", "da completare (VITO)"]
    op.bulk_insert(columns, [dict(name=name, order_index=index, is_terminal=name == "Ultimate") for index, name in enumerate(names)])
    op.execute("""INSERT INTO menus (name, weight, sort_order, parent_id, route, is_active, is_visible, item_type)
        SELECT 'Bacheca fornitori', 40, 86, (SELECT parent_id FROM menus WHERE route='/supplier-orders' ORDER BY id LIMIT 1),
               '/supplier-orders/board', true, true, 'link'
        WHERE NOT EXISTS (SELECT 1 FROM menus WHERE route='/supplier-orders/board')""")


def downgrade():
    op.execute("DELETE FROM menus WHERE route='/supplier-orders/board'")
    op.drop_table("supplier_board_cards")
    op.drop_table("supplier_board_columns")
