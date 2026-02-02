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
                .badge--msg {{ background:#e6f0ff; border:1px solid #6aa6ff; color:#0b3d91; }}
                .badge--note {{ background:#fff6cc; border:1px solid #e0b400; color:#6b4e00; }}
                .badge--issue {{ background:#ffe1e1; border:1px solid #ff6b6b; color:#8a0000; }}

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
                  if (o.msg_count > 1) badges.push(`<span class="badge--msg">msg: ${{o.msg_count}}</span>`);
                  if (o.note_count > 0) badges.push(`<span class="badge--note">note: ${{o.note_count}}</span>`);
                  if (o.has_issues) badges.push(`<span class="badge--issue">issue</span>`);
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


@kiosk_bp.route("/boards")
def kiosk_boards_overview():
    return """
            <!doctype html>
            <html lang="it">
            <head>
              <meta charset="utf-8">
              <meta name="viewport" content="width=device-width, initial-scale=1">
              <title>Kiosk - Tutti i giri</title>
              <style>
                body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; background:#f6f7f9; margin:0; }
                header { padding:12px 16px; background:#111827; color:#fff; font-weight:600; display:flex; gap:12px; align-items:center; }
                header .muted { opacity:.8; font-weight:400; font-size:14px; }
                .wrap { padding:14px; display:grid; gap:14px; }
                .route { background:#fff; border:1px solid #e5e7eb; border-radius:12px; overflow:hidden; }
                .route h2 { margin:0; padding:10px 12px; font-size:16px; border-bottom:1px solid #e5e7eb; display:flex; justify-content:space-between; align-items:center; }
                .route h2 a { color:inherit; text-decoration:none; }
                .cols { display:grid; grid-template-columns: repeat(4, 1fr); gap:10px; padding:12px; }
                .col { background:#f9fafb; border:1px solid #e5e7eb; border-radius:10px; padding:10px; min-height:80px; }
                .col h3 { margin:0 0 8px 0; font-size:13px; color:#374151; display:flex; justify-content:space-between; }
                .pill { font-size:12px; background:#e5e7eb; padding:2px 8px; border-radius:999px; }
                .item { background:#fff; border:1px solid #e5e7eb; border-radius:10px; padding:8px 10px; margin-bottom:8px; }
                .item .name { font-weight:650; }
                .badges { margin-top:6px; display:flex; gap:6px; flex-wrap:wrap; }
                .badge { font-size:12px; padding:2px 7px; border-radius:999px; border:1px solid transparent; }
                .badge--msg { background:#e6f0ff; border-color:#6aa6ff; color:#0b3d91; }
                .badge--note { background:#fff6cc; border-color:#e0b400; color:#6b4e00; }
                .badge--issue { background:#ffe1e1; border-color:#ff6b6b; color:#8a0000; }
                .rowlink { color:#2563eb; text-decoration:none; font-weight:600; font-size:12px; }
              </style>
            </head>
            <body>
              <header>
                <div>Kiosk - Tutti i giri</div>
                <div class="muted" id="ts"></div>
              </header>
              <div class="wrap" id="wrap"></div>
            
            <script>
            const STATUS_LABELS = ["Acquisito","Listato","Preparato","Controllato"];
            const STATUS_KEYS = ["acquired","listed","prepared","checked"];
            
            function esc(s){ return (s||"").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;"); }
            
            async function fetchJson(url){
              const r = await fetch(url, {cache:"no-store"});
              if(!r.ok) throw new Error(url+" "+r.status);
              return await r.json();
            }
            
            function renderOrder(o){
              const badges = [];
              if ((o.msg_count||0) > 1) badges.push(`<span class="badge badge--msg">msg: ${o.msg_count}</span>`);
              if ((o.note_count||0) > 0) badges.push(`<span class="badge badge--note">note: ${o.note_count}</span>`);
              if (o.has_issues) badges.push(`<span class="badge badge--issue">issue</span>`);
              return `
                <div class="item">
                  <div class="name">${esc(o.customer_display || o.customer_key)}</div>
                  <div class="badges">${badges.join("")}</div>
                </div>
              `;
            }
            
            function renderRoute(route, board){
              // board: { route: {...}, start, end, columns:{acquired:[], listed:[], prepared:[], checked:[]} }
              const colsHtml = STATUS_KEYS.map((k, idx) => {
                const arr = (board.columns && board.columns[k]) ? board.columns[k] : [];
                return `
                  <div class="col">
                    <h3><span>${STATUS_LABELS[idx]}</span><span class="pill">${arr.length}</span></h3>
                    ${arr.slice(0, 12).map(renderOrder).join("")}
                  </div>
                `;
              }).join("");
            
              return `
                <section class="route">
                  <h2>
                    <a href="/kiosk/board/${route.id}">${esc(route.name)} <span class="pill">${route.id}</span></a>
                    <a class="rowlink" href="/kiosk/board/${route.id}">Apri</a>
                  </h2>
                  <div class="cols">${colsHtml}</div>
                </section>
              `;
            }
            
            async function main(){
              document.getElementById("ts").textContent = new Date().toLocaleString();
              const wrap = document.getElementById("wrap");
              wrap.innerHTML = "";
            
              const routes = await fetchJson("/kiosk/api/routes");
              if(!routes.length){
                wrap.innerHTML = `<div style="padding:12px;background:#fff;border:1px solid #e5e7eb;border-radius:12px;">
                  Nessun giro attivo (delivery_routes). </div>`;
                return;
              }
            
              // carico tutte le board in parallelo
              const boards = await Promise.all(routes.map(r => fetchJson(`/kiosk/api/board/${r.id}`)));
              for(let i=0;i<routes.length;i++){
                wrap.insertAdjacentHTML("beforeend", renderRoute(routes[i], boards[i]));
              }
            }
            main();
            setInterval(main, 15000);
            </script>
            </body>
            </html>
            """
