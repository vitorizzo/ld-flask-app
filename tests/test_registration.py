"""Public registration regressions, isolated from production DB and SMTP."""
from datetime import date
from pathlib import Path
import re,unittest
from unittest.mock import patch
from flask import Flask,g
from flask_login import LoginManager
from jinja2 import ChoiceLoader,DictLoader,FileSystemLoader
from sqlalchemy.exc import OperationalError,IntegrityError
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from werkzeug.security import check_password_hash,generate_password_hash
from extensions import db
from models import User,Role,UserRole,RoleActivationRequest,SupportTicket,SupportTicketMessage,SupportTicketAttachment
from routes.auth import auth_bp


@compiles(JSONB,'sqlite')
def jsonb_sqlite(type_,compiler,**kw):return 'JSON'


class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__)
        self.app.config.update(TESTING=True,SECRET_KEY='registration-test',SQLALCHEMY_DATABASE_URI='sqlite://',WTF_CSRF_ENABLED=False)
        self.app.jinja_loader=ChoiceLoader([DictLoader({'base.html':"{% block extra_css %}{% endblock %}{% for category,message in get_flashed_messages(with_categories=true) %}<p>{{ message }}</p>{% endfor %}{% block content %}{% endblock %}"}),FileSystemLoader('templates')])
        self.app.jinja_env.globals['app_version']='test'
        db.init_app(self.app);self.app.register_blueprint(auth_bp)
        self.app.add_url_rule('/',endpoint='home',view_func=lambda:'Home')
        login=LoginManager(self.app);login.user_loader(lambda uid:db.session.get(User,int(uid)))
        self.ctx=self.app.app_context();self.ctx.push()
        db.metadata.create_all(db.engine,tables=[m.__table__ for m in [User,Role,UserRole,RoleActivationRequest,SupportTicket,SupportTicketMessage,SupportTicketAttachment]])
        db.session.add(Role(id=1,name='customer',weight=10));db.session.commit()
        self.client=self.app.test_client()
        self.mail_patch=patch('routes.auth.send_assistance_mail');self.mail=self.mail_patch.start();self.addCleanup(self.mail_patch.stop)
        self.sender_patch=patch('routes.auth.assistance_mail_sender',return_value='assistance@example.invalid');self.sender_patch.start();self.addCleanup(self.sender_patch.stop)

    def tearDown(self):
        db.session.remove();self.ctx.pop()

    def data(self,**extra):
        data=dict(name='Mario',surname='Rossi',email='mario@example.it',password='safe-test-password',confirm_password='safe-test-password',phone='3331234567',birth_date='',city='Roma',province='RM',sex='0')
        data.update(extra);return data

    def post(self,**extra):return self.client.post('/auth/register',data=self.data(**extra))

    def test_registration_without_birth_date_succeeds(self):
        response=self.post();self.assertEqual(response.status_code,302);self.assertTrue(response.location.endswith('/auth/login'))
        user=User.query.one();self.assertIsNone(user.birth_date);self.assertTrue(check_password_hash(user.password,'safe-test-password'))
        self.assertEqual(user.max_role_weight,10);self.assertEqual(UserRole.query.one().type,'lifetime');self.mail.assert_not_called()

    def test_registration_with_birth_date_and_trimmed_fields(self):
        self.assertEqual(self.post(name=' Mario ',email=' Mario@Example.IT ',birth_date='1985-05-12').status_code,302)
        user=User.query.one();self.assertEqual(user.email,'mario@example.it');self.assertEqual(user.name,'Mario');self.assertEqual(user.birth_date,date(1985,5,12))

    def test_invalid_fields_visible_and_entered_data_preserved(self):
        response=self.post(phone='123',confirm_password='different',birth_date='not-a-date')
        html=response.get_data(as_text=True)
        self.assertEqual(response.status_code,200);self.assertIn('registrationErrors',html)
        for text in ['Il telefono deve contenere','Le password non coincidono','Scegli una data valida','value="Mario"','aria-invalid="true"']:
            self.assertIn(text,html)
        self.assertNotIn('value="safe-test-password"',html);self.assertEqual(User.query.count(),0)

    def test_email_duplicate_is_case_insensitive_and_keeps_form(self):
        db.session.add(User(name='Existing',surname='User',email='MARIO@EXAMPLE.IT',password='test'));db.session.commit()
        response=self.post(email=' Mario@example.it ');html=response.get_data(as_text=True)
        self.assertEqual(response.status_code,200);self.assertIn('Email già registrata',html);self.assertIn('Recupera la password',html)
        self.assertEqual(User.query.count(),1)

    def test_email_limit_is_checked_before_database(self):
        response=self.post(email='a'*64+'@'+'b'*60+'.'+'c'*30+'.it')
        self.assertIn('al massimo 150 caratteri',response.get_data(as_text=True));self.assertEqual(User.query.count(),0)

    def test_horeca_request_is_committed_before_email(self):
        observed=[]
        def send(message):
            observed.append((User.query.count(),SupportTicket.query.count(),SupportTicketMessage.query.count(),len(db.session.new)))
        self.mail.side_effect=send
        response=self.post(merchant_request='y');self.assertEqual(response.status_code,302);self.mail.assert_called_once()
        self.assertEqual(observed,[(1,1,1,0)])
        self.assertEqual(RoleActivationRequest.query.one().requested_role,'customer_horeca')
        self.assertEqual(UserRole.query.one().role.name,'customer')

    def test_smtp_or_sender_failure_does_not_cancel_registration(self):
        self.mail.side_effect=RuntimeError('private smtp diagnostic')
        response=self.post(merchant_request='y');self.assertEqual(response.status_code,302)
        self.assertEqual(User.query.count(),1);self.assertEqual(RoleActivationRequest.query.count(),1);self.assertEqual(SupportTicket.query.count(),1)
        with self.client.session_transaction() as session:self.assertTrue(any('Registrazione completata' in msg for _,msg in session['_flashes']))
        self.assertNotIn('private smtp diagnostic',response.get_data(as_text=True))

    def test_sender_configuration_failure_is_also_non_blocking(self):
        with patch('routes.auth.assistance_mail_sender',side_effect=RuntimeError('config failure')):
            response=self.post(merchant_request='y')
        self.assertEqual(response.status_code,302);self.assertEqual(User.query.count(),1);self.assertEqual(SupportTicketMessage.query.count(),1)

    def test_database_failure_rolls_back_and_renders_useful_message(self):
        with patch.object(db.session,'commit',side_effect=OperationalError('insert',{},RuntimeError('secret db detail'))):
            response=self.post(merchant_request='y')
        html=response.get_data(as_text=True);self.assertEqual(response.status_code,200);self.assertIn('momentaneamente non disponibile',html)
        self.assertNotIn('secret db detail',html)
        self.assertEqual(User.query.count(),0);self.assertEqual(SupportTicket.query.count(),0);self.mail.assert_not_called()

    def test_integrity_error_is_handled_without_500(self):
        with patch.object(db.session,'commit',side_effect=IntegrityError('insert',{},RuntimeError('constraint failure'))):
            response=self.post()
        self.assertEqual(response.status_code,200);self.assertIn('Registrazione non completata',response.get_data(as_text=True));self.assertEqual(User.query.count(),0)

    def test_missing_customer_role_is_reported_without_creating_user(self):
        db.session.delete(db.session.get(Role,1));db.session.commit()
        response=self.post();self.assertEqual(response.status_code,200);self.assertIn('momentaneamente non disponibile',response.get_data(as_text=True));self.assertEqual(User.query.count(),0)

    def test_csrf_error_visible_and_new_token_can_be_submitted(self):
        self.app.config['WTF_CSRF_ENABLED']=True
        response=self.post();html=response.get_data(as_text=True)
        self.assertIn('sessione del modulo è scaduta',html);self.assertEqual(User.query.count(),0)
        token=re.search(r'name="csrf_token"[^>]*value="([^"]+)"',html).group(1)
        self.assertEqual(self.post(csrf_token=token).status_code,302)

    def test_login_accepts_email_case_and_whitespace(self):
        self.post()
        g.pop('_login_user',None)
        response=self.client.post('/auth/login',data=dict(email=' MARIO@EXAMPLE.IT ',password='safe-test-password'))
        self.assertEqual(response.status_code,302)
        with self.client.session_transaction() as session:self.assertIn('_user_id',session)

    def test_registration_logging_contains_only_field_names_and_ids(self):
        with self.assertLogs('auth',level='INFO') as captured:
            self.post(email='private@example.it',phone='123',password='do-not-log-this',confirm_password='different')
        text=' '.join(captured.output);self.assertIn('fields=confirm_password,phone',text)
        for secret in ['private@example.it','do-not-log-this','<form','csrf_token value']:
            self.assertNotIn(secret,text)
