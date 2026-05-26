from flask import Blueprint, render_template, url_for
from flask_login import login_required, current_user


documents_bp = Blueprint("documents", __name__)


def _ld_selection_pdf_filename() -> str:
    active_roles = {getattr(role, "name", "").strip().lower() for role in current_user.active_roles or []}
    max_weight = current_user.max_role_weight or 0

    if max_weight >= 30:
        return "documents/LD_Selection_top.pdf"
    if "customer" in active_roles:
        return "documents/LD_Selection.pdf"
    if "horeca" in active_roles:
        return "documents/LD_Selection_pro.pdf"
    return "documents/LD_Selection_top.pdf"


@documents_bp.route("/ld-selection", methods=["GET"])
@login_required
def ld_selection():
    pdf_filename = _ld_selection_pdf_filename()
    pdf_url = url_for("static", filename=pdf_filename, _external=True)
    can_share = (current_user.max_role_weight or 0) >= 30
    return render_template(
        "documents/ld_selection.html",
        pdf_url=pdf_url,
        pdf_filename=pdf_filename.rsplit("/", 1)[-1],
        can_share=can_share,
    )
