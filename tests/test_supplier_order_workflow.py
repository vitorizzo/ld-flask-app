import importlib.util
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import create_engine, text, inspect
from alembic.migration import MigrationContext
from alembic.operations import Operations
from io import StringIO
from extensions import db
from models import SupplierBoardCard, SupplierBoardOrderLine, SupplierOrderProductSettings, SupplierOrderGroup, SupplierOrderGroupItem, Articoli
import unittest
import test_supplier_group_orders as group_tests


class SupplierWorkflowTests(unittest.TestCase):
    setUp = group_tests.SupplierGroupOrderTests.setUp
    tearDown = group_tests.SupplierGroupOrderTests.tearDown
    def post(self, **changes):
        body=dict(title='Caffe',column_id=1,lines=[dict(matrix_code='COFFEE',quantity=12)])
        body.update(changes)
        return self.client.post('/supplier-orders/groups/1/orders',json=body)

    def test_draft_resume_confirm_edit_replace_and_delete(self):
        draft=self.post(draft=True,client_key='test-draft-key-123').json['card']
        self.assertTrue(draft['is_draft']);self.assertIsNone(draft['order_pdf_url'])
        editor=self.client.get('/supplier-orders/groups/1/order-editor').json
        self.assertEqual(editor['card']['id'],draft['id']);self.assertEqual(editor['rows'][0]['stock'],11)
        replay=self.post(draft=True,client_key='test-draft-key-123');self.assertTrue(replay.json['replayed'])
        self.assertEqual(SupplierBoardCard.query.count(),1)
        response=self.post(card_id=draft['id'],revision=draft['order_revision'])
        self.assertEqual(response.status_code,200);card=response.json['card'];url=card['order_pdf_url'];original=self.client.get(url).data
        change=self.post(card_id=card['id'],revision=card['order_revision'],lines=[dict(matrix_code='POD',quantity=9)],title='Ordine modificato')
        self.assertEqual(change.status_code,200);changed=change.json['card']
        self.assertNotEqual(self.client.get(url).data,original);self.assertNotEqual(changed['order_pdf_filename'],card['order_pdf_filename'])
        self.assertEqual([(row['matrix_code'],row['quantity']) for row in changed['order_lines']],[('POD',9)])
        stale=self.post(card_id=card['id'],revision=card['order_revision']);self.assertEqual(stale.status_code,409)
        draft=self.post(card_id=card['id'],revision=changed['order_revision'],draft=True).json['card']
        self.assertIsNone(draft['order_pdf_url']);self.assertEqual(self.client.get(url).status_code,404)
        self.assertEqual(self.client.delete(f"/supplier-orders/api/board/cards/{card['id']}").status_code,200)
        self.assertEqual(SupplierBoardOrderLine.query.count(),0);self.assertEqual(self.client.get(url).status_code,404)

    def test_pdf_error_preserves_confirmed_order_and_configuration(self):
        card=self.post().json['card'];url=card['order_pdf_url'];original=self.client.get(url).data
        with patch('tools.supplier_order_pdf.generate_supplier_order_pdf',side_effect=RuntimeError('Failure')):
            with self.assertLogs(level='ERROR'):
                response=self.post(card_id=card['id'],revision=card['order_revision'],product_details=[dict(matrix_code='COFFEE',supplier_code='NEW',order_description='Changed')])
        self.assertEqual(response.status_code,500);self.assertEqual(self.client.get(url).data,original)
        self.assertEqual(db.session.get(SupplierBoardCard,card['id']).order_revision,card['order_revision'])
        self.assertEqual(SupplierOrderProductSettings.query.filter_by(group_id=1,matrix_code='COFFEE').first().supplier_code,'V-COFFEE')

    def test_missing_supplier_code_draft_allowed_confirmation_rejected(self):
        setting=SupplierOrderProductSettings.query.filter_by(group_id=1,matrix_code='COFFEE').first();setting.supplier_code='';db.session.commit()
        self.assertEqual(self.post().status_code,400)
        draft=self.post(draft=True).json['card']
        response=self.post(card_id=draft['id'],revision=draft['order_revision'],product_details=[dict(matrix_code='COFFEE',supplier_code='2947',order_description='Don Carlo Nera 100pz')])
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['card']['order_lines'][0]['supplier_code'],'2947')

    def test_migration_upgrade_repeat_backfill_downgrade(self):
        spec=importlib.util.spec_from_file_location('draft_migration',Path('migrations/versions/q2f3a4b5c6d7_supplier_order_drafts.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with create_engine('sqlite://').begin() as connection:
            connection.execute(text('CREATE TABLE supplier_order_groups (id INTEGER PRIMARY KEY, name VARCHAR(160))'))
            connection.execute(text('CREATE TABLE supplier_board_cards (id INTEGER PRIMARY KEY, notes TEXT)'))
            connection.execute(text('CREATE TABLE supplier_board_order_lines (id INTEGER PRIMARY KEY)'))
            connection.execute(text("INSERT INTO supplier_order_groups VALUES (1,'Caffe')"))
            connection.execute(text("INSERT INTO supplier_board_cards VALUES (1,'Creato dal gruppo: Caffe')"))
            with Operations.context(MigrationContext.configure(connection)):
                module.upgrade();module.upgrade()
                self.assertEqual(connection.execute(text('SELECT order_group_id,is_draft,order_revision FROM supplier_board_cards')).one(),(1,0,1))
                module.downgrade()
            self.assertEqual(connection.execute(text('SELECT notes FROM supplier_board_cards')).scalar(),'Creato dal gruppo: Caffe')

    def test_reference_seed_reuses_existing_schema_and_preserves_custom_codes(self):
        spec=importlib.util.spec_from_file_location('draft_seed',Path('migrations/versions/q2f3a4b5c6d7_supplier_order_drafts.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        db.session.add(SupplierOrderGroup(id=3,name=module.COFFEE_REFERENCE_GROUP));db.session.flush()
        for index,(code,description,_,_) in enumerate(module.COFFEE_REFERENCE[:2],100):
            db.session.execute(Articoli.__table__.insert().values(id_art=index,cod_art=code,descrizione=description))
            db.session.add(SupplierOrderGroupItem(group_id=3,cod_art=code))
        preserved=module.COFFEE_REFERENCE[0][0]
        db.session.add(SupplierOrderProductSettings(group_id=3,matrix_code=preserved,supplier_code='CUSTOM',order_description='Custom label'))
        db.session.commit()
        with db.engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):module.upgrade();module.upgrade()
        db.session.expire_all()
        self.assertEqual(SupplierOrderProductSettings.query.filter_by(group_id=3,matrix_code=preserved).first().supplier_code,'CUSTOM')
        code,_,expected,_=module.COFFEE_REFERENCE[1]
        self.assertEqual(SupplierOrderProductSettings.query.filter_by(group_id=3,matrix_code=code).first().supplier_code,expected)

    def test_migration_offline_postgresql_contains_new_constraints(self):
        spec=importlib.util.spec_from_file_location('draft_offline',Path('migrations/versions/q2f3a4b5c6d7_supplier_order_drafts.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        output=StringIO()
        with Operations.context(MigrationContext.configure(dialect_name='postgresql',opts={'as_sql':True,'output_buffer':output})):module.upgrade()
        self.assertIn('uq_supplier_card_order_key',output.getvalue());self.assertIn('CREATE TABLE supplier_order_product_settings',output.getvalue())
