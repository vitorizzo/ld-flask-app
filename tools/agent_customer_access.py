"""Shared authorization helpers for agent customer-facing features."""

from sqlalchemy import or_

from extensions import db
from models import AgentCustomer, AgentCustomerZone, BusinessRegistry


AGENT_ROLE_NAMES = {"agente", "agent"}


def user_is_agent(user):
    return bool(
        user
        and any(
            (getattr(role, "name", "") or "").strip().casefold() in AGENT_ROLE_NAMES
            for role in (getattr(user, "active_roles", None) or [])
        )
    )


def agent_customer_registry_query(user):
    """Active customer records assigned directly or through an assigned zone."""
    user_id = getattr(user, "id", None)
    if not user_id:
        return BusinessRegistry.query.filter(db.false())
    individual_registry_ids = db.session.query(AgentCustomer.registry_id).filter(
        AgentCustomer.user_id == user_id
    )
    zone_codes = db.session.query(AgentCustomerZone.zone_code).filter(
        AgentCustomerZone.user_id == user_id
    )
    return BusinessRegistry.query.filter(
        BusinessRegistry.kind == "customer",
        BusinessRegistry.is_active.is_(True),
        or_(
            BusinessRegistry.id.in_(individual_registry_ids),
            BusinessRegistry.zone_code.in_(zone_codes),
        ),
    )


def agent_can_access_registry(user, registry_id):
    try:
        requested_id = int(registry_id)
    except (TypeError, ValueError):
        return False
    return agent_customer_registry_query(user).filter(BusinessRegistry.id == requested_id).first() is not None
