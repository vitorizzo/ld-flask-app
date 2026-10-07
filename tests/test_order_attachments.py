from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest
import inspect
import io

from flask import Flask
from tools.order_attachments import local_order_attachment_path, post_order_message
from tools.slack_api import SlackAPI, SlackAPIConfig
from routes import kiosk
from routes import route_orders
from routes import pwa


class OrderAttachmentTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.app = Flask(__name__, static_folder=str(self.root))
        self.app.config.update(TESTING=True, SLACK_BOT_TOKEN='test-token')
        self.app.register_blueprint(kiosk.kiosk_bp)
        self.context = self.app.app_context(); self.context.push()
        self.client = self.app.test_client()

    def tearDown(self):
        self.context.pop(); self.directory.cleanup()

    def attachment(self, folder='route_orders', name='ordine.pdf'):
        path = self.root / 'uploads' / folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'%PDF-test attachment')
        return {'id': 'local-1', 'source': {'route_orders': 'route_board', 'customer_orders': 'customer_order', 'shared_orders': 'pwa_share'}[folder],
                'name': name, 'filename': name, 'mimetype': 'application/pdf', 'static_path': path.relative_to(self.root).as_posix()}

    def test_existing_local_attachments_open_without_slack_url(self):
        for folder in ['route_orders', 'customer_orders', 'shared_orders']:
            with self.subTest(folder=folder):
                attachment = self.attachment(folder)
                with patch.object(kiosk, 'SlackOrder') as orders, patch.object(kiosk, '_order_attachments', return_value=[attachment]), patch.object(kiosk.requests, 'get') as fetch:
                    orders.query.get.return_value = SimpleNamespace(id=1)
                    for variant in ['', '?variant=thumb']:
                        response = self.client.get('/kiosk/api/order/1/attachment/local-1' + variant)
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(response.data, b'%PDF-test attachment')
                        self.assertEqual(response.mimetype, 'application/pdf')
                        response.close()
                    fetch.assert_not_called()

    def test_local_attachments_support_range_requests(self):
        attachment = self.attachment()
        with patch.object(kiosk, 'SlackOrder') as orders, patch.object(kiosk, '_order_attachments', return_value=[attachment]):
            orders.query.get.return_value = SimpleNamespace(id=1)
            response = self.client.get('/kiosk/api/order/1/attachment/local-1', headers={'Range': 'bytes=0-3'})
            self.assertEqual(response.status_code, 206)
            self.assertEqual(response.data, b'%PDF')
            response.close()

    def test_only_order_upload_folders_are_served(self):
        self.attachment()
        (self.root / 'private.txt').write_text('private')
        for rel in ['private.txt', '../private.txt', 'uploads/route_orders/../../private.txt', 'uploads/route_orders', 'uploads/route_orders/missing.pdf', str(self.root / 'private.txt')]:
            with self.subTest(rel=rel):
                self.assertIsNone(local_order_attachment_path({'static_path': rel}))
        self.assertIsNotNone(local_order_attachment_path({'url': '/static/uploads/route_orders/ordine.pdf'}))

    def test_slack_private_attachment_fallback_is_preserved(self):
        attachment = {'id': 'F1', 'name': 'photo.png', 'url_private_download': 'https://files.slack.com/test', 'mimetype': 'image/png'}
        with patch.object(kiosk, 'SlackOrder') as orders, patch.object(kiosk, '_order_attachments', return_value=[attachment]), patch.object(kiosk.requests, 'get', return_value=SimpleNamespace(status_code=200, content=b'file', headers={'Content-Type': 'image/png'})) as fetch:
            orders.query.get.return_value = SimpleNamespace(id=1)
            response = self.client.get('/kiosk/api/order/1/attachment/F1')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, b'file')
            self.assertEqual(fetch.call_args.kwargs['headers'], {'Authorization': 'Bearer test-token'})

    def test_root_upload_contains_text_and_all_files_without_thread_reply(self):
        api = SlackAPI(SlackAPIConfig(bot_token='test-token')); api.client = Mock()
        uploads = [{'file': 'one.pdf', 'filename': 'one.pdf'}, {'file': 'two.png', 'filename': 'two.png'}]
        api.client.files_upload_v2.return_value = {'files': [{'id': 'F1'}, {'id': 'F2'}]}
        api.client.files_info.side_effect = [
            {'file': {'id': 'F1', 'shares': {'private': {'C1': [{'ts': '123.456'}]}}}},
            {'file': {'id': 'F2', 'shares': {'private': {'C1': [{'ts': '123.456'}]}}}},
        ]
        result = api.post_message_with_files('C1', '*Cliente*\nOrdine', uploads)
        self.assertEqual(result['ts'], '123.456')
        api.client.files_upload_v2.assert_called_once_with(channel='C1', initial_comment='*Cliente*\nOrdine', file_uploads=uploads)
        api.client.chat_postMessage.assert_not_called()

    def test_root_timestamp_waits_for_share_and_does_not_use_file_creation_time(self):
        api = SlackAPI(SlackAPIConfig(bot_token='test-token')); api.client = Mock()
        api.client.files_upload_v2.return_value = {'files': [{'id': 'F1', 'timestamp': 999}]}
        api.client.files_info.side_effect = [
            {'file': {'id': 'F1', 'timestamp': 999, 'shares': {}}},
            {'file': {'id': 'F1', 'shares': {'public': {'C1': [{'ts': '123.456', 'thread_ts': '123.456'}]}}}},
        ]
        with patch('tools.slack_api.time.sleep'):
            self.assertEqual(api.post_message_with_files('C1', 'ordine', [{'file': 'test.pdf'}])['ts'], '123.456')
        api.client.files_upload_v2.assert_called_once()

    def test_missing_share_does_not_publish_a_second_message(self):
        api = SlackAPI(SlackAPIConfig(bot_token='test-token')); api.client = Mock()
        api.client.files_upload_v2.return_value = {'files': [{'id': 'F1'}]}
        api.client.files_info.return_value = {'file': {'id': 'F1', 'shares': {}}}
        with patch('tools.slack_api.time.sleep'), self.assertRaises(RuntimeError):
            api.post_message_with_files('C1', 'ordine', [{'file': 'test.pdf'}])
        api.client.files_upload_v2.assert_called_once()
        api.client.chat_postMessage.assert_not_called()

    def test_no_file_keeps_normal_message_and_metadata_is_saved_for_files(self):
        api = Mock()
        post_order_message(api, 'C1', 'ordine', [], client_msg_id='order-1')
        api.post_message.assert_called_once_with('C1', 'ordine', client_msg_id='order-1')
        api.post_message_with_files.assert_not_called()
        attachment = self.attachment()
        api.post_message_with_files.return_value = {'ts': '123.456', 'files': [{'id': 'F1', 'url_private_download': 'https://files.slack.com/test'}]}
        result = post_order_message(api, 'C1', 'ordine', [attachment])
        self.assertEqual(result['ts'], '123.456')
        self.assertEqual(attachment['id'], 'local-1')
        self.assertEqual(attachment['slack_file_id'], 'F1')
        self.assertEqual(attachment['url_private_download'], 'https://files.slack.com/test')

    def test_missing_file_prevents_any_slack_publication(self):
        api = Mock()
        with self.assertRaises(RuntimeError):
            post_order_message(api, 'C1', 'ordine', [{'id': 'local', 'static_path': 'uploads/route_orders/missing.pdf'}])
        api.post_message.assert_not_called(); api.post_message_with_files.assert_not_called()

    def test_local_and_slack_webhook_events_are_merged_once(self):
        local = self.attachment(); local['slack_file_id'] = 'F1'
        remote = {'id': 'F1', 'name': 'ordine.pdf', 'url_private': 'https://files.slack.com/test'}
        events = [SimpleNamespace(payload={'attachments': [local]}, order_id=1), SimpleNamespace(payload={'attachments': [remote]}, order_id=1)]
        with patch.object(kiosk, 'SlackOrderEvent') as model:
            model.query.filter.return_value.order_by.return_value.all.return_value = events
            attachments = kiosk._order_attachments(1)
            self.assertEqual(len(attachments), 1)
            self.assertEqual(attachments[0]['id'], 'local-1')
            self.assertEqual(attachments[0]['url_private'], remote['url_private'])
            self.assertNotIn('url_private', local)
            model.query.filter.return_value.filter.return_value.all.return_value = events
            self.assertEqual(kiosk._attachment_counts_for_order_ids([1]), {1: 1})

    def test_pwa_attachment_metadata_survives_event_conversion(self):
        intent = SimpleNamespace(id=1, files=[
            {'diagnostic': True},
            {'id': 'local-1', 'filename': 'ordine.pdf', 'static_path': 'uploads/shared_orders/ordine.pdf', 'slack_file_id': 'F1', 'url_private_download': 'https://files.slack.com/test'},
        ])
        attachments = pwa._shared_attachments(intent)
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0]['id'], 'local-1')
        self.assertEqual(attachments[0]['slack_file_id'], 'F1')
        self.assertEqual(attachments[0]['url_private_download'], 'https://files.slack.com/test')

    def test_manual_order_upload_is_stored_and_readable_from_app(self):
        self.app.add_url_rule('/create-order-test', view_func=inspect.unwrap(route_orders.api_direct_order_create), methods=['POST'])
        route = SimpleNamespace(id=1, default_time=None)
        api = Mock()
        api.post_message_with_files.return_value = {'ts': '123.456', 'files': [{'id': 'F1', 'url_private_download': 'https://files.slack.com/test'}]}
        with patch.object(route_orders, '_direct_order_route', return_value=(route, 'C1')), patch.object(route_orders, 'SlackAPI', return_value=api), patch.object(route_orders, 'db') as db, patch.object(route_orders, 'SlackOrder', side_effect=lambda **kw: SimpleNamespace(id=1, **kw)), patch.object(route_orders, 'SlackOrderEvent') as event, patch.object(route_orders, '_reset_documents_for_customer_orders'), patch.object(route_orders, 'send_order_push_to_staff'), patch.object(route_orders, '_order_to_dict', return_value={'id': 1}):
            response = self.client.post('/create-order-test', data={'customer_name': 'Cliente test', 'order_note': 'Tre cartoni', 'files': (io.BytesIO(b'%PDF-test attachment'), 'ordine.pdf')}, content_type='multipart/form-data')
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json['ok'])
            db.session.commit.assert_called_once()
            payload = event.call_args.kwargs['payload']
            self.assertEqual(payload['ts'], '123.456')
            self.assertEqual(payload['attachments'][0]['slack_file_id'], 'F1')
            self.assertIn('Tre cartoni', api.post_message_with_files.call_args.args[1])
            self.assertTrue(Path(api.post_message_with_files.call_args.args[2][0]['file']).is_file())
            api.post_message.assert_not_called(); api.upload_file.assert_not_called()
        with patch.object(kiosk, 'SlackOrder') as orders, patch.object(kiosk, '_order_attachments', return_value=payload['attachments']), patch.object(kiosk.requests, 'get') as fetch:
            orders.query.get.return_value = SimpleNamespace(id=1)
            response = self.client.get('/kiosk/api/order/1/attachment/' + payload['attachments'][0]['id'])
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, b'%PDF-test attachment')
            response.close(); fetch.assert_not_called()

    def test_attachments_added_later_keep_existing_thread(self):
        api = Mock(); attachment = self.attachment()
        route_orders._upload_attachments_to_slack(api, 'C1', '123.456', [attachment])
        self.assertEqual(api.upload_file.call_args.kwargs['thread_ts'], '123.456')
        api.post_message_with_files.assert_not_called()


if __name__ == '__main__':
    unittest.main()
