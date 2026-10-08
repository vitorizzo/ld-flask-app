from datetime import date, datetime, timedelta
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from flask import Flask
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from extensions import db
from models import OrderStatus, SlackOrder, SlackOrderEvent
from routes import kiosk
from tools.slack_processor import SlackProcessor


@compiles(JSONB, 'sqlite')
def compile_jsonb_sqlite(type_, compiler, **kwargs):
    return 'JSON'


def initial_rows():
    return [dict(code='acquisito', label='Acquisito', slack_reaction=None, is_visible=True, is_terminal=False),
            dict(code='evaso', label='Evaso', slack_reaction='100', is_visible=True, is_terminal=True)]


class KioskStatusTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI='sqlite://', LOGIN_DISABLED=True)
        db.init_app(self.app)
        self.app.register_blueprint(kiosk.kiosk_bp)
        self.ctx = self.app.app_context(); self.ctx.push()
        db.metadata.create_all(db.engine, tables=[OrderStatus.__table__, SlackOrder.__table__, SlackOrderEvent.__table__])
        for index, row in enumerate(initial_rows()):
            db.session.add(OrderStatus(**row, order_index=index))
        self.order = SlackOrder(slack_channel_id='C1', slack_message_ts='1.0', slack_thread_ts='1.0',
                                customer_display='Cliente', customer_key='cliente', order_date=date.today())
        db.session.add(self.order); db.session.commit()
        self.auth = patch('tools.role_required.get_current_user', return_value=SimpleNamespace(
            active_roles=[SimpleNamespace(name='staff', weight=30)], max_role_weight=30))
        self.auth.start()
        self.client = self.app.test_client()

    def tearDown(self):
        self.auth.stop(); db.session.remove(); self.ctx.pop()

    def test_configuration_persists_and_drives_columns_and_reactions(self):
        rows = initial_rows()
        rows.insert(1, dict(code='preparazione', label='In preparazione', slack_reaction=':package:', is_visible=True, is_terminal=False))
        response = self.client.put('/kiosk/api/status-config', json={'statuses': rows})
        self.assertEqual(response.status_code, 200)
        data = self.client.get('/kiosk/api/statuses').json
        self.assertEqual([row['code'] for row in data], ['acquisito', 'preparazione', 'evaso'])
        self.assertEqual(data[1]['slack_reaction'], 'package')
        processor = object.__new__(SlackProcessor)
        api = Mock(); processor._get_api = Mock(return_value=api)
        processor.sync_order_status_reactions(self.order, 'acquisito', 'preparazione')
        api.add_reaction.assert_called_once_with(channel='C1', timestamp='1.0', name='package')

    def test_invalid_configuration_does_not_write(self):
        variants = []
        rows = initial_rows(); rows[1]['slack_reaction'] = 'not an emoji'; variants.append(rows)
        rows = initial_rows(); rows[1]['code'] = 'renamed'; variants.append(rows)
        rows = initial_rows(); rows[0]['is_visible'] = False; variants.append(rows)
        rows = initial_rows(); rows[0]['slack_reaction'] = ':100:'; variants.append(rows)
        rows = initial_rows(); rows[1]['code'] = 'a' * 31; variants.append(rows)
        variants.append([])
        for rows in variants:
            with self.subTest(rows=rows):
                response = self.client.put('/kiosk/api/status-config', json={'statuses': rows})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(OrderStatus.query.count(), 2)
                self.assertEqual(OrderStatus.query.filter_by(code='evaso').one().slack_reaction, '100')

    def test_hiding_an_occupied_column_is_rejected(self):
        self.order.status = 'evaso'; db.session.commit()
        rows = initial_rows(); rows[1]['is_visible'] = False
        response = self.client.put('/kiosk/api/status-config', json={'statuses': rows})
        self.assertEqual(response.status_code, 400)
        self.assertTrue(OrderStatus.query.filter_by(code='evaso').one().is_visible)

    def test_config_permission_is_checked(self):
        with patch('tools.role_required.get_current_user', return_value=SimpleNamespace(
                active_roles=[SimpleNamespace(name='viewer', weight=1)], max_role_weight=1)):
            response = self.client.put('/kiosk/api/status-config', json={'statuses': initial_rows()})
            self.assertEqual(response.status_code, 403)

    def test_custom_terminal_closes_and_reopening_clears_timestamp(self):
        db.session.add(OrderStatus(code='completato', label='Completato', order_index=2,
                                   slack_reaction='checkered_flag', is_terminal=True, is_visible=True))
        db.session.commit()
        with patch.object(kiosk, 'SlackProcessor') as processor:
            response = self.client.post(f'/kiosk/api/order/{self.order.id}/set-status', json={'status':'completato'})
            self.assertTrue(response.json['ok']); self.assertIsNotNone(self.order.closed_at)
            with self.app.test_request_context():
                self.assertFalse(kiosk._hide_closed_or_cancelled_order(self.order))
                self.order.closed_at = datetime.utcnow() - timedelta(days=2)
                self.assertTrue(kiosk._hide_closed_or_cancelled_order(self.order))
            self.client.post(f'/kiosk/api/order/{self.order.id}/set-status', json={'status':'acquisito'})
            self.assertIsNone(self.order.closed_at)
            self.assertEqual(SlackOrderEvent.query.count(), 2)

    def test_slack_failure_is_reported_after_local_save(self):
        with patch.object(kiosk, 'SlackProcessor') as processor:
            processor.return_value.sync_order_status_reactions.side_effect = RuntimeError('Slack down')
            response = self.client.post(f'/kiosk/api/order/{self.order.id}/set-status', json={'status':'evaso'})
            self.assertTrue(response.json['ok']); self.assertIn('warning', response.json)
            self.assertEqual(self.order.status, 'evaso')

    def test_return_to_state_without_reaction_removes_higher_reactions(self):
        processor = object.__new__(SlackProcessor)
        api = Mock(); processor._get_api = Mock(return_value=api)
        processor.sync_order_status_reactions(self.order, 'evaso', 'acquisito')
        api.remove_reaction.assert_any_call(channel='C1', timestamp='1.0', name='100')
        api.add_reaction.assert_not_called()


if __name__ == '__main__':
    unittest.main()
