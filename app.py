import logging
import sys

from routes.status_routes import status_bp
from tools.log_utils import get_logger
import os

from dotenv import load_dotenv
from flask import render_template
from flask_login import LoginManager, current_user
from models import User, Menu
from routes.auth import auth_bp
from routes.settings import settings_bp
from routes.elaborazioni_sconti import sconti_bp
from routes.articoli import articoli_bp
from routes.inventario import inventario_bp
from routes.tools import get_user_menu
from routes.esportazioni_teamsystem import file_bp
from routes.search import search_bp
from tools.app_factory import create_app
# from tools.log_utils import debug_loggers


# Inizializza il logger globale (ad esempio "main") prima di altri import
logger = get_logger("main", level=logging.DEBUG)
# Imposta anche una configurazione base per il root logger (opzionale)
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
dotenvlocal_path = os.path.join(os.path.dirname(__file__), ".env.local")
dotenvdefaults_path = os.path.join(os.path.dirname(__file__), ".env.defaults")

logger.info(f"Caricamento .env da {dotenv_path}")
load_dotenv(dotenv_path, override=False)
load_dotenv(dotenvlocal_path, override=True)
load_dotenv(dotenvdefaults_path, override=False)

FLASK_ENV = os.getenv("FLASK_ENV", "production")
EXPORT_FOLDER = os.getenv("EXPORT_FOLDER")
EXPORT_FOLDER_URL = os.getenv("EXPORT_FOLDER_URL")
UPLOAD_FOLDER = os.path.normpath(os.path.join(os.getcwd(), 'ld-flask-app', 'static', 'uploads'))

SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL'),
SQLALCHEMY_TRACK_MODIFICATIONS = False,

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
    logger.info(f"Cartella upload creata: {UPLOAD_FOLDER}")

PS_URL = os.getenv("PRESTASHOP_URL")
PS_KEY = os.getenv("PRESTASHOP_KEY")
PS_USER = os.getenv("PRESTASHOP_USER")
PS_PSWD = os.getenv("PRESTASHOP_PASSWORD")

app = create_app()
werkzeug_logger = logging.getLogger('werkzeug')
werkzeug_logger.handlers = []      # rimuove gli handler predefiniti
werkzeug_logger.propagate = True     # fa propagare i messaggi al logger root
app.logger.handlers = logger.handlers  # Usa i nostri handler
app.logger.setLevel(logging.DEBUG)
app.logger.propagate = False

logger.info("Flask app creata.")

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth.login"

# Registrazione Blueprint
app.register_blueprint(auth_bp, url_prefix='/auth')
app.register_blueprint(settings_bp, url_prefix='/settings')
app.register_blueprint(sconti_bp, url_prefix='/sconti')
app.register_blueprint(articoli_bp, url_prefix='/articoli')
app.register_blueprint(file_bp, url_prefix='/exported')
app.register_blueprint(search_bp, url_prefix='/search')
app.register_blueprint(inventario_bp, url_prefix='/inventario')
app.register_blueprint(status_bp, url_prefix='/task')

logger.info("Blueprint registrati.")
# debug_loggers()


def build_menu_tree(menus):
    menu_dict = {menu.id: menu for menu in menus}
    tree = []
    for menu in menus:
        if menu.parent_id is None:
            tree.append(build_menu_item(menu, menu_dict))
    return tree


def build_menu_item(menu, menu_dict):
    item = {
        'id': menu.id,
        'name': menu.name,
        'route': menu.route,
        'weight': menu.weight,
        'children': []
    }
    for potential_child in menu_dict.values():
        if potential_child.parent_id == menu.id:
            item['children'].append(build_menu_item(potential_child, menu_dict))
    item['children'].sort(key=lambda x: x['weight'])
    return item


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route('/', methods=['GET'])
def home():
    return render_template('home.html')


@app.context_processor
def inject_user_menu():
    return {'user_menu': get_user_menu()}


@app.context_processor
def inject_user():
    return {'current_user': current_user}


@app.context_processor
def inject_menus():
    def build_menu_tree(roots, all_menus, user_role_weight):
        result = []
        for root in roots:
            if root.weight <= user_role_weight:
                children = [m for m in all_menus if m.parent_id == root.id and m.weight <= user_role_weight]
                children_tree = build_menu_tree(children, all_menus, user_role_weight)
                result.append({
                    "id": root.id,
                    "name": root.name,
                    "weight": root.weight,
                    "route": root.route,
                    "is_active": root.is_active,
                    "children": children_tree
                })
        return result

    user_role_weight = current_user.role.weight if current_user.is_authenticated else 0
    roots_menu = Menu.query.filter_by(parent_id=None).all()
    childs_menu = Menu.query.filter(Menu.parent_id.isnot(None)).all()
    menu_tree = build_menu_tree(roots_menu, childs_menu, user_role_weight)
    return {"menu_tree": menu_tree}


if __name__ == '__main__':
    logger.info("Avvio server Flask in modalità standalone...")
    app.run(host='0.0.0.0', debug=True, use_reloader=False)
