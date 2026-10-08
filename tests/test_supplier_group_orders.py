import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from sqlalchemy import create_engine, text, inspect
from alembic.migration import MigrationContext
from alembic.operations import Operations
from extensions import db
from models import SupplierBoardColumn, SupplierBoardCard, SupplierBoardOrderLine, Giacenza
import test_supplier_subgroups as subgroup_tests


class SupplierGroupOrderTests(unittest.TestCase):
    tearDown = subgroup_tests.SupplierSubgroupTests.tearDown
    create = subgroup_tests.SupplierSubgroupTests.create

    def setUp(self):
        subgroup_tests.SupplierSubgroupTests.setUp(self)
        db.metadata.create_all(db.engine,tables=[SupplierBoardCard.__table__,SupplierBoardOrderLine.__table__])
        db.session.add(SupplierBoardColumn(id=1,name='In Arrivo',order_index=0,is_terminal=False));db.session.commit()

    def test_create_order_freezes_quantities_stock_names_and_survives_board_edit(self):
        subgroup=self.create('Nespresso')
        self.client.post('/supplier-orders/groups/1/subgroup-assignment',json=dict(codes=['COFFEE'],subgroup_id=subgroup))
        response=self.client.post('/supplier-orders/groups/1/orders',json=dict(title='Ordine caffe',column_id=1,lines=[dict(matrix_code='COFFEE',quantity=20),dict(matrix_code='POD',quantity=4)]))
        self.assertEqual(response.status_code,201);card=response.json['card']
        self.assertEqual([(line['matrix_code'],line['quantity'],line['stock_at_order'],line['subgroup_name']) for line in card['order_lines']],[('COFFEE',20,11,'Nespresso'),('POD',4,0,'')])
        self.assertEqual(Giacenza.query.filter_by(cod_art='COFFEE-24').first().giac_neg,4)
        db.session.execute(Giacenza.__table__.update().values(giac_neg=99));db.session.commit()
        response=self.client.put(f"/supplier-orders/api/board/cards/{card['id']}",json=dict(title='Titolo modificato',notes='Note aggiornate'))
        self.assertEqual(response.status_code,200);self.assertEqual(response.json['card']['order_lines'],card['order_lines'])
        self.assertEqual(self.client.get('/supplier-orders/api/board').json['cards'][0]['order_lines'],card['order_lines'])

    def test_order_validation_creates_no_partial_cards(self):
        good=dict(column_id=1,lines=[dict(matrix_code='COFFEE',quantity=1)])
        invalid=[dict(lines=[]),dict(column_id=999),dict(title=''),dict(title='x'*201)]
        invalid += [dict(lines=[dict(matrix_code='COFFEE',quantity=q)]) for q in [0,-1,1.5,True,'4',1000001]]
        invalid += [dict(lines=[dict(matrix_code='FOREIGN',quantity=1)]),dict(lines=[dict(matrix_code='COFFEE',quantity=1)]*2),dict(lines=['invalid'])]
        for delta in invalid:
            self.assertEqual(self.client.post('/supplier-orders/groups/1/orders',json=dict(good,**delta)).status_code,400,delta)
        self.assertEqual(SupplierBoardCard.query.count(),0);self.assertEqual(SupplierBoardOrderLine.query.count(),0)

    def test_order_creation_permissions(self):
        with patch('tools.role_required.get_current_user',return_value=SimpleNamespace(active_roles=[],max_role_weight=0)):
            self.assertEqual(self.client.post('/supplier-orders/groups/1/orders',json={}).status_code,403)

    def test_order_lines_migration(self):
        spec=importlib.util.spec_from_file_location('order_migration',Path('migrations/versions/o0d1e2f3a4b5_supplier_order_lines.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with create_engine('sqlite://').begin() as connection:
            connection.execute(text('CREATE TABLE supplier_board_cards (id INTEGER PRIMARY KEY)'))
            with Operations.context(MigrationContext.configure(connection)):
                module.upgrade();self.assertIn('supplier_board_order_lines',inspect(connection).get_table_names());module.downgrade()
            self.assertIn('supplier_board_cards',inspect(connection).get_table_names())
