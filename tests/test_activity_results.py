from io import BytesIO, StringIO
import json
from pathlib import Path
import importlib.util
from unittest.mock import patch
import unittest
from sqlalchemy import create_engine, text, inspect
from alembic.migration import MigrationContext
from alembic.operations import Operations
from extensions import db
from models import (OperationalActivity,ActivityResultNotice,ActivityAttachment,ActivityResultRole,ActivityResultUser,PushSubscription,UserRole,ActivityEvent)
from test_activities import ActivityTests


class ResultTests(unittest.TestCase):
    def setUp(self):
        ActivityTests.setUp(self)
        db.metadata.create_all(db.engine,tables=[PushSubscription.__table__])
    tearDown=ActivityTests.tearDown
    login=ActivityTests.login
    image=ActivityTests.image
    act=ActivityTests.act

    def create(self, **extra):
        body=dict(title='Inventario',role_ids=[],user_ids=[2],client_key='result-request-123',result_recipients=dict(user_ids=[6]))
        body.update(extra)
        result=self.client.post('/activities/api',json=body)
        self.assertEqual(result.status_code,201,result.json)
        return result.json['activity']

    def complete(self,row):
        self.login(2)
        with patch('tools.activity_results.enqueue_results') as enqueue:
            response=self.act(row,'complete','Scaffale verificato')
            self.assertEqual(response.status_code,200,response.json)
            enqueue.assert_called_once()
        return response.json['activity']

    def test_event_recipients_read_only_and_unrelated_user_private(self):
        row=self.create()
        self.login(6)
        self.assertEqual(self.client.get(f"/activities/api/{row['id']}").status_code,200)
        self.assertEqual(self.client.get('/activities/api/results').json['count'],1)
        completed=self.complete(row)
        self.login(6)
        detail=self.client.get(f"/activities/api/{row['id']}").json['activity']
        self.assertFalse(detail['can_act']);self.assertFalse(detail['can_manage'])
        self.assertEqual(self.act(completed,'reopen','Nuova verifica').status_code,404)
        results=self.client.get('/activities/api/results').json
        self.assertEqual(results['count'],2);self.assertEqual(results['rows'][0]['note'],'Scaffale verificato')
        self.assertEqual(self.client.get('/activities/api/summary').json['results']['count'],2)
        notice=results['rows'][0]['id'];self.login(3)
        self.assertEqual(self.client.post(f'/activities/api/results/{notice}/read').status_code,404)
        self.assertEqual(self.client.get(f"/activities/api/{row['id']}").status_code,404)
        self.login(6);self.assertEqual(self.client.post(f'/activities/api/results/{notice}/read').status_code,200)
        self.assertEqual(self.client.get('/activities/api/results').json['count'],1)
        self.assertEqual(self.client.get(f"/activities/api/{row['id']}").status_code,200)

    def test_combined_targets_deduplicated_expired_roles_excluded_and_cycles(self):
        row=self.create(result_recipients=dict(role_ids=[1],user_ids=[6,2],target_min_weight=50))
        done=self.complete(row)
        self.assertEqual({n.user_id for n in ActivityResultNotice.query.all()},{1,2,3,6,7,8})
        self.assertEqual(ActivityResultNotice.query.count(),12)
        self.assertEqual(self.act(done,'complete').status_code,400)
        self.login(1);reopened=self.act(done,'reopen','Ripetere').json['activity']
        self.login(6);self.assertEqual(self.client.get(f"/activities/api/{row['id']}").status_code,200)
        self.assertEqual(self.client.get('/activities/api/results').json['count'],3)
        self.complete(reopened);self.assertEqual(ActivityResultNotice.query.count(),24)
        self.login(6);self.assertEqual(self.client.get('/activities/api/results').json['count'],4)

    def test_result_exact_role_not_same_or_higher_weight(self):
        row=self.create(result_recipients=dict(role_ids=[2]))
        self.complete(row)
        self.assertEqual({n.user_id for n in ActivityResultNotice.query.all()},{2,6})

    def test_required_validated_and_replay_includes_result_targets(self):
        row=self.create()
        body=dict(title='Inventario',role_ids=[],user_ids=[2],client_key='result-request-123',result_recipients=dict(user_ids=[6]))
        self.assertTrue(self.client.post('/activities/api',json=body).json['replayed'])
        self.assertEqual(self.client.post('/activities/api',json={**body,'result_recipients':dict(role_ids=[2])}).status_code,409)
        for recipients in [None,{},dict(user_ids=[5]),dict(role_ids=[999]),dict(target_min_weight=True),dict(user_ids=['2'])]:
            response=self.client.post('/activities/api',json={**body,'client_key':'validation-request','result_recipients':recipients})
            self.assertEqual(response.status_code,400,response.json)

    def multipart(self, body, raw=None, filename='foto.png', header=True):
        return self.client.post('/activities/api',data=dict(data=json.dumps(body),files=(raw or self.image(),filename)),headers={'X-Requested-With':'XMLHttpRequest'} if header else {})

    def test_creation_files_atomic_retry_validation_and_access(self):
        body=dict(title='Inventario',user_ids=[2],client_key='files-request-123',result_recipients=dict(user_ids=[6]))
        self.assertEqual(self.multipart(body,header=False).status_code,403)
        bad=self.multipart(body,BytesIO(b'fake pdf'),'test.pdf');self.assertEqual(bad.status_code,400)
        self.assertEqual(OperationalActivity.query.count(),0)
        response=self.multipart(body);self.assertEqual(response.status_code,201,response.json)
        row=response.json['activity'];file=row['attachments'][0]
        self.assertEqual(file['purpose'],'instructions')
        self.assertEqual(self.multipart(body).status_code,200);self.assertEqual(ActivityAttachment.query.count(),1)
        self.assertEqual(self.multipart(body,filename='renamed.png').status_code,409)
        self.login(6);self.assertEqual(self.client.get(file['url']).status_code,200)
        self.login(2);download=self.client.get(file['url']);self.assertEqual(download.status_code,200)
        self.assertIn('attachment',download.headers['Content-Disposition']);self.assertIn('no-store',download.headers['Cache-Control'])
        done=self.complete(row);self.login(6);self.assertEqual(self.client.get(file['url']).status_code,200)
        self.assertEqual(self.client.delete(file['url'],json=dict(revision=done['revision'])).status_code,404)

    def test_result_upload_owner_revision_and_historical_immutability(self):
        row=self.create();self.login(2)
        def upload(revision):
            return self.client.post(f"/activities/api/{row['id']}/attachments",data=dict(revision=str(revision),files=(self.image(),'esito.png')),headers={'X-Requested-With':'XMLHttpRequest'})
        response=upload(1);self.assertEqual(response.status_code,201,response.json)
        updated=response.json['activity'];self.assertEqual(upload(1).status_code,409)
        file=updated['attachments'][0];self.assertEqual(file['purpose'],'result')
        done=self.complete(updated);self.login(1)
        self.assertEqual(self.client.delete(file['url'],json=dict(revision=done['revision'])).status_code,400)
        reopened=self.act(done,'reopen','Rivedere').json['activity']
        self.assertEqual(self.client.delete(file['url'],json=dict(revision=reopened['revision'])).status_code,400)

    def test_push_deferred_without_config_failure_retry_and_dedup(self):
        from tools.activity_results import dispatch_results
        row=self.create();self.complete(row)
        with patch('tools.push_notifications.is_push_configured',return_value=False):
            self.assertTrue(dispatch_results()['skipped'])
        pending=ActivityResultNotice.query.join(ActivityEvent).filter(ActivityEvent.action=='complete',ActivityResultNotice.user_id==6).one()
        for notice in ActivityResultNotice.query.all():
            if notice.id!=pending.id: notice.push_sent_at=__import__('datetime').datetime.utcnow()
        db.session.commit()
        self.assertIsNone(pending.push_sent_at)
        with patch('tools.push_notifications.is_push_configured',return_value=True), patch('tools.push_notifications.send_push_to_subscriptions',side_effect=[dict(sent=0,failed=1),dict(sent=1,failed=0)]) as send:
            self.assertFalse(dispatch_results()['success']);self.assertIsNone(pending.push_sent_at)
            self.assertTrue(dispatch_results()['success']);self.assertIsNotNone(pending.push_sent_at)
            dispatch_results();self.assertEqual(send.call_count,2)
            self.assertEqual(send.call_args.args[1]['url'],f"/activities?activity={row['id']}")
            self.assertFalse(send.call_args.kwargs['commit'])

    def test_migration_repeat_existing_data_create_all_and_downgrade(self):
        path=Path('migrations/versions/x9a0b1c2d3e4_activity_results_files.py')
        spec=importlib.util.spec_from_file_location('result_migration',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with create_engine('sqlite://').begin() as connection:
            for name in ['user','roles','activity_events']: connection.execute(text(f'CREATE TABLE {name} (id INTEGER PRIMARY KEY)'))
            connection.execute(text('CREATE TABLE operational_activities (id INTEGER PRIMARY KEY,title TEXT)'))
            connection.execute(text("INSERT INTO operational_activities VALUES (1,'Preesistente')"))
            with Operations.context(MigrationContext.configure(connection)):
                module.upgrade();module.upgrade()
                self.assertEqual(connection.execute(text('SELECT title,result_min_weight FROM operational_activities')).one(),('Preesistente',None))
                module.downgrade()
            self.assertNotIn('activity_attachments',inspect(connection).get_table_names())
        with db.engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)): module.upgrade();module.upgrade()
        output=StringIO()
        with Operations.context(MigrationContext.configure(dialect_name='postgresql',opts=dict(as_sql=True,output_buffer=output))): module.upgrade()
        self.assertIn('uq_activity_result_event_user',output.getvalue())

    def test_enqueue_failure_keeps_durable_result_and_cancellation_esito(self):
        row=self.create();self.login(1)
        with patch('tools.activity_results.enqueue_results',side_effect=RuntimeError('broker offline')):
            response=self.act(row,'cancel','Richiesta superata')
        self.assertEqual(response.status_code,200,response.json)
        notice=ActivityResultNotice.query.join(ActivityEvent).filter(ActivityEvent.action=='cancel',ActivityResultNotice.user_id==6).one();self.assertIsNone(notice.push_sent_at)
        self.login(6);data=self.client.get('/activities/api/results').json
        self.assertEqual(data['rows'][0]['status'],'cancelled');self.assertEqual(data['rows'][0]['note'],'Richiesta superata')

    def test_result_files_other_owner_cannot_upload_and_current_cycle_remove(self):
        row=self.create(user_ids=[2,3]);self.login(2)
        claimed=self.act(row,'claim').json['activity'];self.login(3)
        url=f"/activities/api/{row['id']}/attachments"
        def upload():return self.client.post(url,data=dict(revision=str(claimed['revision']),files=(self.image(),'esito.png')),headers={'X-Requested-With':'XMLHttpRequest'})
        self.assertEqual(upload().status_code,403)
        self.login(2);uploaded=upload();self.assertEqual(uploaded.status_code,201,uploaded.json)
        current=uploaded.json['activity'];file=current['attachments'][0]
        removed=self.client.delete(file['url'],json=dict(revision=current['revision']))
        self.assertEqual(removed.status_code,200);self.assertEqual(removed.json['activity']['attachments'],[])
        self.assertEqual(self.client.get(file['url']).status_code,404)
