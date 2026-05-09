"""add menu visibility and item type

Revision ID: f0a1b2c3d4e5
Revises: 6c7693e36d37
Create Date: 2026-05-09 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f0a1b2c3d4e5'
down_revision = '6c7693e36d37'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('menus', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_visible', sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column('item_type', sa.String(length=20), nullable=False, server_default='link'))

    with op.batch_alter_table('menus', schema=None) as batch_op:
        batch_op.alter_column('is_visible', server_default=None)
        batch_op.alter_column('item_type', server_default=None)


def downgrade():
    with op.batch_alter_table('menus', schema=None) as batch_op:
        batch_op.drop_column('item_type')
        batch_op.drop_column('is_visible')
