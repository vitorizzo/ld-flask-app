"""External supplier orders, payment metadata and multiple attachments."""
from alembic import op
import sqlalchemy as sa
from tools.supplier_migration_compat import add_column_if_needed, create_table_if_needed, create_index_if_needed

revision = 'v7e8f9a0b1c2'
down_revision = 'u6d7e8f9a0b1'
branch_labels = None
depends_on = None


def upgrade():
    for column in [sa.Column('order_text', sa.Text, nullable=True),
                   sa.Column('transmission_notes', sa.Text, nullable=True),
                   sa.Column('cash_on_delivery', sa.Boolean, nullable=False, server_default=sa.false()),
                   sa.Column('payment_terms', sa.String(20), nullable=True),
                   sa.Column('payment_terms_other', sa.String(500), nullable=True),
                   sa.Column('payment_date', sa.Date, nullable=True),
                   sa.Column('is_external_order', sa.Boolean, nullable=False, server_default=sa.false())]:
        add_column_if_needed('supplier_board_cards', column)
    create_table_if_needed('supplier_board_attachments',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('card_id', sa.Integer, sa.ForeignKey('supplier_board_cards.id', ondelete='CASCADE'), nullable=False),
        sa.Column('filename', sa.String(200), nullable=False),
        sa.Column('mimetype', sa.String(100), nullable=False),
        sa.Column('size', sa.Integer, nullable=False),
        sa.Column('content', sa.LargeBinary, nullable=False))
    create_index_if_needed('ix_supplier_board_attachments_card_id', 'supplier_board_attachments', ['card_id'])


def downgrade():
    op.drop_table('supplier_board_attachments')
    with op.batch_alter_table('supplier_board_cards') as batch:
        for name in ['order_text', 'transmission_notes', 'cash_on_delivery', 'payment_terms',
                     'payment_terms_other', 'payment_date', 'is_external_order']:
            batch.drop_column(name)
