# routes/slack.py
import hmac
import time
import hashlib
import logging

from flask import Blueprint, request, jsonify, current_app
from datetime import datetime

from models import db, SlackConnection, SlackAction
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

        # --- Persistenza evento (audit + dedup) ---
        try:
            from models import db, SlackEvent

            # Dedup: usa event_id se presente, altrimenti combinazione stabile
            event_id = payload.get("event_id")
            event_ts = event.get("event_ts") or event.get("ts") or (event.get("item") or {}).get("ts")

            dedup_key = event_id or f"{event_type}:{event_ts}:{payload.get('team_id')}"

            exists = SlackEvent.query.filter_by(dedup_key=dedup_key).first()
            if not exists:
                se = SlackEvent(
                    connection_id=None,  # lo agganceremo dopo (quando salviamo SlackConnection)
                    trigger_type=event_type if event_type != "message" else "message.channels",
                    event_ts=str(event_ts) if event_ts else None,
                    dedup_key=dedup_key,
                    payload=payload
                )
                db.session.add(se)
                db.session.commit()
            else:
                logger.debug("SlackEvent duplicato ignorato dedup_key=%s", dedup_key)

        except Exception:
            logger.exception("Errore salvando SlackEvent (non blocco ACK)")
            db.session.rollback()
        # --- fine persistenza ---

        if event_type == "reaction_added":
            logger.info(
                "Slack reaction_added: user=%s item_channel=%s item_ts=%s reaction=%s",
                event.get("user"),
                (event.get("item") or {}).get("channel"),
                (event.get("item") or {}).get("ts"),
                event.get("reaction"),
            )

        p = SlackProcessor()
        logger.info("Slack event_callback ricevuto: event_type=%s", event.get("type"))

        p.dispatch_event(event_type, event)

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


@slack_bp.route("/actions", methods=["GET"])
def list_slack_actions():
    connection_id = request.args.get("connection_id", type=int)
    if not connection_id:
        return jsonify({"error": "connection_id mancante"}), 400

    actions = (
        SlackAction.query
        .filter_by(connection_id=connection_id)
        .order_by(SlackAction.ordine.asc().nullslast())
        .all()
    )

    return jsonify([a.to_dict() for a in actions])


@slack_bp.route("/actions/<int:action_id>", methods=["GET"])
def get_slack_action(action_id):
    action = SlackAction.query.get_or_404(action_id)
    return jsonify(action.to_dict())


@slack_bp.route("/actions", methods=["POST"])
def create_slack_action():
    data = request.get_json(force=True)

    required = ["connection_id", "trigger_type", "action_type", "config_json"]
    missing = [k for k in required if k not in data]
    if missing:
        return jsonify({"error": f"Campi mancanti: {missing}"}), 400

    action = SlackAction(
        connection_id=data["connection_id"],
        trigger_type=data["trigger_type"],
        action_type=data["action_type"],
        config_json=data["config_json"],
        ordine=data.get("ordine"),
        created_at=datetime.utcnow(),
    )

    db.session.add(action)
    db.session.commit()

    logger.info("SlackAction creata id=%s", action.id)
    return jsonify(action.to_dict()), 201


@slack_bp.route("/actions/<int:action_id>", methods=["PUT"])
def update_slack_action(action_id):
    action = SlackAction.query.get_or_404(action_id)
    data = request.get_json(force=True)

    for field in ["trigger_type", "action_type", "config_json", "ordine"]:
        if field in data:
            setattr(action, field, data[field])

    db.session.commit()

    logger.info("SlackAction aggiornata id=%s", action.id)
    return jsonify(action.to_dict())


@slack_bp.route("/actions/<int:action_id>", methods=["DELETE"])
def delete_slack_action(action_id):
    action = SlackAction.query.get_or_404(action_id)

    db.session.delete(action)
    db.session.commit()

    logger.info("SlackAction eliminata id=%s", action_id)
    return jsonify({"ok": True})


def to_dict(self):
    return {
        "id": self.id,
        "connection_id": self.connection_id,
        "trigger_type": self.trigger_type,
        "action_type": self.action_type,
        "config_json": self.config_json,
        "ordine": self.ordine,
        "created_at": self.created_at.isoformat() if self.created_at else None,
    }


