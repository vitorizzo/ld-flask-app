import hashlib
import secrets
from datetime import datetime, timezone

from flask import g, request
from sqlalchemy.exc import SQLAlchemyError

from extensions import db
from models import AppVisitor
from tools.log_utils import get_logger


logger = get_logger("visitor_analytics")
VISITOR_COOKIE = "ldapp_visitor"
VISIT_COOKIE = "ldapp_visit"
VISITOR_MAX_AGE = 400 * 24 * 60 * 60
VISIT_MAX_AGE = 30 * 60
BOT_MARKERS = ("bot", "crawler", "spider", "slurp", "headless", "preview")
EXCLUDED_ENDPOINTS = {"static", "service_worker", "app_version"}


def _is_document_request():
    if request.method != "GET" or request.endpoint in EXCLUDED_ENDPOINTS:
        return False
    if request.path.startswith(("/task/", "/api/")):
        return False
    if request.headers.get("DNT") == "1" or request.headers.get("Sec-GPC") == "1":
        return False
    user_agent = (request.headers.get("User-Agent") or "").lower()
    if any(marker in user_agent for marker in BOT_MARKERS):
        return False
    destination = (request.headers.get("Sec-Fetch-Dest") or "").lower()
    return destination == "document" or "text/html" in (request.headers.get("Accept") or "").lower()


def record_visit():
    """Registra solo conteggi aggregati; non conserva IP, user-agent, URL o user_id."""
    if not _is_document_request():
        return

    raw_token = request.cookies.get(VISITOR_COOKIE)
    is_new_visitor = not raw_token
    if is_new_visitor:
        raw_token = secrets.token_urlsafe(32)

    if not is_new_visitor and request.cookies.get(VISIT_COOKIE) == "1":
        g.analytics_visitor_token = raw_token
        g.analytics_refresh_visitor_cookie = False
        g.analytics_refresh_visit_cookie = True
        return

    visitor_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    new_visit = request.cookies.get(VISIT_COOKIE) != "1"
    now = datetime.now(timezone.utc)

    try:
        visitor = AppVisitor.query.filter_by(visitor_hash=visitor_hash).first()
        if visitor is None:
            visitor = AppVisitor(
                visitor_hash=visitor_hash,
                first_seen=now,
                last_seen=now,
                visit_count=1,
            )
            db.session.add(visitor)
            new_visit = True
        elif new_visit:
            visitor.last_seen = now
            visitor.visit_count = int(visitor.visit_count or 0) + 1
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        logger.debug("Visitor analytics unavailable; request continues without tracking", exc_info=True)
        return

    g.analytics_visitor_token = raw_token
    g.analytics_refresh_visitor_cookie = is_new_visitor
    g.analytics_refresh_visit_cookie = True


def set_analytics_cookies(response):
    token = getattr(g, "analytics_visitor_token", None)
    if not token:
        return response
    forwarded_proto = (request.headers.get("X-Forwarded-Proto") or "").split(",", 1)[0].strip().lower()
    common = {
        "secure": request.is_secure or forwarded_proto == "https",
        "httponly": True,
        "samesite": "Lax",
        "path": "/",
    }
    if getattr(g, "analytics_refresh_visitor_cookie", False):
        response.set_cookie(VISITOR_COOKIE, token, max_age=VISITOR_MAX_AGE, **common)
    if getattr(g, "analytics_refresh_visit_cookie", False):
        response.set_cookie(VISIT_COOKIE, "1", max_age=VISIT_MAX_AGE, **common)
    return response
