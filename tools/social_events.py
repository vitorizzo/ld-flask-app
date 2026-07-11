from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from flask import current_app, url_for

from extensions import db
from models import Event, SocialEventPost

APP_PUBLIC_URL = "https://ldapp.ldenoteca.it"
BRAND_LOGO_PATH = "images/loghi_azienda/logo-ldenoteca-bianco.png"


@dataclass(frozen=True)
class SocialPostPlan:
    kind: str
    title: str
    period_start: date
    period_end: date


def period_for_kind(kind: str, today: date | None = None) -> SocialPostPlan:
    today = today or date.today()
    kind = (kind or "week").strip().lower()
    monday = today - timedelta(days=today.weekday())
    if kind == "weekend":
        friday = monday + timedelta(days=4)
        sunday = monday + timedelta(days=6)
        return SocialPostPlan("weekend", "In programma questo weekend", friday, sunday)
    return SocialPostPlan("week", "Eventi della settimana", monday, monday + timedelta(days=6))


def _day_start(day: date):
    return datetime.combine(day, time.min, tzinfo=timezone.utc)


def _day_end(day: date):
    return datetime.combine(day, time.max, tzinfo=timezone.utc)


def events_for_period(period_start: date, period_end: date):
    start_dt = _day_start(period_start)
    end_dt = _day_end(period_end)
    return (
        Event.query
        .filter(Event.is_published.is_(True))
        .filter(Event.starts_at <= end_dt)
        .filter(db.or_(Event.ends_at.is_(None), Event.ends_at >= start_dt))
        .order_by(Event.starts_at.asc(), Event.id.asc())
        .all()
    )


def _format_event_date(event: Event) -> str:
    starts = event.starts_at
    ends = event.ends_at
    if ends and ends.date() != starts.date():
        return f"{starts.strftime('%d/%m')} - {ends.strftime('%d/%m/%Y')}"
    return starts.strftime("%d/%m/%Y")


def _event_calendar_parts(event: Event):
    starts = event.starts_at
    ends = event.ends_at
    month = starts.strftime("%b").upper()
    if ends and ends.date() != starts.date():
        same_month = starts.strftime("%b").upper() == ends.strftime("%b").upper()
        day = f"{starts.strftime('%d')} - {ends.strftime('%d')}" if same_month else f"{starts.strftime('%d/%m')} - {ends.strftime('%d/%m')}"
        return month, day
    return month, starts.strftime("%d")


def build_caption(plan: SocialPostPlan, events, public_url: str) -> str:
    lines = [plan.title, ""]
    if plan.kind == "week":
        lines.insert(1, f"{plan.period_start.strftime('%d/%m/%Y')} - {plan.period_end.strftime('%d/%m/%Y')}")
        lines.insert(2, "")
    if events:
        if plan.kind == "weekend":
            with_posters = [event for event in events if _event_poster_paths(event)]
            without_posters = [event for event in events if not _event_poster_paths(event)]
            if with_posters:
                lines.append("Scorri le locandine degli eventi in programma.")
            for event in without_posters:
                line = f"{event.title}\n{_format_event_date(event)}"
                if event.location:
                    line += f" | {event.location}"
                if event.summary:
                    line += f"\n{event.summary}"
                lines.append(line)
        else:
            for event in events:
                line = f"- {_format_event_date(event)}: {event.title}"
                if event.location:
                    line += f" | {event.location}"
                lines.append(line)
    else:
        lines.append("Al momento non ci sono eventi in programma per questo periodo.")
    return "\n".join(lines)


def _absolute_static_url(path: str):
    path = (path or "").lstrip("/")
    try:
        return url_for("static", filename=path, _external=True)
    except RuntimeError:
        base = (current_app.config.get("PUBLIC_BASE_URL") or APP_PUBLIC_URL).rstrip("/")
        return f"{base}/static/{path}"


def _event_poster_paths(event: Event):
    posters = list(getattr(event, "posters", []) or [])
    if posters:
        return [poster.file_path for poster in posters if not (poster.file_path or "").lower().endswith(".pdf")]
    if event.poster_path and not event.poster_path.lower().endswith(".pdf"):
        return [event.poster_path]
    return []


def build_media_payload(plan: SocialPostPlan, events):
    logo_url = _absolute_static_url(BRAND_LOGO_PATH)
    media = {
        "brand": {
            "name": "LD Enoteca",
            "logo_path": BRAND_LOGO_PATH,
            "logo_url": logo_url,
            "position": "header",
        },
        "footer": {
            "app_url": APP_PUBLIC_URL,
            "text": "Tutti gli eventi e le info sulla nostra app nella sezione eventi",
            "button_label": "LDApp",
        },
        "format": "week_card" if plan.kind == "week" else "carousel",
        "heading": plan.title,
        "subheading": f"{plan.period_start.strftime('%d/%m/%Y')} - {plan.period_end.strftime('%d/%m/%Y')}",
        "carousel_items": [],
        "text_items": [],
        "week_items": [],
    }
    if plan.kind == "week":
        for event in events:
            poster_paths = _event_poster_paths(event)
            month, day = _event_calendar_parts(event)
            media["week_items"].append({
                "event_id": event.id,
                "title": event.title,
                "date": _format_event_date(event),
                "day": day,
                "month": month,
                "location": event.location,
                "summary": event.summary,
                "poster_path": poster_paths[0] if poster_paths else None,
                "image_url": _absolute_static_url(poster_paths[0]) if poster_paths else None,
            })
        return media
    for event in events:
        poster_paths = _event_poster_paths(event)
        month, day = _event_calendar_parts(event)
        if not poster_paths:
            media["text_items"].append({
                "event_id": event.id,
                "title": event.title,
                "date": _format_event_date(event),
                "day": day,
                "month": month,
                "location": event.location,
                "summary": event.summary,
            })
            continue
        media["carousel_items"].append({
            "event_id": event.id,
            "title": event.title,
            "date": _format_event_date(event),
            "day": day,
            "month": month,
            "poster_path": poster_paths[0],
            "image_url": _absolute_static_url(poster_paths[0]),
        })
    return media


def _public_events_url():
    configured = (current_app.config.get("EVENTS_PUBLIC_URL") or "").strip()
    if configured:
        return configured
    try:
        return url_for("events.public_index", _external=True)
    except RuntimeError:
        base = (current_app.config.get("PUBLIC_BASE_URL") or "https://ldapp.ldenoteca.it").rstrip("/")
        return f"{base}/events/public"


def _destination_config_status():
    facebook_enabled = bool(current_app.config.get("META_FACEBOOK_EVENTS_AUTO_PUBLISH"))
    instagram_enabled = bool(current_app.config.get("META_INSTAGRAM_EVENTS_AUTO_PUBLISH"))
    destinations = []
    missing = []
    if facebook_enabled:
        destinations.append("facebook")
        for key in ("META_PAGE_ID", "META_PAGE_ACCESS_TOKEN"):
            if not current_app.config.get(key):
                missing.append(key)
    if instagram_enabled:
        destinations.append("instagram")
        for key in ("META_INSTAGRAM_ACCOUNT_ID", "META_PAGE_ACCESS_TOKEN"):
            if not current_app.config.get(key):
                missing.append(key)
    return destinations, sorted(set(missing))


def create_social_event_post(kind: str, *, created_by_user_id=None, today: date | None = None, auto=False) -> SocialEventPost:
    plan = period_for_kind(kind, today=today)
    public_url = _public_events_url()
    events = events_for_period(plan.period_start, plan.period_end)
    caption = build_caption(plan, events, public_url)
    media_payload = build_media_payload(plan, events)
    destinations, missing = _destination_config_status()
    status = "draft"
    status_message = "Bozza generata."
    if auto:
        if not destinations:
            status = "config_missing"
            status_message = "Auto-pubblicazione non abilitata per Facebook o Instagram."
        elif missing:
            status = "config_missing"
            status_message = "Configurazione Meta incompleta: " + ", ".join(missing)
        else:
            status = "ready"
            status_message = "Configurazione presente. Pubblicazione API non ancora attivata."

    post = SocialEventPost(
        kind=plan.kind,
        title=plan.title,
        period_start=plan.period_start,
        period_end=plan.period_end,
        caption=caption,
        public_url=public_url,
        destinations=destinations,
        status=status,
        status_message=status_message,
        payload={
            "event_ids": [event.id for event in events],
            "auto": bool(auto),
            "media": media_payload,
        },
        created_by_user_id=created_by_user_id,
    )
    db.session.add(post)
    db.session.commit()
    return post
