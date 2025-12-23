from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, session
from flask_login import current_user, login_user, logout_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from extensions import db
from forms.forms import LoginForm, RegistrationForm, EditProfileForm
from tools.auth_manager import get_current_user, get_current_user_id
from models import User
from tools.log_utils import log_task, get_logger
import os
from PIL import Image
import shutil

logger = get_logger('auth')

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}


# @auth_bp.app_context_processor
# def inject_user():
#     from flask_login import current_user
#     return {'current_user': current_user}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@auth_bp.route('/register', methods=['GET', 'POST'])
@log_task(logger)
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            flash("Email già registrata. Usa un'altra email.", 'danger')
            return redirect(url_for('auth.register'))
        hashed_password = generate_password_hash(form.password.data)
        new_user = User(
            name=form.name.data,
            surname=form.surname.data,
            email=form.email.data,
            password=hashed_password,
            phone=form.phone.data,
            birth_date=form.birth_date.data,
            city=form.city.data,
            province=form.province.data,
            sex=int(form.sex.data)
        )
        db.session.add(new_user)
        db.session.commit()
        flash('Registrazione completata! Ora puoi effettuare il login.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('register.html', form=form)


@auth_bp.route('/login', methods=['GET', 'POST'])
@log_task(logger)
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and check_password_hash(user.password, form.password.data):
            # login_user(user, remember=form.remember.data)
            login_user(user, remember=False)

            next_page = request.args.get('next')
            if next_page and next_page.startswith('/'):
                response = redirect(next_page)
            else:
                response = redirect(url_for('home'))

            # LOG: cosa stiamo mandando come cookie?
            logger.info("LOGIN RESPONSE Set-Cookie: %s", response.headers.getlist('Set-Cookie'))

            return response
        flash('Credenziali errate.', 'danger')
    return render_template('login.html', form=form)


@auth_bp.route('/reset_password', methods=['GET', 'POST'])
@log_task(logger)
def reset_password():
    return render_template('reset_password.html')


@auth_bp.route('/edit_profile', methods=['GET', 'POST'])
@log_task(logger)
def edit_profile():
    user = get_current_user()
    logger.info(f"Utente attuale: {user}, Foto profilo: {user.foto_profilo}")
    form = EditProfileForm(obj=user)
    if form.validate_on_submit():
        user.name = form.name.data
        user.surname = form.surname.data
        user.phone = form.phone.data
        user.birth_date = form.birth_date.data
        user.city = form.city.data
        user.province = form.province.data
        user.sex = int(form.sex.data)
        db.session.commit()
        flash('Profilo aggiornato con successo!', 'success')
        return redirect(url_for('home'))
    return render_template('edit_profile.html', form=form)


@auth_bp.route('/upload_photo', methods=['GET', 'POST'])
@log_task(logger)
def upload_photo():

    if request.method == 'POST':
        file = request.files.get('photo')
        logger.info(f"File ricevuto: {file}")
        if file and allowed_file(file.filename):
            user_id = get_current_user_id()

            base_upload_folder = current_app.config['UPLOAD_FOLDER']
            user_folder = os.path.join(base_upload_folder, f"user_{user_id}").replace('\\', '/')
            logger.info(f"Cartella utente: {user_folder}")
            if not os.path.exists(user_folder):
                os.makedirs(user_folder)
            filename = secure_filename(f"profile_{len(os.listdir(user_folder)) + 1}.jpg")
            filepath = os.path.join(user_folder, filename).replace("\\", "/")
            file.save(filepath)
            try:
                img = Image.open(filepath)
                img = img.convert("RGB")
                img.thumbnail((150, 150))
                img.save(filepath, "JPEG")
            except Exception as e:
                logger.exception("Errore nel ridimensionamento immagine")
                flash("Errore durante il caricamento dell'immagine. Riprova.", "danger")
                return redirect(url_for('auth.upload_photo'))
            web_path = f"static/uploads/user_{user_id}/{filename}"
            user = get_current_user()
            user.foto_profilo = web_path
            db.session.commit()
            logger.info(f"Foto salvata: {web_path}")
            flash("Foto profilo aggiornata con successo.", "success")
            return redirect(url_for('auth.upload_photo'))
        flash("File non valido. Usa estensioni: jpg, jpeg, png, gif.", "danger")
    return render_template('upload_photo.html')


@auth_bp.route('/delete_photo', methods=['POST'])
@log_task(logger)
def delete_photo():
    user = get_current_user()
    user_id = user.id

    user_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], f"user_{user_id}")
    if user.foto_profilo:
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], current_user.foto_profilo)
        if os.path.exists(filepath):
            os.remove(filepath)
        current_user.foto_profilo = None
        db.session.commit()
        flash('Foto profilo eliminata con successo!', 'success')
        return redirect(url_for('home'))
    else:
        flash('Nessuna foto profilo da eliminare.', 'warning')
    return redirect(url_for('auth.upload_photo'))


def delete_user_folder(user_id):
    user_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], f"user_{user_id}")
    if os.path.exists(user_folder):
        shutil.rmtree(user_folder)


@auth_bp.route('/delete_user', methods=['POST'])
@log_task(logger)
def delete_user():
    user = get_current_user()
    user_id = user.id
    db.session.delete(user)
    db.session.commit()
    delete_user_folder(user_id)
    flash('Account eliminato con successo.', 'success')
    return redirect(url_for('auth.logout'))


# @auth_bp.route('/logout', methods=['GET'])
# @log_task(logger)
# def logout():
#     logout_user()
#
#     # session.clear()
#
#     session.pop('_user_id', None)
#     session.pop('remember', None)
#     session.pop('remember_token', None)
#
#     # Rimuove cookie remember se presente
#     resp = redirect(url_for('home'))
#     resp.delete_cookie('remember_token')
#
#     flash('Logout effettuato con successo!', 'success')
#     return resp


@auth_bp.route('/logout', methods=['GET'])
@log_task(logger)
def logout():
    logout_user()
    session.clear()

    resp = redirect(url_for('home'))

    # se la tua app vive sotto /flask, questo è fondamentale
    resp.delete_cookie('remember_token', path='/flask')
    # in più, prova anche root per coprire entrambi i casi
    resp.delete_cookie('remember_token', path='/')

    flash('Logout effettuato con successo!', 'success')
    return resp
