from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
import json
import os
import threading
import time
import unittest
from unittest.mock import Mock, patch

import fakeredis
from celery import Celery
from celery.app.task import Task
from flask import Flask

from config.celery_app import FlaskContextTask, celery
from tools import celery_runtime as runtime
from tools.celery_contexts import destination, canonical_task
from tools.celery_schedule_settings import default_document
from tools.redis_utils import update_task

ARTICLE = 'config.tasks.import_articoli_task'
STOCK = 'config.tasks.import_giacenze_task'
REGISTRY = 'config.tasks.import_anagrafiche_task'
NOTICE = 'config.tasks.notify_customer_payment_case_task'


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.redis = fakeredis.FakeRedis(decode_responses=True)
        self.mocks = [patch('tools.celery_runtime.get_redis', return_value=self.redis),
                      patch('tools.redis_utils.get_redis', return_value=self.redis),
                      patch.dict(os.environ, {'MATRIX_FILE_IMPORTS_PAUSED':'false', 'CELERY_CONTEXT_QUEUES_ENABLED':'true'}),
                      patch.object(celery, 'flask_app', None)]
        for mock in self.mocks: mock.start()
        self.app = Celery('runtime-test', broker='memory://', backend='cache+memory://')
        self.app.conf.task_default_queue = 'celery'

    def tearDown(self):
        for mock in reversed(self.mocks): mock.stop()

    def job(self, name=ARTICLE, id='one', **options):
        value, reason = runtime.reserve(name, id, **options)
        self.assertIsNone(reason)
        return value

    def stats(self, name=ARTICLE):
        return runtime.runtime_snapshot([name])[canonical_task(name)]

    def task(self, name=ARTICLE):
        class RegisteredTask(FlaskContextTask):
            abstract = False
            def run(self): return {'success': True}
        instance = RegisteredTask(); instance.name = name
        return self.app.register_task(instance)

    def test_destinations_and_legacy_rollout_switch(self):
        self.assertEqual(destination(ARTICLE), 'ld_gestionale')
        self.assertEqual(destination(NOTICE), 'ld_notifiche')
        self.assertEqual(destination('config.tasks.import_poleepo_orders_task'), 'ld_spedizioni')
        self.assertEqual(destination('config.tasks.send_mailing_campaign_task'), 'celery')
        with patch.dict(os.environ, {'CELERY_CONTEXT_QUEUES_ENABLED':'false'}):
            self.assertEqual(destination(ARTICLE), 'celery')

    def test_simultaneous_producers_admit_one_and_count_every_duplicate(self):
        barrier = threading.Barrier(8)
        def enqueue(index):
            barrier.wait()
            return runtime.reserve(ARTICLE, str(index))
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(enqueue, range(8)))
        self.assertEqual(sum(value is not None for value, reason in results), 1)
        self.assertEqual(self.stats()['recent']['skip_queued'], 7)
        self.assertEqual(self.stats()['recent']['attempted'], 8)

    def test_aliases_share_identity_and_running_duplicates_are_skipped(self):
        job = self.job(STOCK)
        self.assertEqual(runtime.reserve('config.tasks.import_giacenze_matrixws_task', 'two')[1], 'skip_queued')
        with runtime.execution(job, 'gestionale'):
            self.assertEqual(runtime.reserve(STOCK, 'three')[1], 'skip_running')
            self.assertEqual(self.stats(STOCK)['states'], ['running'])
        runtime.finish(job, 'completed', 8.25)
        stats = self.stats(STOCK)
        self.assertEqual(stats['recent']['started'], 1)
        self.assertEqual(stats['last_duration'], 8.25)
        self.assertEqual(stats['average_duration'], 8.25)
        self.assertAlmostEqual(stats['skip_percent'], 66.7)
        self.job(STOCK, id='four')

    def test_context_serializes_different_imports_but_notification_can_run(self):
        first = self.job(ARTICLE); second = self.job(REGISTRY)
        notice = self.job(NOTICE, id='notification', args=[12])
        entered = threading.Event()
        def another_import():
            with runtime.execution(second, 'gestionale'): entered.set()
            runtime.finish(second, 'completed', .01)
        with runtime.execution(first, 'gestionale'):
            thread = threading.Thread(target=another_import); thread.start()
            self.assertFalse(entered.wait(.1))
            with runtime.execution(notice, 'notifiche'):
                self.assertFalse(entered.is_set())
            runtime.finish(notice, 'completed', .01)
        thread.join(3); self.assertFalse(thread.is_alive()); self.assertTrue(entered.is_set())
        runtime.finish(first, 'completed', .2)

    def test_notifications_for_different_cases_are_never_deduplicated(self):
        self.job(NOTICE, id='case-one', args=[1])
        self.job(NOTICE, id='case-two', args=[2])
        self.assertEqual(len(self.stats(NOTICE)['states']), 2)

    def test_queue_expiration_is_counted_once_by_reaper_and_revocation(self):
        job = self.job()
        self.redis.hset(job['key'], 'deadline', time.time()-1)
        self.redis.zadd(runtime.DUE_KEY, {job['member']: time.time()-1})
        runtime.reap_expired(); runtime.reap_expired()
        runtime.revoked_task(request=NS(_request_dict={'ld_runtime':job}, id='one'), expired=True)
        self.assertEqual(self.stats()['recent']['expired'], 1)
        self.assertFalse(self.redis.exists(job['key']))
        self.job(id='new')

    def test_expiration_after_long_outage_and_missing_lease_has_a_single_counter(self):
        job = self.job()
        self.redis.delete(job['key'])
        self.redis.zadd(runtime.DUE_KEY, {job['member']:time.time()-1})
        runtime.reap_expired(); runtime.reap_expired()
        self.assertEqual(self.stats()['recent']['expired'], 1)

    def test_renewal_crash_recovery_and_old_owner_cannot_delete_replacement(self):
        job = self.job()
        with runtime.execution(job, 'gestionale'):
            self.redis.eval(runtime.RENEW, 2, job['key'], runtime.CONTEXT_KEY, job['token'], time.time()+100, 180, 1)
            self.assertGreater(float(self.redis.hget(job['key'],'deadline')), time.time()+270)
            self.redis.hset(job['key'],'deadline',time.time()-1)
            member = self.redis.hget(job['key'],'member')
            self.redis.zadd(runtime.DUE_KEY,{member:time.time()-1})
            runtime.reap_expired()
        replacement = self.job(id='replacement')
        self.assertFalse(runtime.finish(job))
        self.assertEqual(self.redis.hget(replacement['key'],'token'), replacement['token'])
        self.assertEqual(self.stats()['recent']['lost_worker'],1)

    def test_retry_moves_reservation_without_old_completion_releasing_it(self):
        old = self.job()
        with runtime.execution(old,'gestionale'):
            new, reason = runtime.reserve(ARTICLE,'one',previous=old['token'],countdown=20)
            self.assertIsNone(reason)
            self.assertFalse(runtime.finish(old,'completed',2))
        self.assertEqual(self.redis.hget(new['key'],'state'),'queued')
        self.assertEqual(self.stats()['recent']['attempted'],1)

    def test_24h_window_pause_exclusion_and_reset_only_cumulative_totals(self):
        job = self.job()
        with runtime.execution(job,'gestionale'): runtime.reserve(ARTICLE,'two')
        runtime.finish(job,'completed',10)
        runtime.record(ARTICLE,'paused')
        self.redis.zadd('celery:runtime:stats:'+ARTICLE+':window',{
            json.dumps(dict(kind='skip_running',time=time.time()-86401,id='old')):time.time()-86401})
        stats=self.stats(); self.assertEqual(stats['recent']['skip_running'],1)
        self.assertEqual(stats['recent']['paused'],1);self.assertEqual(stats['skip_percent'],50)
        runtime.reset_totals(ARTICLE)
        self.assertEqual(self.stats()['total'],{})
        self.assertEqual(self.stats()['recent'],stats['recent'])
        self.assertEqual(self.stats()['last_duration'],10)

    def test_publish_boundary_routes_real_messages_and_skips_without_phantom_monitor(self):
        task=self.task()
        first=task.apply_async(task_id='publish-one')
        duplicate=task.apply_async(task_id='publish-two')
        self.assertEqual(duplicate.result['reason'],'skip_queued')
        update_task(duplicate.id,'Import articoli',0,'in coda...')
        self.assertFalse(self.redis.exists('task_status:'+duplicate.id))
        with self.app.connection() as connection:
            queue=connection.SimpleQueue('ld_gestionale')
            message=queue.get(block=False)
            self.assertEqual(message.headers['id'],first.id)
            self.assertIn('ld_runtime',message.headers);message.ack()
            from queue import Empty
            with self.assertRaises(Empty):queue.get(block=False)
            queue.close()

    def test_publish_failure_rolls_back_and_redis_failure_blocks_admission(self):
        task=self.task()
        with patch.object(Task,'apply_async',side_effect=RuntimeError('publish failed')):
            with self.assertRaises(RuntimeError):task.apply_async(task_id='failed')
        self.assertEqual(self.stats()['recent']['publish_failed'],1)
        self.job(id='retry')
        with patch('tools.celery_runtime.get_redis',side_effect=RuntimeError('redis unavailable')):
            with patch.object(Task,'apply_async') as send:
                with self.assertRaises(RuntimeError):task.apply_async(task_id='blocked')
                send.assert_not_called()

    def test_worker_lifecycle_updates_duration_and_paused_jobs_without_calling_callback(self):
        task=self.task(); job=self.job()
        app=Flask('worker-test')
        task.run=Mock(return_value={'success':True})
        task.push_request(id='one',called_directly=False,headers={'ld_runtime':job})
        try:
            with patch.object(celery,'flask_app',app), patch('tools.celery_schedule_settings.read_document',return_value=default_document()):
                task();task.run.assert_called_once()
            self.assertEqual(self.stats()['recent']['completed'],1)
            self.assertIsNotNone(self.stats()['last_duration'])
        finally:task.pop_request()
        next_job=self.job(id='paused');doc=default_document();doc['schedules']['import-articoli']['enabled']=False
        task.push_request(id='paused',called_directly=False,headers={'ld_runtime':next_job})
        try:
            with patch.object(celery,'flask_app',app),patch('tools.celery_schedule_settings.read_document',return_value=doc):
                result=task();self.assertEqual(result['reason'],'schedule_paused')
            self.assertEqual(self.stats()['recent']['paused'],1)
            self.assertFalse(self.redis.exists(next_job['key']))
        finally:task.pop_request()

    def test_manual_producer_pause_is_not_counted_as_duplicate(self):
        task=self.task();app=Flask('producer-test');doc=default_document();doc['schedules']['import-articoli']['enabled']=False
        with patch.object(celery,'flask_app',app),patch('tools.celery_schedule_settings.read_document',return_value=doc):
            result=task.apply_async(task_id='paused-publish')
        self.assertEqual(result.result['reason'],'schedule_paused')
        self.assertEqual(self.stats()['recent'],{'paused':1})

    def test_datetime_expiry_and_eta_reservation_match_broker_validity(self):
        expires=datetime.now(timezone.utc)+timedelta(minutes=15)
        self.assertEqual(runtime.queue_deadline(expires),expires.timestamp())
        eta=datetime.now(timezone.utc)+timedelta(days=2)
        self.assertGreaterEqual(runtime.queue_deadline(eta=eta),eta.timestamp()+1800)

    def test_legacy_delivery_is_moved_to_context_without_a_premature_result(self):
        from celery.exceptions import Ignore
        task=self.task();app=Flask('transition-test')
        old=self.job();task.run=Mock()
        task.push_request(id='one',called_directly=False,headers={'ld_runtime':old},
                          args=[],kwargs={},delivery_info={'routing_key':'celery'})
        try:
            with patch.object(celery,'flask_app',app),patch('tools.celery_schedule_settings.read_document',return_value=default_document()):
                with self.assertRaises(Ignore):task()
            task.run.assert_not_called()
            self.assertEqual(self.stats()['recent']['attempted'],1)
            self.assertNotEqual(self.redis.hget(old['key'],'token'),old['token'])
            self.assertEqual(self.redis.hget(old['key'],'state'),'queued')
            with self.app.connection() as connection:
                queue=connection.SimpleQueue('ld_gestionale');message=queue.get(block=False)
                self.assertEqual(message.headers['id'],'one');message.ack();queue.close()
        finally:task.pop_request()

    def test_configuration_error_cleans_queued_reservation(self):
        task=self.task();job=self.job();app=Flask('config-failure-test');task.run=Mock()
        task.push_request(id='one',called_directly=False,headers={'ld_runtime':job})
        try:
            with patch.object(celery,'flask_app',app),patch('tools.celery_schedule_settings.read_document',side_effect=RuntimeError('offline')):
                with self.assertRaises(RuntimeError):task()
            task.run.assert_not_called();self.assertFalse(self.redis.exists(job['key']))
            self.assertEqual(self.stats()['recent']['failed'],1)
        finally:task.pop_request()

    def test_worker_ready_marker_matches_pid_and_queue(self):
        sender=NS(hostname='gestionale@test',task_consumer=NS(queues=[NS(name='ld_gestionale')]))
        runtime.worker_started(sender=sender)
        marker=json.loads(self.redis.get('celery:runtime:worker_ready:gestionale@test'))
        self.assertEqual(marker['pid'],os.getpid());self.assertEqual(marker['queues'],['ld_gestionale'])

    def test_activation_check_accepts_current_workers_and_rejects_stale_markers(self):
        from tools import check_celery_workers as check
        values={name:dict(pid=123,queues=[queue]) for name,(service,queue) in check.SERVICES.items()}
        client=Mock();client.get.side_effect=lambda key:json.dumps(values[key.rsplit(':',1)[-1].split('@')[0]])
        with patch.object(check,'load_dotenv'),patch.object(check.redis.Redis,'from_url',return_value=client),\
             patch.object(check.subprocess,'check_output',return_value=b'123'),patch.object(check.socket,'gethostname',return_value='test'),\
             patch('builtins.print'):
            self.assertEqual(check.main(),0)
            values['gestionale']['pid']=100
            with patch.object(check.time,'monotonic',side_effect=[0,1,121]),patch.object(check.time,'sleep'):
                self.assertEqual(check.main(),1)

    def test_partial_item_skip_count_does_not_mark_the_whole_task_skipped(self):
        task=self.task();job=self.job();app=Flask('partial-result-test')
        task.run=Mock(return_value={'success':True,'skipped':2})
        task.push_request(id='one',called_directly=False,headers={'ld_runtime':job})
        try:
            with patch.object(celery,'flask_app',app),patch('tools.celery_schedule_settings.read_document',return_value=default_document()):task()
            self.assertEqual(self.stats()['recent']['completed'],1)
            self.assertNotIn('paused',self.stats()['recent'])
        finally:task.pop_request()

    def test_legacy_lock_skip_is_not_double_counted_in_skip_rate(self):
        task=self.task();job=self.job();app=Flask('legacy-lock-test')
        task.run=Mock(return_value={'success':True,'skipped':True,'reason':'previous_run_active'})
        task.push_request(id='one',called_directly=False,headers={'ld_runtime':job})
        try:
            with patch.object(celery,'flask_app',app),patch('tools.celery_schedule_settings.read_document',return_value=default_document()):task()
            self.assertEqual(self.stats()['recent']['skip_running'],1)
            self.assertEqual(self.stats()['skip_percent'],100)
        finally:task.pop_request()


if __name__=='__main__':unittest.main()
