"""Parent activities and dependent subactivities."""
from alembic import op
import sqlalchemy as sa
revision='y0b1c2d3e4f5'
down_revision='x9a0b1c2d3e4'
branch_labels=None
depends_on=None


def upgrade():
    if not op.get_context().as_sql:
        inspector=sa.inspect(op.get_bind())
        columns={c['name']:c for c in inspector.get_columns('operational_activities')}
        if 'parent_id' in columns:
            if not isinstance(columns['parent_id']['type'],sa.Integer) or not columns['parent_id']['nullable']: raise RuntimeError('parent_id: schema incompatibile')
            fks=inspector.get_foreign_keys('operational_activities')
            if not any(fk['constrained_columns']==['parent_id'] and fk['referred_table']=='operational_activities' and fk.get('options',{}).get('ondelete')=='RESTRICT' for fk in fks):
                raise RuntimeError('operational_activities.parent_id: chiave esterna mancante')
            if not any(index['column_names']==['parent_id'] for index in inspector.get_indexes('operational_activities')):
                op.create_index('ix_operational_activities_parent_id','operational_activities',['parent_id'])
            return
    with op.batch_alter_table('operational_activities',reflect_kwargs={'resolve_fks':False}) as batch:
        batch.add_column(sa.Column('parent_id',sa.Integer,nullable=True))
        batch.create_foreign_key('fk_activity_parent','operational_activities',['parent_id'],['id'],ondelete='RESTRICT')
        batch.create_index('ix_operational_activities_parent_id',['parent_id'])


def downgrade():
    with op.batch_alter_table('operational_activities',reflect_kwargs={'resolve_fks':False}) as batch:
        batch.drop_index('ix_operational_activities_parent_id')
        # Reflected create_all constraints may be unnamed on SQLite.
        if op.get_context().as_sql or any(fk.get('name')=='fk_activity_parent' for fk in sa.inspect(op.get_bind()).get_foreign_keys('operational_activities')):
            batch.drop_constraint('fk_activity_parent',type_='foreignkey')
        batch.drop_column('parent_id')
