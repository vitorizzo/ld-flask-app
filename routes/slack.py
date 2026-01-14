# routes/slack.py
import os
import hmac
import time
import json
import hashlib

import logging
from flask import Blueprint, request, jsonify, current_app

from tools.log_utils import get_logger

logger = get_logger("slack", level=logging.DEBUG)
logger.debug("🧪 Logger 'slack' inizializzato correttamente - test DEBUG")

slack_bp = Blueprint("slack", __name__, url_prefix="/slack")


def _verify_slack_signature(req) -> bool:
    """
    Verifica firma Slack Events API.
    Richiede env: SLACK_SIGNING_SECRET
    """
    signing_secret = os.getenv("SLACK_SIGNING_SECRET", "")
    logger.debug("Verifica firma Slack con secret: %s", signing_secret)
    if not signing_secret:
        current_app.logger.error("SLACK_SIGNING_SECRET mancante")
        return False

    timestamp = req.headers.get("X-Slack-Request-Timestamp", "")
    signature = req.headers.get("X-Slack-Signature", "")

    if not timestamp or not signature:
        return False

    # Protezione replay: rifiuta richieste più vecchie di 5 minuti
    try:
        ts = int(timestamp)
    except ValueError:
        return False

    if abs(time.time() - ts) > 60 * 5:
        current_app.logger.warning("Slack request timestamp fuori finestra (possible replay)")
        return False

    body = req.get_data(as_text=True)  # raw body
    basestring = f"v0:{timestamp}:{body}".encode("utf-8")

    computed = "v0=" + hmac.new(
        signing_secret.encode("utf-8"),
        basestring,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(computed, signature)


@slack_bp.route("/events", methods=["POST"])
def slack_events():
    # 1) Verifica firma
    if not _verify_slack_signature(request):
        return jsonify({"error": "invalid_signature"}), 401

    payload = request.get_json(silent=True) or {}

    # 2) Handshake Slack: url_verification
    if payload.get("type") == "url_verification":
        return jsonify({"challenge": payload.get("challenge", "")})

    # 3) Event callback (per ora solo log / ack)
    if payload.get("type") == "event_callback":
        event = payload.get("event", {}) or {}
        event_type = event.get("type")
        subtype = event.get("subtype")

        # Primo evento: message.channels -> type=message, channel_type=channel
        if event_type == "message" and event.get("channel_type") == "channel" and not subtype:
            current_app.logger.info(
                "Slack message event: channel=%s user=%s ts=%s text=%s",
                event.get("channel"),
                event.get("user"),
                event.get("ts"),
                (event.get("text") or "")[:200]
            )

        # ACK sempre rapido
        return jsonify({"ok": True})

    # fallback
    return jsonify({"ok": True})
