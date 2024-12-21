from flask import Flask, render_template
from flask_login import LoginManager, current_user
from models import User
from flask_migrate import Migrate
from extensions import db  # Importa db da extensions.py
from routes.auth import auth_bp
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'fallback_key')

UPLOAD_FOLDER = os.path.join(os.getcwd(), 'ld-flask-app', 'static', 'uploads').replace("\\", "/")
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)  # Crea la cartella principale se non esiste

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Configurazione del Login Manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth.login"  # Route di login

# Configurazione database
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

if not app.config['SQLALCHEMY_DATABASE_URI']:
    raise RuntimeError("DATABASE_URL is not set. Check your .env file.")

# Inizializzazione estensioni
db.init_app(app)
migrate = Migrate(app, db)

# Registrazione Blueprint
app.register_blueprint(auth_bp, url_prefix='/auth')


@app.context_processor
def inject_user():
    return {'current_user': current_user}


@login_manager.user_loader
def load_user(user_id):
    # Funzione per caricare l'utente dalla sessione
    return User.query.get(int(user_id))


@app.route('/', methods=['GET'])
def home():
    return render_template('home.html')


@app.route('/prova', methods=['GET'])
def prova():
    return render_template('prova.html')


if __name__ == '__main__':
    app.run(debug=True)
