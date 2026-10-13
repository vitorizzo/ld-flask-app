import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import unittest
from sqlalchemy import create_engine, text, inspect
from alembic.migration import MigrationContext
from alembic.operations import Operations
from extensions import db
from models import SupplierBoardSection, SupplierBoardCardSection, SupplierBoardCard
from tools.supplier_board_sections import rich_text, DEFAULT_SECTIONS
import test_supplier_board as board_tests


class SupplierSectionTests(unittest.TestCase):
    setUp = board_tests.SupplierBoardTests.setUp
    tearDown = board_tests.SupplierBoardTests.tearDown

    def create_section(self, name='Anomalia', position=0):
        result = self.client.post('/supplier-orders/api/board/sections', json={'name':name, 'order_index':position})
        self.assertEqual(result.status_code,201)
        return next(row for row in result.json['sections'] if row['name']==name)

    def create_card(self, sections, **extra):
        result = self.client.post('/supplier-orders/api/board/cards',json=dict(title='Arrivo test',column_id=1,sections=sections,**extra))
        self.assertEqual(result.status_code,201,result.json)
        return result.json['card']

    def test_nested_text_roundtrip_sanitize_rename_and_board(self):
        section=self.create_section()
        content='<p><strong>Verificare</strong> annata</p><ul><li>Primo<ul><li><em>Secondo</em></li></ul></li></ul>'
        card=self.create_card({str(section['id']):content})
        saved=card['sections'][0]
        self.assertEqual(saved['content_html'],content)
        self.assertIn('Secondo',saved['text'])
        self.assertEqual(self.client.get('/supplier-orders/api/board').json['sections'][0]['card_count'],1)
        endpoint='/supplier-orders/api/board/sections/'+str(section['id'])
        result=self.client.put(endpoint,json=dict(name='Anomalia Sistemata',order_index=3,revision=section['revision']))
        self.assertEqual(result.status_code,200)
        self.assertEqual(self.client.get('/supplier-orders/api/board').json['cards'][0]['sections'][0]['name'],'Anomalia Sistemata')
        self.assertEqual(db.session.get(SupplierBoardCard,card['id']).notes,'')

    def test_partial_move_retains_text_empty_removes_only_target_section(self):
        a=self.create_section();b=self.create_section('Omaggi',1)
        card=self.create_card({str(a['id']):'<p>A</p>',str(b['id']):'<p>B</p>'})
        endpoint='/supplier-orders/api/board/cards/'+str(card['id'])
        moved=self.client.put(endpoint,json={'column_id':2}).json['card']
        self.assertEqual(len(moved['sections']),2)
        cleared=self.client.put(endpoint,json={'sections':{str(a['id']):'<p><br></p>'},'revision':moved['order_revision']})
        self.assertEqual(cleared.status_code,200)
        self.assertEqual([row['name'] for row in cleared.json['card']['sections']],['Omaggi'])
        self.assertEqual(SupplierBoardCardSection.query.count(),1)

    def test_definition_validation_duplicates_order_revision_and_permissions(self):
        section=self.create_section()
        for payload in [None, [], {'name':''}, {'name':4}, {'name':'a'*81},
                        {'name':'Other','order_index':True}, {'name':'Other','order_index':-1},
                        {'name':'anomalia','order_index':0}]:
            self.assertEqual(self.client.post('/supplier-orders/api/board/sections',json=payload).status_code,400,payload)
        endpoint='/supplier-orders/api/board/sections/'+str(section['id'])
        self.assertEqual(self.client.put(endpoint,json={'name':'Other','revision':0}).status_code,409)
        self.assertEqual(self.client.delete(endpoint,json={'revision':1}).status_code,409)
        with patch('tools.role_required.get_current_user',return_value=SimpleNamespace(active_roles=[],max_role_weight=0)):
            for method,url in [('get','/supplier-orders/api/board/sections'),('post','/supplier-orders/api/board/sections'),('put',endpoint),('delete',endpoint)]:
                self.assertEqual(getattr(self.client,method)(url,json={}).status_code,403)

    def test_delete_requires_current_usage_confirmation_and_cascades_archived(self):
        a=self.create_section();b=self.create_section('Omaggi',1)
        card=self.create_card({str(a['id']):'<p>Note</p>',str(b['id']):'<p>Keep</p>'},is_archived=True)
        endpoint='/supplier-orders/api/board/sections/'+str(a['id'])
        self.assertEqual(self.client.delete(endpoint,json={'revision':1,'confirm':True,'card_count':0}).status_code,409)
        result=self.client.delete(endpoint,json={'revision':1,'confirm':True,'card_count':1})
        self.assertEqual(result.status_code,200)
        saved=self.client.get('/supplier-orders/api/board?archived=1').json['cards'][0]
        self.assertEqual([row['name'] for row in saved['sections']],['Omaggi'])
        self.assertEqual(saved['order_revision'],card['order_revision']+1)
        self.assertEqual(SupplierBoardCardSection.query.count(),1)
        self.assertEqual(self.client.delete('/supplier-orders/api/board/cards/'+str(card['id'])).status_code,200)
        self.assertEqual(SupplierBoardCardSection.query.count(),0)

    def test_invalid_sections_and_stale_card_do_not_overwrite(self):
        a=self.create_section()
        for content in [[], {'999':'x'}, {str(a['id']):['bad']}, {'01':'bad'}, {str(a['id']):'x'*20001}]:
            result=self.client.post('/supplier-orders/api/board/cards',json={'title':'Test','column_id':1,'sections':content})
            self.assertEqual(result.status_code,400,content)
        self.assertEqual(SupplierBoardCard.query.count(),0)
        card=self.create_card({str(a['id']):'<p>Keep</p>'})
        endpoint='/supplier-orders/api/board/cards/'+str(card['id'])
        self.assertEqual(self.client.put(endpoint,json={'notes':'New','revision':card['order_revision']}).status_code,200)
        self.assertEqual(self.client.put(endpoint,json={'sections':{str(a['id']):'Lost'},'revision':card['order_revision']}).status_code,409)
        self.assertEqual(self.client.get('/supplier-orders/api/board').json['cards'][0]['sections'][0]['text'],'Keep')

    def test_pasted_html_keeps_only_safe_formatting(self):
        a=self.create_section()
        html='<p style="color:red" onclick="evil()">Caffè &amp; tè <img src=x onerror=evil()><b>ok</b></p><script>evil()</script><svg><script>evil()</script></svg><a href="javascript:evil()">link</a>'
        card=self.create_card({str(a['id']):html})
        safe=card['sections'][0]['content_html']
        self.assertEqual(safe,'<p>Caffè &amp; tè <b>ok</b></p>link')
        self.assertNotIn('evil',safe)
        self.assertEqual(rich_text('<p>&nbsp; <br></p>'),('',''))
        self.assertEqual(rich_text('<ul><li>Unclosed')[0],'<ul><li>Unclosed</li></ul>')

    def test_migration_seed_upgrade_twice_and_downgrade(self):
        path=Path(__file__).resolve().parents[1]/'migrations/versions/r3a4b5c6d7e8_supplier_board_sections.py'
        spec=importlib.util.spec_from_file_location('supplier_sections_migration',path)
        migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
        engine=create_engine('sqlite://')
        with engine.begin() as conn:
            conn.execute(text('CREATE TABLE supplier_board_cards (id INTEGER PRIMARY KEY)'))
            context=MigrationContext.configure(conn)
            # Shared compatibility helpers use Alembic's active op proxy.
            with Operations.context(context):
                migration.upgrade();migration.upgrade()
                names=conn.execute(text('SELECT name FROM supplier_board_sections ORDER BY order_index')).scalars().all()
                self.assertEqual(names,list(DEFAULT_SECTIONS))
                migration.downgrade()
            self.assertNotIn('supplier_board_sections',inspect(conn).get_table_names())

    def test_migration_accepts_tables_precreated_by_models(self):
        path=Path(__file__).resolve().parents[1]/'migrations/versions/r3a4b5c6d7e8_supplier_board_sections.py'
        spec=importlib.util.spec_from_file_location('supplier_sections_precreated',path)
        migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
        engine=create_engine('sqlite://')
        with engine.begin() as conn:
            conn.execute(text('CREATE TABLE supplier_board_cards (id INTEGER PRIMARY KEY)'))
            db.metadata.create_all(conn,tables=[SupplierBoardSection.__table__,SupplierBoardCardSection.__table__])
            with Operations.context(MigrationContext.configure(conn)):
                migration.upgrade()
            self.assertEqual(conn.execute(text('SELECT count(*) FROM supplier_board_sections')).scalar(),11)
