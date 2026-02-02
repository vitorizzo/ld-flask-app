import logging
import hashlib
from datetime import datetime, timezone, timedelta

from flask import Blueprint, request, make_response, jsonify, render_template
from sqlalchemy import func

from extensions import db
from tools.log_utils import get_logger
from models import SlackOrder, SlackOrderEvent, DeliveryRoute


kiosk_bp = Blueprint("kiosk", __name__, url_prefix="/kiosk")
logger = get_logger("kiosk", level=logging.INFO)

STATUS_ORDER = ["acquisito", "listato", "controllato", "evaso"]


def _best_effort_client_ip():
    xff = request.headers.get("X-Forwarded-For", "")
    return xff.split(",")[0].strip() if xff else request.remote_addr


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
    start = datetime.combine(delivery_dt.date(), datetime.min.time())
    end = start + timedelta(days=1)
    return start, end


def _route_light_color(route_id: int) -> str:
    """
    Colore LIGHT deterministico per giro, senza colonna DB.
    Ritorna un esadecimale tipo #RRGGBB con luminanza alta.
    """
    # hash -> hue 0..359
    h = hashlib.sha1(str(route_id).encode("utf-8")).hexdigest()
    hue = int(h[:4], 16) % 360

    # HSL -> RGB (light palette)
    # S ~ 70%, L ~ 92%
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
    # planned_delivery_at in DB è verosimilmente naive UTC o timezone-aware: best effort
    try:
        local = dt.astimezone()
    except Exception:
        local = dt
    return local.date() == datetime.now().astimezone().date()


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


@kiosk_bp.get("/api/routes")
def kiosk_api_routes():
    routes = (
        DeliveryRoute.query
        .filter_by(is_active=True)
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


@kiosk_bp.get("/api/board/<int:route_id>")
def kiosk_api_board(route_id: int):
    """
    Ritorna gli ordini del prossimo giro (planned_delivery_at minimo >= now) per il route.
    Raggruppa per status e include note_count + msg_count + has_issues.
    """
    now = datetime.utcnow()
    route = DeliveryRoute.query.get(route_id)
    if not route or not route.is_active:
        return jsonify({"error": "route_not_found"}), 404

    delivery_dt = _next_delivery_dt(route, now)
    if not delivery_dt:
        return jsonify({
            "route": {"id": route.id, "name": route.name},
            "delivery_dt": None,
            "groups": {s: [] for s in STATUS_ORDER},
        }), 200

    start, end = _delivery_window(delivery_dt)

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
        .filter(
            SlackOrder.route_id == route.id,
            SlackOrder.planned_delivery_at >= start,
            SlackOrder.planned_delivery_at < end,
        )
        .order_by(SlackOrder.status.asc(), SlackOrder.customer_display.asc())
        .all()
    )

    groups = {s: [] for s in STATUS_ORDER}
    for order, note_count, msg_count in rows:
        payload = {
            "id": order.id,
            "customer": order.customer_display,
            "status": order.status,
            "has_issues": bool(order.has_issues),
            "note_count": int(note_count or 0),
            "msg_count": int(msg_count or 0),
            "planned_delivery_at": order.planned_delivery_at.isoformat() if order.planned_delivery_at else None,
            "created_at": order.created_at.isoformat() if order.created_at else None,
            "raw_text": order.raw_text or "",
        }
        groups.setdefault(order.status, []).append(payload)

    return jsonify({
        "route": {"id": route.id, "name": route.name},
        "delivery_dt": delivery_dt.isoformat(),
        "groups": groups,
    }), 200


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
        SlackOrderEvent.query
        .filter(SlackOrderEvent.order_id == order.id)
        .order_by(SlackOrderEvent.created_at.asc())
        .all()
    )

    children = []
    thread_notes = []

    # best-effort: payload potrebbe contenere "text"
    for ev in events:
        if ev.type in ("created", "append_text"):
            txt = ""
            try:
                if isinstance(ev.payload, dict):
                    txt = ev.payload.get("text", "") or ev.payload.get("raw_text", "") or ""
            except Exception:
                txt = ""
            children.append({
                "label": ev.type,
                "ts": ev.created_at.isoformat() if ev.created_at else "",
                "text": txt,
            })

        if ev.type == "note":
            txt = ""
            try:
                if isinstance(ev.payload, dict):
                    txt = ev.payload.get("text", "") or ""
            except Exception:
                txt = ""
            thread_notes.append({
                "at": ev.created_at.isoformat() if ev.created_at else "",
                "text": txt,
            })

    # conteggi coerenti con overview
    notes_count = sum(1 for e in events if e.type == "note")
    multi_count = sum(1 for e in events if e.type in ("created", "append_text"))
    issues_count = 1 if bool(order.has_issues) else 0

    return jsonify({
        "id": order.id,
        "route_id": order.route_id,
        "route_name": route.name if route else "",
        "customer_display": order.customer_display,
        "status": order.status,
        "raw_text": order.raw_text or "",
        "planned_delivery_at": order.planned_delivery_at.isoformat() if order.planned_delivery_at else None,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "multi_count": multi_count,
        "notes_count": notes_count,
        "issues_count": issues_count,
        "children": children,
        "thread_notes": thread_notes,
    }), 200


@kiosk_bp.get("/board/<int:route_id>")
def kiosk_board(route_id: int):
    """
    Placeholder (board singola): la teniamo minimale.
    """
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


@kiosk_bp.get("/board/all")
def kiosk_board_all():
    """
    Overview server-side:
    - mostra SOLO DeliveryRoute attive
    - per ogni route prende il "prossimo giro" (min planned_delivery_at >= now) e include gli ordini di quel giorno
    - gli ordini in status=evaso vengono mostrati SOLO se planned_delivery_at è nella data odierna (local)
    """
    now_local = datetime.now(timezone.utc).astimezone()
    now_utc_naive = datetime.utcnow()

    routes = (
        DeliveryRoute.query
        .filter_by(is_active=True)
        .order_by(DeliveryRoute.name.asc())
        .all()
    )

    # subquery conteggi eventi (note / msg)
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
        delivery_dt = _next_delivery_dt(r, now_utc_naive)
        r_color = _route_light_color(r.id)

        if delivery_dt:
            start, end = _delivery_window(delivery_dt)

            rows = (
                db.session.query(
                    SlackOrder,
                    func.coalesce(note_counts_sq.c.note_count, 0).label("note_count"),
                    func.coalesce(msg_counts_sq.c.msg_count, 0).label("msg_count"),
                )
                .outerjoin(note_counts_sq, note_counts_sq.c.order_id == SlackOrder.id)
                .outerjoin(msg_counts_sq, msg_counts_sq.c.order_id == SlackOrder.id)
                .filter(
                    SlackOrder.route_id == r.id,
                    SlackOrder.planned_delivery_at >= start,
                    SlackOrder.planned_delivery_at < end,
                )
                .order_by(SlackOrder.status.asc(), SlackOrder.customer_display.asc())
                .all()
            )
        else:
            rows = []

        # filtro evaso: solo se oggi
        filtered_rows = []
        for order, note_count, msg_count in rows:
            if order.status == "evaso" and not _is_today_local(order.planned_delivery_at):
                continue
            filtered_rows.append((order, note_count, msg_count))

        routes_out.append({
            "id": r.id,
            "name": r.name,
            "color": r_color,
            "count": len(filtered_rows),
        })

        for order, note_count, msg_count in filtered_rows:
            total_orders += 1
            orders_out.append({
                "id": order.id,
                "route_id": r.id,
                "route_name": r.name,
                "route_color": r_color,
                "customer_display": order.customer_display,
                "status": order.status,
                "multi_count": int(msg_count or 0),
                "notes_count": int(note_count or 0),
                "issues_count": 1 if bool(order.has_issues) else 0,
                "preview": (order.raw_text or "").strip().splitlines()[0][:120] if (order.raw_text or "").strip() else "",
            })

    # ordinamento globale (prima per giro, poi status, poi cliente) -> mantiene consistenza visiva
    status_rank = {s: i for i, s in enumerate(STATUS_ORDER)}
    orders_out.sort(key=lambda o: (
        o["route_name"].lower(),
        status_rank.get(o["status"], 999),
        (o["customer_display"] or "").lower()
    ))

    return render_template(
        "kiosk_overview.html",
        now_local=now_local,
        show_closed_today=True,
        totals={"total": total_orders},
        routes=routes_out,
        orders=orders_out,
    )
