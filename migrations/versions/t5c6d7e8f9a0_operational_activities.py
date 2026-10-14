"""Shared role-based activities, supplier arrivals, history and protected photos."""
from alembic import op
import sqlalchemy as sa
from tools.supplier_migration_compat import create_table_if_needed, create_index_if_needed

revision='t5c6d7e8f9a0'
down_revision='s4b5c6d7e8f9'
branch_labels=None
depends_on=None


def upgrade():
    create_table_if_needed('supplier_arrivals',
        sa.Column('id',sa.Integer,primary_key=True),
        sa.Column('event_key',sa.String(64),nullable=False,unique=True),
        sa.Column('card_id',sa.Integer,sa.ForeignKey('supplier_board_cards.id',ondelete='SET NULL'),nullable=True),
        sa.Column('label',sa.String(200),nullable=False),sa.Column('reference',sa.String(160),nullable=False),
        sa.Column('received_on',sa.Date,nullable=False),sa.Column('partial',sa.Boolean,nullable=False),
        sa.Column('note',sa.Text,nullable=False),
        sa.Column('created_by_id',sa.Integer,sa.ForeignKey('user.id',ondelete='SET NULL'),nullable=True),
        sa.Column('created_at',sa.DateTime,nullable=False),unique_keys=(('event_key',),))
    create_table_if_needed('operational_activities',
        sa.Column('id',sa.Integer,primary_key=True),
        sa.Column('arrival_id',sa.Integer,sa.ForeignKey('supplier_arrivals.id',ondelete='SET NULL'),nullable=True),
        sa.Column('kind',sa.String(40),nullable=False),sa.Column('title',sa.String(200),nullable=False),
        sa.Column('status',sa.String(20),nullable=False),
        sa.Column('owner_id',sa.Integer,sa.ForeignKey('user.id',ondelete='SET NULL'),nullable=True),
        sa.Column('revision',sa.Integer,nullable=False),sa.Column('cycle',sa.Integer,nullable=False),
        sa.Column('created_at',sa.DateTime,nullable=False),sa.Column('completed_at',sa.DateTime,nullable=True),
        sa.UniqueConstraint('arrival_id','kind',name='uq_activity_arrival_kind'),unique_keys=(('arrival_id','kind'),))
    create_table_if_needed('activity_target_roles',
        sa.Column('activity_id',sa.Integer,sa.ForeignKey('operational_activities.id',ondelete='CASCADE'),primary_key=True),
        sa.Column('role_id',sa.Integer,sa.ForeignKey('roles.id',ondelete='CASCADE'),primary_key=True))
    create_table_if_needed('activity_events',
        sa.Column('id',sa.Integer,primary_key=True),
        sa.Column('activity_id',sa.Integer,sa.ForeignKey('operational_activities.id',ondelete='CASCADE'),nullable=False),
        sa.Column('actor_id',sa.Integer,sa.ForeignKey('user.id',ondelete='SET NULL'),nullable=True),
        sa.Column('action',sa.String(30),nullable=False),sa.Column('note',sa.Text,nullable=False),
        sa.Column('created_at',sa.DateTime,nullable=False))
    create_table_if_needed('activity_photos',
        sa.Column('id',sa.Integer,primary_key=True),
        sa.Column('activity_id',sa.Integer,sa.ForeignKey('operational_activities.id',ondelete='CASCADE'),nullable=False),
        sa.Column('cycle',sa.Integer,nullable=False),sa.Column('storage_name',sa.String(64),nullable=False,unique=True),
        sa.Column('label',sa.String(200),nullable=False),
        sa.Column('actor_id',sa.Integer,sa.ForeignKey('user.id',ondelete='SET NULL'),nullable=True),
        sa.Column('created_at',sa.DateTime,nullable=False),unique_keys=(('storage_name',),))
    for table,column in [('supplier_arrivals','card_id'),('operational_activities','arrival_id'),
                         ('operational_activities','status'),('activity_events','activity_id'),('activity_photos','activity_id')]:
        create_index_if_needed('ix_'+table+'_'+column,table,[column])
    op.execute("""INSERT INTO menus (name,weight,sort_order,parent_id,route,is_active,is_visible,item_type)
        SELECT 'Attività',30,85,NULL,'/activities',true,true,'link'
        WHERE NOT EXISTS (SELECT 1 FROM menus WHERE route='/activities')""")


def downgrade():
    op.execute("DELETE FROM menus WHERE route='/activities'")
    for table in ['activity_photos','activity_events','activity_target_roles','operational_activities','supplier_arrivals']:
        op.drop_table(table)
