from datetime import date,datetime,timedelta
from io import BytesIO
from pathlib import Path
import importlib.util
import tempfile
import unittest
from flask_login import LoginManager
from flask import g
from PIL import Image
from sqlalchemy import create_engine,text,inspect
from alembic.migration import MigrationContext
from alembic.operations import Operations
from extensions import db
from models import (User,Role,UserRole,AppPreference,SupplierArrival,OperationalActivity,ActivityTargetRole,ActivityTargetUser,ActivityEvent,ActivityPhoto)
from routes.activities import activities_bp
from tools.activity_photos import photo_path
import test_supplier_board as board


class ActivityTests(unittest.TestCase):
    def setUp(self):
        board.SupplierBoardTests.setUp(self)
        self.app.config['SECRET_KEY']='activity-test-only'
        self.app.register_blueprint(activities_bp,url_prefix='/activities')
        login=LoginManager(self.app)
        login.user_loader(lambda value:db.session.get(User,int(value)))
        names=[Role,User,UserRole,AppPreference,SupplierArrival,OperationalActivity,ActivityTargetRole,ActivityTargetUser,ActivityEvent,ActivityPhoto]
        db.metadata.create_all(db.engine,tables=[model.__table__ for model in names])
        db.session.add_all([Role(id=1,name='Staff',weight=30),Role(id=2,name='Ufficio',weight=40),Role(id=3,name='Altro',weight=30)])
        for user_id,role_id in [(1,2),(2,1),(3,1),(4,3),(5,1)]:
            db.session.add(User(id=user_id,name=f'User{user_id}',surname='Test',email=f'test{user_id}@example.invalid',password='test'))
            db.session.add(UserRole(user_id=user_id,role_id=role_id,type='period',valid_from=datetime.now()-timedelta(days=10),valid_until=datetime.now()-timedelta(days=1) if user_id==5 else None))
        db.session.commit()
        self.temp=tempfile.TemporaryDirectory();self.app.instance_path=self.temp.name
        self.login(1)
        response=self.client.post('/supplier-orders/api/board/cards',json={'title':'Scarico Rossi','column_id':1,'reference':'DDT 123'})
        self.card=response.json['card']

    def tearDown(self):
        self.temp.cleanup();board.SupplierBoardTests.tearDown(self)

    def login(self,user_id):
        g.pop('_login_user',None)
        with self.client.session_transaction() as session:
            session['_user_id']=str(user_id);session['_fresh']=True

    def arrival_body(self,**extra):
        return dict(card_id=self.card['id'],revision=self.card['order_revision'],event_key='arrival-event-123',received_on='2026-10-14',partial=False,note='Prodotti ricevuti',**extra)

    def arrival(self,key='arrival-event-123',partial=False):
        body=self.arrival_body();body.update(event_key=key,partial=partial)
        result=self.client.post('/activities/api/supplier-arrivals',json=body)
        self.assertEqual(result.status_code,201,result.json)
        return result.json['arrival_id']

    def rows(self): return self.client.get('/activities/api?status=all').json['rows']

    def act(self,row,action,note=''):
        return self.client.post(f"/activities/api/{row['id']}/actions",json=dict(action=action,note=note,revision=row['revision']))

    def image(self):
        output=BytesIO();Image.new('RGB',(10,10),'red').save(output,format='PNG');output.seek(0);return output

    def upload(self,row):
        return self.client.post(f"/activities/api/{row['id']}/photos",data={'revision':str(row['revision']),'label':'Prodotto A, lotto 123','photo':(self.image(),'lotto.png')},content_type='multipart/form-data',headers={'X-Requested-With':'XMLHttpRequest'})

    def test_arrival_three_activities_idempotent_and_partial_separate(self):
        first=self.arrival()
        self.assertEqual(len(self.rows()),3)
        self.assertEqual(self.client.post('/activities/api/supplier-arrivals',json=self.arrival_body()).json['arrival_id'],first)
        self.assertEqual(OperationalActivity.query.count(),3)
        changed=self.arrival_body();changed['note']='Different'
        self.assertEqual(self.client.post('/activities/api/supplier-arrivals',json=changed).status_code,409)
        self.assertNotEqual(self.arrival('second-arrival-123',True),first)
        self.assertEqual(OperationalActivity.query.count(),6)
        self.assertTrue(any(row['source']['partial'] for row in self.rows()))

    def test_role_visibility_expired_roles_and_authentication(self):
        self.arrival();self.login(2)
        self.assertEqual(len(self.rows()),3)
        target=self.rows()[0]['id']
        for user_id in [4,5]:
            self.login(user_id);self.assertEqual(self.rows(),[])
            self.assertEqual(self.client.get(f'/activities/api/{target}').status_code,404)
            self.assertEqual(self.client.post(f'/activities/api/{target}/actions',json={'revision':1,'action':'claim'}).status_code,404)
        self.login(2);self.assertEqual(self.client.get('/activities/api/routing').status_code,403)
        self.assertEqual(self.client.post('/activities/api/supplier-arrivals',json=self.arrival_body()).status_code,403)
        with self.client.session_transaction() as session:session.clear()
        g.pop('_login_user',None)
        self.assertEqual(self.client.get('/activities/api').status_code,401)

    def test_claim_conflict_release_complete_and_history(self):
        self.arrival();self.login(2);row=self.rows()[0]
        claimed=self.act(row,'claim').json['activity'];self.assertEqual(claimed['owner_id'],2)
        self.login(3);self.assertEqual(self.act(row,'claim').status_code,409)
        self.assertEqual(self.act(claimed,'complete').status_code,403)
        self.login(2);released=self.act(claimed,'release').json['activity'];self.assertIsNone(released['owner_id'])
        self.login(3);completed=self.act(released,'complete','Merce verificata').json['activity']
        self.assertEqual(completed['status'],'completed');self.assertEqual(completed['owner_id'],3)
        self.assertEqual([event['action'] for event in completed['events']],['created','claim','release','complete'])
        self.assertEqual(self.act(completed,'complete').status_code,400)

    def test_lots_need_photo_or_reason_and_reopen_cycle(self):
        self.arrival();self.login(2);row=next(row for row in self.rows() if row['kind']=='lots')
        self.assertEqual(self.act(row,'complete').status_code,400)
        self.assertEqual(self.act(row,'not_required').status_code,400)
        skipped=self.act(row,'not_required','Prodotto senza lotto da tracciare').json['activity']
        self.assertEqual(skipped['status'],'not_required')
        self.assertEqual(self.act(skipped,'reopen','Riapri').status_code,403)
        self.login(1);reopened=self.act(skipped,'reopen','Nuova verifica').json['activity']
        self.assertEqual(reopened['cycle'],2);self.assertEqual(reopened['status'],'pending')
        goods=next(row for row in self.rows() if row['kind']=='check_goods')
        self.assertEqual(self.act(goods,'not_required','No').status_code,400)

    def test_photo_normalized_protected_and_old_cycle_cannot_complete(self):
        self.arrival();self.login(2);row=next(row for row in self.rows() if row['kind']=='lots')
        result=self.upload(row);self.assertEqual(result.status_code,201,result.json);uploaded=result.json['activity']
        self.assertEqual(uploaded['owner_id'],2)
        photo=uploaded['photos'][0];response=self.client.get(photo['url']);self.assertEqual(response.status_code,200)
        self.assertEqual(response.mimetype,'image/jpeg');self.assertTrue(response.data.startswith(b'\xff\xd8'))
        self.assertIn('private',response.headers['Cache-Control']);response.close()
        self.login(4);self.assertEqual(self.client.get(photo['url']).status_code,404)
        self.login(2);done=self.act(uploaded,'complete').json['activity'];self.login(1)
        reopened=self.act(done,'reopen','Controllare un altro lotto').json['activity']
        self.assertEqual(self.act(reopened,'complete').status_code,400)
        self.assertEqual(self.client.delete(photo['url'],json={'revision':reopened['revision']}).status_code,400)

    def test_photo_invalid_type_revision_and_remove(self):
        self.arrival();self.login(2);row=next(row for row in self.rows() if row['kind']=='lots')
        bad=self.client.post(f"/activities/api/{row['id']}/photos",data={'revision':'1','label':'Bad','photo':(BytesIO(b'<svg>not an image</svg>'),'photo.svg')},content_type='multipart/form-data',headers={'X-Requested-With':'XMLHttpRequest'})
        self.assertEqual(bad.status_code,400);self.assertEqual(ActivityPhoto.query.count(),0)
        uploaded=self.upload(row).json['activity'];photo=uploaded['photos'][0]
        name=ActivityPhoto.query.first().storage_name
        self.assertEqual(self.client.delete(photo['url'],json={'revision':1}).status_code,409)
        removed=self.client.delete(photo['url'],json={'revision':uploaded['revision']})
        self.assertEqual(removed.status_code,200);self.assertEqual(removed.json['activity']['photos'],[])
        self.assertFalse(photo_path(name).exists());self.assertEqual(self.act(removed.json['activity'],'complete').status_code,400)

    def test_routing_revision_validation_and_snapshot(self):
        config=self.client.get('/activities/api/routing').json;rules={kind:[3] for kind in config['kinds']}
        result=self.client.put('/activities/api/routing',json={'revision':0,'rules':rules});self.assertEqual(result.status_code,200)
        self.assertEqual(self.client.put('/activities/api/routing',json={'revision':0,'rules':rules}).status_code,409)
        rules['lots']=[];self.assertEqual(self.client.put('/activities/api/routing',json={'revision':1,'rules':rules}).status_code,400)
        self.arrival();self.login(2);self.assertEqual(self.rows(),[]);self.login(4);self.assertEqual(len(self.rows()),3)
        self.login(1);rules={kind:[1] for kind in config['kinds']}
        self.assertEqual(self.client.put('/activities/api/routing',json={'revision':1,'rules':rules}).status_code,200)
        self.login(4);self.assertEqual(len(self.rows()),3)

    def test_cross_site_simple_form_cannot_upload_or_claim(self):
        self.arrival();self.login(2);row=next(row for row in self.rows() if row['kind']=='lots')
        response=self.client.post(f"/activities/api/{row['id']}/photos",data={'revision':'1','label':'Forged','photo':(self.image(),'lotto.png')},content_type='multipart/form-data')
        self.assertEqual(response.status_code,403);self.assertEqual(ActivityPhoto.query.count(),0)
        self.assertEqual(db.session.get(OperationalActivity,row['id']).status,'pending')

    def test_summary_filter_cancel_and_input_validation(self):
        self.arrival();self.login(2);row=self.rows()[0]
        self.assertEqual(self.client.get('/activities/api/summary').json['count'],3)
        self.assertEqual(self.client.get('/activities/api?q=DDT%20123').json['total'],3)
        self.assertEqual(self.client.get('/activities/api?q=missing').json['total'],0)
        self.assertEqual(self.client.get('/activities/api?status=invalid').status_code,400)
        self.assertEqual(self.client.get('/activities/api?page=bad').status_code,400)
        self.login(1);self.assertEqual(self.act(row,'cancel').status_code,400)
        cancelled=self.act(row,'cancel','Arrivo registrato per errore').json['activity']
        self.assertEqual(cancelled['status'],'cancelled');self.assertEqual(self.client.get('/activities/api/summary').json['count'],2)
        body=self.arrival_body();body['event_key']='different-key';body['partial']='yes'
        self.assertEqual(self.client.post('/activities/api/supplier-arrivals',json=body).status_code,400)

    def test_migration_repeat_model_compatibility_and_downgrade(self):
        path=Path(__file__).resolve().parents[1]/'migrations/versions/t5c6d7e8f9a0_operational_activities.py'
        spec=importlib.util.spec_from_file_location('activity_migration',path)
        migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
        engine=create_engine('sqlite://')
        with engine.begin() as conn:
            for name in ['supplier_board_cards','user','roles']:conn.execute(text(f'CREATE TABLE {name} (id INTEGER PRIMARY KEY)'))
            conn.execute(text('CREATE TABLE menus (name TEXT,weight INTEGER,sort_order INTEGER,parent_id INTEGER,route TEXT,is_active BOOLEAN,is_visible BOOLEAN,item_type TEXT)'))
            models=[SupplierArrival,OperationalActivity,ActivityTargetRole,ActivityTargetUser,ActivityEvent,ActivityPhoto]
            db.metadata.create_all(conn,tables=[model.__table__ for model in models])
            with Operations.context(MigrationContext.configure(conn)):
                migration.upgrade();migration.upgrade()
                self.assertEqual(conn.execute(text("SELECT count(*) FROM menus WHERE route='/activities'")).scalar(),1)
                migration.downgrade()
            self.assertNotIn('operational_activities',inspect(conn).get_table_names())

    def test_manual_combined_targets_visibility_claim_and_retry(self):
        body=dict(title='Inventario',description='Contare scaffale A\nContare scaffale B',role_ids=[1,1],user_ids=[4,4],client_key='manual-request-123')
        response=self.client.post('/activities/api',json=body)
        self.assertEqual(response.status_code,201,response.json)
        row=response.json['activity'];self.assertEqual(row['kind'],'manual');self.assertIsNone(row['source'])
        self.assertEqual(row['roles'],['Staff']);self.assertEqual(row['users'][0]['id'],4)
        self.assertEqual(self.client.post('/activities/api',json=body).json['activity']['id'],row['id'])
        self.assertEqual(OperationalActivity.query.count(),1)
        body['title']='Diverso';self.assertEqual(self.client.post('/activities/api',json=body).status_code,409)
        self.login(4);self.assertEqual(len(self.rows()),1)
        claimed=self.act(row,'claim').json['activity'];self.assertEqual(claimed['owner_id'],4)
        self.login(2);self.assertEqual(len(self.rows()),1);self.assertEqual(self.act(claimed,'complete').status_code,403)
        self.login(5);self.assertEqual(self.rows(),[])
        self.login(4);self.assertEqual(self.act(claimed,'complete').json['activity']['status'],'completed')

    def test_manual_users_from_role_and_validation(self):
        response=self.client.get('/activities/api/assignees?role_id=1')
        self.assertEqual({user['id'] for user in response.json['users']},{2,3})
        self.assertEqual(self.client.get('/activities/api/assignees?role_id=1&q=User2').json['total'],1)
        self.assertEqual(self.client.get('/activities/api/assignees?role_id=bad').status_code,400)
        body=dict(title='Pulizia',description='Magazzino',role_ids=[],user_ids=[2],client_key='manual-user-123')
        for changes in [dict(title=''),dict(user_ids=[]),dict(user_ids=[5]),dict(user_ids=[999]),dict(role_ids=[True]),dict(description='a'*5001)]:
            self.assertEqual(self.client.post('/activities/api',json={**body,**changes}).status_code,400)
        row=self.client.post('/activities/api',json=body).json['activity']
        self.assertEqual(self.client.get('/activities/api?q=Magazzino').json['total'],1)
        self.login(3);self.assertEqual(self.rows(),[])
        self.assertEqual(self.client.get(f"/activities/api/{row['id']}").status_code,404)
        self.assertEqual(self.client.get('/activities/api/assignees').status_code,403)
        self.assertEqual(self.client.post('/activities/api',json=body).status_code,403)
        self.login(2);self.assertEqual(len(self.rows()),1)

    def test_manual_migration_existing_rows_and_repeat(self):
        path=Path(__file__).resolve().parents[1]/'migrations/versions/u6d7e8f9a0b1_manual_activities.py'
        spec=importlib.util.spec_from_file_location('manual_migration',path)
        migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
        engine=create_engine('sqlite://')
        with engine.begin() as conn:
            conn.execute(text('CREATE TABLE user (id INTEGER PRIMARY KEY)'))
            conn.execute(text('CREATE TABLE operational_activities (id INTEGER PRIMARY KEY, title VARCHAR(200))'))
            conn.execute(text("INSERT INTO operational_activities(id,title) VALUES(1,'Esistente')"))
            with Operations.context(MigrationContext.configure(conn)):
                migration.upgrade();migration.upgrade()
                self.assertEqual(conn.execute(text('SELECT description FROM operational_activities WHERE id=1')).scalar(),'')
                conn.execute(text("INSERT INTO operational_activities(id,title,client_key) VALUES(2,'Nuova','same-key')"))
                migration.downgrade()
            self.assertNotIn('client_key',{column['name'] for column in inspect(conn).get_columns('operational_activities')})
        engine=create_engine('sqlite://')
        with engine.begin() as conn:
            for name in ['user','supplier_arrivals']: conn.execute(text(f'CREATE TABLE {name} (id INTEGER PRIMARY KEY)'))
            db.metadata.create_all(conn,tables=[OperationalActivity.__table__,ActivityTargetUser.__table__])
            with Operations.context(MigrationContext.configure(conn)):
                migration.upgrade();migration.upgrade();migration.downgrade()
