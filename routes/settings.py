from flask import request, flash, render_template, Blueprint, jsonify
from flask_login import login_required

from extensions import db
from models import Menu, Role
from routes.decorators import role_required

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')


@settings_bp.route('/update_menus', methods=['POST'])
@login_required
@role_required('menus')  # Use a string identifier instead
def update_menu():
    # Aggiorna i menu
    for menu in Menu.query.all():
        menu.weight = request.form.get(f'weight_{menu.id}', 0)
    db.session.commit()
    flash('Menu aggiornati con successo!', 'success')
    return render_template('settings/menus.html', menus=Menu.query.order_by(Menu.weight).all())


@settings_bp.route('/menu/<int:menu_id>')
def get_menu_data(menu_id):
    menu = Menu.query.get_or_404(menu_id)
    return jsonify(menu.to_dict())


@settings_bp.route('/menus', methods=['GET', 'POST'])
@login_required
@role_required('menus')  # Use a string identifier instead
def manage_menus():
    if request.method == 'POST':
        # Aggiungi o modifica un menu
        name = request.form['name']
        route = request.form['route']
        parent_id = request.form.get('parent_id', None)
        weight = request.form.get('weight', 0)
        new_menu = Menu(name=name, route=route, parent_id=parent_id, weight=weight)
        db.session.add(new_menu)
        db.session.commit()
        flash('Menu salvato con successo!', 'success')
    menus = Menu.query.all()
    roles = Role.query.order_by(Role.weight.desc()).all()
    menu_fields = [column.name for column in Menu.__table__.columns if column.name != 'id']
    return render_template('settings/menus.html', menus=menus, roles=roles, menu_fields=menu_fields)
