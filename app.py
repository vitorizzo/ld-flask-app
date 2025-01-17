import os

from dotenv import load_dotenv
from extensions import db  # Importa db da extensions.py
from flask import Flask, render_template
from flask_login import LoginManager, current_user
from flask_migrate import Migrate
from models import User, Menu, Role
from routes.auth import auth_bp
from routes.settings import settings_bp
from routes.elaborazioni_sconti import sconti_bp
from routes.tools import get_user_menu

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
app.register_blueprint(settings_bp, url_prefix='/settings')
app.register_blueprint(sconti_bp, url_prefix='/sconti')


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
    # Funzione per caricare l'utente dalla sessione
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
    app.run(debug=True)
