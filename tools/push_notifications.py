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


def send_push_to_user(user_id: int, title: str, body: str, url: str = "/"):
    subscriptions = PushSubscription.query.filter_by(user_id=user_id, is_active=True).all()
    return send_push_to_subscriptions(subscriptions, {"title": title, "body": body, "url": url})


def send_push_to_staff(title: str, body: str, url: str = "/", min_weight: int = 30):
    users = User.query.all()
    user_ids = [user.id for user in users if (user.max_role_weight or 0) >= min_weight]
    if not user_ids:
        return {"sent": 0, "failed": 0, "errors": []}
    subscriptions = (
        PushSubscription.query
        .filter(PushSubscription.user_id.in_(user_ids), PushSubscription.is_active.is_(True))
        .all()
    )
    return send_push_to_subscriptions(subscriptions, {"title": title, "body": body, "url": url})
