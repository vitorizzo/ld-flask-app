"""Explicit minimum role weight for activity recipients."""
from alembic import op
import sqlalchemy as sa
from tools.supplier_migration_compat import add_column_if_needed

revision = 'w8f9a0b1c2d3'
down_revision = 'v7e8f9a0b1c2'
branch_labels = None
depends_on = None


def upgrade():
    add_column_if_needed('operational_activities', sa.Column('target_min_weight', sa.Integer, nullable=True))


def downgrade():
    with op.batch_alter_table('operational_activities') as batch:
        batch.drop_column('target_min_weight')
