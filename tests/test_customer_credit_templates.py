import base64
import unittest
import time
from io import BytesIO
from types import SimpleNamespace as NS
from unittest.mock import patch

from pypdf import PdfReader
from models import AppPreference
import test_customer_account_open_api as account_tests


class CreditTemplateTests(unittest.TestCase):
    setUp = account_tests.OpenAccountApiTests.setUp
    tearDown = account_tests.OpenAccountApiTests.tearDown
    def save(self, **changes):
        data = dict(name='Gentile promemoria', kind='statement', subject='Situazione di {{cliente}}',
                    body='Spett.le {{cliente}},\nSaldo {{saldo}}\n{{partite}}\nGrazie per la collaborazione.')
        data.update(changes)
        return self.client.post('/admin/customer-credit/templates', json=data)

    def preview(self, **changes):
        payload = dict(action='preview', kind='statement', channel='email', test_mode=True, test_email='test@example.com')
        payload.update(changes)
        return self.client.post('/admin/customer-credit/1066/communications', json=payload)

    def test_create_update_list_delete_and_kind_validation(self):
        response = self.save(); self.assertEqual(response.status_code, 200, response.json)
        id = response.json['template']['id']
        self.assertEqual(len(self.client.get('/admin/customer-credit/templates').json['templates']), 1)
        changed = self.save(id=id, name='Personalizzato', body='Gentile {{cliente}},\n{{partite}}\nA presto.')
        self.assertEqual(changed.json['template']['name'], 'Personalizzato')
        self.assertEqual(AppPreference.query.count(), 1)
        self.assertEqual(self.preview(template_id=id, kind='reminder').status_code, 400)
        self.assertEqual(self.client.delete('/admin/customer-credit/templates/' + id).status_code, 200)
        self.assertEqual(self.preview(template_id=id).status_code, 400)
        self.assertEqual(AppPreference.query.count(), 0)

    def test_validation_preserves_existing_data(self):
        for changes in [dict(body='Nessuna tabella'), dict(body='{{partite}} {{partite}}'), dict(body='{{partite}} {{sconosciuto}}'),
                        dict(subject='{{partite}}'), dict(name=''), dict(kind='other'), dict(subject='Oggetto\nErrato')]:
            self.assertEqual(self.save(**changes).status_code, 400, changes)
        self.assertEqual(AppPreference.query.count(), 0)

    def test_template_pdf_and_exact_attachment_with_short_email_body(self):
        id = self.save().json['template']['id']
        preview = self.preview(template_id=id).json['preview']
        pdf = base64.b64decode(preview['pdf_base64'])
        text = ''.join(page.extract_text() for page in PdfReader(BytesIO(pdf)).pages)
        self.assertIn('Grazie per la collaborazione.', text)
        self.assertIn('Cliente prova', text)
        self.assertIn('DOCUMENTO OPEN', text)
        self.assertNotIn('DOCUMENTO 890', text)
        self.send.return_value = {'suppressed': False}
        response = self.preview(action='send', template_id=id, pdf_token=preview['pdf_token'], subject=preview['subject'], email_body=preview['email_body'])
        self.assertEqual(response.status_code, 200, response.json)
        message = self.send.call_args.args[1]
        self.assertEqual(message.attachments[0].data, pdf)
        self.assertEqual(message.attachments[0].content_type, 'application/pdf')
        self.assertEqual(message.body, preview['email_body'])
        self.assertIsNone(message.html)
        self.assertNotIn('DOCUMENTO OPEN', message.body)

    def test_send_requires_valid_preview_bound_to_customer_recipient_and_snapshot(self):
        preview = self.preview().json['preview']
        for changes in [dict(pdf_token='invalid'), dict(pdf_token=preview['pdf_token'], test_email='other@example.com'), dict(pdf_token='')]:
            self.assertEqual(self.preview(action='send', email_body='Allegato', **changes).status_code, 409)
        with patch('routes.administration._latest_statement_import', return_value=NS(id=2)):
            self.assertEqual(self.preview(action='send', email_body='Allegato', pdf_token=preview['pdf_token']).status_code, 404)
        self.send.assert_not_called()

    def test_template_access_allowed_to_office_denied_to_customer(self):
        low = NS(active_roles=[NS(name='customer', weight=10)], max_role_weight=10)
        with patch('tools.role_required.get_current_user', return_value=low):
            self.assertEqual(self.save().status_code, 403)
            response = self.client.get('/admin/customer-credit/templates', headers={'Content-Type': 'application/json'})
            self.assertEqual(response.status_code, 403)

    def test_expired_preview_and_pdf_generation_failure_never_send(self):
        preview = self.preview().json['preview']
        with patch('itsdangerous.timed.TimestampSigner.get_timestamp', return_value=int(time.time()) + 901):
            response = self.preview(action='send', email_body='Allegato', pdf_token=preview['pdf_token'])
        self.assertEqual(response.status_code, 409)
        with patch('routes.administration.communication_pdf', side_effect=ValueError('Invalid layout')):
            response = self.preview()
            self.assertEqual(response.status_code, 502)
        self.send.assert_not_called()
