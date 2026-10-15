from io import BytesIO,StringIO
from pathlib import Path
import importlib.util,json,unittest
from unittest.mock import patch
from sqlalchemy import create_engine,text,inspect
from alembic.migration import MigrationContext
from alembic.operations import Operations
from extensions import db
from models import OperationalActivity,ActivityResultNotice,ActivityAttachment,ActivityEvent
import test_activities as base


class TreeTests(unittest.TestCase):
    setUp=base.ActivityTests.setUp
    tearDown=base.ActivityTests.tearDown
    login=base.ActivityTests.login
    image=base.ActivityTests.image
    act=base.ActivityTests.act

    def create(self,title='Reso Roviano',**extra):
        body=dict(title=title,user_ids=[2,6],result_recipients=dict(user_ids=[9]),client_key='request-'+title.replace(' ','-'))
        body.update(extra);response=self.client.post('/activities/api',json=body)
        self.assertIn(response.status_code,[200,201],response.json)
        return response.json['activity']

    def child(self,parent,title,**extra):
        return self.create(title,parent_id=parent['id'],parent_revision=parent['revision'],user_ids=[4],**extra)

    def detail(self,row):return self.client.get(f"/activities/api/{row['id']}")

    def complete(self,row):
        with patch('tools.activity_results.enqueue_results'):
            response=self.act(row,'complete','Conteggio verificato')
        self.assertEqual(response.status_code,200,response.json)
        return response.json['activity']

    def edit_body(self,row,**extra):
        body=dict(title=row['title'],description=row['description'],revision=row['revision'],role_ids=row['role_ids'],user_ids=[u['id'] for u in row['users']],target_min_weight=row['target_min_weight'],result_recipients=dict(role_ids=row['result_recipients']['role_ids'],user_ids=[u['id'] for u in row['result_recipients']['users']],target_min_weight=row['result_recipients']['target_min_weight']))
        body.update(extra);return body

    def test_two_children_block_parent_then_allow_complete_and_pin_in_tree(self):
        parent=self.create();self.login(2)
        a=self.child(parent,'Reconta merce');parent=self.detail(parent).json['activity']
        b=self.child(parent,'Reconta sacche');parent=self.detail(parent).json['activity']
        self.assertEqual(self.act(parent,'complete').status_code,400)
        self.login(4);self.complete(a)
        self.login(2);parent=self.detail(parent).json['activity'];self.assertEqual(parent['blocked_children'],1)
        self.assertEqual(len(parent['children']),2)
        rows=self.client.get('/activities/api?status=active').json['rows']
        self.assertEqual({r['id'] for r in rows},{parent['id'],a['id'],b['id']})
        self.assertEqual(next(r for r in rows if r['id']==a['id'])['status'],'completed')
        self.login(4);self.complete(b);self.login(2);self.complete(self.detail(parent).json['activity'])
        archived=self.client.get('/activities/api?status=completed').json
        self.assertEqual(archived['total'],1);self.assertEqual(len(archived['rows']),3)

    def test_child_private_upward_and_parent_can_follow_and_receives_result(self):
        parent=self.create();child=self.child(parent,'Privata figlia')
        self.login(4);self.assertEqual(self.detail(parent).status_code,404)
        self.assertFalse(self.detail(child).json['activity']['parent_visible'])
        self.complete(child)
        self.assertEqual({n.user_id for n in ActivityResultNotice.query.filter_by(activity_id=child['id']).all()},{2,6,9})
        self.login(6);self.assertEqual(self.detail(child).status_code,200)
        self.assertTrue(self.detail(child).json['activity']['can_edit'])
        self.login(3);self.assertEqual(self.detail(child).status_code,404)

    def test_share_only_selected_files_snapshot_survives_source_delete(self):
        parent=self.create();self.login(2)
        response=self.client.post(f"/activities/api/{parent['id']}/attachments",data=dict(revision='1',files=[(self.image(),'uno.png'),(self.image(),'due.png')]),headers={'X-Requested-With':'XMLHttpRequest'})
        parent=response.json['activity'];first=parent['attachments'][0]
        child=self.child(parent,'Con allegato',share_attachment_ids=[first['id']])
        self.assertEqual([f['filename'] for f in child['attachments']],['uno.png'])
        parent=self.detail(parent).json['activity']
        self.assertEqual(self.client.delete(first['url'],json=dict(revision=parent['revision'])).status_code,200)
        self.login(4);self.assertEqual(self.client.get(child['attachments'][0]['url']).status_code,200)
        self.assertEqual(self.client.get(parent['attachments'][1]['url']).status_code,404)

    def test_shared_foreign_files_rejected_and_revision_retry_idempotent(self):
        parent=self.create();self.login(2)
        payload=dict(title='Figlia',user_ids=[4],result_recipients=dict(user_ids=[9]),client_key='child-retry-key',parent_id=parent['id'],parent_revision=1,share_attachment_ids=[999])
        self.assertEqual(self.client.post('/activities/api',json=payload).status_code,400)
        payload['share_attachment_ids']=[]
        self.assertEqual(self.client.post('/activities/api',json=payload).status_code,201)
        self.assertEqual(self.client.post('/activities/api',json=payload).status_code,200)
        self.assertEqual(OperationalActivity.query.count(),2)
        payload.update(client_key='different-child-key')
        self.assertEqual(self.client.post('/activities/api',json=payload).status_code,409)

    def test_staff_can_create_subactivity_but_not_root_and_cannot_modify_fields(self):
        parent=self.create();self.login(2)
        self.assertEqual(self.client.get('/activities/api/assignees?parent_id='+str(parent['id'])).status_code,200)
        child=self.child(parent,'Staff delega')
        self.assertEqual(self.client.post('/activities/api',json=dict(title='Root',user_ids=[2],result_recipients=dict(user_ids=[2]),client_key='staff-root-key')).status_code,403)
        self.assertEqual(self.client.put(f"/activities/api/{child['id']}",json=self.edit_body(child,title='Nuovo')).status_code,403)

    def test_edit_open_fields_targets_and_revision_audit(self):
        row=self.create();self.login(6)
        response=self.client.put(f"/activities/api/{row['id']}",json=self.edit_body(row,title='Reso corretto',description='Verificare dettagli',user_ids=[6],result_recipients=dict(role_ids=[2],target_min_weight=50)))
        self.assertEqual(response.status_code,200,response.json)
        changed=response.json['activity'];self.assertEqual(changed['title'],'Reso corretto')
        self.assertEqual(changed['users'][0]['id'],6);self.assertEqual(changed['result_recipients']['target_min_weight'],50)
        self.assertEqual(OperationalActivity.query.count(),1)
        self.assertEqual(changed['events'][-1]['action'],'updated');self.assertIn('Reso Roviano',changed['events'][-1]['note'])
        self.assertEqual(self.client.put(f"/activities/api/{row['id']}",json=self.edit_body(row,title='Stale')).status_code,409)
        self.login(2);self.assertEqual(self.detail(row).status_code,404)

    def test_edit_completed_notifies_old_and_new_recipients_without_reopen(self):
        row=self.create();self.login(2);row=self.complete(row);self.login(6)
        with patch('tools.activity_results.enqueue_results') as enqueue:
            response=self.client.put(f"/activities/api/{row['id']}",json=self.edit_body(row,title='Reso corretto dopo chiusura',result_recipients=dict(user_ids=[8])))
        self.assertEqual(response.status_code,200,response.json);enqueue.assert_called_once()
        changed=response.json['activity'];self.assertEqual(changed['status'],'completed')
        event=ActivityEvent.query.order_by(ActivityEvent.id.desc()).first()
        self.assertEqual({n.user_id for n in ActivityResultNotice.query.filter_by(event_id=event.id)},{8,9})
        self.login(9);self.assertEqual(self.client.get('/activities/api/results').json['rows'][0]['action'],'updated')
        self.assertFalse(self.detail(changed).json['activity']['can_edit'])
        self.assertEqual(self.client.put(f"/activities/api/{changed['id']}",json=self.edit_body(changed,title='Forbidden')).status_code,403)

    def test_no_new_children_or_reopened_child_under_closed_parent(self):
        parent=self.create();child=self.child(parent,'Da finire')
        self.login(4);child=self.complete(child);self.login(6);parent=self.complete(self.detail(parent).json['activity'])
        self.assertEqual(self.act(child,'reopen','Rifare').status_code,400)
        body=dict(title='Tardiva',user_ids=[4],result_recipients=dict(user_ids=[2]),client_key='late-child-key',parent_id=parent['id'],parent_revision=parent['revision'])
        self.assertEqual(self.client.post('/activities/api',json=body).status_code,400)
        parent=self.act(parent,'reopen','Riaprire reso').json['activity']
        self.assertEqual(self.act(child,'reopen','Rifare').status_code,200)
        self.assertEqual(self.act(parent,'complete').status_code,400)

    def test_migration_existing_create_all_repeat_and_downgrade(self):
        path=Path('migrations/versions/y0b1c2d3e4f5_activity_tree.py')
        spec=importlib.util.spec_from_file_location('tree_migration',path);migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
        with create_engine('sqlite://').begin() as connection:
            connection.execute(text('CREATE TABLE operational_activities (id INTEGER PRIMARY KEY,title TEXT)'))
            connection.execute(text("INSERT INTO operational_activities VALUES(1,'Esistente')"))
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade();migration.upgrade()
                self.assertEqual(connection.execute(text('SELECT title,parent_id FROM operational_activities')).one(),('Esistente',None))
                migration.downgrade()
            self.assertNotIn('parent_id',{c['name'] for c in inspect(connection).get_columns('operational_activities')})
        with db.engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)): migration.upgrade();migration.upgrade();migration.downgrade();migration.upgrade()
        output=StringIO()
        with Operations.context(MigrationContext.configure(dialect_name='postgresql',opts=dict(as_sql=True,output_buffer=output))):migration.upgrade()
        self.assertIn('fk_activity_parent',output.getvalue())

    def test_nested_subactivities_and_depth_limit(self):
        parent=self.create();original=parent
        for depth in range(1,8): parent=self.child(parent,'Livello '+str(depth))
        body=dict(title='Troppo profonda',user_ids=[4],result_recipients=dict(user_ids=[2]),client_key='too-deep-request',parent_id=parent['id'],parent_revision=parent['revision'])
        self.assertEqual(self.client.post('/activities/api',json=body).status_code,400)
        self.login(6)
        self.assertEqual(self.detail(parent).status_code,200)
        self.assertEqual(self.act(self.detail(original).json['activity'],'complete').status_code,400)
        self.assertEqual(self.client.get('/activities/api?status=active').json['total'],1)

    def test_tree_pagination_does_not_split_children_and_edit_noop_no_notice(self):
        from models import ActivityTargetUser
        root=self.create();child=self.child(root,'Figlia inclusa')
        for i in range(31):
            item=OperationalActivity(title='Root '+str(i),kind='manual');item.user_targets=[ActivityTargetUser(user_id=6)];db.session.add(item)
        db.session.commit();self.login(6)
        first=self.client.get('/activities/api?page=1').json;second=self.client.get('/activities/api?page=2').json
        self.assertEqual(first['total'],32);self.assertEqual(first['pages'],2)
        self.assertIn(child['id'],{r['id'] for r in first['rows']})
        self.assertFalse({r['id'] for r in first['rows']} & {r['id'] for r in second['rows']})
        row=self.detail(root).json['activity'];events=len(row['events'])
        response=self.client.put(f"/activities/api/{row['id']}",json=self.edit_body(row))
        self.assertEqual(response.status_code,200);self.assertEqual(len(response.json['activity']['events']),events)

    def test_parent_office_can_delegate_an_additional_level(self):
        parent=self.create();child=self.child(parent,'Prima delega');self.login(6)
        self.assertTrue(self.detail(child).json['activity']['can_create_child'])
        nested=self.child(child,'Ulteriore verifica')
        self.assertEqual(nested['parent_id'],child['id'])
