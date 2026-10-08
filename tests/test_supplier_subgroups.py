import unittest
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from flask import Flask
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import create_engine, text, inspect
from alembic.migration import MigrationContext
from alembic.operations import Operations
from extensions import db
from models import (Articoli, Giacenza, SupplierOrderGroup, SupplierOrderGroupItem,
                    SupplierOrderMatrixName, SupplierOrderSubgroup, SupplierOrderSubgroupMatrix)
from routes.supplier_orders import supplier_orders_bp, _expanded_articles_for_group


@compiles(JSONB, 'sqlite')
def compile_jsonb_sqlite(type_, compiler, **kwargs):
    return 'JSON'


class SupplierSubgroupTests(unittest.TestCase):
    def setUp(self):
        app=Flask(__name__);app.config.update(TESTING=True,SQLALCHEMY_DATABASE_URI='sqlite://')
        db.init_app(app);app.register_blueprint(supplier_orders_bp,url_prefix='/supplier-orders')
        self.ctx=app.app_context();self.ctx.push();self.client=app.test_client()
        default=Articoli.__table__.c.id_art.server_default
        try:
            Articoli.__table__.c.id_art.server_default=None
            db.metadata.create_all(db.engine,tables=[m.__table__ for m in [Articoli,Giacenza,SupplierOrderGroup,SupplierOrderGroupItem,SupplierOrderMatrixName,SupplierOrderSubgroup,SupplierOrderSubgroupMatrix]])
        finally: Articoli.__table__.c.id_art.server_default=default
        db.session.execute(Articoli.__table__.insert(),[dict(id_art=i,cod_art=code,descrizione=code) for i,code in enumerate(['COFFEE','COFFEE-24','COFFEE-25','POD'],1)])
        db.session.add_all([SupplierOrderGroup(id=1,name='Caffe'),SupplierOrderGroup(id=2,name='Altro')]);db.session.flush()
        db.session.add_all([SupplierOrderGroupItem(group_id=1,cod_art='COFFEE'),SupplierOrderGroupItem(group_id=1,cod_art='COFFEE-24'),SupplierOrderGroupItem(group_id=1,cod_art='POD')])
        db.session.execute(Giacenza.__table__.insert(),[dict(cod_art='COFFEE-24',giac_neg=4,giac_www=0),dict(cod_art='COFFEE-25',giac_neg=7,giac_www=0)])
        db.session.commit()
        self.auth=patch('tools.role_required.get_current_user',return_value=SimpleNamespace(active_roles=[SimpleNamespace(name='office',weight=40)],max_role_weight=40));self.auth.start()

    def tearDown(self):
        self.auth.stop();db.session.remove();self.ctx.pop()

    def create(self,name='Nespresso',group=1):
        r=self.client.post(f'/supplier-orders/groups/{group}/subgroups',json={'name':name})
        self.assertEqual(r.status_code,200);return r.json['subgroup']['id']

    def test_create_assign_variants_rename_delete_preserves_products(self):
        id_=self.create()
        r=self.client.post('/supplier-orders/groups/1/subgroup-assignment',json=dict(codes=['COFFEE-24'],subgroup_id=id_))
        self.assertEqual(r.status_code,200)
        items=self.client.get('/supplier-orders/groups/1/items').json['items']
        self.assertEqual({i['subgroup_id'] for i in items if i['root']=='COFFEE'},{id_})
        rows=_expanded_articles_for_group(db.session.get(SupplierOrderGroup,1))
        coffee=next(r for r in rows if r['root']=='COFFEE');self.assertEqual(coffee['subgroup_id'],id_);self.assertEqual(coffee['stock'],11)
        self.assertEqual(self.client.put(f'/supplier-orders/groups/1/subgroups/{id_}',json={'name':'Lavazza'}).status_code,200)
        self.assertEqual(self.client.delete(f'/supplier-orders/groups/1/subgroups/{id_}').status_code,200)
        self.assertEqual(SupplierOrderGroupItem.query.count(),3);self.assertEqual(SupplierOrderSubgroupMatrix.query.count(),0)
        self.assertTrue(all(i['subgroup_id'] is None for i in self.client.get('/supplier-orders/groups/1/items').json['items']))

    def test_unassign_and_move_multiple_products(self):
        first=self.create();second=self.create('Cialde')
        for id_ in [first,second,None]:
            self.assertEqual(self.client.post('/supplier-orders/groups/1/subgroup-assignment',json=dict(codes=['COFFEE','POD'],subgroup_id=id_)).status_code,200)
            data=self.client.get('/supplier-orders/groups/1/items').json
            self.assertEqual({i['subgroup_id'] for i in data['items']},{id_})

    def test_validation_is_atomic_and_scoped_to_group(self):
        id_=self.create(group=2)
        for payload in [dict(codes=['COFFEE'],subgroup_id=id_),dict(codes=['COFFEE','FOREIGN'],subgroup_id=None),dict(codes=[],subgroup_id=None),dict(codes='COFFEE'),dict(codes=[None]),dict(codes=['COFFEE'],subgroup_id=True)]:
            self.assertEqual(self.client.post('/supplier-orders/groups/1/subgroup-assignment',json=payload).status_code,400)
        self.assertEqual(SupplierOrderSubgroupMatrix.query.count(),0)
        self.assertEqual(self.client.delete(f'/supplier-orders/groups/1/subgroups/{id_}').status_code,404)
        self.create()
        for name in [' nespresso ','','x'*161]:
            self.assertEqual(self.client.post('/supplier-orders/groups/1/subgroups',json={'name':name}).status_code,400)

    def test_permissions(self):
        with patch('tools.role_required.get_current_user',return_value=SimpleNamespace(active_roles=[],max_role_weight=0)):
            self.assertEqual(self.client.post('/supplier-orders/groups/1/subgroups',json={'name':'X'}).status_code,403)

    def test_consultation_sections_keep_unassigned_and_stock_totals(self):
        id_=self.create()
        self.client.post('/supplier-orders/groups/1/subgroup-assignment',json=dict(codes=['COFFEE'],subgroup_id=id_))
        with patch('routes.supplier_orders.render_template',return_value='OK') as renderer:
            self.assertEqual(self.client.get('/supplier-orders/').status_code,200)
            card=next(c for c in renderer.call_args.kwargs['group_cards'] if c['group'].id==1)
            self.assertEqual([(s['name'],s['stock']) for s in card['stock_sections']],[('Nespresso',11),('Senza sottogruppo',0)])

    def test_migration_upgrade_downgrade_preserves_existing_items(self):
        spec=importlib.util.spec_from_file_location('migration',Path('migrations/versions/n9c0d1e2f3a4_supplier_subgroups.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        engine=create_engine('sqlite://')
        with engine.begin() as connection:
            connection.execute(text('CREATE TABLE supplier_order_groups (id INTEGER PRIMARY KEY)'))
            connection.execute(text('CREATE TABLE supplier_order_group_items (id INTEGER PRIMARY KEY, group_id INTEGER, cod_art TEXT)'))
            connection.execute(text("INSERT INTO supplier_order_group_items VALUES (1,1,'COFFEE')"))
            with Operations.context(MigrationContext.configure(connection)):
                module.upgrade();self.assertIn('supplier_order_subgroups',inspect(connection).get_table_names());module.downgrade()
            self.assertEqual(connection.execute(text('SELECT cod_art FROM supplier_order_group_items')).scalar(),'COFFEE')


if __name__=='__main__': unittest.main()
