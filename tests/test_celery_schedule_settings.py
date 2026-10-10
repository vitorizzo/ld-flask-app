from copy import deepcopy
from datetime import datetime, timedelta, timezone
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import os
import unittest
from unittest.mock import patch, Mock

from celery import Celery
from flask import Flask, jsonify
from flask_login import LoginManager
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.exc import SQLAlchemyError

from extensions import db
from models import AppPreference
from routes.settings import settings_bp
from tools.celery_schedule_settings import (
    catalog, default_document, effective_schedule, pause_reason, read_document,
    update_document, validate_frequency, PREFERENCE_KEY,
)
from tools.import_pause import PAUSE_ENV
from tools.celery_scheduler import PreferenceScheduler


@compiles(JSONB, 'sqlite')
def compile_jsonb_sqlite(type_, compiler, **kwargs):
    return 'JSON'


class CelerySettingsTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY='test', SQLALCHEMY_DATABASE_URI='sqlite://')
        db.init_app(self.app)
        self.app.register_blueprint(settings_bp)
        self.ctx = self.app.app_context(); self.ctx.push()
        db.metadata.create_all(db.engine, tables=[AppPreference.__table__])
        self.user = NS(id=12, is_authenticated=True, is_active=True, is_anonymous=False,
                       max_role_weight=999, active_roles=[NS(name='dev', weight=999)])
        LoginManager(self.app).user_loader(lambda _: self.user)
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session['_user_id'] = '12'
        self.mocks = [patch('tools.role_required.get_current_user', return_value=self.user),
                      patch('tools.celery_schedule_settings.beat_status', return_value=None),
                      patch.dict(os.environ, {PAUSE_ENV: 'false'})]
        for mock in self.mocks: mock.start()

    def tearDown(self):
        for mock in reversed(self.mocks): mock.stop()
        db.session.remove(); self.ctx.pop()

    def mutate(self, name='import-articoli', action='pause', revision=None, **kw):
        if revision is None: revision = read_document()['revision']
        return self.client.post('/settings/celery-tasks/' + name, json=dict(action=action, revision=revision, **kw))

    def test_existing_defaults_and_paused_environment_preserved(self):
        self.assertEqual(len(self.client.get('/settings/celery-tasks/data').json['tasks']), 13)
        with patch.dict(os.environ, {PAUSE_ENV: 'true'}):
            doc = read_document()
            self.assertEqual(len(effective_schedule(doc)), 8)
            self.assertEqual(pause_reason('config.tasks.import_giacenze_matrixws_task', doc), 'schedule_paused')
            response = self.mutate(name='support-mailbox-sync', action='frequency', frequency=dict(kind='interval', seconds=600))
            self.assertEqual(response.status_code, 200, response.json)
        saved = read_document()
        self.assertFalse(saved['schedules']['import-articoli']['enabled'])
        self.assertTrue(saved['imports_paused'])
        self.assertEqual(AppPreference.query.count(), 1)

    def test_play_pause_delete_restore_persist_and_do_not_touch_other_tasks(self):
        original = deepcopy(read_document()['schedules']['poleepo-import-orders'])
        for action in ['pause', 'play', 'delete']:
            self.assertEqual(self.mutate(action=action).status_code, 200)
        self.assertNotIn('import-articoli', effective_schedule(read_document()))
        self.assertEqual(self.mutate(action='play').status_code, 400)
        self.assertEqual(self.mutate(action='restore').status_code, 200)
        self.assertFalse(read_document()['schedules']['import-articoli']['enabled'])
        self.assertEqual(self.mutate(action='play').status_code, 200)
        self.assertEqual(read_document()['schedules']['poleepo-import-orders'], original)
        self.assertEqual(AppPreference.query.first().value_json['updated_by'], 12)

    def test_frequency_validation_and_stale_revision_preserve_document(self):
        self.assertEqual(self.mutate(action='frequency', frequency=dict(kind='interval', seconds=3600)).status_code, 200)
        original = deepcopy(AppPreference.query.first().value_json)
        for frequency in [dict(kind='interval', seconds=1), dict(kind='interval', seconds=True),
                          dict(kind='interval', seconds=10**10), dict(kind='interval', seconds='60'),
                          dict(kind='cron', minute='*/0', hour='*', day_of_week='*', day_of_month='*', month_of_year='*'),
                          dict(kind='cron', minute='0', hour='25', day_of_week='*', day_of_month='*', month_of_year='*'),
                          dict(kind='cron', minute='0', hour='0', day_of_week='*', day_of_month='31', month_of_year='2')]:
            self.assertEqual(self.mutate(action='frequency', frequency=frequency).status_code, 400, frequency)
        self.assertEqual(self.mutate(revision=0).status_code, 409)
        self.assertEqual(self.mutate(name='not-a-task').status_code, 400)
        self.assertEqual(self.client.post('/settings/celery-tasks/import-articoli', data='invalid', content_type='application/json').status_code, 400)
        self.assertEqual(AppPreference.query.first().value_json, original)

    def test_cron_and_group_pause_resume_preserve_arguments_and_deleted_states(self):
        cron = dict(kind='cron', minute='15', hour='8,18', day_of_week='mon-fri', day_of_month='*', month_of_year='*')
        self.assertEqual(self.mutate(action='frequency', frequency=cron).status_code, 200)
        self.assertEqual(read_document()['schedules']['import-articoli']['frequency'], cron)
        self.mutate(name='import-barcode', action='delete')
        self.assertEqual(self.mutate(name='imports', action='imports_pause').status_code, 200)
        self.assertEqual(pause_reason('config.tasks.matrixws_test_poll_task', read_document()), 'imports_paused')
        self.assertEqual(self.mutate(name='imports', action='imports_play').status_code, 200)
        doc = read_document()
        self.assertIsNone(pause_reason('config.tasks.import_articoli_task', doc))
        self.assertNotIn('import-barcode', effective_schedule(doc))
        self.assertEqual(effective_schedule(doc)['poleepo-import-orders']['args'], ({'background': True},))
        self.assertEqual(effective_schedule(doc)['support-mailbox-sync']['args'], (100,))

    def test_developer_permission_on_page_api_mutations_and_tile(self):
        with patch('routes.settings.render_template', side_effect=lambda template, **ctx: jsonify(template=template, titles=[entry['title'] for entry in ctx.get('entries', [])])):
            self.assertIn('Task Celery', self.client.get('/settings/').json['titles'])
            self.assertEqual(self.client.get('/settings/celery-tasks').status_code, 200)
            self.user.max_role_weight = 900
            self.user.active_roles = [NS(name='office', weight=900)]
            self.assertNotIn('Task Celery', self.client.get('/settings/').json['titles'])
        self.assertEqual(self.client.get('/settings/celery-tasks', headers={'Content-Type': 'application/json'}).status_code, 403)
        self.assertEqual(self.client.get('/settings/celery-tasks/data', headers={'Content-Type': 'application/json'}).status_code, 403)
        self.assertEqual(self.mutate().status_code, 403)
        self.assertEqual(AppPreference.query.count(), 0)

    def test_database_failure_is_visible_without_mutating_configuration(self):
        with patch('tools.celery_schedule_settings.read_document', side_effect=SQLAlchemyError('offline')):
            self.assertEqual(self.client.get('/settings/celery-tasks/data').status_code, 503)

    def new_scheduler(self, directory):
        app = Celery('settings-tests', broker='memory://', backend='cache+memory://')
        app.flask_app = self.app
        app.conf.update(beat_schedule=catalog(), timezone='Europe/Rome', beat_max_loop_interval=5)
        return PreferenceScheduler(app=app, schedule_filename=directory + '/beat')

    def test_running_scheduler_reloads_pause_frequency_delete_and_restart(self):
        with TemporaryDirectory() as directory, patch.object(PreferenceScheduler, 'publish_status'):
            scheduler = self.new_scheduler(directory)
            self.assertTrue(scheduler.reload_preferences(force=True))
            entry = scheduler.schedule['poleepo-import-orders']
            last = entry.last_run_at; count = entry.total_run_count
            self.mutate()
            scheduler.reload_preferences(force=True)
            self.assertNotIn('import-articoli', scheduler.schedule)
            self.assertEqual(scheduler.schedule['poleepo-import-orders'].last_run_at, last)
            self.assertEqual(scheduler.schedule['poleepo-import-orders'].total_run_count, count)
            self.mutate(action='frequency', frequency=dict(kind='interval', seconds=7200))
            self.mutate(action='play')
            scheduler.reload_preferences(force=True)
            self.assertEqual(scheduler.schedule['import-articoli'].schedule.run_every.total_seconds(), 7200)
            self.assertFalse(scheduler.schedule['import-articoli'].is_due().is_due)
            self.mutate(action='delete')
            scheduler.reload_preferences(force=True)
            scheduler.close()
            restarted = self.new_scheduler(directory)
            restarted.reload_preferences(force=True)
            self.assertNotIn('import-articoli', restarted.schedule)
            self.assertEqual(restarted.schedule['poleepo-import-orders'].last_run_at, last)
            restarted.close()

    def test_scheduler_tick_dispatches_only_enabled_entries_and_stops_on_db_failure(self):
        with TemporaryDirectory() as directory, patch.object(PreferenceScheduler, 'publish_status'):
            self.mutate()
            scheduler = self.new_scheduler(directory)
            scheduler.reload_preferences(force=True)
            self.mutate(name='support-mailbox-sync', action='frequency', frequency=dict(kind='interval', seconds=60))
            scheduler.reload_preferences(force=True)
            scheduler.schedule['support-mailbox-sync'].last_run_at -= timedelta(minutes=2)
            scheduler._heap = None
            with patch.object(scheduler, 'apply_entry') as send:
                for _ in range(20): scheduler.tick()
                self.assertTrue(any(call.args[0].name == 'support-mailbox-sync' for call in send.call_args_list))
                self.assertFalse(any(call.args[0].name == 'import-articoli' for call in send.call_args_list))
                scheduler._preferences_checked_at = None
                with patch('tools.celery_scheduler.read_document', side_effect=SQLAlchemyError('offline')):
                    send.reset_mock()
                    self.assertEqual(scheduler.tick(), 5)
                    send.assert_not_called()
            scheduler.close()

    def test_worker_reads_pause_before_running_queued_callback(self):
        from config.celery_app import celery, FlaskContextTask
        FlaskContextTask.bind(celery)
        task = FlaskContextTask(); task.name = 'config.tasks.import_articoli_task'
        task.push_request(id='queued')
        task.run = Mock(return_value='executed')
        try:
            with patch.object(celery, 'flask_app', self.app), patch('tools.redis_utils.clear_task_status'):
                self.mutate()
                self.assertEqual(task()['reason'], 'schedule_paused'); task.run.assert_not_called()
                self.mutate(action='play')
                self.assertEqual(task(), 'executed')
                self.mutate(action='delete')
                self.assertEqual(task()['reason'], 'schedule_paused')
                task.name = 'config.tasks.send_mailing_campaign_task'
                self.assertEqual(task(), 'executed')
        finally: task.pop_request()


if __name__ == '__main__': unittest.main()
