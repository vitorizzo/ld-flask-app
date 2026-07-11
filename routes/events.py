import os
from datetime import datetime, time, timezone, timedelta
from types import SimpleNamespace

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from extensions import db
from models import Event, EventPoster, SocialEventPost
from tools.social_events import create_social_event_post
from tools.role_required import role_required


events_bp = Blueprint("events", __name__)
ALLOWED_POSTER_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}


def _can_manage_events():
    return current_user.is_authenticated and (current_user.max_role_weight or 0) >= 40


def _parse_event_datetime(value):
    value = (value or "").strip()
    if not value:
        return None
    return datetime.fromisoformat(value)


def _poster_upload_folder():
    folder = os.path.join(current_app.static_folder, "uploads", "events")
    os.makedirs(folder, exist_ok=True)
    return folder


def _static_rel_path(abs_path):
    return os.path.relpath(abs_path, current_app.static_folder).replace(os.sep, "/")


def _save_poster_file(file_storage):
    if not file_storage or not getattr(file_storage, "filename", ""):
        return None
    filename = secure_filename(file_storage.filename)
    if not filename:
        raise ValueError("Nome file locandina non valido.")
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_POSTER_EXTENSIONS:
        raise ValueError("Formato locandina non valido. Usa JPG, PNG, WebP o PDF.")
    mimetype = (file_storage.mimetype or "").lower()
    if mimetype and not (mimetype.startswith("image/") or mimetype == "application/pdf"):
        raise ValueError("La locandina deve essere un'immagine o un PDF.")
    target_name = f"evento_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_{filename}"
    target_path = os.path.join(_poster_upload_folder(), target_name)
    file_storage.save(target_path)
    return _static_rel_path(target_path)


def _poster_media_type(path):
    return "pdf" if (path or "").lower().endswith(".pdf") else "image"


def _event_posters(event):
    posters = list(getattr(event, "posters", []) or [])
    if posters:
        return posters
    if event.poster_path:
        return [SimpleNamespace(file_path=event.poster_path, media_type=_poster_media_type(event.poster_path))]
    return []


def _add_posters(event, files):
    saved_paths = []
    next_order = len(getattr(event, "posters", []) or [])
    for file_storage in files:
        poster_path = _save_poster_file(file_storage)
        if not poster_path:
            continue
        event.posters.append(EventPoster(file_path=poster_path, media_type=_poster_media_type(poster_path), sort_order=next_order))
        next_order += 1
        saved_paths.append(poster_path)
    if saved_paths and not event.poster_path:
        event.poster_path = saved_paths[0]


def _poster_uploads():
    files = []
    files.extend(request.files.getlist("posters"))
    files.extend(request.files.getlist("poster"))
    return [item for item in files if item and getattr(item, "filename", "")]


def _day_start(dt):
    return datetime.combine(dt.date(), time.min, tzinfo=dt.tzinfo)


def _day_end(dt):
    return datetime.combine(dt.date(), time.max, tzinfo=dt.tzinfo)


def _event_occurrences(events, from_dt=None):
    from_dt = from_dt or datetime.now(timezone.utc)
    from_day = _day_start(from_dt)
    occurrences = []
    for event in events:
        event_end = event.ends_at or event.starts_at
        start_day = max(_day_start(event.starts_at), from_day)
        end_day = _day_start(event_end)
        if end_day < from_day:
            continue
        total_days = max(1, (end_day - _day_start(event.starts_at)).days + 1)
        current = start_day
        while current <= end_day:
            day_number = (current - _day_start(event.starts_at)).days + 1
            occurrences.append({
                "event": event,
                "posters": _event_posters(event),
                "day": current,
                "day_number": day_number,
                "total_days": total_days,
                "is_multi_day": total_days > 1,
            })
            current += timedelta(days=1)
    occurrences.sort(key=lambda item: (item["day"], item["event"].starts_at, item["event"].id))
    return occurrences


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
    from_day = _day_start(now)
    upcoming_events = (
        Event.query
        .filter(Event.is_published.is_(True))
        .filter(db.or_(Event.ends_at >= from_day, db.and_(Event.ends_at.is_(None), Event.starts_at >= from_day)))
        .order_by(Event.starts_at.asc(), Event.id.asc())
        .all()
    )
    upcoming_occurrences = _event_occurrences(upcoming_events, now)
    return render_template(
        "events/index.html",
        upcoming_events=upcoming_occurrences,
        can_manage_events=_can_manage_events(),
        public_view=False,
        public_events_url=url_for("events.public_index", _external=True),
    )


@events_bp.route("/public", methods=["GET"])
def public_index():
    now = datetime.now(timezone.utc)
    from_day = _day_start(now)
    upcoming_events = (
        Event.query
        .filter(Event.is_published.is_(True))
        .filter(db.or_(Event.ends_at >= from_day, db.and_(Event.ends_at.is_(None), Event.starts_at >= from_day)))
        .order_by(Event.starts_at.asc(), Event.id.asc())
        .all()
    )
    return render_template(
        "events/index.html",
        upcoming_events=_event_occurrences(upcoming_events, now),
        can_manage_events=False,
        public_view=True,
        public_events_url=url_for("events.public_index", _external=True),
    )


@events_bp.route("/manage", methods=["GET"])
@login_required
@role_required(40)
def manage():
    managed_events = (
        Event.query
        .order_by(Event.starts_at.desc(), Event.id.desc())
        .limit(120)
        .all()
    )
    social_posts = (
        SocialEventPost.query
        .order_by(SocialEventPost.created_at.desc(), SocialEventPost.id.desc())
        .limit(12)
        .all()
    )
    return render_template(
        "events/manage.html",
        managed_events=managed_events,
        social_posts=social_posts,
        public_events_url=url_for("events.public_index", _external=True),
    )


@events_bp.route("/social-posts", methods=["POST"])
@login_required
@role_required(40)
def create_social_post():
    kind = (request.form.get("kind") or "week").strip().lower()
    if kind not in {"week", "weekend"}:
        kind = "week"
    post = create_social_event_post(kind, created_by_user_id=current_user.id, auto=False)
    flash(f"Bozza social creata: {post.title}.", "success")
    return redirect(url_for("events.manage"))


@events_bp.route("/social-posts/<int:post_id>/delete", methods=["POST"])
@login_required
@role_required(40)
def delete_social_post(post_id):
    post = SocialEventPost.query.get_or_404(post_id)
    db.session.delete(post)
    db.session.commit()
    flash("Bozza social eliminata.", "success")
    return redirect(url_for("events.manage"))


@events_bp.route("/", methods=["POST"])
@login_required
@role_required(40)
def create():
    try:
        data = _event_form_data()
        if not data["title"]:
            raise ValueError("Il titolo e' obbligatorio.")
        event = Event(**data, created_by_user_id=current_user.id)
        _add_posters(event, _poster_uploads())
        db.session.add(event)
        db.session.commit()
        flash("Evento inserito.", "success")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "warning")
    return redirect(url_for("events.manage"))


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
    return redirect(url_for("events.manage"))


@events_bp.route("/<int:event_id>/delete", methods=["POST"])
@login_required
@role_required(40)
def delete(event_id):
    event = Event.query.get_or_404(event_id)
    db.session.delete(event)
    db.session.commit()
    flash("Evento eliminato.", "success")
    return redirect(url_for("events.manage"))


@events_bp.route("/<int:event_id>/posters", methods=["POST"])
@login_required
@role_required(40)
def upload_posters(event_id):
    event = Event.query.get_or_404(event_id)
    try:
        files = _poster_uploads()
        if not files:
            raise ValueError("Seleziona almeno una locandina.")
        _add_posters(event, files)
        db.session.commit()
        flash("Locandine caricate.", "success")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "warning")
    return redirect(url_for("events.manage"))


@events_bp.route("/<int:event_id>/posters/<int:poster_id>/delete", methods=["POST"])
@login_required
@role_required(40)
def delete_poster(event_id, poster_id):
    poster = EventPoster.query.filter_by(id=poster_id, event_id=event_id).first_or_404()
    event = poster.event
    if event.poster_path == poster.file_path:
        event.poster_path = None
    db.session.delete(poster)
    db.session.flush()
    first_poster = (
        EventPoster.query
        .filter_by(event_id=event_id)
        .order_by(EventPoster.sort_order.asc(), EventPoster.id.asc())
        .first()
    )
    if first_poster:
        event.poster_path = first_poster.file_path
    db.session.commit()
    flash("Locandina rimossa.", "success")
    return redirect(url_for("events.manage"))
