from functools import wraps
from flask import current_app, redirect, url_for, flash
from flask_login import current_user
from models import Menu


def role_required(menu_identifier):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            with current_app.app_context():
                menu = Menu.query.filter_by(route=f'/settings/{menu_identifier}').first()
                if menu is None:
                    return redirect(url_for('home'))
                if not current_user.is_authenticated:
                    flash("Devi effettuare il login per accedere a questa pagina.", "warning")
                    return redirect(url_for('auth.login'))
                if current_user.role.weight < menu.weight:
                    flash("Non hai i permessi per accedere a questa pagina.", "danger")
                    return redirect(url_for('home'))
            return func(*args, **kwargs)
        return wrapper
    return decorator
