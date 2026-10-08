"""Persist quantities ordered from supplier product groups."""
from alembic import op
import sqlalchemy as sa
revision = "o0d1e2f3a4b5"
down_revision = "n9c0d1e2f3a4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("supplier_board_order_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("card_id", sa.Integer(), sa.ForeignKey("supplier_board_cards.id", ondelete="CASCADE"), nullable=False),
        sa.Column("matrix_code", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("subgroup_name", sa.String(160), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("stock_at_order", sa.Integer(), nullable=False),
        sa.UniqueConstraint("card_id", "matrix_code", name="uq_supplier_board_order_matrix"))
    op.create_index("ix_supplier_board_order_lines_card_id", "supplier_board_order_lines", ["card_id"])


def downgrade():
    op.drop_table("supplier_board_order_lines")
