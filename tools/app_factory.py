import logging
import os
import threading
import time
import click

from flask import Flask, render_template, send_from_directory, make_response, session, jsonify, request
from flask_login import LoginManager, current_user
from flask_migrate import Migrate
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from sqlalchemy import asc
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from werkzeug.exceptions import RequestEntityTooLarge

from extensions import db, mail
from routes.automations_v2 import automations_v2_bp
from routes.kiosk import kiosk_bp
from tools.log_utils import get_logger
from models import User, Menu, PasswordResetToken, SupportTicket
from routes.tools import get_user_menu
from tools.preferences import PREFERENCE_DEFINITIONS, load_preferences_into_app_config

# Determina la root del progetto (supponendo che questo file sia in tools/)
project_root = os.path.dirname(os.path.dirname(__file__))


def _compute_app_version(base_path):
    explicit_version = (
        os.getenv("APP_VERSION")
        or os.getenv("RENDER_GIT_COMMIT")
        or os.getenv("GIT_COMMIT")
    )
    if explicit_version:
        return explicit_version[:40]

    latest_mtime = 0.0
    version_paths = [
        "app.py",
        "models.py",
        "tools",
        "routes",
        "templates",
        os.path.join("static", "css"),
        os.path.join("static", "js"),
        os.path.join("static", "service-worker.js"),
        os.path.join("static", "manifest.json"),
    ]
    ignored_dirs = {"__pycache__", ".git", ".pytest_cache", "venv", ".venv"}

    for relative_path in version_paths:
        absolute_path = os.path.join(base_path, relative_path)
        if os.path.isfile(absolute_path):
            latest_mtime = max(latest_mtime, os.path.getmtime(absolute_path))
            continue
        if not os.path.isdir(absolute_path):
            continue
        for root, dirs, files in os.walk(absolute_path):
            dirs[:] = [name for name in dirs if name not in ignored_dirs]
            for filename in files:
                filepath = os.path.join(root, filename)
                try:
                    latest_mtime = max(latest_mtime, os.path.getmtime(filepath))
                except OSError:
                    continue

    return str(int(latest_mtime))

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

    if os.path.exists(env_defaults_path):
        load_dotenv(env_defaults_path, override=False)
    load_dotenv(env_path, override=True)
    if os.path.exists(env_local_path):
        load_dotenv(env_local_path, override=True)

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
    ASSISTANCE_MAIL_SERVER = os.getenv('ASSISTANCE_MAIL_SERVER')
    ASSISTANCE_MAIL_PORT = int(os.getenv('ASSISTANCE_MAIL_PORT', os.getenv('MAIL_PORT', 25)))
    ASSISTANCE_MAIL_USE_TLS = os.getenv('ASSISTANCE_MAIL_USE_TLS', os.getenv('MAIL_USE_TLS', 'false')).lower() == 'true'
    ASSISTANCE_MAIL_USE_SSL = os.getenv('ASSISTANCE_MAIL_USE_SSL', os.getenv('MAIL_USE_SSL', 'false')).lower() == 'true'
    ASSISTANCE_MAIL_USERNAME = os.getenv('ASSISTANCE_MAIL_USERNAME')
    ASSISTANCE_MAIL_PASSWORD = os.getenv('ASSISTANCE_MAIL_PASSWORD')
    ASSISTANCE_MAIL_DEFAULT_SENDER = os.getenv('ASSISTANCE_MAIL_DEFAULT_SENDER')
    export_folder = os.getenv("EXPORT_FOLDER")
    export_folder_url = os.getenv("EXPORT_FOLDER_URL")
    upload_folder = os.path.normpath(os.path.join(os.getcwd(), "ld-flask-app", "static", "uploads"))
    sqlalchemy_database_uri = os.getenv("DATABASE_URL")
    max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "64"))

    # ... creazione app, config, ecc.
    app = Flask(
        __name__,
        static_folder=os.path.join(project_root, "static"),
        template_folder=os.path.join(project_root, "templates")
    )

    @app.after_request
    def configure_response_cache(response):
        if request.endpoint == "static":
            # Gli asset con ?v= sono legati alla versione applicativa: il browser
            # puo conservarli senza ricontrollarli a ogni apertura pagina.
            max_age = 31536000 if request.args.get("v") else 3600
            suffix = ", immutable" if request.args.get("v") else ""
            response.headers["Cache-Control"] = f"public, max-age={max_age}{suffix}"
            response.headers.pop("Pragma", None)
            response.headers.pop("Expires", None)
        else:
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
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
        ASSISTANCE_MAIL_SERVER=ASSISTANCE_MAIL_SERVER,
        ASSISTANCE_MAIL_PORT=ASSISTANCE_MAIL_PORT,
        ASSISTANCE_MAIL_USE_TLS=ASSISTANCE_MAIL_USE_TLS,
        ASSISTANCE_MAIL_USE_SSL=ASSISTANCE_MAIL_USE_SSL,
        ASSISTANCE_MAIL_USERNAME=ASSISTANCE_MAIL_USERNAME,
        ASSISTANCE_MAIL_PASSWORD=ASSISTANCE_MAIL_PASSWORD,
        ASSISTANCE_MAIL_DEFAULT_SENDER=ASSISTANCE_MAIL_DEFAULT_SENDER,
        PS_URL=os.getenv("PRESTASHOP_URL"),
        PS_KEY=os.getenv("PRESTASHOP_KEY"),
        PS_USER=os.getenv("PRESTASHOP_USER"),
        PS_PSWD=os.getenv("PRESTASHOP_PASSWORD"),
        FERNET_KEY=os.getenv('FERNET_KEY'),
        TRELLO_KEY=os.getenv("TRELLO_KEY"),
        TRELLO_API_KEY=os.getenv("TRELLO_KEY"),
        TRELLO_SECRET=os.getenv("TRELLO_SECRET"),
        TRELLO_TOKEN=os.getenv("TRELLO_TOKEN"),
        SLACK_SIGNING_SECRET=os.getenv("SLACK_SIGNING_SECRET"),
        SLACK_BOT_TOKEN=os.getenv("SLACK_BOT_TOKEN"),
        VAPID_PUBLIC_KEY=os.getenv("VAPID_PUBLIC_KEY"),
        VAPID_PRIVATE_KEY=os.getenv("VAPID_PRIVATE_KEY"),
        VAPID_PRIVATE_KEY_FILE=os.getenv("VAPID_PRIVATE_KEY_FILE"),
        VAPID_SUBJECT=os.getenv("VAPID_SUBJECT", "mailto:admin@ldenoteca.it"),
        POLEEPO_URL=os.getenv("POLEEPO_URL"),
        POLEEPO_PKEY=os.getenv("POLEEPO_PKEY"),
        POLEEPO_PPKEY=os.getenv("POLEEPO_PPKEY"),
        MAX_CONTENT_LENGTH=max_upload_mb * 1024 * 1024,
        MAX_UPLOAD_MB=max_upload_mb,
        APP_VERSION=_compute_app_version(base)
    )

    @app.errorhandler(RequestEntityTooLarge)
    def request_entity_too_large(error):
        limit_mb = app.config.get("MAX_UPLOAD_MB", 64)
        if request.path.startswith("/customer-orders") or request.path.startswith("/events"):
            return render_template(
                "errors/413.html",
                limit_mb=limit_mb,
                back_url=request.referrer or "/customer-orders/",
            ), 413
        return jsonify({"ok": False, "error": f"File troppo grande. Limite: {limit_mb} MB."}), 413

    app.extensions.setdefault("ldapp_runtime_preferences", {})
    app.extensions["ldapp_runtime_preferences"]["base_config"] = {
        definition.config_key: app.config.get(definition.config_key, definition.default)
        for definition in PREFERENCE_DEFINITIONS
        if definition.config_key
    }

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

    try:
        with app.app_context():
            load_preferences_into_app_config(app)
    except OperationalError:
        logger.debug("Startup preferences load skipped: database not ready or table missing")
    except SQLAlchemyError:
        logger.debug("Startup preferences load skipped: SQLAlchemy error while reading preferences")
    except Exception:
        logger.exception("Unexpected error while loading startup preferences")

    preference_refresh_seconds = max(
        0.0,
        float(os.getenv("PREFERENCES_REFRESH_SECONDS", "5")),
    )
    preference_refresh_lock = threading.Lock()
    preference_refresh_state = {"last_check": time.monotonic()}

    @app.before_request
    def refresh_runtime_preferences():
        if request.endpoint == "static":
            return
        now = time.monotonic()
        if now - preference_refresh_state["last_check"] < preference_refresh_seconds:
            return
        with preference_refresh_lock:
            now = time.monotonic()
            if now - preference_refresh_state["last_check"] < preference_refresh_seconds:
                return
            preference_refresh_state["last_check"] = now
            try:
                load_preferences_into_app_config(app)
            except (OperationalError, SQLAlchemyError):
                logger.debug("refresh_runtime_preferences: database not available, keep current config")
            except Exception:
                logger.exception("refresh_runtime_preferences: unexpected error while loading runtime preferences")

    @app.before_request
    def record_visitor_analytics():
        from tools.visitor_analytics import record_visit

        record_visit()

    @app.after_request
    def attach_visitor_analytics_cookies(response):
        from tools.visitor_analytics import set_analytics_cookies

        return set_analytics_cookies(response)

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
        return {
            "user_menu": get_user_menu(),
            "app_version": app.config.get("APP_VERSION", "dev"),
        }

    @app.route("/app-version.json")
    def app_version():
        response = jsonify({
            "version": app.config.get("APP_VERSION", "dev"),
        })
        response.headers["Cache-Control"] = "no-store, max-age=0"
        return response

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

                own_badge_sources = []
                own_badge_count = 0
                if node.route == "/settings/support-tickets":
                    own_badge_sources.append("support")
                    own_badge_count = support_badge_count
                elif node.route == "/settings/horeca-activations":
                    own_badge_sources.append("activation")
                    own_badge_count = activation_badge_count
                child_badge_sources = {
                    source
                    for child in children_tree
                    for source in child.get("badge_sources", [])
                }
                badge_sources = sorted(set(own_badge_sources) | child_badge_sources)

                result.append({
                    "id": node.id,
                    "name": node.name,
                    "weight": node.weight,
                    "route": node.route,
                    "is_active": node.is_active,
                    "is_visible": node.is_visible,
                    "item_type": node.item_type,
                    "badge_count": own_badge_count + sum(child.get("badge_count", 0) for child in children_tree),
                    "badge_sources": badge_sources,
                    "children": children_tree
                })
            return result

        user_role_weight = current_user.max_role_weight if current_user.is_authenticated else 0
        support_badge_count = 0
        activation_badge_count = 0
        if current_user.is_authenticated and user_role_weight >= 40:
            try:
                activation_badge_count = SupportTicket.query.filter(
                    SupportTicket.ticket_type == "horeca_activation",
                    SupportTicket.status.notin_(["closed", "activated"]),
                ).count()
            except SQLAlchemyError:
                db.session.rollback()
                logger.exception("inject_menus: activation count unavailable")
        if current_user.is_authenticated and user_role_weight >= 900:
            try:
                from tools.support_tickets import support_unread_count

                support_badge_count = support_unread_count()
            except SQLAlchemyError:
                db.session.rollback()
                logger.exception("inject_menus: support unread count unavailable")

        # Carichiamo TUTTI i menu ordinati in modo deterministico
        try:
            all_menus = (
                Menu.query
                .filter(Menu.is_visible.is_(True), Menu.weight <= user_role_weight)
                .order_by(asc(Menu.parent_id), asc(Menu.sort_order), asc(Menu.id))
                .all()
            )
        except OperationalError:
            logger.exception("inject_menus: menu query unavailable, returning empty menu tree")
            return {"menu_tree": []}
        except Exception:
            logger.exception("inject_menus: unexpected error while loading menus")
            return {"menu_tree": []}

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
    from routes.shipping import shipping_bp
    from routes.events import events_bp
    from routes.customer_orders import customer_orders_bp
    from routes.supplier_orders import supplier_orders_bp
    from routes.developer import developer_bp
    from routes.mailing_list import mailing_list_bp
    from routes.administration import administration_bp

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
    app.register_blueprint(shipping_bp, url_prefix="/shipping")
    app.register_blueprint(events_bp, url_prefix="/events")
    app.register_blueprint(customer_orders_bp, url_prefix="/customer-orders")
    app.register_blueprint(supplier_orders_bp, url_prefix="/supplier-orders")
    app.register_blueprint(developer_bp, url_prefix="/developer")
    app.register_blueprint(mailing_list_bp, url_prefix="/mailing-list")
    app.register_blueprint(administration_bp, url_prefix="/administration")

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
