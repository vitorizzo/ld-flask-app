from __future__ import annotations

import os
from datetime import datetime

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from extensions import db
from models import PushSubscription, SharedOrderIntent
from tools.push_notifications import is_push_configured, push_config, send_push_to_user


pwa_bp = Blueprint("pwa", __name__)


def _share_upload_folder():
    folder = os.path.join(current_app.static_folder, "uploads", "shared_orders", datetime.utcnow().strftime("%Y%m%d"))
    os.makedirs(folder, exist_ok=True)
    return folder


def _public_upload_path(abs_path):
    rel = os.path.relpath(abs_path, current_app.static_folder).replace(os.sep, "/")
    return f"/static/{rel}"


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
def share_review(intent_id):
    intent = SharedOrderIntent.query.get_or_404(intent_id)
    if intent.user_id and intent.user_id != current_user.id and current_user.max_role_weight < 100:
        return "Accesso negato", 403
    return render_template("pwa/share_review.html", intent=intent)


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
