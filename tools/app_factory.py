import logging
import os
import click

from flask import Flask, render_template, send_from_directory, make_response, session
from flask_login import LoginManager, current_user
from flask_migrate import Migrate
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from sqlalchemy import asc

from extensions import db, mail
from routes.automations_v2 import automations_v2_bp
from routes.kiosk import kiosk_bp
from tools.log_utils import get_logger
from models import User, Menu, PasswordResetToken
from routes.tools import get_user_menu

load_dotenv()
# Determina la root del progetto (supponendo che questo file sia in tools/)
project_root = os.path.dirname(os.path.dirname(__file__))

# PRIMA definiamo i path dei .env
# dotenv_path = os.path.join(project_root, ".env")
# dotenvlocal_path = os.path.join(project_root, ".env.local")
# dotenvdefaults_path = os.path.join(project_root, ".env.defaults")
#
# POI creiamo il logger e possiamo usare dotenv_path
# logger = get_logger('factory')
# logger.debug("Cerco di caricare il file: %s", dotenv_path)
#
# # Caricamento environment
# load_dotenv(dotenv_path, override=False)
# load_dotenv(dotenvlocal_path, override=True)
# if os.path.exists(dotenvdefaults_path):
#     load_dotenv(dotenvdefaults_path, override=False)
#
# # Logger globale di avvio app
# logger = get_logger('factory')
#
# logger.debug("Cerco di caricare il file: %s", dotenv_path)
# logger.info("DATABASE_URL rilevato: %s", SQLALCHEMY_DATABASE_URI)


def create_app():
    base = os.path.dirname(os.path.dirname(__file__))

    env_path = os.path.join(base, ".env")
    env_local_path = os.path.join(base, ".env.local")
    env_defaults_path = os.path.join(base, ".env.defaults")

    load_dotenv(env_path, override=False)
    load_dotenv(env_local_path, override=True)
    if os.path.exists(env_defaults_path):
        load_dotenv(env_defaults_path, override=False)

    logger = get_logger('factory')
    # ora che gli env sono caricati, leggi qui le variabili
    SECRET_KEY = os.getenv("SECRET_KEY"),
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
    export_folder = os.getenv("EXPORT_FOLDER")
    export_folder_url = os.getenv("EXPORT_FOLDER_URL")
    upload_folder = os.path.normpath(os.path.join(os.getcwd(), "ld-flask-app", "static", "uploads"))
    sqlalchemy_database_uri = os.getenv("DATABASE_URL")

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
        SECRET_KEY=os.getenv("SECRET_KEY"),
        EXPORT_FOLDER=export_folder,
        EXPORT_FOLDER_URL=export_folder_url,
        UPLOAD_FOLDER=upload_folder,
        SQLALCHEMY_DATABASE_URI=sqlalchemy_database_uri,
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
        MAIL_DEFAULT_SENDER=MAIL_DEFAULT_SENDER,
        PS_URL=os.getenv("PRESTASHOP_URL"),
        PS_KEY=os.getenv("PRESTASHOP_KEY"),
        PS_USER=os.getenv("PRESTASHOP_USER"),
        PS_PSWD=os.getenv("PRESTASHOP_PASSWORD"),
        FERNET_KEY=os.getenv('FERNET_KEY'),
        TRELLO_KEY=os.getenv("TRELLO_KEY"),
        TRELLO_SECRET=os.getenv("TRELLO_SECRET"),
        TRELLO_TOKEN=os.getenv("TRELLO_TOKEN"),
        SLACK_SIGNING_SECRET=os.getenv("SLACK_SIGNING_SECRET"),
        SLACK_BOT_TOKEN=os.getenv("SLACK_BOT_TOKEN"),
        VAPID_PUBLIC_KEY=os.getenv("VAPID_PUBLIC_KEY"),
        VAPID_PRIVATE_KEY=os.getenv("VAPID_PRIVATE_KEY"),
        VAPID_PRIVATE_KEY_FILE=os.getenv("VAPID_PRIVATE_KEY_FILE"),
        VAPID_SUBJECT=os.getenv("VAPID_SUBJECT", "mailto:admin@ldenoteca.it")
    )

    if not app.config.get("SECRET_KEY"):
        logger.critical("SECRET_KEY non impostata! Verifica .env / environment systemd.")
        raise RuntimeError("SECRET_KEY is not set")

    # Dopo app.config.update(...)
    # Logghiamo un identificatore della SECRET_KEY (hash) per verificare che sia identica su tutti i worker
    safe_key_id = hash(app.config['SECRET_KEY'])
    logger.info("SECRET_KEY identifier (hash): %s", safe_key_id)

    if not app.config['SQLALCHEMY_DATABASE_URI']:
        logger.critical("DATABASE_URL non impostato! Verifica il file .env.")
        raise RuntimeError("DATABASE_URL is not set. Check your .env file.")

    mail.init_app(app)

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
    # from tools.log_utils import get_logger
    main_handler = get_logger("main", level=logging.DEBUG, also_main_log=False)
    # Aggiungilo al logger dell’app (o a quello root se preferisci)
    app.logger.addHandler(main_handler)

    logger.info("App Flask creata e database inizializzato correttamente.")

    # --- LOGIN MANAGER ---
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # --- ROUTE HOME (minimo) ---
    @app.route("/", methods=["GET"])
    def home():
        app.logger.info(
            "HOME VIEW - is_authenticated=%s, user_id=%s, session_keys=%s",
            current_user.is_authenticated,
            getattr(current_user, "id", None),
            list(session.keys())
        )
        return render_template("home.html")

    # --- CONTEXT PROCESSORS ---
    @app.context_processor
    def inject_user_menu():
        return {"user_menu": get_user_menu()}

    @app.context_processor
    def inject_menus():
        def build_menu_tree(nodes, all_menus, user_role_weight):
            """
            nodes: lista di Menu (già ordinata) da trattare come 'radici' del livello corrente
            all_menus: lista completa Menu (già ordinata) usata per trovare i figli
            """
            result = []
            for node in nodes:
                if not node.is_visible:
                    continue
                if node.weight > user_role_weight:
                    continue

                children = [
                    m for m in all_menus
                    if m.parent_id == node.id and m.is_visible and m.weight <= user_role_weight
                ]

                children_tree = build_menu_tree(children, all_menus, user_role_weight)

                result.append({
                    "id": node.id,
                    "name": node.name,
                    "weight": node.weight,
                    "route": node.route,
                    "is_active": node.is_active,
                    "is_visible": node.is_visible,
                    "item_type": node.item_type,
                    "children": children_tree
                })
            return result

        user_role_weight = current_user.max_role_weight if current_user.is_authenticated else 0

        # Carichiamo TUTTI i menu ordinati in modo deterministico
        all_menus = (
            Menu.query
            .filter(Menu.is_visible.is_(True), Menu.weight <= user_role_weight)
            .order_by(asc(Menu.parent_id), asc(Menu.sort_order), asc(Menu.id))
            .all()
        )

        # Radici = parent_id NULL (manteniamo l'ordine del queryset)
        roots = [m for m in all_menus if m.parent_id is None]

        menu_tree = build_menu_tree(roots, all_menus, user_role_weight)
        return {"menu_tree": menu_tree}

    # --- SERVICE WORKER ROUTE (opzionale ma utile) ---
    @app.route("/service-worker.js")
    def service_worker():
        response = make_response(send_from_directory(app.static_folder, "service-worker.js"))
        response.headers["Content-Type"] = "application/javascript"
        response.headers["Cache-Control"] = "no-cache"
        return response

    # --- BLUEPRINTS ---
    from routes.auth import auth_bp
    from routes.settings import settings_bp
    from routes.elaborazioni_sconti import sconti_bp
    from routes.articoli import articoli_bp
    from routes.esportazioni_teamsystem import file_bp
    from routes.search import search_bp
    from routes.inventario import inventario_bp
    from routes.status_routes import status_bp
    from routes.task_routes import task_bp
    from routes.importazioni_routes import importazioni_bp
    from routes.logs_display import logs_bp
    from routes.trello import trello_bp
    from routes.app_installation import installation_bp
    from routes.slack import slack_bp
    from routes.cassa import cassa_bp
    from routes.registry import registry_bp
    from routes.route_orders import route_orders_bp
    from routes.pwa import pwa_bp
    from routes.documents import documents_bp
    from routes.wine_cards import wine_cards_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(settings_bp, url_prefix="/settings")
    app.register_blueprint(sconti_bp, url_prefix="/sconti")
    app.register_blueprint(articoli_bp, url_prefix="/articoli")
    app.register_blueprint(file_bp, url_prefix="/exported")
    app.register_blueprint(search_bp, url_prefix="/search")
    app.register_blueprint(inventario_bp, url_prefix="/inventario")
    app.register_blueprint(status_bp, url_prefix="/task")
    app.register_blueprint(task_bp, url_prefix="/task_manage")
    app.register_blueprint(importazioni_bp, url_prefix="/importazioni")
    app.register_blueprint(logs_bp, url_prefix="/logs")
    app.register_blueprint(trello_bp, url_prefix="/trello")
    app.register_blueprint(installation_bp, url_prefix="/installation")
    app.register_blueprint(slack_bp, url_prefix="/slack")
    app.register_blueprint(automations_v2_bp, url_prefix="/api")
    app.register_blueprint(kiosk_bp, url_prefix="/kiosk")
    app.register_blueprint(cassa_bp, url_prefix="/cassa")
    app.register_blueprint(registry_bp, url_prefix="/registry")
    app.register_blueprint(route_orders_bp, url_prefix="/route-orders")
    app.register_blueprint(pwa_bp, url_prefix="/pwa")
    app.register_blueprint(documents_bp)
    app.register_blueprint(wine_cards_bp, url_prefix="/wine-cards")

    @app.cli.command("cleanup-reset-tokens")
    @click.option("--retention-days", default=30, show_default=True, type=int,
                  help="Elimina token usati/scaduti più vecchi di N giorni.")
    def cleanup_reset_tokens(retention_days: int):
        """Elimina token reset password scaduti/usati più vecchi della retention."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=retention_days)

        q = PasswordResetToken.query.filter(
            db.or_(
                db.and_(PasswordResetToken.used_at.isnot(None), PasswordResetToken.used_at < cutoff),
                db.and_(PasswordResetToken.expires_at < cutoff),
            )
        )

        count = q.count()
        q.delete(synchronize_session=False)
        db.session.commit()

        click.echo(f"cleanup-reset-tokens: deleted {count} rows (retention_days={retention_days})")

    from config.celery_app import init_celery
    init_celery(app)

    return app
