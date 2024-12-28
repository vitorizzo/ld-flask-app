from functools import wraps
from flask import redirect, url_for, flash
from flask_login import current_user


def role_required(role_id):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                flash("Devi effettuare il login per accedere a questa pagina.", "warning")
                return redirect(url_for('auth.login'))
            if current_user.role_id != role_id:
                flash("Non hai i permessi per accedere a questa pagina.", "danger")
                return redirect(url_for('main.index'))  # Cambia in base alla tua home
            return func(*args, **kwargs)
        return wrapper
    return decorator
