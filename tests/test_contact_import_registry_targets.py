import inspect
import io
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from flask import Flask
from routes import registry


class ContactImportTargetTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config['TESTING'] = True
        self.app.register_blueprint(registry.registry_bp, url_prefix='/registry')
        self.app.add_url_rule('/create-test', view_func=inspect.unwrap(registry.api_contact_import_create), methods=['POST'])
        self.app.add_url_rule('/confirm-test/<int:intent_id>', view_func=inspect.unwrap(registry.api_contact_import_confirm), methods=['POST'])
        self.client = self.app.test_client()

    def test_vcard_keeps_customer_or_supplier_as_suggested_target(self):
        for kind in ('customer', 'supplier'):
            with self.subTest(kind=kind), patch.object(registry, 'BusinessRegistry') as model, patch.object(registry, 'current_user', SimpleNamespace(id=7)), patch.object(registry, 'create_contact_import_intent') as create:
                model.query.filter_by.return_value.filter.return_value.first.return_value = SimpleNamespace(id=12, kind=kind)
                create.return_value = SimpleNamespace(id=99, to_dict=lambda: {'id': 99})
                response = self.client.post('/create-test', data={'registry_id': '12', 'file': (io.BytesIO(b'BEGIN:VCARD\nVERSION:3.0\nFN:Mario\nEND:VCARD'), 'mario.vcf')}, content_type='multipart/form-data')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(create.call_args.args[1:], (7, 12))
                self.assertNotIn('kind', model.query.filter_by.call_args.kwargs)
                model.kind.in_.assert_called_with(('customer', 'supplier'))

    def test_confirmation_links_contact_and_returns_correct_book(self):
        for kind in ('customer', 'supplier'):
            with self.subTest(kind=kind), patch.object(registry, 'BusinessRegistry') as model, patch.object(registry, '_contact_import_access', return_value=SimpleNamespace(status='pending', display_name='Mario')), patch.object(registry, 'finalize_contact_import') as finalize, patch.object(registry, 'BusinessRegistryContactLink') as links, patch.object(registry, 'db') as db, patch.object(registry, '_registry_to_dict', return_value={'id': 12}):
                target = SimpleNamespace(id=12, kind=kind)
                model.query.filter_by.return_value.filter.return_value.first.return_value = target
                finalize.return_value = (SimpleNamespace(id=8, to_dict=lambda: {'id': 8}), False)
                link = SimpleNamespace(role=None, notes=None, is_active=False)
                links.query.filter_by.return_value.first.return_value = link
                response = self.client.post('/confirm-test/99', json={'registry_id': 12, 'selected_points': ['phone:0'], 'role': 'Agente'})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(link.is_active)
                self.assertEqual(link.role, 'Agente')
                self.assertEqual(response.json['redirect_url'], '/registry/suppliers' if kind == 'supplier' else '/registry/customers')
                self.assertIs(finalize.call_args.args[1], target)
                db.session.commit.assert_called_once()


if __name__ == '__main__':
    unittest.main()
