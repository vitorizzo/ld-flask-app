import logging
from flask import Blueprint, render_template
from flask_login import login_required

from tools.log_utils import get_logger

cassa_bp = Blueprint("cassa", __name__, url_prefix="/cassa")
logger = get_logger("cassa", level=logging.INFO)


@cassa_bp.route("/agenda", methods=["GET"])
@login_required
def agenda():
    return render_template("agenda.html")
