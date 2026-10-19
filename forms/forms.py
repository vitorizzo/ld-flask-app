from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField, BooleanField, IntegerField, \
    HiddenField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional
from tools.log_utils import get_logger
from wtforms.fields import DateField
from datetime import date


logger = get_logger('forms')
logger.info("Form caricati.")


def _strip_text(value):
    return value.strip() if isinstance(value,str) else value


def _normalize_email(value):
    return value.strip().lower() if isinstance(value,str) else value


class RegistrationForm(FlaskForm):
    name = StringField('Nome', filters=[_strip_text], validators=[DataRequired(message='Inserisci il nome.'), Length(min=2,max=150,message='Il nome deve contenere da 2 a 150 caratteri.')])
    surname = StringField('Cognome', filters=[_strip_text], validators=[DataRequired(message='Inserisci il cognome.'), Length(min=2,max=150,message='Il cognome deve contenere da 2 a 150 caratteri.')])
    email = StringField('Email', filters=[_normalize_email], validators=[DataRequired(message='Inserisci l’email.'), Length(max=150,message='L’email può contenere al massimo 150 caratteri.'), Email(message='Inserisci un indirizzo email valido.')])
    password = PasswordField('Password', validators=[DataRequired(message='Inserisci la password.'), Length(min=6,message='La password deve contenere almeno 6 caratteri.')])
    confirm_password = PasswordField('Conferma password', validators=[DataRequired(message='Conferma la password.'), EqualTo('password',message='Le password non coincidono.')])
    phone = StringField('Telefono', filters=[_strip_text], validators=[DataRequired(message='Inserisci il telefono.'), Length(min=8,max=20,message='Il telefono deve contenere da 8 a 20 caratteri.')])
    birth_date = DateField('Data di nascita (facoltativa)', format='%Y-%m-%d', validators=[Optional()], render_kw={'aria-describedby':'birth_date-help'})
    city = StringField('Città di residenza', filters=[_strip_text], validators=[DataRequired(message='Inserisci la città di residenza.'), Length(max=100,message='La città può contenere al massimo 100 caratteri.')])
    province = StringField('Provincia', filters=[_strip_text], validators=[DataRequired(message='Inserisci la provincia.'), Length(max=50,message='La provincia può contenere al massimo 50 caratteri.')])
    sex = SelectField('Sesso', choices=[('0','Neutro'),('1','Maschio'),('2','Femmina')], validators=[DataRequired(message='Scegli una voce.')])
    merchant_request = BooleanField('Esercente')
    submit = SubmitField('Registrati')


class LoginForm(FlaskForm):
    email = StringField('Email', filters=[_normalize_email], validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Ricordami')
    submit = SubmitField('Accedi')


class EditProfileForm(FlaskForm):
    name = StringField('Nome', validators=[DataRequired(), Length(min=2, max=150)])
    surname = StringField('Cognome', validators=[DataRequired(), Length(min=2, max=150)])
    phone = StringField('Telefono', validators=[Length(min=8, max=20)])
    birth_date = DateField('Data di Nascita', format='%Y-%m-%d')
    city = StringField('Città', validators=[Length(max=100)])
    province = StringField('Provincia', validators=[Length(max=50)])
    sex = SelectField('Sesso', choices=[('0', 'Neutro'), ('1', 'Maschio'), ('2', 'Femmina')])
    submit = SubmitField('Salva Modifiche')


class InventarioForm(FlaskForm):
    barcode_articolo = StringField("Barcode")
    descrizione_articolo = StringField("Descrizione", validators=[Optional()])
    quantita_inserita = IntegerField("Quantità Inserita")
    num_pedane = IntegerField("N. Pedane", default=0)
    num_cartoni = IntegerField("N. Cartoni", default=0)
    num_pezzi_sciolti = IntegerField("N. Pezzi Sciolti", default=0)
    data_inventario = DateField("Data Inventario", default=date.today)
    deposito = SelectField("Deposito", choices=[("000", "Negozio"), ("400", "Online")], default="000")

    # 👇 Aggiungi questi nuovi campi
    cod_art = StringField("Codice Articolo")
    hidden_cpp = HiddenField()
    hidden_ppc = HiddenField()

    calcola = SubmitField("Calcola")
    submit = SubmitField("Inserisci")


class ForgotPasswordForm(FlaskForm):
    email = StringField(
        "Email",
        validators=[DataRequired(), Email(message="Email non valida")]
    )
    submit = SubmitField("Invia link di reset")


class ResetPasswordForm(FlaskForm):
    password = PasswordField(
        "Nuova password",
        validators=[DataRequired(), Length(min=8, message="Minimo 8 caratteri")]
    )
    confirm_password = PasswordField(
        "Conferma password",
        validators=[
            DataRequired(),
            EqualTo("password", message="Le password non coincidono")
        ]
    )
    submit = SubmitField("Imposta nuova password")
