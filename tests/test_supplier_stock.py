import unittest
from types import SimpleNamespace
from flask import Flask
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from extensions import db
from models import Articoli, Giacenza
from routes.supplier_orders import _stock_map, _expanded_articles_for_group


@compiles(JSONB, 'sqlite')
def compile_jsonb_sqlite(type_, compiler, **kwargs):
    return 'JSON'


class SupplierStockTests(unittest.TestCase):
    def setUp(self):
        app=Flask(__name__);app.config.update(TESTING=True,SQLALCHEMY_DATABASE_URI='sqlite://')
        db.init_app(app);self.ctx=app.app_context();self.ctx.push()
        default=Articoli.__table__.c.id_art.server_default
        try:
            Articoli.__table__.c.id_art.server_default=None
            db.metadata.create_all(db.engine,tables=[Articoli.__table__,Giacenza.__table__])
        finally:
            Articoli.__table__.c.id_art.server_default=default

    def tearDown(self):
        db.session.remove();self.ctx.pop()

    def test_current_stock_totals_both_depots_without_inventory_export(self):
        db.session.execute(Giacenza.__table__.insert(),[dict(cod_art='CF1',giac_neg=17,giac_www=3),dict(cod_art='CF2',giac_neg=-2,giac_www=0),dict(cod_art='OTHER',giac_neg=999,giac_www=999)])
        self.assertEqual(_stock_map(['CF1','CF2','MISSING']),{'CF1':20,'CF2':-2})
        self.assertEqual(_stock_map([]),{})

    def test_group_expansion_uses_current_stock_for_each_variant(self):
        db.session.execute(Articoli.__table__.insert(),[dict(id_art=1,cod_art='COFFEE',descrizione='Caffe'),dict(id_art=2,cod_art='COFFEE-24',descrizione='Caffe 2024'),dict(id_art=3,cod_art='COFFEE-25',descrizione='Caffe 2025')])
        db.session.execute(Giacenza.__table__.insert(),[dict(cod_art='COFFEE-24',giac_neg=4,giac_www=2),dict(cod_art='COFFEE-25',giac_neg=7,giac_www=0)])
        group=SimpleNamespace(items=[SimpleNamespace(cod_art='COFFEE')],matrix_names=[])
        rows=_expanded_articles_for_group(group)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['stock'],13)
        self.assertEqual({v['cod_art']:v['stock'] for v in rows[0]['variants']},{'COFFEE':0,'COFFEE-24':6,'COFFEE-25':7})


if __name__=='__main__':
    unittest.main()
