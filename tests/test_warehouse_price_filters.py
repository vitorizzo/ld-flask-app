import unittest
from types import SimpleNamespace
from unittest.mock import patch
from flask import Flask
from flask_login import LoginManager
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from extensions import db
from models import Articoli, Giacenza
from routes.search import search_bp


@compiles(JSONB, 'sqlite')
def compile_jsonb_sqlite(type_, compiler, **kwargs):
    return 'JSON'


class WarehousePriceFilterTests(unittest.TestCase):
    def setUp(self):
        app=Flask(__name__)
        app.config.update(TESTING=True,SECRET_KEY='test',SQLALCHEMY_DATABASE_URI='sqlite://')
        db.init_app(app);app.register_blueprint(search_bp,url_prefix='/search')
        self.user=SimpleNamespace(id=1,is_authenticated=True,is_active=True,is_anonymous=False,
            max_role_weight=40,listino_prezzo='prezzo3',has_active_role=lambda *roles:False,
            active_roles=[SimpleNamespace(name='office',weight=40)])
        login=LoginManager(app);login.user_loader(lambda _:self.user)
        self.auth=patch('tools.role_required.get_current_user',side_effect=lambda:self.user);self.auth.start()
        self.ctx=app.app_context();self.ctx.push();self.client=app.test_client()
        with self.client.session_transaction() as session:session['_user_id']='1'
        default=Articoli.__table__.c.id_art.server_default
        try:
            Articoli.__table__.c.id_art.server_default=None
            db.metadata.create_all(db.engine,tables=[Articoli.__table__,Giacenza.__table__])
        finally:Articoli.__table__.c.id_art.server_default=default
        for index,(code,p3,legacy,p1,cost) in enumerate([
            ('A',0,99,20,3),('B',10.5,99,7,4),('C',20,99,8,5),
            ('D',None,15,9,6),('E',None,None,None,None)],1):
            db.session.execute(Articoli.__table__.insert().values(id_art=index,cod_art=code,descrizione='Caffe '+code,
                prezzo_3=p3,prezzo=legacy,prezzo_1=p1,costo=cost))
        db.session.add_all([Giacenza(cod_art='B',giac_neg=1,giac_www=0),Giacenza(cod_art='D',giac_neg=0,giac_www=2)])
        db.session.commit()

    def tearDown(self):
        self.auth.stop();db.session.remove();self.ctx.pop()

    def get(self, **params):
        return self.client.get('/search/elenco-prodotti/dati',query_string=params)

    def codes(self, **params):
        response=self.get(**params);self.assertEqual(response.status_code,200,response.json)
        return [row['cod_art'] for row in response.json['prodotti']]

    def test_bounds_inclusive_fallback_zero_and_missing_price(self):
        self.assertEqual(self.codes(),['A','B','C','D','E'])
        self.assertEqual(self.codes(price_min='10,5',price_max='20'),['B','C','D'])
        self.assertEqual(self.codes(price_min='0',price_max='0'),['A'])
        self.assertEqual(self.codes(price_min='15'),['C','D'])
        self.assertEqual(self.codes(price_max='10.5'),['A','B'])

    def test_stock_description_and_pagination_share_filtered_total(self):
        response=self.get(price_min='10.5',price_max='20',stock_scope='any',filter='Caffe',per_page=1,page=2)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['totale_prodotti'],2);self.assertEqual(response.json['pagine_totali'],2)
        self.assertEqual(response.json['prodotti'][0]['cod_art'],'D')
        self.assertEqual(self.codes(price_min='10',stock_scope='store'),['B'])
        self.assertEqual(self.codes(price_max='16',stock_scope='online'),['D'])

    def test_price_list_selection_uses_actual_column_and_enforces_permissions(self):
        self.assertEqual(self.codes(price_min='7',price_max='8',price_list='prezzo1'),['B','C'])
        self.assertEqual(self.codes(price_max='4',price_list='costo'),['A','B'])
        self.user.max_role_weight=30
        self.assertEqual(self.get(price_list='costo',price_min='0').status_code,400)
        self.assertEqual(self.get(price_list='unknown').status_code,400)
        self.assertEqual(self.codes(price_min='10,5',price_max='10,5'),['B'])

    def test_invalid_ranges_rejected_and_blank_limits_restore_all(self):
        for params in [dict(price_min='20',price_max='10'),dict(price_min='-1'),dict(price_max='NaN'),
                       dict(price_min='Infinity'),dict(price_max='abc'),dict(price_min='1,2,3')]:
            self.assertEqual(self.get(**params).status_code,400,params)
        self.assertEqual(self.codes(price_min='',price_max=' '),['A','B','C','D','E'])
