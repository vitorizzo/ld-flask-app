from datetime import datetime, timezone

from extensions import db
from models import BusinessRegistry, CustomerRegistryMembership


ACTIVE_STATUS = "active"
ACCESS_ADMINISTRATION = "administration"
ACCESS_MANAGEMENT = "management"
ACCESS_BOTH = "both"
ACCESS_SCOPES = {ACCESS_ADMINISTRATION, ACCESS_MANAGEMENT, ACCESS_BOTH}
LEGACY_ACCESS_MAP = {
    "owner": ACCESS_BOTH,
    "payments": ACCESS_ADMINISTRATION,
    "viewer": ACCESS_ADMINISTRATION,
}


def normalize_access_scope(value):
    normalized = str(value or "").strip().lower()
    normalized = LEGACY_ACCESS_MAP.get(normalized, normalized)
    return normalized if normalized in ACCESS_SCOPES else ACCESS_BOTH


def membership_allows(membership, capability):
    if capability is None:
        return True
    scope = normalize_access_scope(getattr(membership, "role", None))
    return scope == ACCESS_BOTH or scope == capability


def active_customer_memberships(user, capability=None):
    if not user or not getattr(user, "id", None):
        return []
    memberships = (
        CustomerRegistryMembership.query
        .join(BusinessRegistry, CustomerRegistryMembership.registry_id == BusinessRegistry.id)
        .filter(
            CustomerRegistryMembership.user_id == user.id,
            CustomerRegistryMembership.status == ACTIVE_STATUS,
            BusinessRegistry.kind == "customer",
            BusinessRegistry.is_active.is_(True),
        )
        .order_by(
            CustomerRegistryMembership.is_primary.desc(),
            BusinessRegistry.display_name.asc(),
            CustomerRegistryMembership.id.asc(),
        )
        .all()
    )
    return [membership for membership in memberships if membership_allows(membership, capability)]


def customer_membership_for_user(user, registry_id, capability=None):
    try:
        requested_id = int(registry_id)
    except (TypeError, ValueError):
        return None
    return next(
        (
            membership
            for membership in active_customer_memberships(user, capability=capability)
            if membership.registry_id == requested_id
        ),
        None,
    )


def customer_registry_for_user(user, registry_id=None, capability=None):
    all_memberships = active_customer_memberships(user)
    memberships = [
        membership
        for membership in all_memberships
        if membership_allows(membership, capability)
    ]
    if registry_id is not None:
        try:
            requested_id = int(registry_id)
        except (TypeError, ValueError):
            return None
        matched = next((membership.registry for membership in memberships if membership.registry_id == requested_id), None)
        if matched is not None or all_memberships:
            return matched
    if memberships:
        primary = next((membership for membership in memberships if membership.is_primary), memberships[0])
        return primary.registry
    if all_memberships:
        return None

    # Compatibilita durante il deploy: il campo storico resta la sorgente primaria
    # finche la migrazione non ha completato il backfill delle associazioni.
    registry = getattr(user, "customer_registry", None)
    if registry and registry.kind == "customer" and registry.is_active:
        if registry_id is not None and registry.id != requested_id:
            return None
        return registry
    return None


def set_customer_membership(
    user,
    registry,
    *,
    access_scope=ACCESS_BOTH,
    is_primary=False,
    approved_by_user_id=None,
    source="manual",
):
    if registry.kind != "customer" or not registry.is_active:
        raise ValueError("L'anagrafica deve essere un cliente attivo")

    now = datetime.now(timezone.utc)
    membership = CustomerRegistryMembership.query.filter_by(user_id=user.id, registry_id=registry.id).first()
    if is_primary:
        for current in CustomerRegistryMembership.query.filter_by(user_id=user.id, is_primary=True).all():
            if current.registry_id != registry.id:
                current.is_primary = False
        db.session.flush()
    if membership is None:
        membership = CustomerRegistryMembership(user=user, registry=registry)
        db.session.add(membership)
    membership.role = normalize_access_scope(access_scope)
    membership.status = ACTIVE_STATUS
    # Se non viene richiesto un cambio di cliente principale, conserva
    # l'eventuale associazione primaria gia' esistente.
    if is_primary:
        membership.is_primary = True
    membership.source = source
    membership.approved_by_user_id = approved_by_user_id
    membership.approved_at = now
    if membership.is_primary:
        user.customer_registry_id = registry.id
    elif not CustomerRegistryMembership.query.filter(
        CustomerRegistryMembership.user_id == user.id,
        CustomerRegistryMembership.status == ACTIVE_STATUS,
        CustomerRegistryMembership.is_primary.is_(True),
        CustomerRegistryMembership.id != membership.id,
    ).first():
        # Il primo collegamento diventa principale anche se il form non lo richiede.
        membership.is_primary = True
        user.customer_registry_id = registry.id
    return membership


def user_has_customer_capability(user, capability):
    if active_customer_memberships(user, capability=capability):
        return True
    # Il vecchio collegamento singolo vale solo finche' non esistono
    # associazioni esplicite: in questo modo non aggira i nuovi permessi.
    if active_customer_memberships(user):
        return False
    registry = getattr(user, "customer_registry", None)
    return bool(registry and registry.kind == "customer" and registry.is_active)


def set_primary_customer_membership(user, registry, approved_by_user_id=None, source="manual", role=ACCESS_BOTH):
    return set_customer_membership(
        user,
        registry,
        access_scope=role,
        is_primary=True,
        approved_by_user_id=approved_by_user_id,
        source=source,
    )


def revoke_customer_membership(user, membership):
    if membership.user_id != user.id:
        raise ValueError("L'associazione non appartiene all'utente")
    was_primary = bool(membership.is_primary) or user.customer_registry_id == membership.registry_id
    membership.status = "revoked"
    membership.is_primary = False
    if was_primary:
        replacement = (
            CustomerRegistryMembership.query
            .filter(
                CustomerRegistryMembership.user_id == user.id,
                CustomerRegistryMembership.status == ACTIVE_STATUS,
                CustomerRegistryMembership.id != membership.id,
            )
            .order_by(CustomerRegistryMembership.id.asc())
            .first()
        )
        if replacement:
            replacement.is_primary = True
            user.customer_registry_id = replacement.registry_id
        else:
            user.customer_registry_id = None
    return membership


def clear_primary_customer_membership(user):
    for membership in CustomerRegistryMembership.query.filter_by(user_id=user.id, is_primary=True).all():
        membership.is_primary = False
        membership.status = "revoked"
    user.customer_registry_id = None
