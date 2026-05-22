from __future__ import annotations

import os
import mimetypes
from datetime import datetime

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_
from werkzeug.utils import secure_filename

from extensions import db
from models import (
    BusinessRegistry,
    DeliveryRoute,
    DeliveryRouteCustomer,
    PushSubscription,
    RouteOrderBoardEntry,
    SharedOrderIntent,
    SlackOrder,
    SlackOrderEvent,
)
from tools.push_notifications import is_push_configured, push_config, send_push_to_staff, send_push_to_user
from tools.role_required import role_required
from tools.slack_api import SlackAPI, SlackAPIConfig
from tools.slack_processor import SlackProcessor


pwa_bp = Blueprint("pwa", __name__)


def _share_upload_folder():
    folder = os.path.join(current_app.static_folder, "uploads", "shared_orders", datetime.utcnow().strftime("%Y%m%d"))
    os.makedirs(folder, exist_ok=True)
    return folder


def _public_upload_path(abs_path):
    rel = os.path.relpath(abs_path, current_app.static_folder).replace(os.sep, "/")
    return f"/static/{rel}"


def _static_rel_path(abs_path):
    return os.path.relpath(abs_path, current_app.static_folder).replace(os.sep, "/")


def _shared_file_abs_path(file_info):
    rel = (file_info.get("static_path") or "").strip().replace("\\", "/")
    if not rel and file_info.get("url", "").startswith("/static/"):
        rel = file_info["url"][len("/static/"):]
    if not rel.startswith("uploads/shared_orders/"):
        return None
    candidate = os.path.abspath(os.path.join(current_app.static_folder, rel))
    static_root = os.path.abspath(current_app.static_folder)
    if not candidate.startswith(static_root + os.sep) or not os.path.exists(candidate):
        return None
    return candidate


def _shared_attachments(intent):
    out = []
    for index, file_info in enumerate(intent.files or []):
        if file_info.get("diagnostic"):
            continue
        content_type = file_info.get("content_type") or file_info.get("mimetype") or ""
        filename = file_info.get("filename") or file_info.get("name") or f"allegato-{index + 1}"
        out.append({
            "id": file_info.get("id") or f"pwa-{intent.id}-{index + 1}",
            "source": "pwa_share",
            "name": filename,
            "title": filename,
            "mimetype": content_type,
            "filetype": os.path.splitext(filename)[1].lstrip(".").lower(),
            "size": file_info.get("size"),
            "is_image": content_type.startswith("image/"),
            "url": file_info.get("url") or "",
            "static_path": file_info.get("static_path") or "",
        })
    return out


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


def _direct_order_route():
    configured = (current_app.config.get("DIRECT_ORDER_SLACK_CHANNEL_ID") or current_app.config.get("PWA_DIRECT_ORDER_SLACK_CHANNEL_ID") or "").strip()
    if configured:
        route = DeliveryRoute.query.filter_by(slack_channel_id=configured, is_active=True).first()
        return route, configured
    route = (
        DeliveryRoute.query
        .filter(DeliveryRoute.is_active.is_(True), DeliveryRoute.name.ilike("%carsoli%"))
        .order_by(DeliveryRoute.id.asc())
        .first()
    )
    return route, route.slack_channel_id if route else ""


def _format_order_message(registry, note, planned_delivery_at=None):
    lines = [f"*{_customer_label(registry)}*"]
    if note:
        lines.append(note.strip())
    if planned_delivery_at:
        lines.append(f"Consegna: {planned_delivery_at.strftime('%d/%m/%Y')}")
    return "\n".join(lines)


def _upload_shared_files_to_slack(api, channel_id, thread_ts, intent):
    uploaded = []
    for file_info in intent.files or []:
        abs_path = _shared_file_abs_path(file_info)
        if not abs_path:
            raise RuntimeError(f"file condiviso non trovato: {file_info.get('filename') or file_info.get('url') or 'allegato'}")
        filename = file_info.get("filename") or os.path.basename(abs_path)
        uploaded.append(api.upload_file(
            channel_id,
            abs_path,
            title=filename,
            filename=filename,
            thread_ts=thread_ts,
        ))
    return uploaded


def _add_shared_attachment_event(order, intent, event_type="note"):
    attachments = _shared_attachments(intent)
    if not attachments:
        return
    db.session.add(SlackOrderEvent(
        order_id=order.id,
        type=event_type,
        payload={
            "text": "Allegati condivisi dalla webapp",
            "attachments": attachments,
            "via": "pwa_share",
            "intent_id": intent.id,
        },
    ))


@pwa_bp.post("/share")
@login_required
def share_target():
    title = (request.form.get("title") or "").strip()
    text = (request.form.get("text") or "").strip()
    url = (request.form.get("url") or "").strip()
    uploaded = []

    files = request.files.getlist("files") + request.files.getlist("file")
    for file in files:
        if not file:
            continue
        raw_filename = file.filename or f"condivisione-{len(uploaded) + 1}{mimetypes.guess_extension(file.mimetype or '') or ''}"
        filename = secure_filename(raw_filename)
        if not filename:
            filename = f"condivisione-{len(uploaded) + 1}"
        target = os.path.join(_share_upload_folder(), f"{datetime.utcnow().strftime('%H%M%S%f')}_{filename}")
        file.save(target)
        uploaded.append({
            "id": f"pwa-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}-{len(uploaded) + 1}",
            "filename": filename,
            "content_type": file.mimetype,
            "size": os.path.getsize(target),
            "url": _public_upload_path(target),
            "static_path": _static_rel_path(target),
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
    order_type = (request.args.get("type") or "route").strip()
    route_id = request.args.get("route_id", type=int)
    q = (request.args.get("q") or "").strip()
    if order_type != "direct" and not route_id:
        return jsonify({"ok": True, "customers": []})

    query = BusinessRegistry.query.filter(BusinessRegistry.kind == "customer", BusinessRegistry.is_active.is_(True))
    if order_type != "direct":
        query = query.join(DeliveryRouteCustomer, DeliveryRouteCustomer.registry_id == BusinessRegistry.id).filter(
            DeliveryRouteCustomer.route_id == route_id,
            DeliveryRouteCustomer.is_active.is_(True),
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
        .order_by(BusinessRegistry.display_name.asc(), BusinessRegistry.id.asc())
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
    order_type = (data.get("type") or "route").strip()
    route = DeliveryRoute.query.filter_by(id=data.get("route_id"), is_active=True).first() if order_type != "direct" else None
    registry = BusinessRegistry.query.filter_by(id=data.get("registry_id"), kind="customer", is_active=True).first()
    if not registry:
        return jsonify({"ok": False, "error": "Cliente non valido"}), 404

    if order_type == "direct":
        direct_route, channel_id = _direct_order_route()
        route = direct_route
        if not channel_id:
            return jsonify({"ok": False, "error": "Canale diretto Carsoli non configurato"}), 400
    else:
        if not route:
            return jsonify({"ok": False, "error": "Giro non valido"}), 404
        channel_id = route.slack_channel_id
        if not channel_id or channel_id.startswith("manual-"):
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

    api = SlackAPI(SlackAPIConfig(bot_token=bot_token))
    entry = None
    if order_type == "direct":
        planned_delivery_at = None
        message_text = _format_order_message(registry, note)
    else:
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
        planned_delivery_at = entry.planned_delivery_at
        db.session.flush()
        message_text = _format_slack_message(registry, entry)

    response = api.post_message(channel_id, message_text)
    ts = response.get("ts") or (response.get("message") or {}).get("ts")
    if not ts:
        db.session.rollback()
        return jsonify({"ok": False, "error": f"Slack non ha restituito il timestamp del messaggio: {response}"}), 502

    try:
        _upload_shared_files_to_slack(api, channel_id, ts, intent)
    except Exception as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": f"Ordine inviato, ma allegati non caricati su Slack: {exc}"}), 502

    target_status = "acquisito"
    if entry:
        entry.slack_channel_id = channel_id
        entry.slack_message_ts = ts
        entry.slack_thread_ts = ts
        entry.sent_at = datetime.utcnow()
        target_status = "listato" if entry.list_done else "acquisito"
    elif data.get("list_done"):
        target_status = "listato"

    if data.get("list_done"):
        try:
            if entry:
                _set_list_done_reaction(entry, True)
            else:
                SlackProcessor().execute_actions(
                    [{"action_type": "addReaction", "config_json": {"reaction": "white_check_mark"}}],
                    {"channel": channel_id, "ts": ts},
                )
        except Exception as exc:
            db.session.rollback()
            return jsonify({"ok": False, "error": f"Ordine inviato, ma reaction lista fatta non applicata: {exc}"}), 502

    if entry:
        order = _ensure_slack_order(entry, target_status)
        _add_shared_attachment_event(order, intent, event_type="note")
    else:
        order = SlackOrder(
            route_id=route.id if route else None,
            slack_channel_id=channel_id,
            customer_display=_customer_label(registry),
            customer_key=registry.source_code or str(registry.id),
            order_date=datetime.utcnow().date(),
            planned_delivery_at=planned_delivery_at,
            status=target_status,
            raw_text=message_text,
            slack_message_ts=ts,
            slack_thread_ts=ts,
            has_issues=False,
        )
        db.session.add(order)
        db.session.flush()
        db.session.add(SlackOrderEvent(
            order_id=order.id,
            type="created",
            payload={
                "ts": ts,
                "text": message_text,
                "attachments": _shared_attachments(intent),
                "via": "pwa_share",
                "intent_id": intent.id,
            },
        ))

    intent.status = "sent"
    db.session.commit()
    try:
        send_push_to_staff("Nuovo ordine", _customer_label(registry), f"/kiosk?order_id={order.id}")
    except Exception:
        current_app.logger.exception("Invio push nuovo ordine fallito")
    return jsonify({"ok": True, "entry": entry.to_dict() if entry else None, "order_id": order.id, "intent": intent.to_dict()})


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
