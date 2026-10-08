"""Archive generated supplier order PDF with its card."""
from alembic import op
import sqlalchemy as sa
revision = "p1e2f3a4b5c6"
down_revision = "o0d1e2f3a4b5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('supplier_board_cards', sa.Column('order_pdf', sa.LargeBinary(), nullable=True))
    op.add_column('supplier_board_cards', sa.Column('order_pdf_filename', sa.String(200), nullable=True))


def downgrade():
    op.drop_column('supplier_board_cards', 'order_pdf_filename')
    op.drop_column('supplier_board_cards', 'order_pdf')
