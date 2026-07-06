from flask import Blueprint, abort, render_template, url_for
from flask_login import login_required, current_user


documents_bp = Blueprint("documents", __name__)


LD_SELECTION_VERSIONS = {
    "top": {
        "key": "top",
        "label": "LD Selection Top",
        "filename": "documents/LD_Selection_Top.pdf",
    },
    "standard": {
        "key": "standard",
        "label": "LD Selection Standard",
        "filename": "documents/LD_Selection.pdf",
    },
    "horeca": {
        "key": "horeca",
        "label": "LD Selection Horeca",
        "filename": "documents/LD_Selection_Pro.pdf",
    },
}


def _active_role_names() -> set[str]:
    return {getattr(role, "name", "").strip().lower() for role in current_user.active_roles or []}


def _ld_selection_view_key() -> str | None:
    active_roles = _active_role_names()
    max_weight = current_user.max_role_weight or 0

    if max_weight >= 30:
        return "horeca"
    if "customer_horeca" in active_roles:
        return "horeca"
    if "customer" in active_roles:
        return "standard"
    return None


def _ld_selection_share_keys() -> list[str]:
    max_weight = current_user.max_role_weight or 0
    if max_weight >= 100:
        return ["standard", "horeca", "top"]
    if max_weight >= 30:
        return ["standard", "horeca"]
    return []


def _ld_selection_pdf_filename() -> str:
    view_key = _ld_selection_view_key()
    if not view_key:
        abort(403)
    return LD_SELECTION_VERSIONS[view_key]["filename"]


def _ld_selection_title() -> str:
    view_key = _ld_selection_view_key()
    if not view_key:
        abort(403)
    return LD_SELECTION_VERSIONS[view_key]["label"]


def _ld_selection_share_versions() -> list[dict[str, str]]:
    return [LD_SELECTION_VERSIONS[key] for key in _ld_selection_share_keys()]


@documents_bp.route("/ld-selection", methods=["GET"])
@login_required
def ld_selection():
    pdf_filename = _ld_selection_pdf_filename()
    pdf_url = url_for("static", filename=pdf_filename, _external=True)
    share_source = _ld_selection_share_versions()
    can_share = bool(share_source)
    share_versions = [
        {
            "key": version["key"],
            "label": version["label"],
            "url": url_for("static", filename=version["filename"], _external=True),
        }
        for version in _ld_selection_share_versions()
    ]
    return render_template(
        "documents/ld_selection.html",
        pdf_url=pdf_url,
        pdf_filename=pdf_filename.rsplit("/", 1)[-1],
        pdf_title=_ld_selection_title(),
        can_open_external=(current_user.max_role_weight or 0) >= 30,
        can_share=can_share,
        share_versions=share_versions,
    )
