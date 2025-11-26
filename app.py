import logging
from flask import render_template, send_from_directory, make_response
from flask_login import LoginManager, current_user

from tools.app_factory import create_app

from routes.auth import auth_bp
from routes.settings import settings_bp
from routes.elaborazioni_sconti import sconti_bp
from routes.articoli import articoli_bp
from routes.inventario import inventario_bp
from routes.tools import get_user_menu
from routes.esportazioni_teamsystem import file_bp
from routes.search import search_bp
from routes.status_routes import status_bp
from routes.task_routes import task_bp
from routes.importazioni_routes import importazioni_bp
from routes.logs_display import logs_bp
from routes.trello import trello_bp
from routes.app_installation import installation_bp

from models import User, Menu

import re

app = create_app()

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth.login"

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# registrazione blueprint
app.register_blueprint(auth_bp, url_prefix='/auth')
app.register_blueprint(settings_bp, url_prefix='/settings')
app.register_blueprint(sconti_bp, url_prefix='/sconti')
app.register_blueprint(articoli_bp, url_prefix='/articoli')
app.register_blueprint(file_bp, url_prefix='/exported')
app.register_blueprint(search_bp, url_prefix='/search')
app.register_blueprint(inventario_bp, url_prefix='/inventario')
app.register_blueprint(status_bp, url_prefix='/task')
app.register_blueprint(task_bp, url_prefix='/task_manage')
app.register_blueprint(importazioni_bp, url_prefix='/importazioni')
app.register_blueprint(logs_bp, url_prefix='/logs')
app.register_blueprint(trello_bp, url_prefix='/trello')
app.register_blueprint(installation_bp, url_prefix='/installation')

@app.route('/service-worker.js')
def service_worker():
    response = make_response(send_from_directory('static', 'service-worker.js'))
    response.headers['Content-Type'] = 'application/javascript'
    response.headers['Cache-Control'] = 'no-cache'
    return response

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

    user_role_weight = current_user.max_role_weight if current_user.is_authenticated else 0
    roots_menu = Menu.query.filter_by(parent_id=None).all()
    childs_menu = Menu.query.filter(Menu.parent_id.isnot(None)).all()

    return {"menu_tree": build_menu_tree(roots_menu, childs_menu, user_role_weight)}

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True, use_reloader=False)
