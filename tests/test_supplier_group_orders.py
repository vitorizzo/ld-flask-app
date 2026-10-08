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

    def test_pdf_attachment_open_download_and_immutable_after_edit(self):
        response=self.client.post('/supplier-orders/groups/1/orders',json=dict(column_id=1,lines=[dict(matrix_code='COFFEE',quantity=12)]))
        self.assertEqual(response.status_code,201)
        card=response.json['card'];url=card['order_pdf_url']
        self.assertTrue(url.endswith('/order-pdf'));self.assertTrue(card['order_pdf_filename'].endswith('.pdf'))
        pdf=self.client.get(url);self.assertEqual(pdf.status_code,200);self.assertEqual(pdf.mimetype,'application/pdf');self.assertTrue(pdf.data.startswith(b'%PDF-'))
        self.assertTrue(pdf.headers['Content-Disposition'].startswith('inline'))
        self.assertTrue(self.client.get(url+'?download=1').headers['Content-Disposition'].startswith('attachment'))
        self.client.put(f"/supplier-orders/api/board/cards/{card['id']}",json={'title':'Nuovo titolo'})
        self.assertEqual(self.client.get(url).data,pdf.data)
        self.assertNotIn('order_pdf',self.client.get('/supplier-orders/api/board').json['cards'][0])
        with patch('tools.role_required.get_current_user',return_value=SimpleNamespace(active_roles=[],max_role_weight=0)):
            self.assertEqual(self.client.get(url,headers={'Content-Type':'application/json'}).status_code,403)
        manual=self.client.post('/supplier-orders/api/board/cards',json={'title':'Manuale','column_id':1}).json['card']
        self.assertIsNone(manual['order_pdf_url']);self.assertEqual(self.client.get(f"/supplier-orders/api/board/cards/{manual['id']}/order-pdf").status_code,404)

    def test_pdf_failure_rolls_back_order_and_lines(self):
        with patch('tools.supplier_order_pdf.generate_supplier_order_pdf',side_effect=RuntimeError('PDF failure')):
            with self.assertLogs(level='ERROR'):
                response=self.client.post('/supplier-orders/groups/1/orders',json=dict(column_id=1,lines=[dict(matrix_code='COFFEE',quantity=12)]))
        self.assertEqual(response.status_code,500);self.assertEqual(SupplierBoardCard.query.count(),0);self.assertEqual(SupplierBoardOrderLine.query.count(),0)

    def test_pdf_migration_preserves_existing_cards(self):
        spec=importlib.util.spec_from_file_location('pdf_migration',Path('migrations/versions/p1e2f3a4b5c6_supplier_order_pdf.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with create_engine('sqlite://').begin() as connection:
            connection.execute(text('CREATE TABLE supplier_board_cards (id INTEGER PRIMARY KEY, title TEXT)'))
            connection.execute(text("INSERT INTO supplier_board_cards VALUES (1,'Ordine esistente')"))
            with Operations.context(MigrationContext.configure(connection)):
                module.upgrade();self.assertIn('order_pdf',{c['name'] for c in inspect(connection).get_columns('supplier_board_cards')});module.downgrade()
            self.assertEqual(connection.execute(text('SELECT title FROM supplier_board_cards')).scalar(),'Ordine esistente')

    def test_order_lines_migration(self):
        spec=importlib.util.spec_from_file_location('order_migration',Path('migrations/versions/o0d1e2f3a4b5_supplier_order_lines.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with create_engine('sqlite://').begin() as connection:
            connection.execute(text('CREATE TABLE supplier_board_cards (id INTEGER PRIMARY KEY)'))
            with Operations.context(MigrationContext.configure(connection)):
                module.upgrade();self.assertIn('supplier_board_order_lines',inspect(connection).get_table_names());module.downgrade()
            self.assertIn('supplier_board_cards',inspect(connection).get_table_names())
