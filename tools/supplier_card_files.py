"""Validate card metadata and uploads before mutating persistent attachments."""
import json
import re
import zipfile
from datetime import date
from io import BytesIO
from pathlib import PurePath
from xml.etree import ElementTree

from flask import request
from models import SupplierBoardAttachment

MAX_FILE = 10 * 1024 * 1024
MAX_TOTAL = 50 * 1024 * 1024
TYPES = {'.pdf': 'application/pdf', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
         '.png': 'image/png', '.webp': 'image/webp', '.doc': 'application/msword',
         '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
         '.xls': 'application/vnd.ms-excel',
         '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}


def card_payload():
    if request.mimetype == 'multipart/form-data':
        try:
            payload = json.loads(request.form.get('data', ''))
        except (ValueError, TypeError):
            raise ValueError('Dati scheda non validi.')
    else:
        payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValueError('Dati scheda non validi.')
    return payload


def card_metadata(payload, card):
    values = {}
    for key, maximum in [('order_text', 40000), ('transmission_notes', 40000), ('payment_terms_other', 500)]:
        value = payload.get(key, getattr(card, key) or '')
        if not isinstance(value, str) or len(value) > maximum:
            raise ValueError('Testo ordine, note o pagamento non validi o troppo lunghi.')
        values[key] = value.strip()
    cash = payload.get('cash_on_delivery', card.cash_on_delivery or False)
    terms = payload.get('payment_terms', card.payment_terms or '')
    if type(cash) is not bool or terms not in ('', 'sight', 'month_end', '30', '60', '90', 'other'):
        raise ValueError('Condizioni di pagamento non valide.')
    if cash and not terms:
        raise ValueError('Con contrassegno seleziona il termine di pagamento.')
    if terms == 'other' and not values['payment_terms_other']:
        raise ValueError('Specifica il termine di pagamento Altro.')
    payment = payload.get('payment_date', card.payment_date.isoformat() if card.payment_date else '')
    if not isinstance(payment, str) or (payment and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', payment)):
        raise ValueError('Data pagamento non valida.')
    try:
        values['payment_date'] = date.fromisoformat(payment) if payment else None
    except ValueError:
        raise ValueError('Data pagamento non valida.')
    values.update(cash_on_delivery=cash, payment_terms=terms)
    return values


def _validate_content(content, extension):
    try:
        if extension == '.pdf':
            import pypdfium2
            if not content.startswith(b'%PDF-'):
                raise ValueError()
            with pypdfium2.PdfDocument(content) as reader:
                if not len(reader):
                    raise ValueError()
        elif extension in ('.jpg', '.jpeg', '.png', '.webp'):
            from PIL import Image
            with Image.open(BytesIO(content)) as image:
                if image.format != {'.jpg': 'JPEG', '.jpeg': 'JPEG', '.png': 'PNG', '.webp': 'WEBP'}[extension]:
                    raise ValueError()
                image.verify()
        elif extension in ('.docx', '.xlsx'):
            with zipfile.ZipFile(BytesIO(content)) as archive:
                if sum(i.file_size for i in archive.infolist()) > 100 * 1024 * 1024:
                    raise ValueError()
                main = 'word/document.xml' if extension == '.docx' else 'xl/workbook.xml'
                expected = ('application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'
                            if extension == '.docx' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml')
                types = ElementTree.fromstring(archive.read('[Content_Types].xml'))
                if not any(e.get('PartName') == '/' + main and e.get('ContentType') == expected for e in types):
                    raise ValueError()
                if any('vbaProject' in name for name in archive.namelist()):
                    raise ValueError()
                document = ElementTree.fromstring(archive.read(main))
                expected_root = ('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}document'
                                 if extension == '.docx' else '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}workbook')
                strict_root = ('{http://purl.oclc.org/ooxml/wordprocessingml/main}document'
                               if extension == '.docx' else '{http://purl.oclc.org/ooxml/spreadsheetml/main}workbook')
                if document.tag not in (expected_root, strict_root):
                    raise ValueError()
                if archive.testzip():
                    raise ValueError()
        else:
            # Legacy Office compound files: check directory stream names as well
            # as the container header (a renamed arbitrary file is not accepted).
            if len(content) < 512 or content[:8] != bytes.fromhex('d0cf11e0a1b11ae1'):
                raise ValueError()
            import olefile
            with olefile.OleFileIO(BytesIO(content)) as document:
                streams = document.listdir()
                if extension == '.doc':
                    valid = ['WordDocument'] in streams and (['0Table'] in streams or ['1Table'] in streams)
                else:
                    valid = ['Workbook'] in streams or ['Book'] in streams
                if not valid:
                    raise ValueError()
                if extension == '.doc':
                    if document.openstream('WordDocument').read(2) != b'\xec\xa5':
                        raise ValueError()
                elif document.openstream('Workbook' if ['Workbook'] in streams else 'Book').read(2) not in (b'\x09\x08', b'\x09\x04', b'\x09\x02', b'\x09\x00'):
                    raise ValueError()
    except Exception as exc:
        raise ValueError('Contenuto del file non valido per il formato dichiarato.') from exc


def validate_attachments(payload, card):
    removed = payload.get('remove_attachment_ids', [])
    if not isinstance(removed, list) or any(type(i) is not int for i in removed) or len(set(removed)) != len(removed):
        raise ValueError('Allegati da rimuovere non validi.')
    existing = {item.id: item for item in card.attachments}
    if not set(removed).issubset(existing):
        raise ValueError('Allegato non appartenente alla scheda.')
    uploads = request.files.getlist('files')
    retained = [item for item in card.attachments if item.id not in removed]
    if len(retained) + len(uploads) > 10:
        raise ValueError('Massimo 10 allegati per scheda.')
    total = sum(item.size for item in retained)
    additions = []
    for upload in uploads:
        filename = PurePath((upload.filename or '').replace('\\', '/')).name
        extension = PurePath(filename).suffix.lower()
        if not filename or len(filename) > 200 or any(ord(c) < 32 for c in filename) or extension not in TYPES:
            raise ValueError('Formato allegato non consentito o nome non valido.')
        content = upload.stream.read(MAX_FILE + 1)
        if not content or len(content) > MAX_FILE:
            raise ValueError('Ogni allegato deve contenere dati e non superare 10 MB.')
        total += len(content)
        if total > MAX_TOTAL:
            raise ValueError('Massimo 50 MB di allegati per scheda.')
        _validate_content(content, extension)
        additions.append(SupplierBoardAttachment(filename=filename, mimetype=TYPES[extension], size=len(content), content=content))
    return retained, additions
