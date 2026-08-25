from datetime import datetime, timezone

from extensions import db
from models import BusinessRegistry, CustomerRegistryMembership


ACTIVE_STATUS = "active"


def active_customer_memberships(user):
    if not user or not getattr(user, "id", None):
        return []
    return (
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


def customer_registry_for_user(user, registry_id=None):
    memberships = active_customer_memberships(user)
    if registry_id is not None:
        try:
            requested_id = int(registry_id)
        except (TypeError, ValueError):
            return None
        return next((membership.registry for membership in memberships if membership.registry_id == requested_id), None)
    if memberships:
        primary = next((membership for membership in memberships if membership.is_primary), memberships[0])
        return primary.registry

    # Compatibilita durante il deploy: il campo storico resta la sorgente primaria
    # finche la migrazione non ha completato il backfill delle associazioni.
    registry = getattr(user, "customer_registry", None)
    if registry and registry.kind == "customer" and registry.is_active:
        return registry
    return None


def set_primary_customer_membership(user, registry, approved_by_user_id=None, source="manual", role="owner"):
    if registry.kind != "customer" or not registry.is_active:
        raise ValueError("L'anagrafica deve essere un cliente attivo")

    now = datetime.now(timezone.utc)
    membership = CustomerRegistryMembership.query.filter_by(user_id=user.id, registry_id=registry.id).first()
    for current in CustomerRegistryMembership.query.filter_by(user_id=user.id, is_primary=True).all():
        if current.registry_id != registry.id:
            current.is_primary = False
    db.session.flush()

    if membership is None:
        membership = CustomerRegistryMembership(user=user, registry=registry)
        db.session.add(membership)
    membership.role = role
    membership.status = ACTIVE_STATUS
    membership.is_primary = True
    membership.source = source
    membership.approved_by_user_id = approved_by_user_id
    membership.approved_at = now
    user.customer_registry_id = registry.id
    return membership


def clear_primary_customer_membership(user):
    for membership in CustomerRegistryMembership.query.filter_by(user_id=user.id, is_primary=True).all():
        membership.is_primary = False
        membership.status = "revoked"
    user.customer_registry_id = None
