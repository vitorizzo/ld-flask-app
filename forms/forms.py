from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, DateField, SelectField, BooleanField
from wtforms.validators import DataRequired, Email, EqualTo, Length


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
    sex = SelectField('Sesso', choices=[('0', 'Neutro'), ('1', 'Maschio'), ('2', 'Femmina')], validators=[DataRequired()])
    submit = SubmitField('Registrati')


class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Ricordami')  # Nuovo campo
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
