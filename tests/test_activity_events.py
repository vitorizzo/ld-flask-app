"""Activity lifecycle notifications: audience, atomicity, replay and dispatch."""
from datetime import datetime
from unittest.mock import patch
import unittest
from extensions import db
from models import ActivityEvent,ActivityResultNotice,PushSubscription
import test_activities as base
import test_activity_tree as tree


class EventTests(unittest.TestCase):
    setUp=base.ActivityTests.setUp
    tearDown=base.ActivityTests.tearDown
    login=base.ActivityTests.login
    act=base.ActivityTests.act
    image=base.ActivityTests.image
    create=tree.TreeTests.create
    child=tree.TreeTests.child
    detail=tree.TreeTests.detail
    complete=tree.TreeTests.complete
    edit_body=tree.TreeTests.edit_body
    arrival=base.ActivityTests.arrival
    arrival_body=base.ActivityTests.arrival_body
    upload=base.ActivityTests.upload
    rows=base.ActivityTests.rows

    def notices(self,action):
        return ActivityResultNotice.query.join(ActivityEvent).filter(ActivityEvent.action==action).all()

    def test_creation_claim_release_completion_notify_both_audiences(self):
        with patch('tools.activity_results.enqueue_results') as enqueue:
            row=self.create(user_ids=[2],result_recipients=dict(user_ids=[6]))
            enqueue.assert_called_once()
        self.assertEqual({n.user_id for n in self.notices('created')},{2,6})
        self.login(2)
        row=self.act(row,'claim').json['activity']
        row=self.act(row,'release','Attendo materiale').json['activity']
        row=self.complete(row)
        for action in ['claim','release','complete']:
            self.assertEqual({n.user_id for n in self.notices(action)},{2,6})
        self.login(6)
        data=self.client.get('/activities/api/results').json
        self.assertEqual(data['count'],4)
        claim=next(n for n in data['rows'] if n['action']=='claim')
        self.assertIn('Presa in carico',claim['message']);self.assertIn('User2 Test',claim['message'])
        self.assertIn('Conteggio verificato',data['rows'][0]['message'])
        self.assertFalse(self.detail(row).json['activity']['can_act'])

    def test_replay_conflict_failed_upload_and_read_do_not_emit(self):
        with patch('tools.activity_results.enqueue_results') as enqueue:
            row=self.create(user_ids=[2]);self.assertEqual(enqueue.call_count,1)
            self.create(user_ids=[2]);self.assertEqual(enqueue.call_count,1)
            count=ActivityResultNotice.query.count()
            self.login(2);current=self.act(row,'claim').json['activity']
            self.assertEqual(enqueue.call_count,2)
            self.assertEqual(self.act(row,'release').status_code,409)
            self.assertEqual(enqueue.call_count,2)
            failed=self.client.post(f"/activities/api/{row['id']}/attachments",data=dict(revision=str(current['revision'])),headers={'X-Requested-With':'XMLHttpRequest'})
            self.assertEqual(failed.status_code,400)
            self.assertEqual(ActivityResultNotice.query.count(),count+2)
            notice=self.client.get('/activities/api/results').json['rows'][0]
            self.client.post(f"/activities/api/results/{notice['id']}/read")
            self.assertEqual(enqueue.call_count,2)

    def test_attachment_photo_and_supplier_creation_events(self):
        row=self.create(user_ids=[2]);self.login(2)
        uploaded=self.client.post(f"/activities/api/{row['id']}/attachments",data=dict(revision=str(row['revision']),files=(self.image(),'esito.png')),headers={'X-Requested-With':'XMLHttpRequest'})
        self.assertEqual(uploaded.status_code,201)
        row=uploaded.json['activity'];file=row['attachments'][0]
        self.assertEqual(self.client.delete(file['url'],json=dict(revision=row['revision'])).status_code,200)
        self.assertEqual({n.user_id for n in self.notices('files_added')},{2,9})
        self.assertEqual({n.user_id for n in self.notices('file_removed')},{2,9})
        self.login(1);self.arrival()
        lots=next(r for r in self.rows() if r['kind']=='lots')
        self.assertEqual({n.user_id for n in self.notices('created') if n.activity_id==lots['id']},{2,3})
        self.login(2);photo=self.upload(lots).json['activity']
        self.assertEqual({n.user_id for n in self.notices('photo_added')},{2,3})
        self.assertEqual(self.client.delete(photo['photos'][0]['url'],json=dict(revision=photo['revision'])).status_code,200)
        self.assertEqual({n.user_id for n in self.notices('photo_removed')},{2,3})
        current=self.detail(lots).json['activity']
        self.assertEqual(self.act(current,'not_required','Lotti non necessari').status_code,200)
        self.assertEqual({n.user_id for n in self.notices('not_required')},{2,3})
        self.login(1);current=self.detail(row).json['activity']
        self.assertEqual(self.act(current,'cancel','Annullamento richiesto').status_code,200)
        self.assertEqual({n.user_id for n in self.notices('cancel')},{2,9})

    def test_update_notifies_previous_and_new_audience_and_noop_does_not(self):
        row=self.create(user_ids=[2],result_recipients=dict(user_ids=[6]))
        body=self.edit_body(row,user_ids=[4],result_recipients=dict(user_ids=[8]))
        result=self.client.put(f"/activities/api/{row['id']}",json=body)
        self.assertEqual(result.status_code,200)
        self.assertEqual({n.user_id for n in self.notices('updated')},{2,4,6,8})
        count=ActivityResultNotice.query.count();new=result.json['activity']
        self.client.put(f"/activities/api/{row['id']}",json=self.edit_body(new))
        self.assertEqual(ActivityResultNotice.query.count(),count)
        self.login(2);self.assertFalse(self.detail(row).json['activity']['can_act'])

    def test_reopening_keeps_older_notices_without_access_to_new_cycle(self):
        row=self.complete(self.create(user_ids=[2],result_recipients=dict(user_ids=[6])))
        self.login(1)
        row=self.client.put(f"/activities/api/{row['id']}",json=self.edit_body(row,result_recipients=dict(user_ids=[8]))).json['activity']
        row=self.act(row,'reopen','Altra verifica').json['activity']
        self.login(6)
        notices=self.client.get('/activities/api/results').json
        self.assertEqual(notices['count'],3)
        self.assertTrue(all(not n['can_open'] for n in notices['rows']))
        self.assertEqual(self.detail(row).status_code,404)
        self.assertEqual(self.client.post(f"/activities/api/results/{notices['rows'][0]['id']}/read").status_code,200)
        db.metadata.create_all(db.engine,tables=[PushSubscription.__table__])
        from tools.activity_results import dispatch_results
        with patch('tools.push_notifications.is_push_configured',return_value=True),patch('tools.push_notifications.send_push_to_subscriptions',return_value=dict(sent=1,failed=0)) as send:
            dispatch_results()
        actions=[call.args[1]['title'] for call in send.call_args_list]
        self.assertIn('Attività creata',actions);self.assertIn('Attività completata',actions);self.assertIn('Attività riaperta',actions)
        self.assertEqual(ActivityResultNotice.query.filter_by(push_sent_at=None).count(),0)

    def test_subactivity_events_inform_parent_assignees(self):
        parent=self.create(user_ids=[2],result_recipients=dict(user_ids=[6]))
        child=self.child(parent,'Riconta',result_recipients=dict(user_ids=[8]))
        self.assertEqual({n.user_id for n in self.notices('child_created')},{2,6})
        self.assertEqual({n.user_id for n in self.notices('linked')},{2,4,8})
        self.login(4);self.act(child,'claim')
        self.assertEqual({n.user_id for n in self.notices('claim')},{2,4,8})

    def test_notice_rollback_does_not_leave_orphan_events(self):
        from tools.activities import add_event
        row=self.create();before=ActivityResultNotice.query.count()
        record=db.session.get(__import__('models').OperationalActivity,row['id'])
        add_event(record,db.session.get(__import__('models').User,1),'updated','Rollback example')
        db.session.flush();db.session.rollback()
        self.assertEqual(ActivityResultNotice.query.count(),before)
        self.assertEqual(ActivityEvent.query.filter_by(note='Rollback example').count(),0)
