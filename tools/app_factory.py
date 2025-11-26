import logging
import os
from flask import Flask
from flask_migrate import Migrate
from dotenv import load_dotenv
from extensions import db
from flask_mail import Mail
from tools.log_utils import get_logger

# Root del progetto (ld-flask-app-working)
project_root = os.path.dirname(os.path.dirname(__file__))

logger = get_logger("factory")


def create_app():
    """
    Crea e configura l'app Flask.
    Questo è l'UNICO posto da cui carichiamo le variabili .env e la configurazione.
    """

    # -----------------------
    # CARICAMENTO .env
    # -----------------------
    load_dotenv(os.path.join(project_root, ".env"), override=True)
    load_dotenv(os.path.join(project_root, ".env.local"), override=True)
    load_dotenv(os.path.join(project_root, ".env.defaults"), override=False)

    # -----------------------
    # CREAZIONE APP
    # -----------------------
    app = Flask(
        __name__,
        static_folder=os.path.join(project_root, "static"),
        template_folder=os.path.join(project_root, "templates")
    )

    # -----------------------
    # CACHE CONTROL PER TUTTE LE RISPOSTE
    # -----------------------
    @app.after_request
    def no_cache(response):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    # -----------------------
    # CONFIGURAZIONE DELL'APP
    # -----------------------
    app.config.update(
        SECRET_KEY=os.getenv("SECRET_KEY", "fallback_key"),
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,

        EXPORT_FOLDER=os.getenv("EXPORT_FOLDER"),
        EXPORT_FOLDER_URL=os.getenv("EXPORT_FOLDER_URL"),
        UPLOAD_FOLDER=os.path.join(project_root, "static", "uploads"),

        MAIL_SERVER=os.getenv("MAIL_SERVER"),
        MAIL_PORT=int(os.getenv("MAIL_PORT", 25)),
        MAIL_USE_TLS=os.getenv("MAIL_USE_TLS", "false").lower() == "true",
        MAIL_USE_SSL=os.getenv("MAIL_USE_SSL", "false").lower() == "true",
        MAIL_USERNAME=os.getenv("MAIL_USERNAME"),
        MAIL_PASSWORD=os.getenv("MAIL_PASSWORD"),
        MAIL_DEFAULT_SENDER=os.getenv("MAIL_DEFAULT_SENDER"),

        FERNET_KEY=os.getenv("FERNET_KEY"),

        TRELLO_KEY=os.getenv("TRELLO_KEY"),
        TRELLO_SECRET=os.getenv("TRELLO_SECRET"),
        TRELLO_TOKEN=os.getenv("TRELLO_TOKEN"),

        CELERY_BROKER_URL="redis://localhost:6379/0",
        CELERY_RESULT_BACKEND="redis://localhost:6379/0",

        LOGS_FOLDER=os.path.join(project_root, "logs")
    )

    if not app.config["SQLALCHEMY_DATABASE_URI"]:
        logger.critical("DATABASE_URL non impostato! Verifica .env.")
        raise RuntimeError("DATABASE_URL not set in environment")

    # -----------------------
    # INIZIALIZZA DATABASE
    # -----------------------
    db.init_app(app)
    Migrate(app, db)

    # -----------------------
    # INIZIALIZZA MAIL
    # -----------------------
    Mail(app)

    # -----------------------
    # CONFIGURAZIONE LOGGING
    # -----------------------
    app.logger.handlers = []        # elimina handler flask
    app.logger.propagate = True     # lascia propagare al root
    app.logger.setLevel(logging.DEBUG)

    # aggiungo handler custom "main"
    main_handler = get_logger("main", level=logging.DEBUG, also_main_log=False)
    app.logger.addHandler(main_handler)

    logger.info("App Flask creata e configurata correttamente.")

    return app
