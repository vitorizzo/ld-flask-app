from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, DateField, SelectField, BooleanField, IntegerField, \
    HiddenField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional
from tools.log_utils import get_logger


logger = get_logger('forms')
logger.info("Form caricati.")


class RegistrationForm(FlaskForm):
    name = StringField('Nome', validators=[DataRequired(), Length(min=2, max=150)])
    surname = StringField('Cognome', validators=[DataRequired(), Length(min=2, max=150)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Conferma Password',
                                     validators=[DataRequired(), EqualTo('password')])
    phone = StringField('Telefono', validators=[DataRequired(), Length(min=8, max=20)])
    birth_date = DateField('Data di Nascita', format='%Y-%m-%d')
    city = StringField('Città', validators=[DataRequired(), Length(max=100)])
    province = StringField('Provincia', validators=[DataRequired(), Length(max=50)])
    sex = SelectField('Sesso', choices=[('0', 'Neutro'), ('1', 'Maschio'), ('2', 'Femmina')],
                      validators=[DataRequired()])
    submit = SubmitField('Registrati')


class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
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
    data_inventario = DateField('Data Inventario', validators=[DataRequired()])
    descrizione_articolo = StringField('Descrizione articolo', validators=[Optional()])
    barcode_articolo = StringField('Codice a barre articolo', validators=[Optional()])
    quantita_inserita = IntegerField('Quantità trovata', validators=[DataRequired()])

    # Nuovi campi per calcolo automatico
    num_pedane = IntegerField('N. Pedane', validators=[Optional()])
    num_cartoni = IntegerField('N. Cartoni', validators=[Optional()])
    num_pezzi_sciolti = IntegerField('N. Pezzi sciolti', validators=[Optional()])
    calcola = SubmitField('Calcola da formula')

    hidden_cpp = HiddenField()
    hidden_ppc = HiddenField()

    submit = SubmitField('Salva')
