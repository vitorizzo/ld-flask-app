import functools
from flask import redirect, url_for, request, flash
from tools.auth_manager import get_current_user
from tools.log_utils import get_logger
from models import Role

logger = get_logger("role_required")

def resolve_minimum_weight(minimum_role):
    """Return the current weight for a role-name authorization threshold."""
    if minimum_role is None:
        return None
    if isinstance(minimum_role, str):
        role_name = minimum_role.strip().casefold()
        if role_name in ("dev", "developer"):
            role = Role.query.filter(Role.name.ilike("dev")).first() or Role.query.filter(Role.name.ilike("developer")).first()
        else:
            role = Role.query.filter(Role.name.ilike(role_name)).first()
        return role.weight if role else None
    # Legacy numeric callers are mapped centrally while callers are migrated.
    legacy_roles = ((20, "customer"), (30, "staff"), (40, "office"), (100, "admin"), (500, "dev"))
    role_name = next((name for limit, name in legacy_roles if minimum_role <= limit), "dev")
    role = Role.query.filter(Role.name.ilike(role_name)).first()
    return role.weight if role else None

def menu_minimum_weight(menu):
    """Use the menu role foreign key; translate untouched legacy rows centrally."""
    role = getattr(menu, "minimum_role", None)
    if role is not None:
        return role.weight
    if getattr(menu, "item_type", "link") == "separator":
        return 0
    return resolve_minimum_weight(getattr(menu, "weight", None))

def meets_minimum_role(user, minimum_role):
    """Compare the active user weight with the live weight of a named role."""
    minimum_weight = resolve_minimum_weight(minimum_role)
    return minimum_weight is not None and (user.max_role_weight or 0) >= minimum_weight

def role_required(min_weight=None, roles=None):
    """Authorize against the live weight of the named minimum role."""
    minimum_role = min_weight
    allowed_roles = {str(role).casefold() for role in (roles or [])}
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                user = get_current_user()
            except Exception:
                return _deny_access()
            active_roles = user.active_roles or []
            user_role_names = {r.name.casefold() for r in active_roles}
            minimum_weight = resolve_minimum_weight(minimum_role) if minimum_role is not None else 0
            if minimum_weight is not None and (user.max_role_weight or 0) >= minimum_weight:
                return func(*args, **kwargs)
            if allowed_roles and user_role_names.intersection(allowed_roles):
                return func(*args, **kwargs)
            return _deny_access()
        return wrapper
    return decorator

def _deny_access():
    if request.method == "POST" or request.is_json:
        return {"error": "Accesso negato"}, 403
    flash("Accesso negato", "danger")
    return redirect(url_for("auth.login"))
