from datetime import date
from types import SimpleNamespace
import unittest
import importlib.util
from pathlib import Path
from unittest.mock import patch
from flask import Flask
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy import create_engine, text, inspect
from alembic.migration import MigrationContext
from alembic.operations import Operations
from extensions import db
from models import (SupplierBoardColumn, SupplierBoardCard, BusinessRegistry, BusinessRegistryContact,
                    RegistryContact, RegistryContactPoint, BusinessRegistryContactLink)
from routes.supplier_orders import supplier_orders_bp
from models import SupplierBoardOrderLine


@compiles(JSONB, 'sqlite')
def compile_jsonb_sqlite(type_, compiler, **kwargs):
    return 'JSON'


class SupplierBoardTests(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__);self.app.config.update(TESTING=True,SQLALCHEMY_DATABASE_URI='sqlite://')
        db.init_app(self.app);self.app.register_blueprint(supplier_orders_bp,url_prefix='/supplier-orders')
        self.ctx=self.app.app_context();self.ctx.push()
        tables=[BusinessRegistry, BusinessRegistryContact, RegistryContact, RegistryContactPoint,
                BusinessRegistryContactLink, SupplierBoardColumn, SupplierBoardCard, SupplierBoardOrderLine]
        db.metadata.create_all(db.engine,tables=[model.__table__ for model in tables])
        db.session.add_all([SupplierBoardColumn(id=1,name='In Arrivo',order_index=0),SupplierBoardColumn(id=2,name='Ultimate',order_index=1,is_terminal=True)])
        db.session.add_all([BusinessRegistry(id=1,kind='supplier',source='manual',source_code='S1',display_name='Fornitore prova'),BusinessRegistry(id=2,kind='customer',source='manual',source_code='C1',display_name='Cliente prova')])
        db.session.commit()
        self.auth=patch('tools.role_required.get_current_user',return_value=SimpleNamespace(active_roles=[SimpleNamespace(name='office',weight=40)],max_role_weight=40));self.auth.start()
        self.client=self.app.test_client()

    def tearDown(self):
        self.auth.stop();db.session.remove();self.ctx.pop()

    def test_create_move_edit_archive_restore(self):
        response=self.client.post('/supplier-orders/api/board/cards',json=dict(title='Merce in arrivo',column_id=1,supplier_id=1,expected_date='2026-10-10',notes='Verificare lotti',reference='DDT 12'))
        self.assertEqual(response.status_code,201);card=response.json['card'];self.assertEqual(card['supplier_name'],'Fornitore prova')
        endpoint=f"/supplier-orders/api/board/cards/{card['id']}"
        self.assertEqual(self.client.put(endpoint,json=dict(column_id=2)).json['card']['column_id'],2)
        self.assertEqual(self.client.put(endpoint,json=dict(notes='Arrivata',is_archived=True)).status_code,200)
        self.assertEqual(self.client.get('/supplier-orders/api/board').json['cards'],[])
        self.assertEqual(len(self.client.get('/supplier-orders/api/board?archived=1').json['cards']),1)
        self.client.put(endpoint,json=dict(is_archived=False));self.assertEqual(len(self.client.get('/supplier-orders/api/board').json['cards']),1)

    def test_invalid_input_does_not_create_card(self):
        for payload in [dict(title='',column_id=1),dict(title='X',column_id=99),dict(title='X',column_id=1,supplier_id=2),dict(title='X',column_id=1,expected_date='2026-02-31'),dict(title='X',column_id=True),dict(title='X',column_id=1,notes=['bad'])]:
            with self.subTest(payload=payload):
                self.assertEqual(self.client.post('/supplier-orders/api/board/cards',json=payload).status_code,400)
                self.assertEqual(SupplierBoardCard.query.count(),0)

    def test_free_title_and_unknown_card(self):
        response=self.client.post('/supplier-orders/api/board/cards',json=dict(title='Fornitore da collegare',column_id=1))
        self.assertEqual(response.status_code,201);self.assertIsNone(response.json['card']['supplier_id'])
        self.assertEqual(self.client.put('/supplier-orders/api/board/cards/999',json=dict(column_id=2)).status_code,404)

    def test_permissions(self):
        with patch('tools.role_required.get_current_user',return_value=SimpleNamespace(active_roles=[SimpleNamespace(name='staff',weight=30)],max_role_weight=30)):
            self.assertEqual(self.client.post('/supplier-orders/api/board/cards',json=dict(title='X',column_id=1)).status_code,403)

    def test_migration_creates_seed_columns_and_menu_and_downgrades(self):
        path=Path(__file__).resolve().parents[1]/'migrations/versions/m8b9c0d1e2f3_add_supplier_order_board.py'
        spec=importlib.util.spec_from_file_location('supplier_board_migration',path)
        migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
        engine=create_engine('sqlite://')
        with engine.begin() as connection:
            connection.execute(text('CREATE TABLE business_registries (id INTEGER PRIMARY KEY)'))
            connection.execute(text('CREATE TABLE menus (id INTEGER PRIMARY KEY,name TEXT,weight INTEGER,sort_order INTEGER,parent_id INTEGER,route TEXT,is_active BOOLEAN,is_visible BOOLEAN,item_type TEXT)'))
            connection.execute(text("INSERT INTO menus (route,parent_id) VALUES ('/supplier-orders',5)"))
            migration.op=Operations(MigrationContext.configure(connection));migration.upgrade()
            self.assertEqual(connection.execute(text('SELECT count(*) FROM supplier_board_columns')).scalar(),8)
            self.assertEqual(connection.execute(text("SELECT name FROM supplier_board_columns WHERE is_terminal=true")).scalar(),'Ultimate')
            self.assertEqual(connection.execute(text("SELECT parent_id FROM menus WHERE route='/supplier-orders/board'")).scalar(),5)
            migration.downgrade();self.assertNotIn('supplier_board_cards',inspect(connection).get_table_names())


if __name__=='__main__':
    unittest.main()
