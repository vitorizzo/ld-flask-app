import logging
import hashlib
from datetime import datetime, timezone, timedelta

from flask import Blueprint, request, make_response, jsonify, render_template
from flask_login import login_required
from sqlalchemy import func

from extensions import db
from tools.log_utils import get_logger
from tools.slack_processor import SlackProcessor
from models import SlackOrder, SlackOrderEvent, DeliveryRoute, OrderStatus

kiosk_bp = Blueprint("kiosk", __name__, url_prefix="/kiosk")
logger = get_logger("kiosk", level=logging.INFO)

# Legacy fallback (non deve più pilotare le colonne: ora sono dinamiche da DB)
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

    for ev in events:
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
                "raw_text": order.raw_text or "",
                "planned_delivery_at": order.planned_delivery_at.isoformat()
                if order.planned_delivery_at
                else None,
                "created_at": order.created_at.isoformat() if order.created_at else None,
                "closed_at": order.closed_at.isoformat() if order.closed_at else None,
                "multi_count": multi_count,
                "notes_count": notes_count,
                "issues_count": issues_count,
                "children": children,
                "thread_notes": thread_notes,
            }
        ),
        200,
    )


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
            if order.status == "evaso":
                # mostra evasi solo se "oggi"
                if order.closed_at:
                    if not _is_today_local(order.closed_at):
                        continue
                else:
                    if not _evaded_today_by_event(order.id):
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


@kiosk_bp.route("/kiosk-ordini")
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

    # IMPORTANTE: non hardcodare più le colonne qui
    groups = {}

    for order, note_count, msg_count in rows:
        if order.status == "evaso":
            if not show_closed_today:
                continue

            # Preferisci closed_at (se presente)
            if order.closed_at:
                if not _is_today_local(order.closed_at):
                    continue
            else:
                # fallback vecchio: evento
                if not _evaded_today_by_event(order.id):
                    continue

        groups.setdefault(order.status, []).append(
            {
                "id": order.id,
                "customer": order.customer_display,
                "status": order.status,
                "has_issues": bool(order.has_issues),
                "note_count": int(note_count or 0),
                "msg_count": int(msg_count or 0),
                "planned_delivery_at": order.planned_delivery_at.isoformat()
                if order.planned_delivery_at
                else None,
                "created_at": order.created_at.isoformat() if order.created_at else None,
                "raw_text": order.raw_text or "",
                # campi per grouping client-side
                "delivery_label": order.planned_delivery_at.strftime("%d/%m %H:%M")
                if order.planned_delivery_at
                else "",
                "group_key": f"{route.id}|{(order.planned_delivery_at.date().isoformat() if order.planned_delivery_at else '')}|{(order.customer_norm or '').strip()}",
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
@login_required
def kiosk_api_set_status(order_id: int):
    """
    Richiede cambio stato ordine + feedback su Slack tramite reaction.
    Body JSON:
      { "status": "listato" }

    NOTA: ora consente:
    - salto di più stati (es. acquisito -> evaso)
    - ritorno indietro (es. controllato -> listato)
    """
    data = request.get_json(silent=True) or {}
    target_code = (data.get("status") or "").strip()
    if not target_code:
        return jsonify({"error": "missing_status"}), 400

    order = SlackOrder.query.get(order_id)
    if not order:
        return jsonify({"error": "order_not_found"}), 404

    target = OrderStatus.query.filter_by(code=target_code).first()
    if not target:
        return jsonify({"error": "invalid_status", "status": target_code}), 400

    reaction = _normalize_reaction_name(target.slack_reaction)
    if not reaction:
        return jsonify({"error": "status_has_no_reaction", "status": target_code}), 409

    channel_id = (order.slack_channel_id or "").strip()
    root_ts = (order.slack_thread_ts or order.slack_message_ts or "").strip()
    if not channel_id or not root_ts:
        return jsonify(
            {
                "error": "order_missing_slack_refs",
                "details": {"slack_channel_id": bool(channel_id), "root_ts": bool(root_ts)},
            }
        ), 409

    # Audit richiesta
    db.session.add(
        SlackOrderEvent(
            order_id=order.id,
            type="status_request",
            payload={
                "from": order.status,
                "to": target_code,
                "via": "kiosk_api",
                "reaction": reaction,
                "user_id": getattr(getattr(request, "user", None), "id", None),
            },
        )
    )

    # 1) Aggiungi reaction su Slack (non rimuoviamo le precedenti: per ora è feedback/trace)
    try:
        sp = SlackProcessor()
        api = sp._get_api()
        api.add_reaction(channel=channel_id, timestamp=root_ts, name=reaction)
    except Exception as e:
        logger.exception("set-status: errore add_reaction su slack")
        db.session.rollback()
        return jsonify({"error": "slack_reaction_failed", "details": str(e)}), 502

    # 2) Aggiorna DB subito (UI reattiva)
    old = order.status
    order.status = target_code

    # closed_at coerente: se terminale lo settiamo, se non terminale lo svuotiamo
    if target.is_terminal:
        if not order.closed_at:
            order.closed_at = datetime.utcnow()
    else:
        order.closed_at = None

    db.session.add(
        SlackOrderEvent(
            order_id=order.id,
            type="status_change",
            payload={
                "from": old,
                "to": target_code,
                "via": "kiosk_api",
                "reaction": reaction,
                "root_ts": root_ts,
                "channel": channel_id,
            },
        )
    )

    db.session.commit()

    return (
        jsonify(
            {
                "ok": True,
                "order_id": order.id,
                "from": old,
                "to": target_code,
                "reaction": reaction,
                "closed_at": order.closed_at.isoformat() if order.closed_at else None,
            }
        ),
        200,
    )
