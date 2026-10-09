import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace as NS
from unittest.mock import patch
from flask import Flask, jsonify
from flask_login import LoginManager
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB
from extensions import db
from models import CustomerAccountEntry, CustomerAccountingItemState, AppPreference
from io import BytesIO
from pypdf import PdfReader
from routes.administration import administration_bp
from routes.customer_account import customer_account_bp


@compiles(JSONB, 'sqlite')
def compile_jsonb_sqlite(type_, compiler, **kwargs):return 'JSON'


class OpenAccountApiTests(unittest.TestCase):
    def setUp(self):
        app=Flask(__name__);app.config.update(TESTING=True,SECRET_KEY='test',SQLALCHEMY_DATABASE_URI='sqlite://')
        db.init_app(app);app.register_blueprint(administration_bp,url_prefix='/admin');app.register_blueprint(customer_account_bp,url_prefix='/account')
        self.ctx=app.app_context();self.ctx.push();self.client=app.test_client()
        user=NS(id=1,is_authenticated=True,is_active=True,is_anonymous=False,max_role_weight=40,active_roles=[NS(name='office',weight=40)])
        LoginManager(app).user_loader(lambda _:user)
        with self.client.session_transaction() as session:session['_user_id']='1'
        self.patches=[]
        def mock(name,**kwargs):
            p=patch(name,**kwargs);self.patches.append(p);return p.start()
        mock('tools.role_required.get_current_user',return_value=user)
        mock('routes.administration._latest_statement_import',return_value=NS(id=1))
        mock('routes.administration._monthly_customer_credit_history',return_value=[])
        mock('routes.administration._customer_aging',return_value={'average_days':1,'buckets':[]})
        mock('routes.administration._credit_communication_contacts',return_value={})
        mock('routes.administration._credit_account_available',return_value=True)
        mock('routes.administration.get_email_account',return_value={'is_enabled':True,'default_sender':'office@example.com'})
        self.send=mock('routes.administration.send_account_mail')
        mock('routes.administration.render_template',side_effect=lambda name,**ctx:jsonify(ids=[row.id for row in ctx['entries'].items],count=ctx['entries'].total,balance=str(ctx['totals'].balance)))
        db.metadata.create_all(db.engine,tables=[CustomerAccountEntry.__table__,CustomerAccountingItemState.__table__,AppPreference.__table__])
        for id,amount,reason,relevant,number in [(1,'341.38','001',True,'890'),(2,'341.38','096',False,'890'),(3,'-341.38','096',True,'890'),(4,'100','001',True,'OPEN')]:
            db.session.add(CustomerAccountEntry(id=id,import_id=1,row_number=id,source_customer_code='1066',customer_name='Cliente prova',
                document_number=number,document_date=date(2016,5,14),accounting_reason=reason,is_balance_relevant=relevant,
                accounting_side='D' if Decimal(amount)>0 else 'A',amount=abs(Decimal(amount)),signed_amount=Decimal(amount),description='DOCUMENTO '+number,source_payload={}))
        db.session.commit()

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        db.session.remove();self.ctx.pop()

    def test_detail_paginates_only_open_rows_and_preserves_balance(self):
        response=self.client.get('/admin/customer-credit/1066')
        self.assertEqual(response.status_code,200);self.assertEqual(response.json,dict(ids=[4],count=1,balance='100.00'))
        self.assertEqual(CustomerAccountEntry.query.count(),4)

    def test_statement_and_reminder_preview_exclude_technical_and_closed_documents(self):
        for kind in ['statement','reminder']:
            response=self.client.post('/admin/customer-credit/1066/communications',json=dict(action='preview',kind=kind,channel='email',test_mode=True,test_email='test@example.com'))
            self.assertEqual(response.status_code,200,response.json)
            import base64
            content=''.join(page.extract_text() for page in PdfReader(BytesIO(base64.b64decode(response.json['preview']['pdf_base64']))).pages)
            self.assertNotIn('DOCUMENTO 890',content);self.assertIn('DOCUMENTO OPEN',content);self.assertIn('100,00',content)
        self.send.assert_not_called()

    def test_status_change_and_payment_qr_reject_closed_invoice_from_stale_page(self):
        response=self.client.post('/admin/customer-credit/1066/item-status',data={'entry_ids':'1','status':'under_review','note':'Controllo'})
        self.assertEqual(response.status_code,400);self.assertEqual(CustomerAccountingItemState.query.count(),0)
        with patch('routes.customer_account._role_context',return_value=(False,False)),patch('routes.customer_account._authorized_registry',return_value=NS(id=1)),patch('routes.customer_account._entry_ownership_filter',return_value=CustomerAccountEntry.source_customer_code=='1066'),patch('routes.customer_account._latest_statement_import',return_value=NS(id=1)),patch('routes.customer_account._payment_instructions',return_value=NS(is_active=True,iban='TEST')),patch('routes.customer_account.is_valid_iban',return_value=True):
            response=self.client.post('/account/payments/bank-transfer/qr',json=dict(registry_id=1,entry_ids=[1]))
        self.assertEqual(response.status_code,400,response.json)
