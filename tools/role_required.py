import functools
from types import SimpleNamespace
from flask import redirect, url_for, request, flash
from tools.auth_manager import get_current_user
from tools.log_utils import get_logger
from models import Role
from extensions import db
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

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

def load_navigation_menus():
    """Load visible menus, including during rollout before the FK migration."""
    try:
        columns = {column["name"] for column in inspect(db.engine).get_columns("menus")}
    except SQLAlchemyError:
        db.session.rollback()
        raise
    if "minimum_role_id" in columns:
        from models import Menu
        return Menu.query.filter(Menu.is_visible.is_(True)).order_by(Menu.parent_id, Menu.sort_order, Menu.id).all()
    rows = db.session.execute(text("SELECT id, name, weight, sort_order, parent_id, route, is_active, is_visible, item_type FROM menus WHERE is_visible = 1 ORDER BY parent_id, sort_order, id")).mappings()
    return [SimpleNamespace(**dict(row), minimum_role=None) for row in rows]

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

def role_required(min_weight=None, roles=None, *, configurable=True):
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
            user_role_names = {r.name.strip().casefold() for r in active_roles}
            user_role_ids = {r.id for r in active_roles}
            policy = _access_policy(request.endpoint) if configurable else None
            if policy and policy.mode == "roles":
                permitted = set(policy.allowed_role_ids or [])
                return func(*args, **kwargs) if user_role_ids.intersection(permitted) else _deny_access()
            required_weight = None
            if policy and policy.mode == "minimum":
                required_weight = policy.minimum_role.weight if policy.minimum_role else None
            elif not policy:
                required_weight = resolve_minimum_weight(minimum_role) if minimum_role is not None else 0
            policy_extra_roles = set(policy.allowed_role_ids or []) if policy and policy.mode == "minimum" else set()
            if required_weight is not None and (user.max_role_weight or 0) >= required_weight:
                return func(*args, **kwargs)
            if user_role_ids.intersection(policy_extra_roles):
                return func(*args, **kwargs)
            if not policy and allowed_roles and user_role_names.intersection(allowed_roles):
                return func(*args, **kwargs)
            return _deny_access()
        wrapper._access_default_minimum_role = minimum_role
        wrapper._access_default_allowed_roles = sorted(allowed_roles)
        wrapper._access_configurable = configurable
        return wrapper
    return decorator

def _access_policy(endpoint):
    if not endpoint:
        return None
    try:
        from models import FunctionAccessPolicy
        return FunctionAccessPolicy.query.filter_by(function_key=endpoint).first()
    except SQLAlchemyError:
        db.session.rollback()
        logger.warning("Tabella permessi funzione non disponibile; uso la soglia predefinita.")
        return None

def _deny_access():
    if request.method == "POST" or request.is_json:
        return {"error": "Accesso negato"}, 403
    flash("Accesso negato", "danger")
    return redirect(url_for("auth.login"))
