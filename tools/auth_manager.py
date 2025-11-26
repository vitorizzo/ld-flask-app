# tools/auth_manager.py
import functools

from flask_login import current_user
from werkzeug.exceptions import Unauthorized, Forbidden
from tools.log_utils import get_logger

logger = get_logger("auth_manager")


def has_min_role(required_weight: int) -> bool:
    """
    Verifica che l'utente attuale abbia un ruolo con weight >= required_weight.
    Registra nel log tutti i dettagli utili per debug.
    """
    try:
        user = get_current_user()
    except Unauthorized:
        logger.warning(
            f"Verifica ruolo fallita: utente non autenticato. Richiesto >= {required_weight}"
        )
        return False

    try:
        user_weight = user.role.weight
    except Exception as e:
        logger.exception(
            f"Errore nel leggere il ruolo dell'utente ID {user.id}: {e}"
        )
        return False

    allowed = user_weight >= required_weight

    logger.info(
        f"Verifica ruolo per utente ID {user.id} -> "
        f"peso utente: {user_weight}, minimo richiesto: {required_weight}, "
        f"esito: {'CONSENTITO' if allowed else 'NEGATO'}"
    )

    return allowed


def get_current_user():
    """
    Ritorna l'utente loggato, oppure solleva eccezione se non autenticato.
    È il punto centralizzato per leggere l'utente corrente.
    """
    if not current_user.is_authenticated:
        raise Unauthorized("Utente non autenticato.")
    return current_user


def get_current_user_id():
    """
    Versione leggera: torna solo l'id utente.
    """
    if not current_user.is_authenticated:
        raise Unauthorized("Utente non autenticato.")
    return current_user.id


def is_authenticated():
    """
    True/False se l'utente è loggato.
    """
    return current_user.is_authenticated


def role_required(min_role: int):
    """
    Decoratore per proteggere una route in base al ruolo minimo richiesto.
    Usa logging dettagliato per capire ogni passaggio.
    """
    def decorator(func):

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            logger.debug(f"[role_required] Accesso richiesto: ruolo_minimo={min_role}")

            # 1. Verifica autenticazione
            if not current_user.is_authenticated:
                logger.warning(
                    "[role_required] Accesso negato: utente non autenticato."
                )
                raise Unauthorized("Utente non autenticato.")

            # 2. Recupero ruolo utente
            user_role = getattr(current_user, "role", None)

            logger.debug(
                f"[role_required] Utente autenticato: id={current_user.id}, "
                f"ruolo_utente={user_role}"
            )

            # 3. Verifica che il ruolo esista
            if user_role is None:
                logger.error(
                    "[role_required] Errore: l'utente autenticato non ha un attributo 'role'."
                )
                raise Forbidden("Ruolo utente non definito.")

            # 4. Confronto dei ruoli
            if int(user_role) < int(min_role):
                logger.warning(
                    f"[role_required] Accesso negato: ruolo_utente={user_role} "
                    f"< ruolo_minimo={min_role}"
                )
                raise Forbidden("Permessi insufficienti.")

            logger.debug(
                f"[role_required] Accesso consentito: ruolo_utente={user_role} "
                f">= ruolo_minimo={min_role}"
            )

            # 5. Esecuzione funzione reale
            return func(*args, **kwargs)

        return wrapper
    return decorator
