from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Iterable
from urllib.parse import urlparse
import uuid

from flask import current_app

from extensions import db
from models import PushSubscription, User
from tools.log_utils import get_logger

logger = get_logger("push_notifications")
INVALID_SUBSCRIPTION_STATUSES = {400, 401, 403, 404, 410}
PUSH_TTL_SECONDS = 300
PUSH_TIMEOUT_SECONDS = 8
ORDER_NOTIFICATION_ICON = "/static/icons/icon-192.png"
ORDER_STATUS_BADGES = {
    "acquisito": "/static/icons/icon-192.png",
    "listato": "/static/icons/icon-192.png",
    "preparato": "/static/icons/icon-192.png",
    "controllato": "/static/icons/icon-192.png",
    "inconsegna": "/static/icons/icon-192.png",
    "evaso": "/static/icons/icon-192.png",
    "annullato": "/static/icons/icon-192.png",
}
ORDER_STATUS_LABELS = {
    "acquisito": "Acquisito",
    "listato": "Listato",
    "preparato": "Pronto",
    "controllato": "Controllato",
    "inconsegna": "In consegna",
    "evaso": "Evaso",
    "annullato": "Annullato",
}
SHIPMENT_STATUS_LABELS = {
    "created": "Creata",
    "in_transit": "In transito",
    "out_for_delivery": "In consegna",
    "delivered": "Consegnata",
    "exception": "Problema",
    "unknown": "Sconosciuta",
}


def push_config():
    private_key = current_app.config.get("VAPID_PRIVATE_KEY") or ""
    private_key_file = current_app.config.get("VAPID_PRIVATE_KEY_FILE") or ""
    if private_key_file and not private_key:
        private_key = private_key_file
    return {
        "public_key": current_app.config.get("VAPID_PUBLIC_KEY") or "",
        "private_key": private_key,
        "subject": current_app.config.get("VAPID_SUBJECT") or "mailto:admin@ldenoteca.it",
    }


def is_push_configured():
    cfg = push_config()
    return bool(cfg["public_key"] and cfg["private_key"])


def send_push_to_subscriptions(subscriptions: Iterable[PushSubscription], payload: dict):
    if not is_push_configured():
        raise RuntimeError("Chiavi VAPID mancanti")

    try:
        from pywebpush import WebPushException, webpush
    except Exception as exc:
        raise RuntimeError("Dipendenza pywebpush non installata") from exc

    cfg = push_config()
    prepared_payload = {
        **(payload or {}),
        "notification_id": (payload or {}).get("notification_id") or uuid.uuid4().hex,
        "sent_at": (payload or {}).get("sent_at") or datetime.now(timezone.utc).isoformat(),
    }
    sent = 0
    failed = 0
    errors = []
    for sub in subscriptions:
        if not sub.is_active:
            continue
        endpoint_host = urlparse(sub.endpoint or "").netloc
        try:
            response = webpush(
                subscription_info=sub.to_webpush(),
                data=json.dumps(prepared_payload),
                vapid_private_key=cfg["private_key"],
                vapid_claims={"sub": cfg["subject"]},
                ttl=PUSH_TTL_SECONDS,
                timeout=PUSH_TIMEOUT_SECONDS,
                headers={"Urgency": "high"},
            )
            sent += 1
            logger.info(
                "Push inviata subscription=%s host=%s status=%s notification_id=%s",
                sub.id,
                endpoint_host,
                getattr(response, "status_code", None),
                prepared_payload["notification_id"],
            )
        except WebPushException as exc:
            failed += 1
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            body = ""
            try:
                body = (getattr(exc.response, "text", "") or "")[:500] if exc.response is not None else ""
            except Exception:
                body = ""
            if status_code in INVALID_SUBSCRIPTION_STATUSES:
                sub.is_active = False
            errors.append({
                "subscription_id": sub.id,
                "endpoint_host": endpoint_host,
                "status": status_code,
                "error": str(exc),
                "body": body,
            })
            logger.warning(
                "Push fallita subscription=%s host=%s status=%s inactive=%s notification_id=%s error=%s",
                sub.id,
                endpoint_host,
                status_code,
                status_code in INVALID_SUBSCRIPTION_STATUSES,
                prepared_payload["notification_id"],
                exc,
            )
        except Exception as exc:
            failed += 1
            errors.append({
                "subscription_id": sub.id,
                "endpoint_host": endpoint_host,
                "status": None,
                "error": str(exc),
                "body": "",
            })
            logger.exception(
                "Errore invio push subscription=%s host=%s notification_id=%s: %s",
                sub.id,
                endpoint_host,
                prepared_payload["notification_id"],
                exc,
            )
    db.session.commit()
    return {"sent": sent, "failed": failed, "errors": errors}


def send_push_to_user(user_id: int, title: str, body: str, url: str = "/", payload: dict | None = None):
    subscriptions = PushSubscription.query.filter_by(user_id=user_id, is_active=True).all()
    return send_push_to_subscriptions(subscriptions, {**(payload or {}), "title": title, "body": body, "url": url})


def send_push_to_staff(title: str, body: str, url: str = "/", min_weight: int = 30, payload: dict | None = None):
    users = User.query.all()
    user_ids = [user.id for user in users if (user.max_role_weight or 0) >= min_weight]
    if not user_ids:
        return {"sent": 0, "failed": 0, "errors": []}
    subscriptions = (
        PushSubscription.query
        .filter(PushSubscription.user_id.in_(user_ids), PushSubscription.is_active.is_(True))
        .all()
    )
    return send_push_to_subscriptions(subscriptions, {**(payload or {}), "title": title, "body": body, "url": url})


def _order_notification_actions(status: str):
    actions = [{"action": "view-order", "title": "Apri"}]
    if status in {"acquisito", "listato"}:
        actions.append({"action": "status:preparato", "title": "Pronto"})
    elif status in {"preparato", "controllato"}:
        actions.append({"action": "status:inconsegna", "title": "Consegna"})
    elif status == "inconsegna":
        actions.append({"action": "status:evaso", "title": "Evadi"})
    return actions


def order_push_payload(order, *, title: str = "Nuovo ordine", body: str | None = None, url: str | None = None):
    order_id = getattr(order, "id", None)
    status = (getattr(order, "status", None) or "acquisito").strip()
    customer = body or getattr(order, "customer_display", None) or "Cliente"
    target_url = url or (f"/kiosk/order/{order_id}" if order_id else "/kiosk")
    status_label = ORDER_STATUS_LABELS.get(status, status)
    return {
        "title": title,
        "body": f"{customer} - {status_label}",
        "url": target_url,
        "category": "order",
        "tag": f"order-{order_id}" if order_id else "order",
        "icon": ORDER_NOTIFICATION_ICON,
        "badge": ORDER_STATUS_BADGES.get(status, ORDER_STATUS_BADGES["acquisito"]),
        "renotify": True,
        "order_id": order_id,
        "order_status": status,
        "actions": _order_notification_actions(status),
    }


def send_order_push_to_staff(order, *, title: str = "Nuovo ordine", body: str | None = None, url: str | None = None, min_weight: int = 30):
    payload = order_push_payload(order, title=title, body=body, url=url)
    return send_push_to_staff(
        payload["title"],
        payload["body"],
        payload["url"],
        min_weight=min_weight,
        payload=payload,
    )


def shipment_push_payload(shipment, *, title: str = "Spedizione aggiornata", body: str | None = None, url: str | None = None):
    shipment_id = getattr(shipment, "id", None)
    status = (getattr(shipment, "status", None) or "unknown").strip()
    status_label = SHIPMENT_STATUS_LABELS.get(status, getattr(shipment, "status_label", None) or status)
    tracking = getattr(shipment, "tracking_number", None) or "Tracking"
    customer = getattr(shipment, "customer_name", None) or getattr(shipment, "recipient_name", None) or ""
    message = body or " - ".join(part for part in [tracking, customer, status_label] if part)
    target_url = url or (f"/shipping?shipment_id={shipment_id}" if shipment_id else "/shipping")
    return {
        "title": title,
        "body": message,
        "url": target_url,
        "category": "shipment",
        "tag": f"shipment-{shipment_id}" if shipment_id else f"shipment-{tracking}",
        "icon": ORDER_NOTIFICATION_ICON,
        "badge": ORDER_NOTIFICATION_ICON,
        "renotify": True,
        "shipment_id": shipment_id,
        "shipment_status": status,
        "tracking_number": tracking,
        "actions": [{"action": "view-shipment", "title": "Apri"}],
    }


def send_shipment_push_to_staff(shipment, *, title: str = "Spedizione aggiornata", body: str | None = None, url: str | None = None, min_weight: int = 30):
    payload = shipment_push_payload(shipment, title=title, body=body, url=url)
    return send_push_to_staff(
        payload["title"],
        payload["body"],
        payload["url"],
        min_weight=min_weight,
        payload=payload,
    )
