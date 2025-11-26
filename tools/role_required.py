import functools
from datetime import datetime
from flask import redirect, url_for, request, flash
from tools.auth_manager import get_current_user
from tools.log_utils import get_logger

logger = get_logger("role_required")


def role_required(min_weight=0, roles=None):
    """
    Autorizzazione basata su:
    - min_weight: peso minimo richiesto
    - roles: lista ruoli ammessi (bypassano il min_weight)
    - ruoli multipli con scadenza (UserRole.valid_until)
    """
    roles = roles or []

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):

            logger.info(
                f"[role_required] Entrata nel decoratore per {func.__name__} "
                f"| min_weight={min_weight}, roles={roles}"
            )

            # 1) Recupero utente
            try:
                user = get_current_user()
            except Exception:
                logger.warning("[role_required] Utente non autenticato")
                return _deny_access()

            # 2) Recupero ruoli attivi (già gestiti dal modello User)
            active_roles = user.active_roles

            if not active_roles:
                logger.warning("[role_required] Nessun ruolo attivo per l'utente")
                return redirect(url_for("auth.login"))

            logger.info(f"[role_required] Ruoli attivi utente: "
                        f"{[(r.name, r.weight) for r in active_roles]}")

            # 3) Controllo peso massimo
            if user.max_role_weight < min_weight:
                logger.warning("[role_required] Peso ruolo insufficiente per accedere")
                return redirect(url_for("auth.login"))

            # 4) Controllo ruoli specifici richiesti
            if roles:
                user_role_names = [r.name for r in active_roles]
                if not any(r in user_role_names for r in roles):
                    logger.warning("[role_required] Ruolo specifico richiesto ma non presente")
                    return redirect(url_for("auth.login"))

            # 5) Accesso consentito
            logger.info("[role_required] Accesso consentito")
            return func(*args, **kwargs)

        return wrapper
    return decorator


def _deny_access():
    """
    Risposta uniforme quando l'accesso è negato.
    GET => redirect + flash
    POST/JSON => JSON 403
    """
    if request.method == "POST" or request.is_json:
        return {"error": "Accesso negato"}, 403

    flash("Accesso negato", "danger")
    return redirect(url_for("auth.login"))
