from flask import request, flash, render_template, Blueprint, jsonify
from flask_login import login_required

from extensions import db
from models import Menu, Role
from routes.decorators import role_required

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')


@settings_bp.route('/update_menu', methods=['POST'])
@login_required
@role_required('menus')  # Use a string identifier instead
def update_menu():
    try:
        menu_id = request.form.get('menu_id')
        if not menu_id:
            return jsonify({'success': False, 'error': 'Menu ID is missing'}), 400

        menu = Menu.query.get(menu_id)
        if not menu:
            return jsonify({'success': False, 'error': f'No menu found with ID {menu_id}'}), 404

        # Extract form data
        name = request.form.get('name')
        route = request.form.get('route')
        is_active = request.form.get('is_active') == 'true'
        weight = request.form.get('weight')
        parent_id = request.form.get('parent_id')

        # Update the menu in the database
        menu = Menu.query.get(menu_id)
        if menu:
            menu.name = name
            menu.route = route
            menu.is_active = is_active
            menu.weight = weight
            menu.parent_id = parent_id
            db.session.commit()
            # flash('Menu aggiornati con successo!', 'success')
            # return render_template('settings/menus.html', menus=Menu.query.all())
            return jsonify({'success': True, 'message': 'Menu updated successfully'})
        else:
            return jsonify({'success': False, 'error': f'No menu read with ID {menu_id}'}), 404
    except Exception as e:
        db.session.rollback()
        print(f"Error updating menu: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


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
