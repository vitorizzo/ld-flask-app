import logging
from datetime import datetime, timezone, timedelta

from flask import Blueprint, request, make_response, jsonify
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


@kiosk_bp.get("/test")
def kiosk_test():
    client_ip = _best_effort_client_ip()
    now = datetime.now(timezone.utc).astimezone()

    html = f"""
<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8" />
  <meta http-equiv="refresh" content="10" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Kiosk Test</title>
  <style>
    body {{ font-family: Arial, sans-serif; padding: 16px; }}
    code {{ background: #f3f3f3; padding: 2px 6px; border-radius: 6px; }}
  </style>
</head>
<body>
  <h1>KIOSK TEST OK</h1>
  <p>Ora server: <code>{now.strftime('%Y-%m-%d %H:%M:%S %Z')}</code></p>
  <p>Client IP: <code>{client_ip}</code></p>
  <p>User-Agent: <code>{request.headers.get('User-Agent', '')}</code></p>
  <p>Auto refresh ogni 10s</p>
</body>
</html>
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
    out = [{
        "id": r.id,
        "name": r.name,
        "slack_channel_id": r.slack_channel_id,
        "default_weekday": r.default_weekday,
        "default_time": r.default_time.strftime("%H:%M:%S") if r.default_time else None,
    } for r in routes]
    return jsonify(out), 200


@kiosk_bp.get("/api/board/<int:route_id>")
def kiosk_api_board(route_id: int):
    """
    Ritorna gli ordini del prossimo giro (planned_delivery_at minimo >= now) per il route.
    Raggruppa per status e include note_count + has_issues.
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

    # assicura chiavi per stati eventualmente non in STATUS_ORDER
    for k in list(groups.keys()):
        if k not in groups:
            groups[k] = []

    return jsonify({
        "route": {"id": route.id, "name": route.name},
        "delivery_dt": delivery_dt.isoformat(),
        "groups": groups,
    }), 200


@kiosk_bp.get("/board/<int:route_id>")
def kiosk_board(route_id: int):
    """
    Pagina HTML minimale, auto-refresh, con colonne per stato.
    Fonte dati: /kiosk/api/board/<route_id>
    """
    client_ip = _best_effort_client_ip()
    now = datetime.now(timezone.utc).astimezone()

    html = f"""
            <!doctype html>
            <html lang="it">
            <head>
              <meta charset="utf-8" />
              <meta http-equiv="refresh" content="10" />
              <meta name="viewport" content="width=device-width, initial-scale=1" />
              <title>Kiosk Board</title>
              <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 12px; }}
                .top {{ display:flex; justify-content:space-between; align-items:center; gap:12px; }}
                .meta code {{ background:#f3f3f3; padding:2px 6px; border-radius:6px; }}
                .grid {{ display:grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-top: 12px; }}
                .col {{ border:1px solid #ddd; border-radius:10px; padding:10px; min-height: 65vh; }}
                .col h2 {{ margin:0 0 10px 0; font-size: 18px; }}
                .card {{ border:1px solid #eee; border-radius:10px; padding:8px; margin-bottom:8px; }}
                .badges {{ display:flex; gap:6px; margin-top:6px; }}
                .badge {{ font-size:12px; padding:2px 6px; border-radius:999px; background:#f3f3f3; }}
              </style>
            </head>
            <body>
              <div class="top">
                <div>
                  <h1 style="margin:0;">Kiosk Board</h1>
                  <div class="meta">Ora server: <code>{now.strftime('%Y-%m-%d %H:%M:%S %Z')}</code> — IP: <code>{client_ip}</code></div>
                </div>
                <div class="meta">Auto refresh 10s</div>
              </div>
            
              <div id="hdr" class="meta" style="margin-top:10px;"></div>
            
              <div class="grid">
                <div class="col"><h2>Acquisito</h2><div id="acquisito"></div></div>
                <div class="col"><h2>Listato</h2><div id="listato"></div></div>
                <div class="col"><h2>Controllato</h2><div id="controllato"></div></div>
                <div class="col"><h2>Evaso</h2><div id="evaso"></div></div>
              </div>
            
            <script>
            async function loadBoard() {{
              const res = await fetch('/kiosk/api/board/{route_id}', {{ cache: 'no-store' }});
              const data = await res.json();
            
              const hdr = document.getElementById('hdr');
              if (!data.delivery_dt) {{
                hdr.textContent = `Giro: ${{data.route?.name || ''}} — Nessuna consegna pianificata trovata`;
              }} else {{
                hdr.textContent = `Giro: ${{data.route?.name || ''}} — Consegna: ${{data.delivery_dt}}`;
              }}
            
              const groups = data.groups || {{}};
            
              const render = (status) => {{
                const el = document.getElementById(status);
                el.innerHTML = '';
                (groups[status] || []).forEach(o => {{
                  const div = document.createElement('div');
                  div.className = 'card';
                  const safeCustomer = (o.customer || '').replaceAll('<','&lt;').replaceAll('>','&gt;');
                  div.innerHTML = `<div><strong>${{safeCustomer}}</strong></div>`;
                  const badges = [];
                  if (o.msg_count > 1) badges.push(`<span class="badge">msg: ${{o.msg_count}}</span>`);
                  if (o.note_count > 0) badges.push(`<span class="badge">note: ${{o.note_count}}</span>`);
                  if (o.has_issues) badges.push(`<span class="badge">issue</span>`);
                  if (badges.length) div.innerHTML += `<div class="badges">${{badges.join('')}}</div>`;
                  el.appendChild(div);
                }});
              }}
            
              render('acquisito');
              render('listato');
              render('controllato');
              render('evaso');
            }}
            loadBoard();
            </script>
            
            </body>
            </html>
            """
    resp = make_response(html, 200)
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp
