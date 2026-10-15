"""Activity result recipients, private files and durable result notifications."""
from alembic import op
import sqlalchemy as sa
from tools.supplier_migration_compat import add_column_if_needed, create_table_if_needed, create_index_if_needed
revision='x9a0b1c2d3e4'
down_revision='w8f9a0b1c2d3'
branch_labels=None
depends_on=None


def upgrade():
    add_column_if_needed('operational_activities',sa.Column('result_min_weight',sa.Integer,nullable=True))
    add_column_if_needed('operational_activities',sa.Column('creation_files_digest',sa.String(64),nullable=True))
    for name, column, target in [('activity_result_roles','role_id','roles'),('activity_result_users','user_id','user')]:
        create_table_if_needed(name,
            sa.Column('activity_id',sa.Integer,sa.ForeignKey('operational_activities.id',ondelete='CASCADE'),primary_key=True),
            sa.Column(column,sa.Integer,sa.ForeignKey(target+'.id',ondelete='CASCADE'),primary_key=True))
    create_table_if_needed('activity_attachments',
        sa.Column('id',sa.Integer,primary_key=True),
        sa.Column('activity_id',sa.Integer,sa.ForeignKey('operational_activities.id',ondelete='CASCADE'),nullable=False),
        sa.Column('cycle',sa.Integer,nullable=False),sa.Column('purpose',sa.String(20),nullable=False),
        sa.Column('filename',sa.String(200),nullable=False),sa.Column('mimetype',sa.String(100),nullable=False),
        sa.Column('size',sa.Integer,nullable=False),sa.Column('content',sa.LargeBinary,nullable=False))
    create_index_if_needed('ix_activity_attachments_activity_id','activity_attachments',['activity_id'])
    create_table_if_needed('activity_result_notices',
        sa.Column('id',sa.Integer,primary_key=True),
        sa.Column('activity_id',sa.Integer,sa.ForeignKey('operational_activities.id',ondelete='CASCADE'),nullable=False),
        sa.Column('event_id',sa.Integer,sa.ForeignKey('activity_events.id',ondelete='CASCADE'),nullable=False),
        sa.Column('user_id',sa.Integer,sa.ForeignKey('user.id',ondelete='CASCADE'),nullable=False),
        sa.Column('cycle',sa.Integer,nullable=False),sa.Column('read_at',sa.DateTime,nullable=True),sa.Column('push_sent_at',sa.DateTime,nullable=True),
        sa.UniqueConstraint('event_id','user_id',name='uq_activity_result_event_user'),unique_keys=[('event_id','user_id')])
    for column in ['activity_id','user_id']:
        create_index_if_needed('ix_activity_result_notices_'+column,'activity_result_notices',[column])


def downgrade():
    for name in ['activity_result_notices','activity_attachments','activity_result_users','activity_result_roles']: op.drop_table(name)
    with op.batch_alter_table('operational_activities') as batch:
        batch.drop_column('creation_files_digest');batch.drop_column('result_min_weight')
