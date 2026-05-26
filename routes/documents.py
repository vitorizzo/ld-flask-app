from flask import Blueprint, render_template
from flask_login import login_required


documents_bp = Blueprint("documents", __name__)


@documents_bp.route("/ld-selection", methods=["GET"])
@login_required
def ld_selection():
    return render_template("documents/ld_selection.html")
