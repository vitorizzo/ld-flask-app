import os

from flask import Flask
from flask_migrate import Migrate
from dotenv import load_dotenv
from extensions import db

# Determina la root del progetto (supponendo che questo file sia in tools/)
project_root = os.path.dirname(os.path.dirname(__file__))

dotenv_path = os.path.join(project_root, ".env")
dotenvlocal_path = os.path.join(project_root, ".env.local")
dotenvdefaults_path = os.path.join(project_root, ".env.defaults")
print("DEBUG: Cerco di caricare il file:", dotenv_path)

# Carica prima `.env`, poi `.env.local` (se esiste), poi `.env.default`
load_dotenv(dotenv_path, override=False)
load_dotenv(dotenvlocal_path, override=True)
load_dotenv(dotenvdefaults_path, override=False)


EXPORT_FOLDER = os.getenv("EXPORT_FOLDER")
EXPORT_FOLDER_URL = os.getenv("EXPORT_FOLDER_URL")
UPLOAD_FOLDER = os.path.normpath(os.path.join(os.getcwd(), 'ld-flask-app', 'static', 'uploads'))
SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL')
SQLALCHEMY_TRACK_MODIFICATIONS = False
print("DATABASE_URL:", SQLALCHEMY_DATABASE_URI)


def create_app():
    newapp = Flask(
        __name__,
        static_folder=os.path.join(project_root, "static"),
        template_folder=os.path.join(project_root, "templates")
    )
    newapp.config.update(
        SECRET_KEY=os.getenv('SECRET_KEY', 'fallback_key'),
        EXPORT_FOLDER=EXPORT_FOLDER,
        EXPORT_FOLDER_URL=EXPORT_FOLDER_URL,
        UPLOAD_FOLDER=UPLOAD_FOLDER,
        SQLALCHEMY_DATABASE_URI=SQLALCHEMY_DATABASE_URI,
        SQLALCHEMY_TRACK_MODIFICATIONS=SQLALCHEMY_TRACK_MODIFICATIONS,
        CELERY_BROKER_URL='redis://localhost:6379/0',
        CELERY_RESULT_BACKEND='redis://localhost:6379/0'
    )
    if not newapp.config['SQLALCHEMY_DATABASE_URI']:
        raise RuntimeError("DATABASE_URL is not set. Check your .env file.")

    db.init_app(newapp)

    # Inizializzazione estensioni
    migrate = Migrate(newapp, db)

    # Inizializza le estensioni, registra blueprint, etc.
    return newapp
