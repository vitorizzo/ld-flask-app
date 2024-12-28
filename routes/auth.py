from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, g
from flask_login import current_user, login_user, logout_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from extensions import db
from forms.forms import LoginForm, RegistrationForm, EditProfileForm
from models import User
import os
from PIL import Image
import shutil
from routes.decorators import role_required


auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}


@auth_bp.app_context_processor
def inject_user():
    from flask_login import current_user
    return {'current_user': current_user}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        # Controllo se l'email è già registrata
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            flash('Email già registrata. Usa un\'altra email.', 'danger')
            return redirect(url_for('auth.register'))

        # Creazione del nuovo utente
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
            sex=int(form.sex.data)  # Converti il valore selezionato in intero
        )
        db.session.add(new_user)
        db.session.commit()

        flash('Registrazione completata! Ora puoi effettuare il login.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('register.html', form=form)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and check_password_hash(user.password, form.password.data):
            login_user(user, remember=form.remember.data)
            return redirect(url_for('home'))  # Cambia con la tua homepage
        flash('Credenziali errate.', 'danger')
    return render_template('login.html', form=form)


@auth_bp.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    return render_template('reset_password.html')


@auth_bp.route('/edit_profile', methods=['GET', 'POST'])
def edit_profile():
    print(f"Utente attuale: {current_user}, Foto profilo: {current_user.foto_profilo}")
    form = EditProfileForm(obj=current_user)
    if form.validate_on_submit():
        current_user.name = form.name.data
        current_user.surname = form.surname.data
        current_user.phone = form.phone.data
        current_user.birth_date = form.birth_date.data
        current_user.city = form.city.data
        current_user.province = form.province.data
        current_user.sex = int(form.sex.data)
        db.session.commit()
        flash('Profilo aggiornato con successo!', 'success')
#        return redirect(url_for('auth.edit_profile'))
        return redirect(url_for('home'))  # Redirect alla homepage

    return render_template('edit_profile.html', form=form)


@auth_bp.route('/upload_photo', methods=['GET', 'POST'])
# @login_required  # Attivare questa decorazione una volta confermato il funzionamento
def upload_photo():
    if request.method == 'POST':
        file = request.files.get('photo')
        print ( f"File: {file}")
        if file and allowed_file(file.filename):
            # Percorso della cartella base
            base_upload_folder = current_app.config['UPLOAD_FOLDER']
            user_folder = os.path.join(base_upload_folder, f"user_{current_user.id}").replace("\\", "/")

            # Debugging per confermare i percorsi
            print(f"Base Upload Folder: {base_upload_folder}")
            print(f"User Folder: {user_folder}")

            # Crea la cartella dell'utente se non esiste
            if not os.path.exists(user_folder):
                print (f"la directory {user_folder} non esiste: procedo con la creazione!")
                os.makedirs(user_folder)
            else:
                print (f"la directory {user_folder} esiste!")

            # Salva l'immagine con nome incrementale
            filename = secure_filename(f"profile_{len(os.listdir(user_folder)) + 1}.jpg")
            filepath = os.path.join(user_folder, filename).replace("\\", "/")

            # Debugging per confermare i file
            print(f"Filename: {filename}")
            print(f"Filepath: {filepath}")

            # Salva il file caricato
            file.save(filepath)
            try:
                # Ridimensiona e converte in JPEG
                img = Image.open(filepath)
                img = img.convert("RGB")
                img.thumbnail((150, 150))
                img.save(filepath, "JPEG")
            except Exception as e:
                print(f"Errore durante il ridimensionamento: {e}")
                flash("Errore durante il caricamento dell'immagine. Riprova.", "danger")
                return redirect(url_for('auth.upload_photo'))

            # Salva il percorso nel database
            web_path = f"static/uploads/user_{current_user.id}/{filename}"
            current_user.foto_profilo = web_path
            db.session.commit()

            print(f"Web Path salvato nel database: {web_path}")
            flash("Foto profilo aggiornata con successo.", "success")
            return redirect(url_for('auth.upload_photo'))

        flash("File non valido. Usa estensioni: jpg, jpeg, png, gif.", "danger")

    return render_template('upload_photo.html')


@auth_bp.route('/delete_photo', methods=['POST'])
def delete_photo():
    user_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], f"user_{current_user.id}")
    if current_user.foto_profilo:
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
def delete_user():
    user_id = current_user.id
    db.session.delete(current_user)
    db.session.commit()
    delete_user_folder(user_id)
    flash('Account eliminato con successo.', 'success')
    return redirect(url_for('auth.logout'))


@auth_bp.route('/logout', methods=['GET'])
def logout():
    logout_user()
    flash('Logout effettuato con successo!', 'success')
    return redirect(url_for('home'))
