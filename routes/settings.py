from flask import request, flash, render_template, Blueprint
from flask_login import login_required

from extensions import db
from models import Menu
from routes.decorators import role_required

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')


@settings_bp.route('/menus', methods=['GET', 'POST'])
@login_required
@role_required('admin')  # Solo gli admin possono accedere
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
    menus = Menu.query.order_by(Menu.weight).all()
    return render_template('settings/menus.html', menus=menus)
