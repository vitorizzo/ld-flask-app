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
    - roles: wildcard di ruoli ammessi anche se sotto min_weight
    """
    allowed_roles = roles or []

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):

            logger.info(
                f"[role_required] Entrata nel decoratore per {func.__name__} "
                f"| min_weight={min_weight}, roles={allowed_roles}"
            )

            # 1) Recupero utente
            try:
                user = get_current_user()
            except Exception:
                logger.warning("[role_required] Utente non autenticato")
                return _deny_access()

            # 2) Recupero ruoli attivi
            active_roles = user.active_roles

            if not active_roles:
                logger.warning("[role_required] Nessun ruolo attivo per l'utente")
                return _deny_access()

            logger.info(
                "[role_required] Ruoli attivi utente: "
                f"{[(r.name, r.weight) for r in active_roles]}"
            )

            # Ricavo peso massimo e nomi ruoli utente
            max_weight = user.max_role_weight
            user_role_names = [r.name for r in active_roles]

            # 3) Controllo peso minimo
            if max_weight >= min_weight:
                logger.info("[role_required] Accesso consentito (peso sufficiente)")
                return func(*args, **kwargs)

            # 4) Controllo wildcard roles (bypass peso)
            if allowed_roles and any(r in user_role_names for r in allowed_roles):
                logger.info("[role_required] Accesso consentito tramite wildcard roles")
                return func(*args, **kwargs)

            # 5) Accesso negato
            logger.warning(
                "[role_required] Accesso negato: peso insufficiente "
                "e nessun ruolo nella wildcard"
            )
            return _deny_access()

        return wrapper

    return decorator


def _deny_access():
    """Risposta uniforme per accesso negato."""
    if request.method == "POST" or request.is_json:
        return {"error": "Accesso negato"}, 403

    flash("Accesso negato", "danger")
    return redirect(url_for("auth.login"))
