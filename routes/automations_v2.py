import logging

from flask import Blueprint

from tools.log_utils import get_logger

logger = get_logger("automations_v2", level=logging.INFO)
logger.debug("🧪 Logger 'automations_v2' inizializzato correttamente - test DEBUG")

automations_v2_bp = Blueprint("automations_v2", __name__, url_prefix="/api")

