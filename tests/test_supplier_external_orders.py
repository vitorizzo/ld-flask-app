import importlib.util
import json
import unittest
import zipfile
import struct
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image
from sqlalchemy import create_engine, inspect, text
from alembic.migration import MigrationContext
from alembic.operations import Operations
from extensions import db
from models import SupplierBoardCard, SupplierBoardAttachment, SupplierOrderGroup
import test_supplier_board as board_tests


def image(format='PNG'):
    stream = BytesIO(); Image.new('RGB', (4, 4), 'blue').save(stream, format=format)
    return stream.getvalue()


def office(extension):
    main = 'word/document.xml' if extension == 'docx' else 'xl/workbook.xml'
    content_type = ('application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'
                    if extension == 'docx' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml')
    stream = BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        archive.writestr('[Content_Types].xml', f'<Types><Override PartName="/{main}" ContentType="{content_type}"/></Types>')
        archive.writestr(main, '<document xmlns="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>' if extension == 'docx' else '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>')
    return stream.getvalue()


def legacy_office(extension):
    """Small valid compound container with regular 4096-byte Office streams."""
    streams=[('WordDocument',b'\xec\xa5'),('1Table',b'\x00')] if extension=='doc' else [('Workbook',b'\x09\x08')]
    end, free = 0xfffffffe, 0xffffffff
    header=bytearray(512);header[:8]=bytes.fromhex('d0cf11e0a1b11ae1')
    struct.pack_into('<HHHHH',header,24,0x3e,3,0xfffe,9,6)
    struct.pack_into('<IIIIIIIII',header,40,0,1,1,0,4096,end,0,end,0)
    struct.pack_into('<109I',header,76,0,*([free]*108))
    fat=[free]*128;fat[0]=0xfffffffd;fat[1]=end
    def entry(name,type_,start,size,right=free,child=free):
        data=bytearray(128);name=(name+'\0').encode('utf-16le');data[:len(name)]=name
        struct.pack_into('<HBBIII',data,64,len(name),type_,1,free,right,child)
        struct.pack_into('<IQ',data,116,start,size);return data
    directory=entry('Root Entry',5,end,0,child=1)
    for index,(name,signature) in enumerate(streams):
        start=2+index*8
        for sector in range(start,start+8):fat[sector]=sector+1 if sector<start+7 else end
        directory+=entry(name,2,start,4096,right=index+2 if index+1<len(streams) else free)
    directory+=bytes(512-len(directory))
    return bytes(header)+struct.pack('<128I',*fat)+directory+b''.join(signature+bytes(4096-len(signature)) for _,signature in streams)


class ExternalOrderTests(unittest.TestCase):
    def setUp(self):
        board_tests.SupplierBoardTests.setUp(self)
        db.metadata.create_all(db.engine, tables=[SupplierOrderGroup.__table__])
        db.session.add_all([SupplierOrderGroup(id=1, name='Caffe'), SupplierOrderGroup(id=2, name='Altro')])
        db.session.commit()

    tearDown = board_tests.SupplierBoardTests.tearDown

    def save(self, payload=None, files=(), card=None, external=False):
        body = dict(title='Ordine esterno', column_id=1)
        body.update(payload or {})
        url = '/supplier-orders/groups/1/external-orders' if external else '/supplier-orders/api/board/cards'
        if card:
            url += '/' + str(card['id'])
            body.setdefault('revision', card['order_revision'])
        return self.client.open(url, method='PUT' if card else 'POST', data={
            'data': json.dumps(body), 'files': [(BytesIO(content), name) for name, content in files]},
            content_type='multipart/form-data')

    def test_external_link_payment_retry_and_editor_protection(self):
        payload=dict(client_key='external-request-key-123', supplier_id=1, column_id=2,
                     order_text='Ordine telefonico', transmission_notes='Contattare il referente',
                     cash_on_delivery=True, payment_terms='other', payment_terms_other='Alla consegna', payment_date='2026-11-01')
        result=self.save(payload, [('documento.png',image())], external=True)
        self.assertEqual(result.status_code,201); card=result.json['card']
        self.assertEqual((card['order_group_id'],card['column_id'],card['order_kind']),(1,2,'external'))
        self.assertIsNone(card['order_edit_url']);self.assertIsNone(card['order_pdf_url']);self.assertEqual(card['order_lines'],[])
        self.assertIn('card_id='+str(card['id']),result.json['board_url'])
        self.assertEqual(card['payment_date'],'2026-11-01');self.assertTrue(card['cash_on_delivery'])
        retry=self.save(payload, [('documento.png',image())], external=True)
        self.assertEqual(retry.status_code,200);self.assertTrue(retry.json['replayed'])
        self.assertEqual(SupplierBoardCard.query.count(),1);self.assertEqual(SupplierBoardAttachment.query.count(),1)
        self.assertEqual(self.client.get(f"/supplier-orders/groups/1/order-editor?card_id={card['id']}").status_code,400)
        with patch('routes.supplier_orders._expanded_articles_for_group',return_value=[]):
            self.assertEqual(self.client.post('/supplier-orders/groups/1/orders',json=dict(card_id=card['id'],revision=1)).status_code,400)
        edited=self.save(dict(title='Titolo nuovo'),card=card)
        self.assertEqual(edited.status_code,200);self.assertEqual(edited.json['card']['title'],'Titolo nuovo')
        self.assertEqual(self.client.post('/supplier-orders/groups/2/external-orders',json=payload).status_code,409)

    def test_manual_optional_order_and_files(self):
        result=self.save();self.assertEqual(result.status_code,201)
        self.assertEqual(result.json['card']['order_kind'],'manual');self.assertEqual(result.json['card']['attachments'],[])
        self.assertEqual(result.json['card']['order_text'],'');self.assertFalse(result.json['card']['cash_on_delivery'])

    def test_payment_validation(self):
        for invalid in [dict(cash_on_delivery=True),dict(cash_on_delivery='yes'),dict(payment_terms='invalid'),
                        dict(payment_terms='other'),dict(payment_date='2026-02-30'),dict(payment_date=2026),
                        dict(order_text=[]),dict(transmission_notes='x'*40001)]:
            with self.subTest(invalid=invalid):self.assertEqual(self.save(invalid).status_code,400)
        self.assertEqual(SupplierBoardCard.query.count(),0)
        for term in ['sight','month_end','30','60','90']:
            self.assertEqual(self.save(dict(cash_on_delivery=True,payment_terms=term)).status_code,201)
        self.assertEqual(self.save(dict(payment_terms='other',payment_terms_other='Bonifico')).status_code,201)

    def test_multiple_formats_download_permissions_and_replace(self):
        from reportlab.pdfgen import canvas
        stream=BytesIO();pdf=canvas.Canvas(stream);pdf.drawString(10,10,'Ordine');pdf.save()
        files=[('ordine.pdf',stream.getvalue()),('foto.jpg',image('JPEG')),('foto.png',image()),
               ('foto.webp',image('WEBP')),('ordine.docx',office('docx')),('ordine.xlsx',office('xlsx'))]
        result=self.save(files=files);self.assertEqual(result.status_code,201);card=result.json['card']
        self.assertEqual(len(card['attachments']),6)
        for attachment, (_,content) in zip(card['attachments'],files):
            download=self.client.get(attachment['url']);self.assertEqual(download.data,content)
            self.assertEqual(download.headers['Cache-Control'],'private, no-store')
            self.assertIn('attachment;',download.headers['Content-Disposition'])
            with patch('tools.role_required.get_current_user',return_value=SimpleNamespace(active_roles=[],max_role_weight=0)):
                self.assertEqual(self.client.get(attachment['url'],content_type='application/json').status_code,403)
        first=card['attachments'][0]
        self.assertEqual(self.client.get(first['url'].replace('/cards/'+str(card['id'])+'/', '/cards/999/')).status_code,404)
        replaced=self.save(dict(remove_attachment_ids=[first['id']]),files=[('nuovo.png',image())],card=card)
        self.assertEqual(replaced.status_code,200);self.assertEqual(len(replaced.json['card']['attachments']),6)
        self.assertEqual(self.client.get(first['url']).status_code,404)
        self.client.delete('/supplier-orders/api/board/cards/'+str(card['id']))
        self.assertEqual(SupplierBoardAttachment.query.count(),0)

    def test_legacy_office_formats(self):
        for extension in ['doc','xls']:
            with self.subTest(extension=extension):
                content=legacy_office(extension)
                result=self.save(files=[('ordine.'+extension,content)])
                self.assertEqual(result.status_code,201)
                self.assertEqual(self.client.get(result.json['card']['attachments'][0]['url']).data,content)
        self.assertEqual(self.save(files=[('fake.doc',legacy_office('xls'))]).status_code,400)
        self.assertEqual(self.save(files=[('fake.xls',legacy_office('doc'))]).status_code,400)

    def test_bad_upload_limits_and_rollback_preserve_original(self):
        card=self.save(files=[('originale.png',image())]).json['card']
        for files in [[('fake.pdf',b'%PDF-broken')],[('fake.png',b'bad')],[('fake.doc',b'bad')],
                      [('fake.xls',b'bad')],[('fake.docx',office('xlsx'))],[('fake.xlsx',office('docx'))],
                      [('bad.exe',image())],[('bad.jpg',image())],[('empty.pdf',b'')]]:
            with self.subTest(files=files):
                result=self.save(dict(remove_attachment_ids=[card['attachments'][0]['id']]),files=files,card=card)
                self.assertEqual(result.status_code,400)
                self.assertEqual(self.client.get(card['attachments'][0]['url']).data,image())
                self.assertEqual(db.session.get(SupplierBoardCard,card['id']).order_revision,1)
        self.assertEqual(self.save(files=[('x.png',image())]*10,card=card).status_code,400)
        with patch('tools.supplier_card_files.MAX_FILE',10):
            self.assertEqual(self.save(files=[('x.png',image())],card=card).status_code,400)
        with patch('tools.supplier_card_files.MAX_TOTAL',len(image())*2-1):
            self.assertEqual(self.save(files=[('x.png',image())],card=card).status_code,400)
        self.assertEqual(self.save(dict(remove_attachment_ids=[999]),card=card).status_code,400)
        with patch.object(db.session,'commit',side_effect=RuntimeError('database unavailable')):
            with self.assertLogs(level='ERROR'):
                self.assertEqual(self.save(dict(remove_attachment_ids=[card['attachments'][0]['id']]),card=card).status_code,500)
        self.assertEqual(self.client.get(card['attachments'][0]['url']).status_code,200)

    def test_revision_conflict_preserves_files(self):
        card=self.save(files=[('originale.png',image())]).json['card']
        changed=self.save(dict(order_text='Nuovo'),card=card).json['card']
        stale=self.save(dict(remove_attachment_ids=[card['attachments'][0]['id']]),files=[('secondo.png',image())],card=card)
        self.assertEqual(stale.status_code,409);self.assertEqual(SupplierBoardAttachment.query.count(),1)
        self.assertEqual(self.client.put('/supplier-orders/api/board/cards/'+str(card['id']),json=dict(order_text='Stale')).status_code,409)
        self.assertEqual(changed['order_revision'],2)

    def test_new_migration_preserves_existing_and_create_all(self):
        path=Path(__file__).resolve().parents[1]/'migrations/versions/v7e8f9a0b1c2_supplier_external_orders.py'
        spec=importlib.util.spec_from_file_location('external_migration',path)
        migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
        engine=create_engine('sqlite://')
        with engine.begin() as connection:
            connection.execute(text('CREATE TABLE supplier_board_cards (id INTEGER PRIMARY KEY, title TEXT, order_pdf BLOB)'))
            connection.execute(text("INSERT INTO supplier_board_cards VALUES (1,'Preesistente',X'1234')"))
            migration.op=Operations(MigrationContext.configure(connection))
            with patch('tools.supplier_migration_compat.op',migration.op):
                migration.upgrade();migration.upgrade()
            row=connection.execute(text('SELECT title, order_pdf, cash_on_delivery, is_external_order, order_text FROM supplier_board_cards')).one()
            self.assertEqual(tuple(row),('Preesistente',bytes.fromhex('1234'),0,0,None))
            migration.downgrade();self.assertNotIn('supplier_board_attachments',inspect(connection).get_table_names())
        # Same upgrade on current model tables pre-created by create_all.
        with db.engine.begin() as connection:
            migration.op=Operations(MigrationContext.configure(connection))
            with patch('tools.supplier_migration_compat.op',migration.op):migration.upgrade()


if __name__ == '__main__':
    unittest.main()
