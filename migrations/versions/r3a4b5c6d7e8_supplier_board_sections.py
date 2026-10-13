"""Configurable rich text sections on supplier board cards."""
from alembic import op
import sqlalchemy as sa
from tools.supplier_migration_compat import create_table_if_needed, create_index_if_needed
from tools.supplier_board_sections import DEFAULT_SECTIONS

revision = 'r3a4b5c6d7e8'
down_revision = 'q2f3a4b5c6d7'
branch_labels = None
depends_on = None


def upgrade():
    create_table_if_needed('supplier_board_sections',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('name', sa.String(80), nullable=False, unique=True),
        sa.Column('order_index', sa.Integer, nullable=False),
        sa.Column('revision', sa.Integer, nullable=False), unique_keys=(('name',),))
    create_table_if_needed('supplier_board_card_sections',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('card_id', sa.Integer, sa.ForeignKey('supplier_board_cards.id', ondelete='CASCADE'), nullable=False),
        sa.Column('section_id', sa.Integer, sa.ForeignKey('supplier_board_sections.id', ondelete='CASCADE'), nullable=False),
        sa.Column('content_html', sa.Text, nullable=False),
        sa.UniqueConstraint('card_id', 'section_id', name='uq_supplier_card_section'),
        unique_keys=(('card_id', 'section_id'),))
    for column in ('card_id', 'section_id'):
        create_index_if_needed('ix_supplier_board_card_sections_'+column, 'supplier_board_card_sections', [column])
    for index, name in enumerate(DEFAULT_SECTIONS):
        op.execute(sa.text('INSERT INTO supplier_board_sections (name, order_index, revision) '
                          'SELECT :name, :position, 1 WHERE NOT EXISTS '
                          '(SELECT 1 FROM supplier_board_sections WHERE name=:name)').bindparams(name=name, position=index))


def downgrade():
    op.drop_table('supplier_board_card_sections')
    op.drop_table('supplier_board_sections')
