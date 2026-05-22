from __future__ import annotations

import os
from datetime import datetime

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_
from werkzeug.utils import secure_filename

from extensions import db
from models import BusinessRegistry, DeliveryRoute, DeliveryRouteCustomer, PushSubscription, RouteOrderBoardEntry, SharedOrderIntent
from tools.push_notifications import is_push_configured, push_config, send_push_to_user
from tools.role_required import role_required
from tools.slack_api import SlackAPI, SlackAPIConfig


pwa_bp = Blueprint("pwa", __name__)


def _share_upload_folder():
    folder = os.path.join(current_app.static_folder, "uploads", "shared_orders", datetime.utcnow().strftime("%Y%m%d"))
    os.makedirs(folder, exist_ok=True)
    return folder


def _public_upload_path(abs_path):
    rel = os.path.relpath(abs_path, current_app.static_folder).replace(os.sep, "/")
    return f"/static/{rel}"


def _intent_access_or_404(intent_id):
    intent = SharedOrderIntent.query.get_or_404(intent_id)
    if intent.user_id and intent.user_id != current_user.id and (current_user.max_role_weight or 0) < 100:
        return None
    return intent


def _shared_note(intent):
    parts = []
    if intent.title:
        parts.append(intent.title)
    if intent.text:
        parts.append(intent.text)
    if intent.url:
        parts.append(intent.url)
    for file in intent.files or []:
        url = file.get("url")
        filename = file.get("filename") or "allegato"
        if url:
            parts.append(f"{filename}: {url}")
    return "\n\n".join(part for part in parts if part).strip()


def _customer_label(registry):
    return registry.display_name or registry.legal_name or registry.source_code or f"Cliente {registry.id}"


@pwa_bp.post("/share")
@login_required
def share_target():
    title = (request.form.get("title") or "").strip()
    text = (request.form.get("text") or "").strip()
    url = (request.form.get("url") or "").strip()
    uploaded = []

    files = request.files.getlist("files") or request.files.getlist("file") or []
    for file in files:
        if not file or not file.filename:
            continue
        filename = secure_filename(file.filename)
        if not filename:
            continue
        target = os.path.join(_share_upload_folder(), f"{datetime.utcnow().strftime('%H%M%S%f')}_{filename}")
        file.save(target)
        uploaded.append({
            "filename": filename,
            "content_type": file.mimetype,
            "url": _public_upload_path(target),
        })

    intent = SharedOrderIntent(
        user_id=current_user.id,
        title=title or None,
        text=text or None,
        url=url or None,
        files=uploaded,
    )
    db.session.add(intent)
    db.session.commit()
    return redirect(url_for("pwa.share_review", intent_id=intent.id))


@pwa_bp.get("/share/<int:intent_id>")
@login_required
@role_required(30)
def share_review(intent_id):
    intent = _intent_access_or_404(intent_id)
    if not intent:
        return "Accesso negato", 403
    return render_template("pwa/share_review.html", intent=intent, suggested_note=_shared_note(intent))


@pwa_bp.get("/api/share/<int:intent_id>/options")
@login_required
@role_required(30)
def share_options(intent_id):
    intent = _intent_access_or_404(intent_id)
    if not intent:
        return jsonify({"ok": False, "error": "Accesso negato"}), 403
    routes = DeliveryRoute.query.filter_by(is_active=True).order_by(DeliveryRoute.name.asc()).all()
    return jsonify({
        "ok": True,
        "intent": intent.to_dict(),
        "note": _shared_note(intent),
        "routes": [{"id": route.id, "name": route.name, "slack_channel_id": route.slack_channel_id} for route in routes],
    })


@pwa_bp.get("/api/share/<int:intent_id>/customers")
@login_required
@role_required(30)
def share_customers(intent_id):
    intent = _intent_access_or_404(intent_id)
    if not intent:
        return jsonify({"ok": False, "error": "Accesso negato"}), 403
    route_id = request.args.get("route_id", type=int)
    q = (request.args.get("q") or "").strip()
    if not route_id:
        return jsonify({"ok": True, "customers": []})

    query = (
        BusinessRegistry.query
        .join(DeliveryRouteCustomer, DeliveryRouteCustomer.registry_id == BusinessRegistry.id)
        .filter(
            DeliveryRouteCustomer.route_id == route_id,
            DeliveryRouteCustomer.is_active.is_(True),
            BusinessRegistry.kind == "customer",
            BusinessRegistry.is_active.is_(True),
        )
    )
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            BusinessRegistry.display_name.ilike(like),
            BusinessRegistry.legal_name.ilike(like),
            BusinessRegistry.source_code.ilike(like),
            BusinessRegistry.vat_number.ilike(like),
            BusinessRegistry.tax_code.ilike(like),
            BusinessRegistry.city.ilike(like),
        ))
    customers = (
        query
        .order_by(DeliveryRouteCustomer.sort_order.asc(), BusinessRegistry.display_name.asc(), BusinessRegistry.id.asc())
        .limit(30)
        .all()
    )
    return jsonify({
        "ok": True,
        "customers": [{
            "id": customer.id,
            "display": _customer_label(customer),
            "source_code": customer.source_code,
            "city": customer.city,
        } for customer in customers],
    })


@pwa_bp.post("/api/share/<int:intent_id>/send")
@login_required
@role_required(30)
def share_send_order(intent_id):
    from routes.route_orders import _ensure_slack_order, _format_slack_message, _next_delivery_dt, _set_list_done_reaction

    intent = _intent_access_or_404(intent_id)
    if not intent:
        return jsonify({"ok": False, "error": "Accesso negato"}), 403

    data = request.get_json(silent=True) or {}
    route = DeliveryRoute.query.filter_by(id=data.get("route_id"), is_active=True).first()
    registry = BusinessRegistry.query.filter_by(id=data.get("registry_id"), kind="customer", is_active=True).first()
    if not route or not registry:
        return jsonify({"ok": False, "error": "Giro o cliente non valido"}), 404
    if not route.slack_channel_id or route.slack_channel_id.startswith("manual-"):
        return jsonify({"ok": False, "error": "Il giro non ha un canale Slack valido associato"}), 400

    linked = DeliveryRouteCustomer.query.filter_by(route_id=route.id, registry_id=registry.id, is_active=True).first()
    if not linked:
        return jsonify({"ok": False, "error": "Il cliente selezionato non appartiene al giro scelto"}), 400

    bot_token = current_app.config.get("SLACK_BOT_TOKEN", "") or ""
    if not bot_token:
        return jsonify({"ok": False, "error": "SLACK_BOT_TOKEN mancante"}), 503

    note = (data.get("order_note") or "").strip() or _shared_note(intent)
    if not note:
        return jsonify({"ok": False, "error": "Testo ordine mancante"}), 400

    board_delivery = _next_delivery_dt(route)
    board_date = board_delivery.date()
    entry = RouteOrderBoardEntry.query.filter_by(route_id=route.id, registry_id=registry.id, board_date=board_date).first()
    if not entry:
        entry = RouteOrderBoardEntry(
            route_id=route.id,
            registry_id=registry.id,
            board_date=board_date,
            planned_delivery_at=board_delivery,
        )
        db.session.add(entry)

    entry.order_note = note
    entry.status = "ordine_fatto"
    entry.list_done = bool(data.get("list_done"))
    db.session.flush()

    api = SlackAPI(SlackAPIConfig(bot_token=bot_token))
    response = api.post_message(route.slack_channel_id, _format_slack_message(registry, entry))
    ts = response.get("ts") or (response.get("message") or {}).get("ts")
    if not ts:
        db.session.rollback()
        return jsonify({"ok": False, "error": f"Slack non ha restituito il timestamp del messaggio: {response}"}), 502

    entry.slack_channel_id = route.slack_channel_id
    entry.slack_message_ts = ts
    entry.slack_thread_ts = ts
    entry.sent_at = datetime.utcnow()
    target_status = "listato" if entry.list_done else "acquisito"
    if entry.list_done:
        try:
            _set_list_done_reaction(entry, True)
        except Exception as exc:
            db.session.rollback()
            return jsonify({"ok": False, "error": f"Ordine inviato, ma reaction lista fatta non applicata: {exc}"}), 502
    _ensure_slack_order(entry, target_status)
    intent.status = "sent"
    db.session.commit()
    return jsonify({"ok": True, "entry": entry.to_dict(), "intent": intent.to_dict()})


@pwa_bp.get("/api/push/config")
@login_required
def push_api_config():
    cfg = push_config()
    return jsonify({
        "ok": True,
        "enabled": is_push_configured(),
        "public_key": cfg["public_key"],
    })


@pwa_bp.post("/api/push/subscribe")
@login_required
def push_subscribe():
    data = request.get_json(silent=True) or {}
    endpoint = (data.get("endpoint") or "").strip()
    keys = data.get("keys") or {}
    p256dh = (keys.get("p256dh") or "").strip()
    auth = (keys.get("auth") or "").strip()
    if not endpoint or not p256dh or not auth:
        return jsonify({"ok": False, "error": "Subscription push non valida"}), 400

    sub = PushSubscription.query.filter_by(endpoint=endpoint).first()
    if not sub:
        sub = PushSubscription(endpoint=endpoint)
        db.session.add(sub)
    sub.user_id = current_user.id
    sub.p256dh = p256dh
    sub.auth = auth
    sub.user_agent = request.headers.get("User-Agent")
    sub.is_active = True
    db.session.commit()
    return jsonify({"ok": True})


@pwa_bp.post("/api/push/unsubscribe")
@login_required
def push_unsubscribe():
    data = request.get_json(silent=True) or {}
    endpoint = (data.get("endpoint") or "").strip()
    if endpoint:
        sub = PushSubscription.query.filter_by(endpoint=endpoint, user_id=current_user.id).first()
        if sub:
            sub.is_active = False
            db.session.commit()
    return jsonify({"ok": True})


@pwa_bp.post("/api/push/test")
@login_required
def push_test():
    try:
        result = send_push_to_user(
            current_user.id,
            "LDApp",
            "Notifiche push abilitate correttamente.",
            "/",
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503
    return jsonify({"ok": True, **result})
