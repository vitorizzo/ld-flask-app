"""Editable supplier orders, persisted drafts and supplier product codes."""
from alembic import op
import sqlalchemy as sa
from tools.supplier_migration_compat import add_column_if_needed,create_table_if_needed,create_index_if_needed
revision='q2f3a4b5c6d7'
down_revision='p1e2f3a4b5c6'
branch_labels=None
depends_on=None

# One-time data from the user-provided coffee order reference (2026-10-01).
# Exact group/product descriptions guard against applying these codes to other suppliers.
# Ambiguous system/pack matches and placeholder codes remain blank.
COFFEE_REFERENCE_GROUP='Cialde/Capsule Caffè'
COFFEE_REFERENCE=[('CF10025',
  "CAPSULE LAVAZZA A MODO MIO 100pz - ABBRACCIO MISCELA DECISA - 99 CAFFE'",
  '99007',
  "ABBRACCIO MISCELA DECISA - 99 CAFFE' 100pz"),
 ('CF10026',
  "CAPSULE LAVAZZA A MODO MIO 100pz - CAREZZA MISCELA MORBIDA - 99 CAFFE'",
  '99008',
  "CAREZZA MISCELA MORBIDA - 99 CAFFE' 100pz"),
 ('CF10012',
  "CAPSULE LAVAZZA A MODO MIO 100pz - DON CARLO BLU - CAFFE' BORBONE",
  '2945',
  "DON CARLO BLU - CAFFE' BORBONE 100pz"),
 ('CF10031',
  "CAPSULE LAVAZZA A MODO MIO 100pz - DON CARLO DEK - CAFFE' BORBONE",
  '2946',
  "DON CARLO DEK - CAFFE' BORBONE 100pz"),
 ('CF10038',
  "CAPSULE LAVAZZA A MODO MIO 100pz - DON CARLO NERA - CAFFE' BORBONE",
  '2947',
  "DON CARLO NERA - CAFFE' BORBONE 100pz"),
 ('CF10034',
  "CAPSULE LAVAZZA A MODO MIO 100pz - DON CARLO ORO - CAFFE' BORBONE",
  '2948',
  "DON CARLO ORO - CAFFE' BORBONE 100pz"),
 ('CF10011',
  "CAPSULE LAVAZZA A MODO MIO 100pz - DON CARLO RED - CAFFE' BORBONE",
  '2949',
  "DON CARLO RED - CAFFE' BORBONE 100pz"),
 ('CF10027',
  "CAPSULE LAVAZZA A MODO MIO 100pz - PENSIERO MISCELA DEK - 99 CAFFE'",
  '99009',
  "PENSIERO MISCELA DEK - 99 CAFFE' 100pz"),
 ('CF03003', 'CAPSULE LAVAZZA A MODO MIO 30pz - GINSENG - AROMA LIGHT', '5997', 'GINSENG - AROMA LIGHT 30pz'),
 ('CF03010', 'CAPSULE LAVAZZA A MODO MIO 30pz - NOCCIOLINO - AROMA LIGHT', '', 'NOCCIOLINO - AROMA LIGHT 30pz'),
 ('CF03009', 'CAPSULE LAVAZZA A MODO MIO 30pz - ORZO - AROMA LIGHT', '5995', 'ORZO - AROMA LIGHT 30pz'),
 ('CF08004',
  "CAPSULE LAVAZZA A MODO MIO 80pz - PENSIERO MISCELA DEK - 99 CAFFE'",
  '',
  "PENSIERO MISCELA DEK - 99 CAFFE' 80pz"),
 ('CF05025',
  "CAPSULE LAVAZZA ESPRESSO POINT 50pz - MISCELA ORO - CAFFE' BORBONE",
  '',
  "MISCELA ORO - CAFFE' BORBONE 50pz"),
 ('CF05021',
  "CAPSULE NESCAFE DOLCE GUSTO 50pz - MISCELA BLU - CAFFE' BORBONE",
  '100395',
  "MISCELA BLU - CAFFE' BORBONE 50pz"),
 ('CF05024',
  "CAPSULE NESCAFE DOLCE GUSTO 50pz - MISCELA DEK - CAFFE' BORBONE",
  '',
  "MISCELA DEK - CAFFE' BORBONE 50pz"),
 ('CF05023',
  "CAPSULE NESCAFE DOLCE GUSTO 50pz - MISCELA NERA - CAFFE' BORBONE",
  '100399',
  "MISCELA NERA - CAFFE' BORBONE 50pz"),
 ('CF05022',
  "CAPSULE NESCAFE DOLCE GUSTO 50pz - MISCELA ROSSA - CAFFE' BORBONE",
  '100396',
  "MISCELA ROSSA - CAFFE' BORBONE 50pz"),
 ('CF04001',
  "CAPSULE NESCAFE' DOLCE GUSTO 40pz - CAREZZA MISCELA MORBIDA - 99 CAFFE'",
  '',
  "CAREZZA MISCELA MORBIDA - 99 CAFFE' 40pz"),
 ('CF05008',
  "CAPSULE NESCAFE' DOLCE GUSTO 50pz - ABBRACCIO MISCELA DECISA - 99 CAFFE'",
  '99010',
  "ABBRACCIO MISCELA DECISA - 99 CAFFE' 50pz"),
 ('CF05010',
  "CAPSULE NESCAFE' DOLCE GUSTO 50pz - PENSIERO MISCELA DEK - 99 CAFFE'",
  '99012',
  "PENSIERO MISCELA DEK - 99 CAFFE' 50pz"),
 ('CF10007',
  "CAPSULE NESPRESSO 100pz - RESPRESSO BLU - CAFFE' BORBONE",
  '2940',
  "RESPRESSO BLU - CAFFE' BORBONE 100pz"),
 ('CF10009',
  "CAPSULE NESPRESSO 100pz - RESPRESSO DEK - CAFFE' BORBONE",
  '2941',
  "RESPRESSO DEK - CAFFE' BORBONE 100pz"),
 ('CF10008',
  "CAPSULE NESPRESSO 100pz - RESPRESSO NERA - CAFFE' BORBONE",
  '2942',
  "RESPRESSO NERA - CAFFE' BORBONE 100pz"),
 ('CF10010',
  "CAPSULE NESPRESSO 100pz - RESPRESSO ORO - CAFFE' BORBONE",
  '2943',
  "RESPRESSO ORO - CAFFE' BORBONE 100pz"),
 ('CF10006',
  "CAPSULE NESPRESSO 100pz - RESPRESSO RED - CAFFE' BORBONE",
  '2944',
  "RESPRESSO RED - CAFFE' BORBONE 100pz"),
 ('CF08001',
  "CAPSULE NESPRESSO 80pz - ABBRACCIO MISCELA DECISA - 99 CAFFE'",
  '990042',
  "ABBRACCIO MISCELA DECISA - 99 CAFFE' 80pz"),
 ('CF08002',
  "CAPSULE NESPRESSO 80pz - CAREZZA MISCELA DELICATA - 99 CAFFE'",
  '990052',
  "CAREZZA MISCELA DELICATA - 99 CAFFE' 80pz"),
 ('CF15002', "CIALDA COMPOSTABILE 150pz - MISCELA BLU - CAFFE' BORBONE", '2935', "MISCELA BLU - CAFFE' BORBONE 150pz"),
 ('CF15008', "CIALDA COMPOSTABILE 150pz - MISCELA DEK - CAFFE' BORBONE", '2936', "MISCELA DEK - CAFFE' BORBONE 150pz"),
 ('CF15007',
  "CIALDA COMPOSTABILE 150pz - MISCELA NERA - CAFFE' BORBONE",
  '2937',
  "MISCELA NERA - CAFFE' BORBONE 150pz"),
 ('CF15001', "CIALDA COMPOSTABILE 150pz - MISCELA RED - CAFFE' BORBONE", '2939', "MISCELA RED - CAFFE' BORBONE 150pz"),
 ('CF01806',
  "CIALDA COMPOSTABILE 18pz - CAFFE' AL GINSENG - CAFFE' BORBONE",
  '2978',
  "CAFFE' AL GINSENG - CAFFE' BORBONE 18pz"),
 ('CF01807',
  "CIALDA COMPOSTABILE 18pz - ESPRESSO D'ORZO - CAFFE' BORBONE",
  '2977',
  "ESPRESSO D'ORZO - CAFFE' BORBONE 18pz"),
 ('CF01809',
  "CIALDA COMPOSTABILE 18pz - FRUTTI DI BOSCO - CAFFE' BORBONE",
  '',
  "FRUTTI DI BOSCO - CAFFE' BORBONE 18pz"),
 ('CF01808', "CIALDA COMPOSTABILE 18pz - TISANA DETOX - CAFFE' BORBONE", '', "TISANA DETOX - CAFFE' BORBONE 18pz"),
 ('CF05019', "CIALDA COMPOSTABILE 50pz - MISCELA DEK - CAFFE' BORBONE", '', "MISCELA DEK - CAFFE' BORBONE 50pz"),
 ('CF11001',
  "CIALDA COMPOSTABILE ESE 44mm 110pz - ABBRACCIO MISCELA DECISA - 99 CAFFE'",
  '990012',
  "ABBRACCIO MISCELA DECISA - 99 CAFFE' 110pz"),
 ('CF11003',
  "CIALDA COMPOSTABILE ESE 44mm 110pz - CAREZZA MISCELA DELICATA - 99 CAFFE'",
  '990022',
  "CAREZZA MISCELA DELICATA - 99 CAFFE' 110pz"),
 ('CF11002',
  "CIALDA COMPOSTABILE ESE 44mm 110pz - PENSIERO MISCELA DEK - 99 CAFFE'",
  '990032',
  "PENSIERO MISCELA DEK - 99 CAFFE' 110pz")]


def upgrade():
    for column in [sa.Column('order_group_id',sa.Integer(),nullable=True),
                   sa.Column('is_draft',sa.Boolean(),nullable=False,server_default=sa.false()),
                   sa.Column('order_revision',sa.Integer(),nullable=False,server_default='1'),
                   sa.Column('order_key',sa.String(64),nullable=True),
                   sa.Column('order_confirmed_at',sa.DateTime(),nullable=True)]:
        add_column_if_needed('supplier_board_cards',column)
    offline=op.get_context().as_sql
    inspector=None if offline else sa.inspect(op.get_bind())
    keys=[] if offline else inspector.get_foreign_keys('supplier_board_cards')
    uniques=[] if offline else inspector.get_unique_constraints('supplier_board_cards')
    missing_fk=not any(key['constrained_columns']==['order_group_id'] and key['referred_table']=='supplier_order_groups' for key in keys)
    missing_unique=not any(key['column_names']==['order_key'] for key in uniques)
    if missing_fk or missing_unique:
        with op.batch_alter_table('supplier_board_cards') as batch:
            if missing_fk:batch.create_foreign_key('fk_supplier_card_order_group','supplier_order_groups',['order_group_id'],['id'],ondelete='SET NULL')
            if missing_unique:batch.create_unique_constraint('uq_supplier_card_order_key',['order_key'])
    for column in [sa.Column('supplier_code',sa.String(80),nullable=True),sa.Column('order_description',sa.String(200),nullable=True)]:
        add_column_if_needed('supplier_board_order_lines',column)
    create_table_if_needed('supplier_order_product_settings',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('group_id',sa.Integer(),sa.ForeignKey('supplier_order_groups.id',ondelete='CASCADE'),nullable=False),
        sa.Column('matrix_code',sa.String(255),nullable=False),sa.Column('supplier_code',sa.String(80),nullable=False),
        sa.Column('order_description',sa.String(200),nullable=False),
        sa.UniqueConstraint('group_id','matrix_code',name='uq_supplier_product_settings'),unique_keys=[('group_id','matrix_code')])
    create_index_if_needed('ix_supplier_order_product_settings_group_id','supplier_order_product_settings',['group_id'])
    op.execute(sa.text("""UPDATE supplier_board_cards SET order_group_id=(SELECT g.id FROM supplier_order_groups g
      WHERE supplier_board_cards.notes='Creato dal gruppo: ' || g.name) WHERE order_group_id IS NULL
      AND EXISTS (SELECT 1 FROM supplier_order_groups g WHERE supplier_board_cards.notes='Creato dal gruppo: ' || g.name)"""))
    if not offline:
        tables=set(sa.inspect(op.get_bind()).get_table_names())
        if {'articoli','supplier_order_group_items'}.issubset(tables):
            for code,expected,supplier_code,description in COFFEE_REFERENCE:
                op.get_bind().execute(sa.text("""INSERT INTO supplier_order_product_settings
                    (group_id,matrix_code,supplier_code,order_description)
                    SELECT DISTINCT g.id,:code,:supplier_code,:description FROM supplier_order_groups g
                    JOIN supplier_order_group_items i ON i.group_id=g.id
                    JOIN articoli a ON a.cod_art=i.cod_art
                    WHERE g.name=:group_name AND a.cod_art=:code AND
                    (CASE WHEN TRIM(COALESCE(a.descrizione_aggiuntiva,''))=''
                      THEN TRIM(COALESCE(a.descrizione,''))
                      WHEN TRIM(COALESCE(a.descrizione,''))='' THEN TRIM(a.descrizione_aggiuntiva)
                      ELSE TRIM(a.descrizione) || ' - ' || TRIM(a.descrizione_aggiuntiva) END)=:expected
                    AND NOT EXISTS (SELECT 1 FROM supplier_order_product_settings p
                                    WHERE p.group_id=g.id AND p.matrix_code=:code)"""),
                    dict(code=code,expected=expected,supplier_code=supplier_code,description=description,group_name=COFFEE_REFERENCE_GROUP))


def downgrade():
    op.drop_table('supplier_order_product_settings')
    for name in ['order_description','supplier_code']:op.drop_column('supplier_board_order_lines',name)
    with op.batch_alter_table('supplier_board_cards') as batch:
        batch.drop_constraint('uq_supplier_card_order_key',type_='unique')
        batch.drop_constraint('fk_supplier_card_order_group',type_='foreignkey')
        for name in ['order_confirmed_at','order_key','order_revision','is_draft','order_group_id']:batch.drop_column(name)
