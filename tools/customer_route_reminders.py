from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import current_app
from sqlalchemy.exc import IntegrityError

from extensions import db
from models import (
    CustomerRegistryMembership,
    CustomerRouteOrderReminder,
    DeliveryRoute,
    DeliveryRouteCustomer,
    DeliveryScheduleRule,
    PushSubscription,
    RouteOrderBoardEntry,
    SlackOrder,
    User,
)
from tools.log_utils import get_logger
from tools.push_notifications import send_push_to_user


logger = get_logger("customer_route_reminders")
TERMINAL_ORDER_STATUSES = {"annullato", "annullata", "cancellato", "cancelled"}
BOARD_COMPLETED_STATUSES = {"ordine_fatto", "salta_giro"}


def _local_now(now=None):
    if now is not None:
        return now.replace(tzinfo=None) if getattr(now, "tzinfo", None) else now
    timezone_name = current_app.config.get("CUSTOMER_ROUTE_REMINDER_TIMEZONE", "Europe/Rome")
    return datetime.now(ZoneInfo(timezone_name)).replace(tzinfo=None)


def _delivery_for_date(route, target_date: date, *, local_now: datetime):
    """Restituisce il passaggio effettivo nella data, incluse variazioni una tantum."""
    from routes.route_orders import _next_delivery_dt

    moved_here = (
        DeliveryScheduleRule.query
        .filter_by(
            route_id=route.id,
            scope="once",
            target_date=target_date,
            is_active=True,
        )
        .order_by(DeliveryScheduleRule.id.desc())
        .first()
    )
    if moved_here:
        return datetime.combine(target_date, moved_here.target_time or route.default_time)

    cursor = datetime.combine(local_now.date(), time.min) - timedelta(minutes=1)
    for _ in range(8):
        candidate = _next_delivery_dt(route, cursor)
        if not candidate or candidate.date() > target_date:
            return None
        if candidate.date() == target_date:
            return candidate
        cursor = candidate + timedelta(minutes=1)
    return None


def _eligible_users_by_registry(registry_ids):
    if not registry_ids:
        return {}
    subscribed_user_ids = [
        row[0]
        for row in (
            db.session.query(PushSubscription.user_id)
            .filter(PushSubscription.is_active.is_(True))
            .distinct()
            .all()
        )
    ]
    if not subscribed_user_ids:
        return {}

    users = User.query.filter(User.id.in_(subscribed_user_ids)).all()
    users_by_id = {
        user.id: user
        for user in users
        if user.has_active_role("customer_horeca")
    }
    if not users_by_id:
        return {}

    result = defaultdict(dict)
    memberships = (
        CustomerRegistryMembership.query
        .filter(
            CustomerRegistryMembership.user_id.in_(tuple(users_by_id)),
            CustomerRegistryMembership.registry_id.in_(tuple(registry_ids)),
            CustomerRegistryMembership.status == "active",
        )
        .all()
    )
    for membership in memberships:
        result[membership.registry_id][membership.user_id] = users_by_id[membership.user_id]

    # Compatibilita' con la precedente associazione singola presente su User.
    for user in users_by_id.values():
        if user.customer_registry_id in registry_ids:
            result[user.customer_registry_id][user.id] = user
    return {registry_id: list(users.values()) for registry_id, users in result.items()}


def _blocked_registries(route, links, delivery_at):
    registry_ids = [link.registry_id for link in links]
    if not registry_ids:
        return set()

    blocked = set()
    entries = RouteOrderBoardEntry.query.filter(
        RouteOrderBoardEntry.route_id == route.id,
        RouteOrderBoardEntry.registry_id.in_(registry_ids),
        RouteOrderBoardEntry.board_date == delivery_at.date(),
    ).all()
    for entry in entries:
        if entry.status in BOARD_COMPLETED_STATUSES or entry.sent_at is not None:
            blocked.add(entry.registry_id)

    keys_to_registry = defaultdict(set)
    for link in links:
        registry = link.registry
        if not registry:
            continue
        key = str(registry.source_code or registry.id).strip()
        if key:
            keys_to_registry[key].add(registry.id)
    if not keys_to_registry:
        return blocked

    day_start = datetime.combine(delivery_at.date(), time.min)
    day_end = day_start + timedelta(days=1)
    orders = SlackOrder.query.filter(
        SlackOrder.route_id == route.id,
        SlackOrder.customer_key.in_(tuple(keys_to_registry)),
        SlackOrder.planned_delivery_at >= day_start,
        SlackOrder.planned_delivery_at < day_end,
    ).all()
    for order in orders:
        if (order.status or "").strip().lower() not in TERMINAL_ORDER_STATUSES:
            blocked.update(keys_to_registry.get(str(order.customer_key or "").strip(), ()))
    return blocked


def _reserve_reminder(user, route, registry, delivery_date):
    def retryable(existing):
        if existing is None or existing.status != "queued":
            return None
        created_at = existing.created_at
        if created_at and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if created_at and created_at > datetime.now(timezone.utc) - timedelta(minutes=30):
            return None
        existing.created_at = datetime.now(timezone.utc)
        existing.last_error = None
        db.session.commit()
        return existing

    existing = CustomerRouteOrderReminder.query.filter_by(
        user_id=user.id,
        route_id=route.id,
        registry_id=registry.id,
        delivery_date=delivery_date,
    ).first()
    if existing:
        return retryable(existing)

    reminder = CustomerRouteOrderReminder(
        user_id=user.id,
        route_id=route.id,
        registry_id=registry.id,
        delivery_date=delivery_date,
        status="queued",
    )
    db.session.add(reminder)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        existing = CustomerRouteOrderReminder.query.filter_by(
            user_id=user.id,
            route_id=route.id,
            registry_id=registry.id,
            delivery_date=delivery_date,
        ).first()
        return retryable(existing)
    return reminder


def dispatch_customer_route_order_reminders(now=None, *, ignore_send_hour=False):
    """Invia una sola notifica per utente, cliente, giro e data di consegna."""
    local_now = _local_now(now)
    send_hour = int(current_app.config.get("CUSTOMER_ROUTE_REMINDER_HOUR", 10))
    if not ignore_send_hour and local_now.hour < send_hour:
        return {"success": True, "skipped": True, "reason": "before_send_hour", "sent": 0}

    target_date = local_now.date() + timedelta(days=1)
    routes = DeliveryRoute.query.filter(DeliveryRoute.is_active.is_(True)).all()
    route_deliveries = []
    for route in routes:
        delivery_at = _delivery_for_date(route, target_date, local_now=local_now)
        if delivery_at:
            route_deliveries.append((route, delivery_at))

    sent = failed = skipped = 0
    for route, delivery_at in route_deliveries:
        links = (
            DeliveryRouteCustomer.query
            .filter_by(route_id=route.id, is_active=True)
            .all()
        )
        users_by_registry = _eligible_users_by_registry({link.registry_id for link in links})
        blocked = _blocked_registries(route, links, delivery_at)
        for link in links:
            if link.registry_id in blocked:
                skipped += 1
                continue
            registry = link.registry
            for user in users_by_registry.get(link.registry_id, ()):
                reminder = _reserve_reminder(user, route, registry, target_date)
                if reminder is None:
                    skipped += 1
                    continue
                order_url = f"/customer-orders/reminders/{reminder.public_id}/order"
                skip_url = f"/customer-orders/reminders/{reminder.public_id}/skip"
                payload = {
                    "category": "customer-route-reminder",
                    "tag": f"route-reminder-{user.id}-{route.id}-{registry.id}-{target_date.isoformat()}",
                    "renotify": False,
                    "icon": "/static/icons/icon-192.png",
                    "badge": "/static/icons/icon-192.png",
                    "actions": [
                        {"action": "route-order", "title": "Fai ordine adesso"},
                        {"action": "route-skip", "title": "Salta il giro"},
                    ],
                    "action_urls": {
                        "route-order": order_url,
                        "route-skip": skip_url,
                    },
                }
                try:
                    result = send_push_to_user(
                        user.id,
                        f"Domani passa il giro {route.name}",
                        "Non risulta ancora un ordine. Vuoi farlo adesso o saltare il giro?",
                        order_url,
                        payload=payload,
                    )
                    if int(result.get("sent") or 0) <= 0:
                        db.session.delete(reminder)
                        db.session.commit()
                        failed += 1
                        continue
                    reminder.status = "sent"
                    reminder.sent_at = datetime.now(timezone.utc)
                    db.session.commit()
                    sent += 1
                except Exception as exc:
                    logger.exception(
                        "Promemoria giro fallito user=%s route=%s registry=%s date=%s",
                        user.id, route.id, registry.id, target_date,
                    )
                    db.session.delete(reminder)
                    db.session.commit()
                    failed += 1

    summary = {
        "success": failed == 0,
        "target_date": target_date.isoformat(),
        "routes": len(route_deliveries),
        "sent": sent,
        "failed": failed,
        "skipped": skipped,
    }
    logger.info("Promemoria ordini giro completati: %s", summary)
    return summary
