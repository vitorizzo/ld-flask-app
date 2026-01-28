import logging
import requests

from flask import Blueprint, request, render_template, abort, jsonify
from flask_login import login_required
from sqlalchemy.inspection import inspect as sa_inspect

from extensions import db
from models import AutomationAction, Automation, SlackConnection
from tools.log_utils import get_logger

logger = get_logger("automations_v2", level=logging.INFO)
logger.debug("Logger 'automations_v2' inizializzato correttamente - test DEBUG")

automations_v2_bp = Blueprint("automations_v2", __name__, url_prefix="/api")


def _serialize(model):
    mapper = sa_inspect(model.__class__)
    data = {}
    for col in mapper.columns:
        v = getattr(model, col.key)
        if hasattr(v, "isoformat"):  # datetime/date
            v = v.isoformat()
        data[col.key] = v
    return data


def _model_by_tablename(tablename: str):
    """
    Trova dinamicamente la classe Model mappata a __tablename__ == tablename.
    Evita di dipendere dal nome classe (TrelloConnection/SlackConnection ecc.).
    """
    registry = getattr(db.Model, "registry", None)
    if not registry:
        return None

    class_registry = getattr(registry, "_class_registry", {}) or {}
    for cls in class_registry.values():
        if isinstance(cls, type) and getattr(cls, "__tablename__", None) == tablename:
            return cls
    return None


def _best_label(obj) -> str:
    # prova campi tipici per visualizzare una connection in UI
    for attr in (
        "name",
        "label",
        "title",
        "board_name",
        "workspace_name",
        "team_name",
        "username",
        "bot_name",
        "app_name",
    ):
        if hasattr(obj, attr):
            val = getattr(obj, attr)
            if val:
                return str(val)
    # fallback
    if hasattr(obj, "id"):
        return f"Connection {obj.id}"
    return "Connection"


@automations_v2_bp.route("/automation_v2", methods=["GET"])
@login_required
def automations_home():
    """UI Automazioni V2"""
    logger.info("Apertura pagina Automazioni V2")
    return render_template("automations_v2.html")


@automations_v2_bp.get("/automations/capabilities")
def get_capabilities():
    logger.info("[GET] /automations/capabilities")
    from config.capabilities import CAPABILITIES
    return CAPABILITIES, 200


@automations_v2_bp.get("/connections/<app>")
@login_required
def list_connections(app: str):
    """
    Ritorna le connessioni disponibili per una specifica app.
    App supportate: trello, slack
    Output: [{id, name}]
    """
    app = (app or "").lower().strip()
    logger.info("[GET] /connections/%s", app)

    if app == "trello":
        tablename = "trello_connections"
    elif app == "slack":
        tablename = "slack_connections"
    else:
        abort(404, description="App non supportata")

    Model = _model_by_tablename(tablename)
    if Model is None:
        logger.error("Model non trovato per tabella %s (forse non mappata in models.py)", tablename)
        abort(500, description=f"Model non mappato per {tablename}")

    rows = Model.query.order_by(Model.id.desc()).all()
    out = [{"id": r.id, "name": _best_label(r)} for r in rows]
    return out, 200


# ------------------------------------------------------------
# NEW: Slack channels list for trigger-config UI
# GET /api/connections/slack/<connection_id>/channels
# ------------------------------------------------------------
@automations_v2_bp.get("/connections/slack/<int:connection_id>/channels")
@login_required
def slack_channels(connection_id: int):
    logger.info("[GET] /connections/slack/%s/channels", connection_id)

    conn = SlackConnection.query.get_or_404(connection_id)

    # Slack bot token (decrypted by EncryptedString descriptor in model)
    token = conn.bot_token
    if not token:
        abort(500, description="Slack bot_token mancante per questa connection")

    # Slack conversations.list supports pagination via response_metadata.next_cursor
    url = "https://slack.com/api/conversations.list"
    headers = {"Authorization": f"Bearer {token}"}

    # Include: public, private, im (DM), mpim (group DM)
    params = {
        "limit": 1000,
        "types": "public_channel,private_channel,im,mpim",
        "exclude_archived": "true",
    }

    out = []
    cursor = None
    try:
        while True:
            if cursor:
                params["cursor"] = cursor
            else:
                params.pop("cursor", None)

            r = requests.get(url, headers=headers, params=params, timeout=20)
            r.raise_for_status()
            data = r.json() or {}

            if not data.get("ok"):
                # Slack returns ok:false + error
                err = data.get("error") or "unknown_error"
                logger.error("Slack conversations.list failed: %s", err)
                abort(502, description=f"Slack API error: {err}")

            channels = data.get("channels") or []
            for c in channels:
                if not isinstance(c, dict):
                    continue

                cid = str(c.get("id") or "")
                if not cid:
                    continue

                # name can be missing for IM/MPIM in some contexts; keep fallback stable
                name = (
                    c.get("name")
                    or c.get("name_normalized")
                    or c.get("user")  # for IM often has "user"
                    or cid
                )

                is_private = bool(
                    c.get("is_private")
                    or c.get("is_mpim")
                    or c.get("is_im")
                    or False
                )

                out.append({"id": cid, "name": str(name), "is_private": is_private})

            cursor = ((data.get("response_metadata") or {}).get("next_cursor") or "").strip()
            if not cursor:
                break

    except requests.RequestException:
        logger.exception("Errore chiamando Slack conversations.list")
        abort(502, description="Errore chiamata Slack API (conversations.list)")

    return jsonify(out), 200


@automations_v2_bp.get("/automations")
def list_automations():
    logger.info("[GET] /automations")
    autos = Automation.query.order_by(Automation.id.desc()).all()
    return [_serialize(a) for a in autos], 200


# NOTA: questa route era buggata (path senza <automation_id> ma parametro presente)
@automations_v2_bp.get("/automations/<int:automation_id>")
def get_automation(automation_id: int):
    logger.info("[GET] /automations/%s", automation_id)
    auto = Automation.query.get_or_404(automation_id)

    q = AutomationAction.query.filter_by(automation_id=auto.id)
    for order_col in ("order", "order_index", "position", "pos", "sort_index"):
        if hasattr(AutomationAction, order_col):
            q = q.order_by(getattr(AutomationAction, order_col).asc())
            break
    actions = q.all()

    data = _serialize(auto)
    data["actions"] = [_serialize(a) for a in actions]
    return data, 200


@automations_v2_bp.post("/automations")
def create_automation():
    payload = request.get_json() or {}
    logger.info("[POST] /automations keys=%s", list(payload.keys()))

    name = (payload.get("name") or "").strip()
    description = payload.get("description")
    enabled = payload.get("enabled", True)

    logger.info("[POST] /automations payload.name=%r enabled=%r", name, enabled)

    # name è NOT NULL nel DB: se il frontend non lo manda (o è vuoto) blocchiamo
    if not name:
        abort(400, description="Campo 'name' obbligatorio")

    auto = Automation(
        name=name,
        description=description,
        trigger_app=payload["trigger"]["app"],
        trigger_connection=payload["trigger"]["connection_id"],
        trigger_type=payload["trigger"]["type"],
        trigger_config=payload["trigger"].get("config", {}) or {},
        enabled=enabled,
    )
    db.session.add(auto)
    db.session.flush()

    for act in payload.get("actions", []):
        db.session.add(
            AutomationAction(
                automation_id=auto.id,
                action_app=act["app"],
                action_type=act["type"],
                order_index=act.get("order", 0),
                action_config=act.get("config", {}) or {},
                enabled=True,
            )
        )

    db.session.commit()
    logger.info("[CREATE] automation_id=%s", auto.id)

    data = _serialize(auto)
    # ritorno anche actions appena create
    actions = AutomationAction.query.filter_by(automation_id=auto.id).all()
    data["actions"] = [_serialize(a) for a in actions]
    return data, 201
