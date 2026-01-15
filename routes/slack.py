# routes/slack.py
import os
import hmac
import time
import json
import hashlib

import logging
from flask import Blueprint, request, jsonify, current_app

from tools.log_utils import get_logger

from tools.slack_processor import SlackProcessor

logger = get_logger("slack", level=logging.DEBUG)
logger.debug("🧪 Logger 'slack' inizializzato correttamente - test DEBUG")

slack_bp = Blueprint("slack", __name__, url_prefix="/slack")


def _verify_slack_signature(req) -> bool:
    """
    Verifica firma Slack Events API.
    Richiede env: SLACK_SIGNING_SECRET
    """
    # signing_secret = os.getenv("SLACK_SIGNING_SECRET", "")
    signing_secret = current_app.config.get("SLACK_SIGNING_SECRET", "")
    logger.debug("Verifica firma Slack: secret_present=%s", bool(signing_secret))
    if not signing_secret:
        logger.error("SLACK_SIGNING_SECRET mancante")
        return False

    timestamp = req.headers.get("X-Slack-Request-Timestamp", "")
    signature = req.headers.get("X-Slack-Signature", "")

    if not timestamp or not signature:
        return False
    logger.warning(
        "Slack signature check headers: ts=%s sig_present=%s body_len=%s",
        timestamp,
        bool(signature),
        len(req.get_data() or b""),
    )
    # Protezione replay: rifiuta richieste più vecchie di 5 minuti
    try:
        ts = int(timestamp)
    except ValueError:
        return False

    if abs(time.time() - ts) > 60 * 5:
        logger.warning("Slack request timestamp fuori finestra (possible replay)")
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
    """
    Endpoint per Slack Events API.
    1) Verifica firma
    2) Gestisce url_verification (handshake)
    3) Gestisce event_callback (log / ack)
    4) Fallback
    """

    logger.info("Ricevuta richiesta Slack Events API")

    # 1) Verifica firma
    if not _verify_slack_signature(request):
        logger.warning("Firma Slack non valida")
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
        p = SlackProcessor()
        logger.info("Slack event_callback ricevuto: event_type=%s", event.get("type"))

        # Primo evento: message.channels -> type=message, channel_type=channel
        if event_type == "message" and event.get("channel_type") == "channel" and not subtype:
            logger.info(
                "Slack message event: channel=%s user=%s ts=%s text=%s",
                event.get("channel"),
                event.get("user"),
                event.get("ts"),
                (event.get("text") or "")[:200]
            )
            p.handle_message_channels(channel=event.get("channel", ""), ts=event.get("ts", ""))

        # ACK sempre rapido
        return jsonify({"ok": True})

    # fallback
    return jsonify({"ok": True})
