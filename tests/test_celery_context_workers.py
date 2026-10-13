"""Two real Celery solo consumers, isolated memory queues and fake Redis."""
import os
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

import fakeredis
from celery import Celery
from celery.contrib.testing.worker import start_worker
from flask import Flask

from config.celery_app import FlaskContextTask, celery
from tools.celery_contexts import QUEUES
from tools.celery_schedule_settings import default_document


class ContextWorkerTests(unittest.TestCase):
    def test_notification_finishes_while_import_is_running(self):
        app=Celery('contexts-integration',broker='memory://',backend='cache+memory://')
        app.conf.update(worker_prefetch_multiplier=1,broker_connection_retry_on_startup=True)
        r=fakeredis.FakeRedis(decode_responses=True)
        started=threading.Event();release=threading.Event();notified=threading.Event()
        class ImportTask(FlaskContextTask):
            name='config.tasks.import_articoli_task';abstract=False
            def run(self):
                started.set()
                if not release.wait(10):raise RuntimeError('test import timeout')
                return {'success':True}
        class NoticeTask(FlaskContextTask):
            name='config.tasks.notify_customer_payment_case_task';abstract=False
            def run(self):notified.set();return {'success':True}
        import_task=app.register_task(ImportTask());notice_task=app.register_task(NoticeTask())
        suffix=uuid4().hex
        queues={'gestionale':'gestion-test-'+suffix,'notifiche':'notice-test-'+suffix}
        with patch.dict(os.environ,{'CELERY_CONTEXT_QUEUES_ENABLED':'true','MATRIX_FILE_IMPORTS_PAUSED':'false'}),\
             patch.dict(QUEUES,queues),patch('tools.celery_runtime.get_redis',return_value=r),\
             patch('tools.redis_utils.get_redis',return_value=r),patch.object(celery,'flask_app',Flask('context-worker-test')),\
             patch('tools.celery_schedule_settings.read_document',return_value=default_document()):
            with start_worker(app,queues=[queues['gestionale']],pool='solo',perform_ping_check=False),\
                 start_worker(app,queues=[queues['notifiche']],pool='solo',perform_ping_check=False):
                try:
                    import_result=import_task.apply_async()
                    self.assertTrue(started.wait(5),'real import worker did not start')
                    duplicate=import_task.apply_async()
                    self.assertEqual(duplicate.result['reason'],'skip_running')
                    notice_result=notice_task.apply_async()
                    self.assertTrue(notified.wait(5),'notification waited for import')
                    self.assertFalse(release.is_set())
                    self.assertTrue(notice_result.get(timeout=5,disable_sync_subtasks=False)['success'])
                    release.set()
                    self.assertTrue(import_result.get(timeout=5,disable_sync_subtasks=False)['success'])
                finally:release.set()


if __name__=='__main__':unittest.main()
