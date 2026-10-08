import importlib.util
from pathlib import Path
from io import StringIO
import unittest
from sqlalchemy import create_engine, text, inspect
from alembic.migration import MigrationContext
from alembic.operations import Operations
from extensions import db
from models import SupplierOrderSubgroup, SupplierOrderSubgroupMatrix, SupplierBoardOrderLine


def migrations():
    result=[]
    for filename in ['n9c0d1e2f3a4_supplier_subgroups.py','o0d1e2f3a4b5_supplier_order_lines.py','p1e2f3a4b5c6_supplier_order_pdf.py']:
        spec=importlib.util.spec_from_file_location(filename,Path('migrations/versions')/filename)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);result.append(module)
    return result


class SupplierMigrationCompatibilityTests(unittest.TestCase):
    def connection(self):
        engine=create_engine('sqlite://');connection=engine.connect();self.addCleanup(engine.dispose);self.addCleanup(connection.close)
        connection.execute(text('CREATE TABLE supplier_order_groups (id INTEGER PRIMARY KEY)'))
        connection.execute(text('CREATE TABLE supplier_board_cards (id INTEGER PRIMARY KEY, title TEXT)'))
        return connection

    def test_tables_created_from_models_are_reused_and_data_preserved(self):
        connection=self.connection()
        db.metadata.create_all(connection,tables=[model.__table__ for model in [SupplierOrderSubgroup,SupplierOrderSubgroupMatrix,SupplierBoardOrderLine]])
        connection.execute(text("INSERT INTO supplier_order_subgroups (id,group_id,name) VALUES (1,1,'Nespresso')"))
        connection.execute(text("INSERT INTO supplier_board_order_lines (id,card_id,matrix_code,description,quantity,stock_at_order) VALUES (1,1,'CF1','Capsule',12,17)"))
        with Operations.context(MigrationContext.configure(connection)):
            for migration in migrations():migration.upgrade()
            connection.execute(text("INSERT INTO supplier_board_cards (id,title,order_pdf) VALUES (1,'Ordine',:pdf)"),dict(pdf=b'%PDF-test'))
            for migration in migrations():migration.upgrade()
        self.assertEqual(connection.execute(text('SELECT name FROM supplier_order_subgroups')).scalar(),'Nespresso')
        self.assertEqual(connection.execute(text('SELECT quantity FROM supplier_board_order_lines')).scalar(),12)
        self.assertEqual(connection.execute(text('SELECT order_pdf FROM supplier_board_cards')).scalar(),b'%PDF-test')
        self.assertIn('order_pdf_filename',{column['name'] for column in inspect(connection).get_columns('supplier_board_cards')})

    def test_fresh_schema_upgrades_and_partial_pdf_upgrade_completes(self):
        connection=self.connection();steps=migrations()
        connection.execute(text('ALTER TABLE supplier_board_cards ADD COLUMN order_pdf BLOB'))
        with Operations.context(MigrationContext.configure(connection)):
            for migration in steps:migration.upgrade()
        self.assertTrue(inspect(connection).has_table('supplier_order_subgroup_matrices'))
        self.assertIn('order_pdf_filename',{column['name'] for column in inspect(connection).get_columns('supplier_board_cards')})

    def test_incompatible_existing_table_is_rejected(self):
        connection=self.connection()
        connection.execute(text('CREATE TABLE supplier_order_subgroups (id INTEGER PRIMARY KEY, group_id INTEGER NOT NULL REFERENCES supplier_order_groups(id) ON DELETE CASCADE, name VARCHAR(20) NOT NULL, UNIQUE (group_id,name))'))
        with Operations.context(MigrationContext.configure(connection)):
            with self.assertRaisesRegex(RuntimeError,'lunghezza insufficiente'):migrations()[0].upgrade()

    def test_offline_sql_still_creates_complete_schema(self):
        output=StringIO()
        with Operations.context(MigrationContext.configure(dialect_name='postgresql',opts={'as_sql':True,'output_buffer':output})):
            for migration in migrations():migration.upgrade()
        sql=output.getvalue()
        self.assertIn('CREATE TABLE supplier_order_subgroups',sql);self.assertIn('ADD COLUMN order_pdf BYTEA',sql)
