from functools import wraps
from flask import current_app, redirect, url_for, flash
from flask_login import current_user
from tools.log_utils import get_logger

logger = get_logger('decorators')


def role_required(value):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            with current_app.app_context():
                logger.info(f"Verifica accesso a '{func.__name__}' richiesta con peso minimo {value}")
                if value is None:
                    logger.warning("Valore richiesto per il ruolo non definito.")
                    return redirect(url_for('home'))

                if not current_user.is_authenticated:
                    logger.warning("Utente non autenticato. Reindirizzamento al login.")
                    flash("Devi effettuare il login per accedere a questa pagina.", "warning")
                    return redirect(url_for('auth.login'))

                if current_user.role.weight < value:
                    logger.warning(f"Accesso negato: ruolo utente ({current_user.role.weight}) "
                                   f"insufficiente per '{func.__name__}'")
                    flash("Non hai i permessi per accedere a questa pagina.", "danger")
                    return redirect(url_for('home'))

                logger.info(f"Accesso consentito a '{func.__name__}' per l'utente ID {current_user.id}")
            return func(*args, **kwargs)
        return wrapper
    return decorator
