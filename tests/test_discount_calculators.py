import math
import unittest

from flask import Flask
from routes.elaborazioni_sconti import sconti_bp


class DiscountCalculatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(sconti_bp, url_prefix='/sconti')
        cls.client = app.test_client()

    def calculate(self, path, payload):
        return self.client.post('/sconti/calcola-sconto-' + path, json=payload)

    def test_successive_discounts_are_not_added(self):
        response = self.calculate('equivalente', {'sconti': [20, 10]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['sconto_equivalente'], 28)

    def test_complementary_discount_and_markup(self):
        for target, expected in [(30, 12.5), (20, 0), (10, -12.5), (100, 100)]:
            with self.subTest(target=target):
                response = self.calculate('complementare', {'sconto_finale': target, 'sconti_fissi': [20]})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json['sconto_complementare'], expected)

    def test_free_goods_use_total_received_as_denominator(self):
        response = self.calculate('combinazioni', {'acquistati': 3, 'omaggio': 1})
        self.assertEqual(response.json['sconto_combinazione'], 25)
        response = self.calculate('merce', {'val_acquisto': 125, 'val_omaggio': 20})
        self.assertEqual(response.json['sconto_merce'], 13.79)

    def test_zero_gift_and_complete_discount(self):
        self.assertEqual(self.calculate('combinazioni', {'acquistati': 3, 'omaggio': 0}).json['sconto_combinazione'], 0)
        self.assertEqual(self.calculate('equivalente', {'sconti': [100]}).json['sconto_equivalente'], 100)

    def test_invalid_inputs_return_readable_400(self):
        cases = [
            ('equivalente', {'sconti': []}),
            ('equivalente', {'sconti': [101]}),
            ('equivalente', {'sconti': [-1]}),
            ('equivalente', {'sconti': [True]}),
            ('equivalente', {'sconti': ['10']}),
            ('equivalente', {'sconti': [math.nan]}),
            ('equivalente', {'sconti': [10 ** 400]}),
            ('complementare', {'sconto_finale': 20, 'sconti_fissi': [100]}),
            ('complementare', {'sconto_finale': 20, 'sconti_fissi': [99] * 200}),
            ('complementare', {'sconti_fissi': [20]}),
            ('combinazioni', {'acquistati': 0, 'omaggio': 0}),
            ('combinazioni', {'acquistati': 1.5, 'omaggio': 1}),
            ('combinazioni', {'acquistati': 2, 'omaggio': -1}),
            ('merce', {'val_acquisto': 0, 'val_omaggio': 10}),
            ('merce', {'val_acquisto': 125, 'val_omaggio': -20}),
            ('merce', {'val_acquisto': math.inf, 'val_omaggio': 20}),
        ]
        for path, payload in cases:
            with self.subTest(path=path, payload=payload):
                response = self.calculate(path, payload)
                self.assertEqual(response.status_code, 400)
                self.assertTrue(response.json['error'])

    def test_malformed_request_is_not_a_server_error(self):
        for body in ('null', '[]', '{broken'):
            response = self.client.post('/sconti/calcola-sconto-equivalente', data=body, content_type='application/json')
            self.assertEqual(response.status_code, 400)
            self.assertIn('error', response.json)


if __name__ == '__main__':
    unittest.main()
