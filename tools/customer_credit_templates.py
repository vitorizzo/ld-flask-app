"""Shared email text templates stored in the existing preferences table."""
import re
from uuid import uuid4

from models import AppPreference

PREFIX = 'customer_credit.template.'
FIELDS = {'cliente', 'codice_cliente', 'saldo', 'partite'}
TOKEN = re.compile(r'\{\{\s*([^{}]+?)\s*\}\}')


def template_rows():
    return AppPreference.query.filter(AppPreference.key.startswith(PREFIX)).order_by(AppPreference.label, AppPreference.id)


def template_data(row):
    return dict(row.value_json or {}, id=row.key[len(PREFIX):])


def validate_template(payload):
    data = {key: str(payload.get(key) or '').strip() for key in ('name', 'kind', 'subject', 'body')}
    if data['kind'] not in {'statement', 'reminder'}:
        raise ValueError('Scegli estratto conto o sollecito.')
    if not data['name'] or len(data['name']) > 160:
        raise ValueError('Inserisci un nome di massimo 160 caratteri.')
    if not data['subject'] or len(data['subject']) > 255 or '\n' in data['subject'] or '\r' in data['subject']:
        raise ValueError('Inserisci un oggetto valido di massimo 255 caratteri.')
    if not data['body'] or len(data['body']) > 20000:
        raise ValueError('Inserisci un testo di massimo 20.000 caratteri.')
    if TOKEN.findall(data['body']).count('partite') != 1 or 'partite' in TOKEN.findall(data['subject']):
        raise ValueError('Inserisci {{partite}} una sola volta nel testo, per includere i documenti aggiornati.')
    for text in (data['subject'], data['body']):
        if any(field not in FIELDS for field in TOKEN.findall(text)):
            raise ValueError('Usa soltanto i campi cliente, codice_cliente, saldo e partite.')
    return data


def new_template(data):
    return AppPreference(key=PREFIX + uuid4().hex, category='Comunicazioni clienti',
                         label=data['name'], value_type='json', value_json=data)


