import logging

from flask import Blueprint, request, render_template
from flask_login import login_required
from sqlalchemy.inspection import inspect as sa_inspect

from extensions import db
from models import AutomationAction, Automation
from tools.log_utils import get_logger

logger = get_logger("automations_v2", level=logging.INFO)
logger.debug("🧪 Logger 'automations_v2' inizializzato correttamente - test DEBUG")

automations_v2_bp = Blueprint("automations_v2", __name__, url_prefix="/api")


@automations_v2_bp.route("/automation_v2", methods=["GET"])
@login_required
def automations_home():
    """
    UI Automazioni V2
    """
    logger.info("Apertura pagina Automazioni V2")
    return render_template("automations_v2.html")


@automations_v2_bp.get("/automations/capabilities")
def get_capabilities():
    logger.info("[GET] /automations/capabilities")
    from config.capabilities import CAPABILITIES
    return CAPABILITIES, 200


@automations_v2_bp.get("/automations")
def list_automations():
    logger.info("[GET] /automations")
    autos = Automation.query.order_by(Automation.id.desc()).all()

    def _serialize(model):
        mapper = sa_inspect(model.__class__)
        data = {}
        for col in mapper.columns:
            v = getattr(model, col.key)
            # datetime -> isoformat
            if hasattr(v, "isoformat"):
                v = v.isoformat()
            data[col.key] = v
        return data

    return [_serialize(a) for a in autos], 200


@automations_v2_bp.get("/automations/<int:automation_id>")
def get_automation(automation_id):
    logger.info("[GET] /automations/%s", automation_id)

    auto = Automation.query.get_or_404(automation_id)
    return auto.to_full_dict(), 200


@automations_v2_bp.post("/automations")
def create_automation():
    payload = request.get_json()
    logger.info("[POST] /automations keys=%s", list(payload.keys()))

    auto = Automation(
        trigger_app=payload["trigger"]["app"],
        trigger_connection_id=payload["trigger"]["connection_id"],
        trigger_type=payload["trigger"]["type"],
        trigger_config=payload["trigger"].get("config", {})
    )
    db.session.add(auto)
    db.session.flush()

    for act in payload["actions"]:
        db.session.add(AutomationAction(
            automation_id=auto.id,
            app=act["app"],
            action_type=act["type"],
            order=act["order"],
            action_config=act.get("config", {})
        ))

    db.session.commit()
    logger.info("[CREATE] automation_id=%s", auto.id)
    return auto.to_full_dict(), 201
