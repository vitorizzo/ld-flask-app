"""Manual shared activities and explicit user recipients."""
from alembic import op
import sqlalchemy as sa
from tools.supplier_migration_compat import add_column_if_needed, create_table_if_needed

revision = 'u6d7e8f9a0b1'
down_revision = 't5c6d7e8f9a0'
branch_labels = None
depends_on = None


def upgrade():
    add_column_if_needed('operational_activities', sa.Column('description', sa.Text, nullable=False, server_default=''))
    add_column_if_needed('operational_activities', sa.Column('client_key', sa.String(64), nullable=True))
    inspector = sa.inspect(op.get_bind())
    uniques = inspector.get_unique_constraints('operational_activities') + [i for i in inspector.get_indexes('operational_activities') if i['unique']]
    if not any(i['column_names'] == ['client_key'] for i in uniques):
        op.create_index('uq_activity_client_key', 'operational_activities', ['client_key'], unique=True)
    create_table_if_needed('activity_target_users',
        sa.Column('activity_id', sa.Integer, sa.ForeignKey('operational_activities.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('user.id', ondelete='CASCADE'), primary_key=True))


def downgrade():
    op.drop_table('activity_target_users')
    for index in sa.inspect(op.get_bind()).get_indexes('operational_activities'):
        if 'client_key' in index['column_names']:
            op.drop_index(index['name'], table_name='operational_activities')
    with op.batch_alter_table('operational_activities') as batch:
        batch.drop_column('client_key')
        batch.drop_column('description')
