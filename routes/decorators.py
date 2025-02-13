from functools import wraps
from flask import current_app, redirect, url_for, flash
from flask_login import current_user


def role_required(value):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            with current_app.app_context():
                if value is None:
                    return redirect(url_for('home'))
                if not current_user.is_authenticated:
                    flash("Devi effettuare il login per accedere a questa pagina.", "warning")
                    return redirect(url_for('auth.login'))
                if current_user.role.weight < value:
                    flash("Non hai i permessi per accedere a questa pagina.", "danger")
                    return redirect(url_for('home'))
            return func(*args, **kwargs)
        return wrapper
    return decorator
