import logging
import hashlib
import os
from datetime import date, datetime, time, timezone, timedelta

import requests
from flask import Blueprint, request, make_response, jsonify, render_template, current_app, Response, send_file
from flask_login import current_user, login_required
from sqlalchemy import func

from extensions import db
from tools.log_utils import get_logger
from tools.slack_processor import SlackProcessor
from tools.slack_api import SlackAPI, SlackAPIConfig
from models import SlackOrder, SlackOrderEvent, DeliveryRoute, DeliveryScheduleRule, OrderStatus, RouteOrderBoardEntry

kiosk_bp = Blueprint("kiosk", __name__, url_prefix="/kiosk")
logger = get_logger("kiosk", level=logging.INFO)

# Legacy fallback (non deve più pilotare le colonne: ora sono dinamiche da DB)
STATUS_ORDER = ["acquisito", "listato", "controllato", "evaso"]
WEEKDAY_LABELS = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
FREQUENCY_LABELS = {
    "weekly": "Settimanale",
    "biweekly": "Quindicinale",
    "twice_weekly": "Due volte a settimana",
}


def _best_effort_client_ip():
    xff = request.headers.get("X-Forwarded-For", "")
    return xff.split(",")[0].strip() if xff else request.remote_addr


def _parse_iso_date(value: str | None, field_name: str) -> date:
    try:
        return date.fromisoformat((value or "").strip())
    except Exception:
        raise ValueError(f"{field_name} non valida")


def _parse_hhmm(value: str | None, field_name: str = "orario") -> time:
    raw = (value or "").strip()
    try:
        return time.fromisoformat(raw if len(raw.split(":")) > 1 else f"{raw}:00")
    except Exception:
        raise ValueError(f"{field_name} non valido")


def _parse_weekday(value, field_name: str = "giorno") -> int:
    try:
        weekday = int(value)
    except Exception:
        raise ValueError(f"{field_name} non valido")
    if weekday < 1 or weekday > 7:
        raise ValueError(f"{field_name} non valido")
    return weekday


def _parse_frequency(value: str | None) -> str:
    frequency = (value or "weekly").strip()
    if frequency not in FREQUENCY_LABELS:
        raise ValueError("frequenza non valida")
    return frequency


def _weekday_label(value) -> str:
    try:
        weekday = int(value)
    except Exception:
        return ""
    if weekday == 0:
        return "Immediato"
    if 1 <= weekday <= 7:
        return WEEKDAY_LABELS[weekday - 1]
    return ""


def _route_to_dict(route: DeliveryRoute) -> dict:
    return {
        "id": route.id,
        "name": route.name,
        "slack_channel_id": route.slack_channel_id,
        "default_weekday": route.default_weekday,
        "default_weekday_label": _weekday_label(route.default_weekday),
        "default_time": route.default_time.strftime("%H:%M") if route.default_time else "",
        "frequency": getattr(route, "frequency", None) or "weekly",
        "frequency_label": FREQUENCY_LABELS.get(getattr(route, "frequency", None) or "weekly", "Settimanale"),
        "second_weekday": getattr(route, "second_weekday", None),
        "second_weekday_label": _weekday_label(getattr(route, "second_weekday", None)),
        "second_time": route.second_time.strftime("%H:%M") if getattr(route, "second_time", None) else "",
        "frequency_anchor_date": route.frequency_anchor_date.isoformat() if getattr(route, "frequency_anchor_date", None) else None,
        "is_active": bool(route.is_active),
    }


def _schedule_rule_to_dict(rule: DeliveryScheduleRule) -> dict:
    route = rule.route
    return {
        "id": rule.id,
        "route_id": rule.route_id,
        "route_name": route.name if route else "",
        "scope": rule.scope,
        "source_date": rule.source_date.isoformat() if rule.source_date else None,
        "target_date": rule.target_date.isoformat() if rule.target_date else None,
        "start_date": rule.start_date.isoformat() if rule.start_date else None,
        "end_date": rule.end_date.isoformat() if rule.end_date else None,
        "target_weekday": rule.target_weekday,
        "target_weekday_label": _weekday_label(rule.target_weekday),
        "target_time": rule.target_time.strftime("%H:%M") if rule.target_time else "",
        "frequency": rule.frequency or "weekly",
        "frequency_label": FREQUENCY_LABELS.get(rule.frequency or "weekly", "Settimanale"),
        "second_weekday": rule.second_weekday,
        "second_weekday_label": _weekday_label(rule.second_weekday),
        "second_time": rule.second_time.strftime("%H:%M") if rule.second_time else "",
        "is_active": bool(rule.is_active),
        "note": rule.note or "",
    }


def _next_delivery_dt(route: DeliveryRoute, now: datetime) -> datetime | None:
    """
    Se esistono ordini già pianificati per il route, usa la planned_delivery_at minima >= now.
    Altrimenti ritorna None (route configurato ma nessun ordine ancora).
    """
    return (
        db.session.query(func.min(SlackOrder.planned_delivery_at))
        .filter(
            SlackOrder.route_id == route.id,
            SlackOrder.planned_delivery_at.isnot(None),
            SlackOrder.planned_delivery_at >= now,
        )
        .scalar()
    )


def _delivery_window(delivery_dt: datetime):
    """
    Restituisce start/end del giorno di delivery_dt preservando tzinfo se presente.
    """
    if getattr(delivery_dt, "tzinfo", None) is not None:
        start = delivery_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return start, end

    start = datetime.combine(delivery_dt.date(), datetime.min.time())
    end = start + timedelta(days=1)
    return start, end


def _route_light_color(route_id: int) -> str:
    """
    Colore LIGHT deterministico per giro, senza colonna DB.
    Ritorna un esadecimale tipo #RRGGBB con luminanza alta.
    """
    h = hashlib.sha1(str(route_id).encode("utf-8")).hexdigest()
    hue = int(h[:4], 16) % 360

    s = 0.70
    l = 0.92

    def h2rgb(p, q, t):
        if t < 0:
            t += 1
        if t > 1:
            t -= 1
        if t < 1 / 6:
            return p + (q - p) * 6 * t
        if t < 1 / 2:
            return q
        if t < 2 / 3:
            return p + (q - p) * (2 / 3 - t) * 6
        return p

    h01 = hue / 360.0
    if s == 0:
        r = g = b = l
    else:
        q = l + s - l * s if l >= 0.5 else l * (1 + s)
        p = 2 * l - q
        r = h2rgb(p, q, h01 + 1 / 3)
        g = h2rgb(p, q, h01)
        b = h2rgb(p, q, h01 - 1 / 3)

    return "#{:02x}{:02x}{:02x}".format(int(r * 255), int(g * 255), int(b * 255))


def _is_today_local(dt: datetime | None) -> bool:
    if not dt:
        return False
    try:
        local = dt.astimezone()
    except Exception:
        local = dt
    return local.date() == datetime.now().astimezone().date()


def _is_cancelled_status(status: str | None) -> bool:
    return (status or "").strip().lower() in {"annullato", "annullata", "cancellato", "cancelled"}


def _status_changed_today_by_event(order_id: int, target_statuses: set[str]) -> bool:
    candidates = (
        SlackOrderEvent.query.filter(
            SlackOrderEvent.order_id == order_id,
            SlackOrderEvent.type.in_(["status_change", "status_changed", "status_update"]),
        )
        .order_by(SlackOrderEvent.created_at.desc())
        .limit(20)
        .all()
    )

    normalized_targets = {s.strip().lower() for s in target_statuses if s}
    for ev in candidates:
        if not isinstance(ev.payload, dict):
            continue
        new_status = (
            ev.payload.get("to_status")
            or ev.payload.get("new_status")
            or ev.payload.get("status")
            or ev.payload.get("to")
        )
        if (new_status or "").strip().lower() in normalized_targets:
            return _is_today_local(ev.created_at)

    return False


def _hide_closed_or_cancelled_order(order: SlackOrder, show_closed_today: bool = True) -> bool:
    if order.status == "evaso":
        if not show_closed_today:
            return True
        if order.closed_at:
            return not _is_today_local(order.closed_at)
        return not _status_changed_today_by_event(order.id, {"evaso"})

    if _is_cancelled_status(order.status):
        if order.closed_at:
            return not _is_today_local(order.closed_at)
        return not _status_changed_today_by_event(
            order.id,
            {"annullato", "annullata", "cancellato", "cancelled"},
        )

    return False


def _event_attachments(payload) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    attachments = payload.get("attachments")
    if not isinstance(attachments, list):
        return []
    return [a for a in attachments if isinstance(a, dict) and a.get("id")]


def _order_attachments(order_id: int) -> list[dict]:
    events = (
        SlackOrderEvent.query.filter(SlackOrderEvent.order_id == order_id)
        .order_by(SlackOrderEvent.created_at.asc())
        .all()
    )

    out = []
    seen = set()
    for ev in events:
        for attachment in _event_attachments(ev.payload):
            file_id = str(attachment.get("id") or "")
            if not file_id or file_id in seen:
                continue
            seen.add(file_id)
            out.append(attachment)
    return out


def _attachment_counts_for_order_ids(order_ids: list[int]) -> dict[int, int]:
    if not order_ids:
        return {}

    counts = {int(order_id): 0 for order_id in order_ids}
    events = (
        SlackOrderEvent.query.filter(SlackOrderEvent.order_id.in_(order_ids))
        .filter(SlackOrderEvent.type.in_(["created", "append_text", "note"]))
        .all()
    )

    seen = set()
    for ev in events:
        for attachment in _event_attachments(ev.payload):
            key = (int(ev.order_id), str(attachment.get("id") or ""))
            if not key[1] or key in seen:
                continue
            seen.add(key)
            counts[int(ev.order_id)] = counts.get(int(ev.order_id), 0) + 1
    return counts


def _delivery_hint_flags_for_order_ids(order_ids: list[int]) -> dict[int, bool]:
    if not order_ids:
        return {}

    flags = {int(order_id): False for order_id in order_ids}
    events = (
        SlackOrderEvent.query.filter(SlackOrderEvent.order_id.in_(order_ids))
        .filter(SlackOrderEvent.type.in_(["created", "append_text", "note", "delivery_reparse"]))
        .all()
    )

    for ev in events:
        if isinstance(ev.payload, dict) and ev.payload.get("delivery_hint"):
            flags[int(ev.order_id)] = True

    return flags


def _created_dt_from_slack_ts(ts: str | None, fallback: datetime | None = None) -> datetime:
    try:
        if ts:
            return datetime.fromtimestamp(float(ts))
    except Exception:
        pass
    return fallback or datetime.utcnow()


def _public_attachment(order_id: int, attachment: dict) -> dict:
    file_id = str(attachment.get("id") or "")
    if attachment.get("source") == "pwa_share":
        return {
            "id": file_id,
            "title": attachment.get("title") or attachment.get("name") or "Allegato",
            "name": attachment.get("name") or "",
            "mimetype": attachment.get("mimetype") or "",
            "filetype": attachment.get("filetype") or "",
            "size": attachment.get("size"),
            "is_image": bool(attachment.get("is_image")),
            "permalink": attachment.get("permalink") or "",
            "thumb_url": f"/kiosk/api/order/{order_id}/attachment/{file_id}?variant=thumb",
            "url": f"/kiosk/api/order/{order_id}/attachment/{file_id}",
        }
    return {
        "id": file_id,
        "title": attachment.get("title") or attachment.get("name") or "Allegato",
        "name": attachment.get("name") or "",
        "mimetype": attachment.get("mimetype") or "",
        "filetype": attachment.get("filetype") or "",
        "size": attachment.get("size"),
        "is_image": bool(attachment.get("is_image")),
        "permalink": attachment.get("permalink") or "",
        "thumb_url": f"/kiosk/api/order/{order_id}/attachment/{file_id}?variant=thumb",
        "url": f"/kiosk/api/order/{order_id}/attachment/{file_id}",
    }


def _pick_slack_attachment_url(attachment: dict, variant: str) -> str:
    if variant == "thumb":
        for key in ("thumb_1024", "thumb_720", "thumb_480", "thumb_360"):
            if attachment.get(key):
                return attachment[key]

    return attachment.get("url_private_download") or attachment.get("url_private") or ""


def _local_attachment_path(attachment: dict) -> str | None:
    if attachment.get("source") != "pwa_share":
        return None
    rel = (attachment.get("static_path") or "").strip().replace("\\", "/").lstrip("/")
    if not rel.startswith("uploads/shared_orders/"):
        return None
    candidate = os.path.abspath(os.path.join(current_app.static_folder, rel))
    static_root = os.path.abspath(current_app.static_folder)
    if not candidate.startswith(static_root + os.sep):
        return None
    if not os.path.exists(candidate):
        return None
    return candidate


@kiosk_bp.get("/test")
def kiosk_test():
    client_ip = _best_effort_client_ip()
    now = datetime.now(timezone.utc).astimezone()
    html = f"""
# KIOSK TEST OK

Ora server: `{now.strftime('%Y-%m-%d %H:%M:%S %Z')}`

Client IP: `{client_ip}`

User-Agent: `{request.headers.get('User-Agent', '')}`

Auto refresh ogni 10s
"""
    resp = make_response(html, 200)
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp


@kiosk_bp.get("/order/<int:order_id>")
def kiosk_order_detail(order_id: int):
    order = SlackOrder.query.get_or_404(order_id)
    statuses = (
        OrderStatus.query.filter_by(is_visible=True)
        .order_by(OrderStatus.order_index.asc())
        .all()
    )
    return render_template(
        "kiosk_order_detail.html",
        order=order,
        route=DeliveryRoute.query.get(order.route_id) if order.route_id else None,
        statuses=statuses,
        kiosk_mode=True,
    )


@kiosk_bp.get("/api/routes")
def kiosk_api_routes():
    routes = (
        DeliveryRoute.query.filter_by(is_active=True)
        .order_by(DeliveryRoute.name.asc())
        .all()
    )
    out = [
        {
            "id": r.id,
            "name": r.name,
            "slack_channel_id": r.slack_channel_id,
            "default_weekday": r.default_weekday,
            "default_time": r.default_time.strftime("%H:%M:%S") if r.default_time else None,
        }
        for r in routes
    ]
    return jsonify(out), 200


@kiosk_bp.get("/api/delivery-schedule")
@login_required
def kiosk_api_delivery_schedule():
    routes = (
        DeliveryRoute.query
        .order_by(DeliveryRoute.is_active.desc(), DeliveryRoute.name.asc())
        .all()
    )
    rules = (
        DeliveryScheduleRule.query
        .filter_by(is_active=True)
        .order_by(
            DeliveryScheduleRule.route_id.asc(),
            DeliveryScheduleRule.scope.asc(),
            DeliveryScheduleRule.start_date.asc().nullslast(),
            DeliveryScheduleRule.source_date.asc().nullslast(),
            DeliveryScheduleRule.id.desc(),
        )
        .all()
    )

    return jsonify(
        {
            "routes": [_route_to_dict(r) for r in routes],
            "rules": [_schedule_rule_to_dict(r) for r in rules],
            "weekdays": [{"value": i + 1, "label": label} for i, label in enumerate(WEEKDAY_LABELS)],
            "frequencies": [{"value": value, "label": label} for value, label in FREQUENCY_LABELS.items()],
        }
    )


@kiosk_bp.post("/api/delivery-schedule")
@login_required
def kiosk_api_save_delivery_schedule():
    payload = request.get_json(silent=True) or {}
    mode = (payload.get("mode") or "").strip()
    route_id = payload.get("route_id")

    route = DeliveryRoute.query.get(route_id)
    if not route:
        return jsonify({"ok": False, "error": "Giro non trovato"}), 404

    try:
        note = (payload.get("note") or "").strip() or None
        frequency = _parse_frequency(payload.get("frequency"))
        second_weekday = None
        second_time = None
        if frequency == "twice_weekly":
            second_weekday = _parse_weekday(payload.get("second_weekday"), "secondo giorno")
            second_time = _parse_hhmm(payload.get("second_time"), "secondo orario")

        if mode == "definitive":
            route.default_weekday = _parse_weekday(payload.get("target_weekday"))
            route.default_time = _parse_hhmm(payload.get("target_time"))
            route.frequency = frequency
            route.second_weekday = second_weekday
            route.second_time = second_time
            route.frequency_anchor_date = (
                _parse_iso_date(payload.get("frequency_anchor_date"), "data riferimento frequenza")
                if frequency == "biweekly" and payload.get("frequency_anchor_date")
                else date.today()
                if frequency == "biweekly"
                else None
            )
            db.session.commit()
            return jsonify({"ok": True, "mode": mode, "route": _route_to_dict(route)})

        if mode == "once":
            source_date = _parse_iso_date(payload.get("source_date"), "data giro originale")
            target_date = _parse_iso_date(payload.get("target_date"), "nuova data")
            target_time = _parse_hhmm(payload.get("target_time"))

            rule = DeliveryScheduleRule(
                route_id=route.id,
                scope="once",
                source_date=source_date,
                target_date=target_date,
                target_time=target_time,
                frequency="weekly",
                is_active=True,
                note=note,
            )
            db.session.add(rule)
            db.session.commit()
            return jsonify({"ok": True, "mode": mode, "rule": _schedule_rule_to_dict(rule)}), 201

        if mode == "period":
            start_date = _parse_iso_date(payload.get("start_date"), "data inizio")
            end_date = _parse_iso_date(payload.get("end_date"), "data fine")
            if end_date < start_date:
                return jsonify({"ok": False, "error": "La data fine non può precedere la data inizio"}), 400

            rule = DeliveryScheduleRule(
                route_id=route.id,
                scope="period",
                start_date=start_date,
                end_date=end_date,
                target_weekday=_parse_weekday(payload.get("target_weekday")),
                target_time=_parse_hhmm(payload.get("target_time")),
                frequency=frequency,
                second_weekday=second_weekday,
                second_time=second_time,
                is_active=True,
                note=note,
            )
            db.session.add(rule)
            db.session.commit()
            return jsonify({"ok": True, "mode": mode, "rule": _schedule_rule_to_dict(rule)}), 201

    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    return jsonify({"ok": False, "error": "Modalità non valida"}), 400


def _route_payload_from_request(payload: dict, route: DeliveryRoute | None = None) -> DeliveryRoute:
    name = (payload.get("name") or "").strip()
    slack_channel_id = (payload.get("slack_channel_id") or "").strip()
    if not name:
        raise ValueError("Nome giro obbligatorio")
    if not slack_channel_id:
        raise ValueError("Canale Slack obbligatorio")

    frequency = _parse_frequency(payload.get("frequency"))
    second_weekday = None
    second_time = None
    if frequency == "twice_weekly":
        second_weekday = _parse_weekday(payload.get("second_weekday"), "secondo giorno")
        second_time = _parse_hhmm(payload.get("second_time"), "secondo orario")

    if route is None:
        route = DeliveryRoute()

    route.name = name
    route.slack_channel_id = slack_channel_id
    route.default_weekday = _parse_weekday(payload.get("default_weekday"))
    route.default_time = _parse_hhmm(payload.get("default_time"))
    route.frequency = frequency
    route.second_weekday = second_weekday
    route.second_time = second_time
    route.frequency_anchor_date = (
        _parse_iso_date(payload.get("frequency_anchor_date"), "data riferimento frequenza")
        if frequency == "biweekly" and payload.get("frequency_anchor_date")
        else date.today()
        if frequency == "biweekly"
        else None
    )
    route.is_active = bool(payload.get("is_active", True))
    return route


@kiosk_bp.post("/api/delivery-routes")
@login_required
def kiosk_api_create_delivery_route():
    payload = request.get_json(silent=True) or {}
    try:
        route = _route_payload_from_request(payload)
        db.session.add(route)
        db.session.commit()
        return jsonify({"ok": True, "route": _route_to_dict(route)}), 201
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception:
        db.session.rollback()
        logger.exception("[KIOSK] create delivery route failed")
        return jsonify({"ok": False, "error": "Errore salvataggio giro"}), 500


@kiosk_bp.put("/api/delivery-routes/<int:route_id>")
@login_required
def kiosk_api_update_delivery_route(route_id: int):
    route = DeliveryRoute.query.get(route_id)
    if not route:
        return jsonify({"ok": False, "error": "Giro non trovato"}), 404

    payload = request.get_json(silent=True) or {}
    try:
        _route_payload_from_request(payload, route)
        db.session.commit()
        return jsonify({"ok": True, "route": _route_to_dict(route)})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception:
        db.session.rollback()
        logger.exception("[KIOSK] update delivery route failed route_id=%s", route_id)
        return jsonify({"ok": False, "error": "Errore aggiornamento giro"}), 500


@kiosk_bp.delete("/api/delivery-routes/<int:route_id>")
@login_required
def kiosk_api_delete_delivery_route(route_id: int):
    route = DeliveryRoute.query.get(route_id)
    if not route:
        return jsonify({"ok": False, "error": "Giro non trovato"}), 404

    has_orders = SlackOrder.query.filter_by(route_id=route.id).first() is not None
    if has_orders:
        route.is_active = False
    else:
        db.session.delete(route)
    db.session.commit()
    return jsonify({"ok": True, "soft_deleted": has_orders})


@kiosk_bp.delete("/api/delivery-schedule/<int:rule_id>")
@login_required
def kiosk_api_delete_delivery_schedule(rule_id: int):
    rule = DeliveryScheduleRule.query.get(rule_id)
    if not rule:
        return jsonify({"ok": False, "error": "Regola non trovata"}), 404

    rule.is_active = False
    db.session.commit()
    return jsonify({"ok": True})


@kiosk_bp.get("/api/board/<int:route_id>")
def kiosk_api_board(route_id: int):
    payload = build_board_payload(route_id=route_id, show_closed_today=False)
    if payload is None:
        return jsonify({"error": "route_not_found"}), 404
    return jsonify(payload), 200


@kiosk_bp.get("/api/order/<int:order_id>")
def kiosk_api_order(order_id: int):
    """
    JSON per popup scheda ordine (overview):
    - status, raw_text
    - children: eventi created/append_text (testo raw associato)
    - thread_notes: eventi note
    """
    order = SlackOrder.query.get(order_id)
    if not order:
        return jsonify({"error": "order_not_found"}), 404

    route = DeliveryRoute.query.get(order.route_id) if order.route_id else None

    events = (
        SlackOrderEvent.query.filter(SlackOrderEvent.order_id == order.id)
        .order_by(SlackOrderEvent.created_at.asc())
        .all()
    )

    children = []
    thread_notes = []
    attachments = []
    seen_attachments = set()
    delivery_hints = []

    for ev in events:
        ev_attachments = _event_attachments(ev.payload)
        if isinstance(ev.payload, dict) and ev.payload.get("delivery_hint"):
            delivery_hints.append(
                {
                    "hint": ev.payload.get("delivery_hint"),
                    "planned_delivery_at": ev.payload.get("planned_delivery_at"),
                    "type": ev.type,
                }
            )
        for attachment in ev_attachments:
            file_id = str(attachment.get("id") or "")
            if not file_id or file_id in seen_attachments:
                continue
            seen_attachments.add(file_id)
            attachments.append(_public_attachment(order.id, attachment))

        if ev.type in ("created", "append_text"):
            txt = ""
            try:
                if isinstance(ev.payload, dict):
                    txt = ev.payload.get("text", "") or ev.payload.get("raw_text", "") or ""
            except Exception:
                txt = ""
            children.append(
                {
                    "label": ev.type,
                    "ts": ev.created_at.isoformat() if ev.created_at else "",
                    "text": txt,
                    "attachments_count": len(ev_attachments),
                }
            )

        if ev.type == "note":
            txt = ""
            try:
                if isinstance(ev.payload, dict):
                    txt = ev.payload.get("text", "") or ""
            except Exception:
                txt = ""
            thread_notes.append(
                {
                    "at": ev.created_at.isoformat() if ev.created_at else "",
                    "text": txt,
                    "attachments_count": len(ev_attachments),
                }
            )

    notes_count = sum(1 for e in events if e.type == "note")
    multi_count = sum(1 for e in events if e.type in ("created", "append_text"))
    issues_count = 1 if bool(order.has_issues) else 0

    return (
        jsonify(
            {
                "id": order.id,
                "route_id": order.route_id,
                "route_name": route.name if route else "",
                "route_color": _route_light_color(route.id) if route else "#f1f3f5",
                "customer_display": order.customer_display,
                "status": order.status,
                "document_issued": bool(getattr(order, "document_issued", False)),
                "raw_text": order.raw_text or "",
                "planned_delivery_at": order.planned_delivery_at.isoformat()
                if order.planned_delivery_at
                else None,
                "delivery_hint": delivery_hints[-1]["hint"] if delivery_hints else "",
                "created_at": order.created_at.isoformat() if order.created_at else None,
                "closed_at": order.closed_at.isoformat() if order.closed_at else None,
                "multi_count": multi_count,
                "notes_count": notes_count,
                "issues_count": issues_count,
                "children": children,
                "thread_notes": thread_notes,
                "attachments": attachments,
            }
        ),
        200,
    )


@kiosk_bp.get("/api/order/<int:order_id>/attachment/<file_id>")
def kiosk_api_order_attachment(order_id: int, file_id: str):
    order = SlackOrder.query.get(order_id)
    if not order:
        return jsonify({"error": "order_not_found"}), 404

    attachment = None
    for candidate in _order_attachments(order.id):
        if str(candidate.get("id") or "") == str(file_id):
            attachment = candidate
            break

    if not attachment:
        return jsonify({"error": "attachment_not_found"}), 404

    local_path = _local_attachment_path(attachment)
    if local_path:
        return send_file(
            local_path,
            mimetype=attachment.get("mimetype") or "application/octet-stream",
            download_name=attachment.get("name") or None,
            conditional=True,
        )

    variant = (request.args.get("variant") or "full").strip().lower()
    source_url = _pick_slack_attachment_url(attachment, variant)
    if not source_url:
        return jsonify({"error": "attachment_url_missing"}), 404

    bot_token = current_app.config.get("SLACK_BOT_TOKEN", "") or ""
    if not bot_token:
        return jsonify({"error": "slack_bot_token_missing"}), 503

    try:
        upstream = requests.get(
            source_url,
            headers={"Authorization": f"Bearer {bot_token}"},
            timeout=30,
        )
    except requests.RequestException:
        logger.exception("[KIOSK] Slack attachment fetch failed order_id=%s file_id=%s", order_id, file_id)
        return jsonify({"error": "attachment_fetch_failed"}), 502

    if upstream.status_code >= 400:
        logger.warning(
            "[KIOSK] Slack attachment fetch status=%s order_id=%s file_id=%s",
            upstream.status_code,
            order_id,
            file_id,
        )
        return jsonify({"error": "attachment_fetch_failed", "status": upstream.status_code}), 502

    resp = Response(
        upstream.content,
        status=200,
        content_type=upstream.headers.get("Content-Type") or attachment.get("mimetype") or "application/octet-stream",
    )
    resp.headers["Cache-Control"] = "private, max-age=300"
    return resp


@kiosk_bp.get("/board/<int:route_id>")
def kiosk_board(route_id: int):
    client_ip = _best_effort_client_ip()
    now = datetime.now(timezone.utc).astimezone()
    html = f"""
# Kiosk Board (route_id={route_id})

Ora server: `{now.strftime('%Y-%m-%d %H:%M:%S %Z')}` — IP: `{client_ip}`

Fonte dati: `/kiosk/api/board/{route_id}`

Auto refresh 10s
"""
    resp = make_response(html, 200)
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp


def _evaded_today_by_event(order_id: int) -> bool:
    """
    True se esiste un evento di cambio stato a 'evaso' avvenuto oggi (local).
    Fallback: False se non troviamo eventi.
    """
    candidates = (
        SlackOrderEvent.query.filter(
            SlackOrderEvent.order_id == order_id,
            SlackOrderEvent.type.in_(["status_change", "status_changed", "status_update"]),
        )
        .order_by(SlackOrderEvent.created_at.desc())
        .limit(20)
        .all()
    )

    for ev in candidates:
        if not isinstance(ev.payload, dict):
            continue
        new_status = (
            ev.payload.get("to_status")
            or ev.payload.get("new_status")
            or ev.payload.get("status")
            or ev.payload.get("to")
        )
        if new_status == "evaso":
            return _is_today_local(ev.created_at)

    return False


@kiosk_bp.get("/board/all")
def kiosk_board_all():
    """
    Overview server-side (template):
    NOTA: questa view non è la fonte dati dell’iframe (che usa /api/board/all),
    ma la teniamo coerente: mostra tutti i non-evasi + evasi di oggi.
    """
    now_local = datetime.now(timezone.utc).astimezone()

    routes = (
        DeliveryRoute.query.filter_by(is_active=True)
        .order_by(DeliveryRoute.name.asc())
        .all()
    )

    note_counts_sq = (
        db.session.query(
            SlackOrderEvent.order_id.label("order_id"),
            func.count().label("note_count"),
        )
        .filter(SlackOrderEvent.type == "note")
        .group_by(SlackOrderEvent.order_id)
        .subquery()
    )
    msg_counts_sq = (
        db.session.query(
            SlackOrderEvent.order_id.label("order_id"),
            func.count().label("msg_count"),
        )
        .filter(SlackOrderEvent.type.in_(["created", "append_text"]))
        .group_by(SlackOrderEvent.order_id)
        .subquery()
    )

    orders_out = []
    routes_out = []
    total_orders = 0

    for r in routes:
        r_color = _route_light_color(r.id)

        rows = (
            db.session.query(
                SlackOrder,
                func.coalesce(note_counts_sq.c.note_count, 0).label("note_count"),
                func.coalesce(msg_counts_sq.c.msg_count, 0).label("msg_count"),
            )
            .outerjoin(note_counts_sq, note_counts_sq.c.order_id == SlackOrder.id)
            .outerjoin(msg_counts_sq, msg_counts_sq.c.order_id == SlackOrder.id)
            .filter(SlackOrder.route_id == r.id)
            .order_by(
                SlackOrder.status.asc(),
                SlackOrder.planned_delivery_at.asc().nullslast(),
                SlackOrder.customer_display.asc(),
            )
            .all()
        )

        filtered_rows = []
        for order, note_count, msg_count in rows:
            if _hide_closed_or_cancelled_order(order, show_closed_today=True):
                continue
            filtered_rows.append((order, note_count, msg_count))

        routes_out.append(
            {
                "id": r.id,
                "name": r.name,
                "color": r_color,
                "count": len(filtered_rows),
            }
        )

        for order, note_count, msg_count in filtered_rows:
            total_orders += 1
            orders_out.append(
                {
                    "id": order.id,
                    "route_id": r.id,
                    "route_name": r.name,
                    "route_color": r_color,
                    "customer_display": order.customer_display,
                    "status": order.status,
                    "document_issued": bool(getattr(order, "document_issued", False)),
                    "multi_count": int(msg_count or 0),
                    "notes_count": int(note_count or 0),
                    "issues_count": 1 if bool(order.has_issues) else 0,
                    "preview": (order.raw_text or "").strip().splitlines()[0][:120]
                    if (order.raw_text or "").strip()
                    else "",
                }
            )

    status_rank = {s: i for i, s in enumerate(STATUS_ORDER)}
    orders_out.sort(
        key=lambda o: (
            o["route_name"].lower(),
            status_rank.get(o["status"], 999),
            (o["customer_display"] or "").lower(),
        )
    )

    return render_template(
        "kiosk_overview.html",
        now_local=now_local,
        show_closed_today=True,
        totals={"total": total_orders},
        routes=routes_out,
        orders=orders_out,
        kiosk_mode=True,
    )


@kiosk_bp.get("/api/board/all")
def kiosk_api_board_all():
    only_active = request.args.get("only_active", "1") == "1"
    show_closed_today = request.args.get("show_closed_today", "1") == "1"

    q = DeliveryRoute.query
    if only_active:
        q = q.filter_by(is_active=True)

    routes = q.order_by(DeliveryRoute.id.asc()).all()

    boards = []
    for r in routes:
        payload = build_board_payload(route_id=r.id, show_closed_today=show_closed_today)
        if payload is None:
            continue
        payload["route"]["color"] = _route_light_color(r.id)
        boards.append(payload)

    return (
        jsonify(
            {
                "only_active": only_active,
                "show_closed_today": show_closed_today,
                "boards": boards,
                "server_now": datetime.now().isoformat(timespec="seconds"),
            }
        ),
        200,
    )


@kiosk_bp.get("")
@kiosk_bp.get("/kiosk-ordini")
@login_required  # opzionale
def kiosk_ordini_embed():
    return render_template("kiosk_ordini_embed.html")


def build_board_payload(route_id: int, show_closed_today: bool = True):
    """
    Board per route (API):
    - mostra SEMPRE tutti gli ordini NON evasi
    - mostra gli evasi SOLO se evasi oggi (se show_closed_today=True)
    - NON usa più la finestra del "prossimo giro": evita ordini che spariscono (inclusi default_weekday=0).
    - groups NON è più hardcoded: le chiavi arrivano dagli status presenti nei dati.
    """
    route = DeliveryRoute.query.get(route_id)
    if not route or not route.is_active:
        return None

    note_counts_sq = (
        db.session.query(
            SlackOrderEvent.order_id.label("order_id"),
            func.count().label("note_count"),
        )
        .filter(SlackOrderEvent.type == "note")
        .group_by(SlackOrderEvent.order_id)
        .subquery()
    )

    msg_counts_sq = (
        db.session.query(
            SlackOrderEvent.order_id.label("order_id"),
            func.count().label("msg_count"),
        )
        .filter(SlackOrderEvent.type.in_(["created", "append_text"]))
        .group_by(SlackOrderEvent.order_id)
        .subquery()
    )

    rows = (
        db.session.query(
            SlackOrder,
            func.coalesce(note_counts_sq.c.note_count, 0).label("note_count"),
            func.coalesce(msg_counts_sq.c.msg_count, 0).label("msg_count"),
        )
        .outerjoin(note_counts_sq, note_counts_sq.c.order_id == SlackOrder.id)
        .outerjoin(msg_counts_sq, msg_counts_sq.c.order_id == SlackOrder.id)
        .filter(SlackOrder.route_id == route.id)
        .order_by(
            SlackOrder.status.asc(),
            SlackOrder.planned_delivery_at.asc().nullslast(),
            SlackOrder.customer_display.asc(),
        )
        .all()
    )

    order_ids = [int(order.id) for order, _, _ in rows]
    attachment_counts = _attachment_counts_for_order_ids(order_ids)
    delivery_hint_flags = _delivery_hint_flags_for_order_ids(order_ids)

    # IMPORTANTE: non hardcodare più le colonne qui
    groups = {}

    for order, note_count, msg_count in rows:
        if _hide_closed_or_cancelled_order(order, show_closed_today=show_closed_today):
            continue

        groups.setdefault(order.status, []).append(
            {
                "id": order.id,
                "customer": order.customer_display,
                "customer_key": order.customer_key,
                "status": order.status,
                "has_issues": bool(order.has_issues),
                "document_issued": bool(getattr(order, "document_issued", False)),
                "note_count": int(note_count or 0),
                "msg_count": int(msg_count or 0),
                "attachment_count": int(attachment_counts.get(int(order.id), 0)),
                "planned_delivery_at": order.planned_delivery_at.isoformat()
                if order.planned_delivery_at
                else None,
                "created_at": order.created_at.isoformat() if order.created_at else None,
                "raw_text": order.raw_text or "",
                # campi per grouping client-side
                "delivery_label": order.planned_delivery_at.strftime("%d/%m %H:%M")
                if order.planned_delivery_at
                else "",
                "delivery_from_message": bool(delivery_hint_flags.get(int(order.id))),
                "group_key": f"{route.id}|{(order.planned_delivery_at.date().isoformat() if order.planned_delivery_at else '')}|{(order.customer_key or order.customer_display or '').strip().lower()}",
                "group_seq": getattr(order, "group_seq", 1) or 1,
                "group_size": getattr(order, "group_size", 1) or 1,
            }
        )

    now = datetime.utcnow()
    delivery_dt = _next_delivery_dt(route, now)

    return {
        "route": {"id": route.id, "name": route.name},
        "delivery_dt": delivery_dt.isoformat() if delivery_dt else None,
        "groups": groups,
    }


@kiosk_bp.post("/api/orders/reparse-deliveries")
@login_required
def kiosk_api_reparse_deliveries():
    """
    Ricalcola la consegna prevista delle card attive ripassando i testi nel
    parser Slack corrente. Di default aggiorna solo quando trova una data/fascia
    esplicita nel messaggio; con apply_defaults=1 ricalcola anche la consegna
    default del giro per le card senza hint.
    """
    dry_run = request.args.get("dry_run", "0") == "1"
    apply_defaults = request.args.get("apply_defaults", "0") == "1"
    route_id = request.args.get("route_id", type=int)

    q = SlackOrder.query.filter(
        SlackOrder.status != "evaso",
        SlackOrder.status.notin_(["annullato", "annullata", "cancellato", "cancelled"]),
    )
    if route_id:
        q = q.filter(SlackOrder.route_id == route_id)

    orders = q.order_by(SlackOrder.id.asc()).all()
    processor = SlackProcessor()

    checked = 0
    changed = 0
    skipped = 0
    results = []

    for order in orders:
        checked += 1
        route = DeliveryRoute.query.get(order.route_id) if order.route_id else None
        base_dt = _created_dt_from_slack_ts(order.slack_message_ts, order.created_at)

        events = (
            SlackOrderEvent.query.filter(SlackOrderEvent.order_id == order.id)
            .filter(SlackOrderEvent.type.in_(["created", "append_text", "note"]))
            .order_by(SlackOrderEvent.created_at.asc())
            .all()
        )

        candidates = []
        for ev in events:
            if isinstance(ev.payload, dict):
                text = (ev.payload.get("text") or ev.payload.get("raw_text") or "").strip()
                ts = ev.payload.get("ts") or order.slack_message_ts
                candidates.append((text, _created_dt_from_slack_ts(ts, ev.created_at)))

        if not candidates and order.raw_text:
            candidates.append((order.raw_text, base_dt))

        parsed_delivery_dt = None
        delivery_hint = ""

        for text, candidate_base_dt in candidates:
            if not text:
                continue
            dt, hint = processor._extract_delivery_dt_from_text(text, candidate_base_dt, route)
            if dt:
                parsed_delivery_dt = dt
                delivery_hint = hint

        target_dt = parsed_delivery_dt
        source = "message" if parsed_delivery_dt else ""

        if not target_dt and apply_defaults and route:
            target_dt = processor._compute_next_delivery_dt(base_dt, route)
            source = "route_default"

        if not target_dt:
            skipped += 1
            continue

        old_iso = order.planned_delivery_at.isoformat() if order.planned_delivery_at else None
        new_iso = target_dt.isoformat()
        if old_iso == new_iso:
            continue

        changed += 1
        results.append(
            {
                "id": order.id,
                "customer": order.customer_display,
                "old_planned_delivery_at": old_iso,
                "new_planned_delivery_at": new_iso,
                "source": source,
                "hint": delivery_hint,
            }
        )

        if dry_run:
            continue

        order.planned_delivery_at = target_dt
        db.session.add(
            SlackOrderEvent(
                order_id=order.id,
                type="delivery_reparse",
                payload={
                    "old_planned_delivery_at": old_iso,
                    "new_planned_delivery_at": new_iso,
                    "source": source,
                    "delivery_hint": delivery_hint,
                    "dry_run": False,
                    "client_ip": _best_effort_client_ip(),
                },
            )
        )

    if not dry_run:
        db.session.commit()

    return jsonify(
        {
            "ok": True,
            "dry_run": dry_run,
            "apply_defaults": apply_defaults,
            "checked": checked,
            "changed": changed,
            "skipped": skipped,
            "results": results,
        }
    )


@kiosk_bp.get("/api/statuses")
def kiosk_api_statuses():
    statuses = (
        OrderStatus.query.filter_by(is_visible=True)
        .order_by(OrderStatus.order_index.asc())
        .all()
    )

    return (
        jsonify(
            [
                {
                    "code": s.code,
                    "label": s.label,
                    "order_index": s.order_index,
                    "is_terminal": s.is_terminal,
                }
                for s in statuses
            ]
        ),
        200,
    )


def _normalize_reaction_name(s: str | None) -> str:
    """
    Accetta ':100:' oppure '100' e ritorna sempre '100' (formato slack_sdk).
    """
    if not s:
        return ""
    s = (s or "").strip()
    if s.startswith(":") and s.endswith(":") and len(s) >= 3:
        s = s[1:-1].strip()
    return s


@kiosk_bp.post("/api/order/<int:order_id>/set-status")
def set_order_status(order_id):
    payload = request.get_json(silent=True) or {}
    new_status = (payload.get("status") or "").strip()

    if not new_status:
        return jsonify({"ok": False, "error": "missing status"}), 400

    order = SlackOrder.query.get(order_id)
    if not order:
        return jsonify({"ok": False, "error": "order not found"}), 404

    # stato target valido?
    target_status = OrderStatus.query.filter_by(code=new_status).first()
    if not target_status:
        return jsonify({"ok": False, "error": "invalid status"}), 400

    old_status = order.status

    if old_status == new_status:
        return jsonify({"ok": True, "status": new_status, "noop": True})

    # aggiorna DB
    order.status = new_status
    if _is_cancelled_status(new_status):
        order.closed_at = datetime.utcnow()
    elif target_status.is_terminal and not order.closed_at:
        order.closed_at = datetime.utcnow()

    db.session.add(
        SlackOrderEvent(
            order_id=order.id,
            type="status_change",
            payload={
                "from": old_status,
                "to": new_status,
                "via": "kiosk",
                "client_ip": _best_effort_client_ip(),
            },
        )
    )
    db.session.commit()

    # ---- SYNC SLACK REACTIONS (upgrade/downgrade/jump)
    try:
        SlackProcessor().sync_order_status_reactions(
            order,
            old_status_code=old_status,
            new_status_code=new_status,
        )
    except Exception:
        # non deve mai rompere la UI
        logger.exception(
            "[KIOSK] sync_order_status_reactions failed order_id=%s %s->%s",
            order.id,
            old_status,
            new_status,
        )

    return jsonify({"ok": True, "status": new_status})


@kiosk_bp.delete("/api/order/<int:order_id>")
@login_required
def delete_order(order_id: int):
    order = SlackOrder.query.get(order_id)
    if not order:
        return jsonify({"ok": False, "error": "order not found"}), 404

    slack_warning = None
    slack_action = None
    if order.slack_channel_id and order.slack_message_ts:
        bot_token = current_app.config.get("SLACK_BOT_TOKEN", "") or ""
        if bot_token:
            try:
                actor = " ".join(
                    value for value in (
                        getattr(current_user, "name", None),
                        getattr(current_user, "surname", None),
                    ) if value
                ).strip() or getattr(current_user, "email", None) or f"utente #{current_user.id}"
                result = SlackAPI(SlackAPIConfig(bot_token=bot_token)).delete_or_mark_message(
                    order.slack_channel_id,
                    order.slack_message_ts,
                    actor,
                )
                slack_action = result.get("action")
                if result.get("warning"):
                    slack_warning = f"Ordine marcato su Slack con avviso parziale: {result['warning']}"
            except Exception as exc:
                slack_warning = f"Messaggio Slack non cancellato: {exc}"
                logger.exception("[KIOSK] Slack delete failed order_id=%s", order.id)
        else:
            slack_warning = "SLACK_BOT_TOKEN mancante: cancellazione locale eseguita"

    entries = (
        RouteOrderBoardEntry.query
        .filter_by(slack_channel_id=order.slack_channel_id, slack_message_ts=order.slack_message_ts)
        .all()
    )
    for entry in entries:
        db.session.delete(entry)
    db.session.delete(order)
    db.session.commit()

    payload = {"ok": True, "slack_action": slack_action}
    if slack_warning:
        payload["warning"] = slack_warning
    return jsonify(payload)


@kiosk_bp.put("/api/order/<int:order_id>/delivery")
@login_required
def set_order_delivery(order_id: int):
    payload = request.get_json(silent=True) or {}
    order = SlackOrder.query.get(order_id)
    if not order:
        return jsonify({"ok": False, "error": "order not found"}), 404

    try:
        target_date = _parse_iso_date(payload.get("date"), "data consegna")
        target_time = _parse_hhmm(payload.get("time"), "orario consegna")
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    old_iso = order.planned_delivery_at.isoformat() if order.planned_delivery_at else None
    new_dt = datetime.combine(target_date, target_time)
    order.planned_delivery_at = new_dt
    db.session.add(
        SlackOrderEvent(
            order_id=order.id,
            type="delivery_manual",
            payload={
                "old_planned_delivery_at": old_iso,
                "new_planned_delivery_at": new_dt.isoformat(),
                "delivery_hint": "manuale",
                "client_ip": _best_effort_client_ip(),
            },
        )
    )
    db.session.commit()

    return jsonify({"ok": True, "planned_delivery_at": new_dt.isoformat()})

