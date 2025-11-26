import logging
import os
from flask import Flask
from flask_migrate import Migrate
from dotenv import load_dotenv
from extensions import db
from tools.log_utils import get_logger

# Determina la root del progetto (supponendo che questo file sia in tools/)
project_root = os.path.dirname(os.path.dirname(__file__))

# Logger globale di avvio app
logger = get_logger('factory')

dotenv_path = os.path.join(project_root, ".env")
dotenvlocal_path = os.path.join(project_root, ".env.local")
dotenvdefaults_path = os.path.join(project_root, ".env.defaults")
logger.debug("Cerco di caricare il file: %s", dotenv_path)

# Caricamento environment
load_dotenv(dotenv_path, override=False)
load_dotenv(dotenvlocal_path, override=True)
load_dotenv(dotenvdefaults_path, override=False)

EXPORT_FOLDER = os.getenv("EXPORT_FOLDER")
EXPORT_FOLDER_URL = os.getenv("EXPORT_FOLDER_URL")
UPLOAD_FOLDER = os.path.normpath(os.path.join(os.getcwd(), 'ld-flask-app', 'static', 'uploads'))
SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL')
SQLALCHEMY_TRACK_MODIFICATIONS = False
PROJECT_FOLDER = os.path.dirname(os.path.abspath(__file__))
LOGS_FOLDER = os.path.join(project_root, "logs")
MAIL_SERVER = os.getenv('MAIL_SERVER')
MAIL_PORT = int(os.getenv('MAIL_PORT', 25))
MAIL_USE_TLS = os.getenv('MAIL_USE_TLS', 'false').lower() == 'true'
MAIL_USE_SSL = os.getenv('MAIL_USE_SSL', 'false').lower() == 'true'
MAIL_USERNAME = os.getenv('MAIL_USERNAME')
MAIL_PASSWORD = os.getenv('MAIL_PASSWORD')
MAIL_DEFAULT_SENDER = os.getenv('MAIL_DEFAULT_SENDER')

logger.info("DATABASE_URL rilevato: %s", SQLALCHEMY_DATABASE_URI)


def create_app():
    # Carica .env SEMPRE
    base = os.path.dirname(os.path.dirname(__file__))
    load_dotenv(os.path.join(base, ".env"), override=True)
    load_dotenv(os.path.join(base, ".env.local"), override=True)
    load_dotenv(os.path.join(base, ".env.defaults"), override=False)

    # ... creazione app, config, ecc.
    app = Flask(
        __name__,
        static_folder=os.path.join(project_root, "static"),
        template_folder=os.path.join(project_root, "templates")
    )

    @app.after_request
    def no_cache(response):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    app.config.update(
        SECRET_KEY=os.getenv('SECRET_KEY', 'fallback_key'),
        EXPORT_FOLDER=EXPORT_FOLDER,
        EXPORT_FOLDER_URL=EXPORT_FOLDER_URL,
        UPLOAD_FOLDER=UPLOAD_FOLDER,
        SQLALCHEMY_DATABASE_URI=SQLALCHEMY_DATABASE_URI,
        SQLALCHEMY_TRACK_MODIFICATIONS=SQLALCHEMY_TRACK_MODIFICATIONS,
        CELERY_BROKER_URL='redis://localhost:6379/0',
        CELERY_RESULT_BACKEND='redis://localhost:6379/0',
        PROJECT_FOLDER=PROJECT_FOLDER,
        LOGS_FOLDER=LOGS_FOLDER,
        MAIL_SERVER=MAIL_SERVER,
        MAIL_PORT=MAIL_PORT,
        MAIL_USE_TLS=MAIL_USE_TLS,
        MAIL_USE_SSL=MAIL_USE_SSL,
        MAIL_USERNAME=MAIL_USERNAME,
        MAIL_PASSWORD=MAIL_PASSWORD,
        MAIL_DEFAULT_SENDER=MAIL_DEFAULT_SENDER
    )
    if not app.config['SQLALCHEMY_DATABASE_URI']:
        logger.critical("DATABASE_URL non impostato! Verifica il file .env.")
        raise RuntimeError("DATABASE_URL is not set. Check your .env file.")

    # Inizializza database, migrate, ecc.
    db.init_app(app)
    migrate = Migrate(app, db)

    # **NUOVA CONFIGURAZIONE DI LOGGING**
    # Rimuovi gli handler di default del logger di Flask
    app.logger.handlers = []
    # Imposta la propagazione in modo che i messaggi arrivino al logger root
    app.logger.propagate = True
    # (Opzionale) Puoi anche impostare il livello di app.logger:
    app.logger.setLevel(logging.DEBUG)

    # Ora, se vuoi, aggiungi il nostro handler "main" (già creato con get_logger)
    from tools.log_utils import get_logger
    main_handler = get_logger("main", level=logging.DEBUG, also_main_log=False)
    # Aggiungilo al logger dell’app (o a quello root se preferisci)
    app.logger.addHandler(main_handler)

    logger.info("App Flask creata e database inizializzato correttamente.")

    # Registra blueprint, etc.
    # ...
    return app
