from datetime import datetime, timezone

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from models import Event
from tools.role_required import role_required


events_bp = Blueprint("events", __name__)


def _can_manage_events():
    return current_user.is_authenticated and (current_user.max_role_weight or 0) >= 40


def _parse_event_datetime(value):
    value = (value or "").strip()
    if not value:
        return None
    return datetime.fromisoformat(value)


def _event_form_data():
    starts_at = _parse_event_datetime(request.form.get("starts_at"))
    if starts_at is None:
        raise ValueError("La data di inizio e' obbligatoria.")
    return {
        "title": (request.form.get("title") or "").strip(),
        "starts_at": starts_at,
        "ends_at": _parse_event_datetime(request.form.get("ends_at")),
        "location": (request.form.get("location") or "").strip() or None,
        "summary": (request.form.get("summary") or "").strip() or None,
        "details": (request.form.get("details") or "").strip() or None,
        "contact_info": (request.form.get("contact_info") or "").strip() or None,
        "is_published": request.form.get("is_published") == "1",
    }


@events_bp.route("/", methods=["GET"])
def index():
    now = datetime.now(timezone.utc)
    upcoming_events = (
        Event.query
        .filter(Event.is_published.is_(True))
        .filter(db.or_(Event.ends_at.is_(None), Event.ends_at >= now))
        .order_by(Event.starts_at.asc(), Event.id.asc())
        .all()
    )
    managed_events = []
    if _can_manage_events():
        managed_events = (
            Event.query
            .order_by(Event.starts_at.desc(), Event.id.desc())
            .limit(80)
            .all()
        )
    return render_template(
        "events/index.html",
        upcoming_events=upcoming_events,
        managed_events=managed_events,
        can_manage_events=_can_manage_events(),
    )


@events_bp.route("/", methods=["POST"])
@login_required
@role_required(40)
def create():
    try:
        data = _event_form_data()
        if not data["title"]:
            raise ValueError("Il titolo e' obbligatorio.")
        event = Event(**data, created_by_user_id=current_user.id)
        db.session.add(event)
        db.session.commit()
        flash("Evento inserito.", "success")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "warning")
    return redirect(url_for("events.index"))


@events_bp.route("/<int:event_id>/update", methods=["POST"])
@login_required
@role_required(40)
def update(event_id):
    event = Event.query.get_or_404(event_id)
    try:
        data = _event_form_data()
        if not data["title"]:
            raise ValueError("Il titolo e' obbligatorio.")
        for key, value in data.items():
            setattr(event, key, value)
        db.session.commit()
        flash("Evento aggiornato.", "success")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "warning")
    return redirect(url_for("events.index"))


@events_bp.route("/<int:event_id>/delete", methods=["POST"])
@login_required
@role_required(40)
def delete(event_id):
    event = Event.query.get_or_404(event_id)
    db.session.delete(event)
    db.session.commit()
    flash("Evento eliminato.", "success")
    return redirect(url_for("events.index"))
