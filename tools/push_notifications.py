from __future__ import annotations

import json
from typing import Iterable

from flask import current_app

from extensions import db
from models import PushSubscription
from tools.log_utils import get_logger

logger = get_logger("push_notifications")


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
    sent = 0
    failed = 0
    for sub in subscriptions:
        if not sub.is_active:
            continue
        try:
            webpush(
                subscription_info=sub.to_webpush(),
                data=json.dumps(payload),
                vapid_private_key=cfg["private_key"],
                vapid_claims={"sub": cfg["subject"]},
            )
            sent += 1
        except WebPushException as exc:
            failed += 1
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if status_code in {404, 410}:
                sub.is_active = False
            logger.warning("Push fallita subscription=%s status=%s error=%s", sub.id, status_code, exc)
        except Exception as exc:
            failed += 1
            logger.exception("Errore invio push subscription=%s: %s", sub.id, exc)
    db.session.commit()
    return {"sent": sent, "failed": failed}


def send_push_to_user(user_id: int, title: str, body: str, url: str = "/"):
    subscriptions = PushSubscription.query.filter_by(user_id=user_id, is_active=True).all()
    return send_push_to_subscriptions(subscriptions, {"title": title, "body": body, "url": url})
