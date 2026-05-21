from datetime import date, datetime, time, timedelta

from flask import Blueprint, current_app, jsonify, render_template, request
from flask_login import login_required
from sqlalchemy import or_

from extensions import db
from models import (
    BusinessRegistry,
    BusinessRegistryAlert,
    BusinessRegistryContactLink,
    BusinessRegistryContact,
    DeliveryRoute,
    DeliveryRouteCustomer,
    DeliveryScheduleRule,
    OrderStatus,
    RegistryContact,
    RegistryContactPoint,
    RouteOrderBoardEntry,
    SlackOrder,
    SlackOrderEvent,
)
from tools.role_required import role_required
from tools.slack_api import SlackAPI, SlackAPIConfig


route_orders_bp = Blueprint("route_orders", __name__)

BOARD_STATUSES = [
    {"code": "da_chiamare", "label": "Da chiamare"},
    {"code": "ordine_fatto", "label": "Ordine fatto"},
    {"code": "richiamare", "label": "Richiamare"},
    {"code": "salta_giro", "label": "Salta il giro"},
    {"code": "chiama_lui", "label": "Chiama lui"},
    {"code": "non_risponde", "label": "Non risponde"},
]


def _route_to_dict(route):
    return {
        "id": route.id,
        "name": route.name,
        "slack_channel_id": route.slack_channel_id,
    }


def _label_registry(registry):
    return registry.display_name or registry.legal_name or registry.source_code or f"Cliente {registry.id}"


def _parse_date(value):
    if not value:
        return None
    return date.fromisoformat(str(value)[:10])


def _parse_datetime(value, fallback_time=None):
    if not value:
        return None
    raw = str(value)
    if len(raw) == 10:
        return datetime.combine(date.fromisoformat(raw), fallback_time or time(9, 0))
    return datetime.fromisoformat(raw)


def _python_weekday(delivery_weekday):
    value = int(delivery_weekday or 0)
    return value - 1 if 1 <= value <= 7 else value


def _next_weekday_dt(base_dt, target_weekday, target_time):
    weekday = _python_weekday(target_weekday)
    days_ahead = (weekday - base_dt.weekday()) % 7
    candidate = datetime.combine((base_dt + timedelta(days=days_ahead)).date(), target_time)
    if candidate <= base_dt:
        candidate += timedelta(days=7)
    return candidate


def _week_index(value_date):
    iso = value_date.isocalendar()
    return int(iso.year) * 53 + int(iso.week)


def _next_biweekly_dt(base_dt, target_weekday, target_time, anchor_date, end_date=None):
    anchor = anchor_date or base_dt.date()
    candidate = _next_weekday_dt(base_dt, target_weekday, target_time)
    for _ in range(54):
        if (_week_index(candidate.date()) - _week_index(anchor)) % 2 == 0:
            if end_date and candidate.date() > end_date:
                return None
            return candidate
        candidate += timedelta(days=7)
    return None


def _schedule_candidate(
    base_dt,
    *,
    frequency,
    target_weekday,
    target_time,
    second_weekday=None,
    second_time=None,
    anchor_date=None,
    end_date=None,
):
    if not target_weekday:
        return None
    frequency = frequency or "weekly"
    if frequency == "biweekly":
        return _next_biweekly_dt(base_dt, target_weekday, target_time, anchor_date, end_date=end_date)
    candidates = [_next_weekday_dt(base_dt, target_weekday, target_time)]
    if frequency == "twice_weekly" and second_weekday and second_time:
        candidates.append(_next_weekday_dt(base_dt, second_weekday, second_time))
    if end_date:
        candidates = [candidate for candidate in candidates if candidate.date() <= end_date]
    return min(candidates) if candidates else None


def _period_schedule_candidate(base_dt, route):
    today = base_dt.date()
    rules = (
        DeliveryScheduleRule.query
        .filter(
            DeliveryScheduleRule.route_id == route.id,
            DeliveryScheduleRule.scope == "period",
            DeliveryScheduleRule.is_active.is_(True),
            DeliveryScheduleRule.start_date.isnot(None),
            DeliveryScheduleRule.end_date.isnot(None),
            DeliveryScheduleRule.target_weekday.isnot(None),
            DeliveryScheduleRule.end_date >= today,
        )
        .order_by(DeliveryScheduleRule.start_date.desc(), DeliveryScheduleRule.id.desc())
        .all()
    )
    for rule in rules:
        anchor = base_dt
        if rule.start_date and rule.start_date > today:
            anchor = datetime.combine(rule.start_date, time.min)
        candidate = _schedule_candidate(
            anchor,
            frequency=rule.frequency or "weekly",
            target_weekday=int(rule.target_weekday),
            target_time=rule.target_time,
            second_weekday=rule.second_weekday,
            second_time=rule.second_time,
            anchor_date=rule.start_date,
            end_date=rule.end_date,
        )
        if candidate and (not rule.start_date or candidate.date() >= rule.start_date):
            return candidate
    return None


def _apply_once_rule(route, candidate_dt):
    rule = (
        DeliveryScheduleRule.query
        .filter_by(route_id=route.id, scope="once", is_active=True, source_date=candidate_dt.date())
        .order_by(DeliveryScheduleRule.id.desc())
        .first()
    )
    if rule and rule.target_date:
        return datetime.combine(rule.target_date, rule.target_time or candidate_dt.time())
    return candidate_dt


def _next_delivery_dt(route, base_dt=None):
    base_dt = base_dt or datetime.now()
    period_candidate = _period_schedule_candidate(base_dt, route)
    if period_candidate:
        return _apply_once_rule(route, period_candidate)
    if int(route.default_weekday or 0) == 0:
        candidate = datetime.combine(base_dt.date(), route.default_time)
        if candidate <= base_dt:
            candidate += timedelta(days=1)
    else:
        candidate = _schedule_candidate(
            base_dt,
            frequency=getattr(route, "frequency", None) or "weekly",
            target_weekday=int(route.default_weekday),
            target_time=route.default_time,
            second_weekday=getattr(route, "second_weekday", None),
            second_time=getattr(route, "second_time", None),
            anchor_date=getattr(route, "frequency_anchor_date", None),
        )
    return _apply_once_rule(route, candidate)


def _upcoming_delivery_dates(route, count=8):
    dates = []
    cursor = datetime.now()
    for _ in range(count * 4):
        candidate = _next_delivery_dt(route, cursor)
        if not candidate:
            break
        if not dates or candidate.date() != dates[-1].date():
            dates.append(candidate)
        cursor = candidate + timedelta(minutes=1)
        if len(dates) >= count:
            break
    return dates


def _visible_alerts_query(registry_ids, today):
    if not registry_ids:
        return []
    return (
        BusinessRegistryAlert.query
        .filter(
            BusinessRegistryAlert.registry_id.in_(registry_ids),
            BusinessRegistryAlert.is_active.is_(True),
            or_(BusinessRegistryAlert.end_date.is_(None), BusinessRegistryAlert.end_date >= today),
        )
        .order_by(BusinessRegistryAlert.id.desc())
        .all()
    )


def _phone_contacts(registry):
    phones = []
    seen = set()

    legacy_contacts = (
        BusinessRegistryContact.query
        .filter(
            BusinessRegistryContact.registry_id == registry.id,
            BusinessRegistryContact.contact_type.in_(("phone", "mobile")),
        )
        .order_by(BusinessRegistryContact.is_primary.desc(), BusinessRegistryContact.id.asc())
        .all()
    )
    for contact in legacy_contacts:
        if contact.contact_type in {"phone", "mobile"} and contact.value not in seen:
            phones.append({
                "id": f"legacy:{contact.id}",
                "source": "legacy",
                "contact_id": contact.id,
                "label": contact.label or contact.contact_type,
                "type": contact.contact_type,
                "value": contact.value,
                "display_name": "",
            })
            seen.add(contact.value)

    linked_points = (
        db.session.query(BusinessRegistryContactLink, RegistryContact, RegistryContactPoint)
        .join(RegistryContact, RegistryContact.id == BusinessRegistryContactLink.contact_id)
        .join(RegistryContactPoint, RegistryContactPoint.contact_id == RegistryContact.id)
        .filter(
            BusinessRegistryContactLink.registry_id == registry.id,
            BusinessRegistryContactLink.is_active.is_(True),
            RegistryContact.is_active.is_(True),
            RegistryContactPoint.contact_type.in_(("phone", "mobile")),
        )
        .order_by(BusinessRegistryContactLink.is_primary.desc(), RegistryContactPoint.is_primary.desc(), RegistryContactPoint.id.asc())
        .all()
    )
    for link, contact, point in linked_points:
        if point.value in seen:
            continue
        label_parts = [contact.display_name, point.label or point.contact_type]
        phones.append({
            "id": f"linked:{point.id}",
            "source": "linked",
            "contact_id": contact.id,
            "point_id": point.id,
            "label": point.label or point.contact_type,
            "type": point.contact_type,
            "value": point.value,
            "display_name": contact.display_name,
            "full_label": " - ".join(x for x in label_parts if x),
        })
        seen.add(point.value)
    return phones


def _status_reaction(status_code, fallback):
    status = OrderStatus.query.filter_by(code=status_code).first()
    reaction = (status.slack_reaction if status else "") or fallback
    return SlackAPI._norm_reaction_name(reaction)


def _ensure_slack_order(entry, status_code=None):
    order = None
    if entry.slack_channel_id and entry.slack_thread_ts:
        order = (
            SlackOrder.query
            .filter_by(slack_channel_id=entry.slack_channel_id, slack_thread_ts=entry.slack_thread_ts)
            .order_by(SlackOrder.id.desc())
            .first()
        )
    if order:
        if status_code and order.status != status_code:
            old_status = order.status
            order.status = status_code
            db.session.add(SlackOrderEvent(
                order_id=order.id,
                type="status_change",
                payload={"from": old_status, "to": status_code, "via": "route_order_board"},
            ))
        return order

    if not entry.slack_channel_id or not entry.slack_message_ts:
        return None

    registry = entry.registry
    order = SlackOrder(
        route_id=entry.route_id,
        slack_channel_id=entry.slack_channel_id,
        customer_display=_label_registry(registry),
        customer_key=registry.source_code or str(registry.id),
        order_date=(entry.sent_at or datetime.utcnow()).date(),
        planned_delivery_at=entry.planned_delivery_at,
        status=status_code or "acquisito",
        raw_text=_format_slack_message(registry, entry),
        slack_message_ts=entry.slack_message_ts,
        slack_thread_ts=entry.slack_thread_ts or entry.slack_message_ts,
        has_issues=False,
    )
    db.session.add(order)
    db.session.flush()
    db.session.add(SlackOrderEvent(
        order_id=order.id,
        type="created",
        payload={"via": "route_order_board", "board_entry_id": entry.id},
    ))
    return order


def _set_list_done_reaction(entry, enabled):
    if not entry.slack_channel_id or not entry.slack_message_ts:
        return
    api = SlackAPI(SlackAPIConfig(bot_token=current_app.config.get("SLACK_BOT_TOKEN", "") or ""))
    reaction = _status_reaction("listato", "white_check_mark")
    if enabled:
        api.add_reaction(entry.slack_channel_id, entry.slack_message_ts, reaction)
    else:
        api.remove_reaction(entry.slack_channel_id, entry.slack_message_ts, reaction)


def _entry_for_customer(entries_by_registry, registry_id, board_date):
    customer_entries = entries_by_registry.get(registry_id, [])
    for entry in customer_entries:
        if entry.board_date == board_date:
            return entry
    for entry in customer_entries:
        if entry.planned_delivery_at and entry.planned_delivery_at.date() > board_date:
            return entry
    return None


def _entry_to_dict(entry):
    return entry.to_dict() if entry else {
        "id": None,
        "status": "da_chiamare",
        "order_note": "",
        "list_done": False,
        "planned_delivery_at": None,
        "slack_message_ts": None,
        "sent_at": None,
    }


def _format_slack_message(registry, entry):
    lines = [f"*{_label_registry(registry)}*"]
    note = (entry.order_note or "").strip()
    if note:
        lines.append(note)
    if entry.planned_delivery_at:
        lines.append(f"Consegna: {entry.planned_delivery_at.strftime('%d/%m/%Y')}")
    return "\n".join(lines)


@route_orders_bp.get("/board")
@login_required
@role_required(30)
def board_page():
    return render_template("route_orders/board.html", statuses=BOARD_STATUSES)


@route_orders_bp.get("/api/board")
@login_required
@role_required(30)
def api_board():
    route_id = request.args.get("route_id", type=int)
    routes = DeliveryRoute.query.filter_by(is_active=True).order_by(DeliveryRoute.name.asc()).all()
    selected_route = DeliveryRoute.query.filter_by(id=route_id, is_active=True).first() if route_id else (routes[0] if routes else None)
    if not selected_route:
        return jsonify({"ok": True, "routes": [], "customers": [], "statuses": BOARD_STATUSES})

    next_delivery = _next_delivery_dt(selected_route)
    board_date = next_delivery.date()
    customers = (
        BusinessRegistry.query
        .join(DeliveryRouteCustomer, DeliveryRouteCustomer.registry_id == BusinessRegistry.id)
        .filter(
            DeliveryRouteCustomer.route_id == selected_route.id,
            DeliveryRouteCustomer.is_active.is_(True),
            BusinessRegistry.kind == "customer",
            BusinessRegistry.is_active.is_(True),
        )
        .order_by(DeliveryRouteCustomer.sort_order.asc(), BusinessRegistry.display_name.asc(), BusinessRegistry.id.asc())
        .all()
    )
    registry_ids = [customer.id for customer in customers]
    entries = (
        RouteOrderBoardEntry.query
        .filter(
            RouteOrderBoardEntry.route_id == selected_route.id,
            RouteOrderBoardEntry.registry_id.in_(registry_ids) if registry_ids else False,
            or_(
                RouteOrderBoardEntry.board_date == board_date,
                RouteOrderBoardEntry.planned_delivery_at > datetime.combine(board_date, time.max),
            ),
        )
        .order_by(RouteOrderBoardEntry.board_date.desc(), RouteOrderBoardEntry.id.desc())
        .all()
    )
    entries_by_registry = {}
    for entry in entries:
        entries_by_registry.setdefault(entry.registry_id, []).append(entry)

    alerts_by_registry = {}
    for alert in _visible_alerts_query(registry_ids, date.today()):
        alerts_by_registry.setdefault(alert.registry_id, []).append(alert)

    rows = []
    for customer in customers:
        entry = _entry_for_customer(entries_by_registry, customer.id, board_date)
        rows.append({
            "id": customer.id,
            "display": _label_registry(customer),
            "source_code": customer.source_code,
            "city": customer.city,
            "phones": _phone_contacts(customer),
            "alerts": [alert.to_dict() for alert in alerts_by_registry.get(customer.id, [])],
            "entry": _entry_to_dict(entry),
        })

    return jsonify({
        "ok": True,
        "routes": [_route_to_dict(route) for route in routes],
        "route": _route_to_dict(selected_route),
        "next_delivery_at": next_delivery.isoformat(),
        "upcoming_delivery_dates": [value.isoformat() for value in _upcoming_delivery_dates(selected_route)],
        "statuses": BOARD_STATUSES,
        "customers": rows,
    })


@route_orders_bp.post("/api/entries")
@login_required
@role_required(30)
def api_save_entry():
    data = request.get_json(silent=True) or {}
    route = DeliveryRoute.query.filter_by(id=data.get("route_id"), is_active=True).first()
    registry = BusinessRegistry.query.filter_by(id=data.get("registry_id"), kind="customer", is_active=True).first()
    if not route or not registry:
        return jsonify({"ok": False, "error": "Giro o cliente non valido"}), 404

    board_delivery = _next_delivery_dt(route)
    board_date = _parse_date(data.get("board_date")) or board_delivery.date()
    planned_delivery_at = _parse_datetime(data.get("planned_delivery_at"), route.default_time) or board_delivery
    entry = None
    entry_id = data.get("entry_id")
    if entry_id:
        entry = RouteOrderBoardEntry.query.filter_by(id=entry_id, route_id=route.id, registry_id=registry.id).first()
    if not entry:
        entry = RouteOrderBoardEntry.query.filter_by(route_id=route.id, registry_id=registry.id, board_date=board_date).first()
    if not entry:
        entry = RouteOrderBoardEntry(
            route_id=route.id,
            registry_id=registry.id,
            board_date=board_date,
            planned_delivery_at=planned_delivery_at,
        )
        db.session.add(entry)

    if "status" in data:
        valid_statuses = {status["code"] for status in BOARD_STATUSES}
        entry.status = data.get("status") if data.get("status") in valid_statuses else "da_chiamare"
    if "order_note" in data:
        entry.order_note = (data.get("order_note") or "").strip() or None
    if "list_done" in data:
        entry.list_done = bool(data.get("list_done"))
    if "planned_delivery_at" in data:
        entry.planned_delivery_at = planned_delivery_at

    db.session.flush()
    if entry.slack_channel_id and entry.slack_message_ts and "list_done" in data:
        try:
            _set_list_done_reaction(entry, entry.list_done)
            if entry.list_done:
                _ensure_slack_order(entry, "listato")
        except Exception as exc:
            db.session.rollback()
            return jsonify({"ok": False, "error": f"Reaction lista fatta non applicata: {exc}"}), 502
    db.session.commit()
    return jsonify({"ok": True, "entry": entry.to_dict()})


@route_orders_bp.post("/api/routes/<int:route_id>/delivery-date")
@login_required
@role_required(30)
def api_route_delivery_date(route_id):
    route = DeliveryRoute.query.filter_by(id=route_id, is_active=True).first()
    if not route:
        return jsonify({"ok": False, "error": "Giro non valido"}), 404
    data = request.get_json(silent=True) or {}
    source_date = _parse_date(data.get("source_date"))
    target_dt = _parse_datetime(data.get("target_delivery_at"), route.default_time)
    if not source_date or not target_dt:
        return jsonify({"ok": False, "error": "Data consegna non valida"}), 400

    rule = (
        DeliveryScheduleRule.query
        .filter_by(route_id=route.id, scope="once", source_date=source_date)
        .order_by(DeliveryScheduleRule.id.desc())
        .first()
    )
    if not rule:
        rule = DeliveryScheduleRule(
            route_id=route.id,
            scope="once",
            source_date=source_date,
            frequency="weekly",
        )
        db.session.add(rule)
    rule.target_date = target_dt.date()
    rule.target_time = target_dt.time()
    rule.is_active = True
    db.session.commit()
    return jsonify({"ok": True, "next_delivery_at": _next_delivery_dt(route).isoformat()})


@route_orders_bp.post("/api/entries/<int:entry_id>/send-slack")
@login_required
@role_required(30)
def api_send_slack(entry_id):
    entry = RouteOrderBoardEntry.query.get_or_404(entry_id)
    registry = entry.registry
    route = entry.route
    if not route.slack_channel_id or route.slack_channel_id.startswith("manual-"):
        return jsonify({"ok": False, "error": "Il giro non ha un canale Slack valido associato"}), 400
    bot_token = current_app.config.get("SLACK_BOT_TOKEN", "") or ""
    if not bot_token:
        return jsonify({"ok": False, "error": "SLACK_BOT_TOKEN mancante"}), 503

    api = SlackAPI(SlackAPIConfig(bot_token=bot_token))
    response = api.post_message(route.slack_channel_id, _format_slack_message(registry, entry))
    ts = response.get("ts")
    entry.slack_channel_id = route.slack_channel_id
    entry.slack_message_ts = ts
    entry.slack_thread_ts = ts
    entry.sent_at = datetime.utcnow()
    target_status = "listato" if entry.list_done else "acquisito"
    if entry.list_done and ts:
        try:
            api.add_reaction(route.slack_channel_id, ts, _status_reaction("listato", "white_check_mark"))
        except Exception as exc:
            db.session.rollback()
            return jsonify({"ok": False, "error": f"Ordine inviato, ma reaction lista fatta non applicata: {exc}"}), 502
    _ensure_slack_order(entry, target_status)
    db.session.commit()
    return jsonify({"ok": True, "entry": entry.to_dict()})


@route_orders_bp.post("/api/entries/<int:entry_id>/cancel")
@login_required
@role_required(30)
def api_cancel_order(entry_id):
    entry = RouteOrderBoardEntry.query.get_or_404(entry_id)
    if not entry.slack_channel_id or not entry.slack_message_ts:
        entry.order_note = None
        entry.list_done = False
        entry.status = "da_chiamare"
        db.session.commit()
        return jsonify({"ok": True, "entry": entry.to_dict()})

    bot_token = current_app.config.get("SLACK_BOT_TOKEN", "") or ""
    if not bot_token:
        return jsonify({"ok": False, "error": "SLACK_BOT_TOKEN mancante"}), 503
    api = SlackAPI(SlackAPIConfig(bot_token=bot_token))
    try:
        if entry.list_done:
            api.remove_reaction(entry.slack_channel_id, entry.slack_message_ts, _status_reaction("listato", "white_check_mark"))
        api.add_reaction(entry.slack_channel_id, entry.slack_message_ts, _status_reaction("annullato", "x"))
    except Exception as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": f"Reaction annullamento non applicata: {exc}"}), 502

    entry.order_note = None
    entry.list_done = False
    entry.status = "da_chiamare"
    order = _ensure_slack_order(entry, "annullato")
    if order and not order.closed_at:
        order.closed_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True, "entry": entry.to_dict()})


@route_orders_bp.get("/api/registries/<int:registry_id>/phone-contacts")
@login_required
@role_required(30)
def api_registry_phone_contacts(registry_id):
    registry = BusinessRegistry.query.filter_by(id=registry_id, kind="customer", is_active=True).first()
    if not registry:
        return jsonify({"ok": False, "error": "Cliente non valido"}), 404
    return jsonify({"ok": True, "contacts": _phone_contacts(registry)})


@route_orders_bp.post("/api/registries/<int:registry_id>/phone-contacts")
@login_required
@role_required(30)
def api_registry_phone_contact_create(registry_id):
    registry = BusinessRegistry.query.filter_by(id=registry_id, kind="customer", is_active=True).first()
    if not registry:
        return jsonify({"ok": False, "error": "Cliente non valido"}), 404
    data = request.get_json(silent=True) or {}
    display_name = (data.get("display_name") or "").strip()
    value = (data.get("value") or "").strip()
    contact_type = (data.get("type") or "phone").strip()
    label = (data.get("label") or "").strip() or contact_type
    if contact_type not in {"phone", "mobile"} or not value:
        return jsonify({"ok": False, "error": "Tipo o numero non valido"}), 400
    contact = RegistryContact(display_name=display_name or _label_registry(registry))
    point = RegistryContactPoint(contact=contact, contact_type=contact_type, value=value, label=label, is_primary=True)
    link = BusinessRegistryContactLink(registry=registry, contact=contact, is_primary=False, role=label)
    db.session.add_all([contact, point, link])
    db.session.commit()
    return jsonify({"ok": True, "contacts": _phone_contacts(registry)})


@route_orders_bp.put("/api/phone-contacts/<source>/<int:item_id>")
@login_required
@role_required(30)
def api_registry_phone_contact_update(source, item_id):
    data = request.get_json(silent=True) or {}
    value = (data.get("value") or "").strip()
    contact_type = (data.get("type") or "phone").strip()
    label = (data.get("label") or "").strip() or contact_type
    display_name = (data.get("display_name") or "").strip()
    if contact_type not in {"phone", "mobile"} or not value:
        return jsonify({"ok": False, "error": "Tipo o numero non valido"}), 400
    if source == "legacy":
        contact = BusinessRegistryContact.query.get_or_404(item_id)
        contact.contact_type = contact_type
        contact.value = value
        contact.label = label
        registry = contact.registry
    elif source == "linked":
        point = RegistryContactPoint.query.get_or_404(item_id)
        point.contact_type = contact_type
        point.value = value
        point.label = label
        if display_name and point.contact:
            point.contact.display_name = display_name
        registry = point.contact.registry_links[0].registry if point.contact and point.contact.registry_links else None
    else:
        return jsonify({"ok": False, "error": "Origine contatto non valida"}), 400
    db.session.commit()
    return jsonify({"ok": True, "contacts": _phone_contacts(registry) if registry else []})


@route_orders_bp.delete("/api/phone-contacts/<source>/<int:item_id>")
@login_required
@role_required(30)
def api_registry_phone_contact_delete(source, item_id):
    registry = None
    if source == "legacy":
        contact = BusinessRegistryContact.query.get_or_404(item_id)
        registry = contact.registry
        db.session.delete(contact)
    elif source == "linked":
        point = RegistryContactPoint.query.get_or_404(item_id)
        contact = point.contact
        registry = contact.registry_links[0].registry if contact and contact.registry_links else None
        db.session.delete(point)
        if contact and not contact.points:
            for link in contact.registry_links:
                link.is_active = False
    else:
        return jsonify({"ok": False, "error": "Origine contatto non valida"}), 400
    db.session.commit()
    return jsonify({"ok": True, "contacts": _phone_contacts(registry) if registry else []})


@route_orders_bp.get("/api/registries/<int:registry_id>/alerts")
@login_required
@role_required(30)
def api_registry_alerts(registry_id):
    alerts = (
        BusinessRegistryAlert.query
        .filter_by(registry_id=registry_id, is_active=True)
        .order_by(BusinessRegistryAlert.id.desc())
        .all()
    )
    return jsonify({"ok": True, "alerts": [alert.to_dict() for alert in alerts]})


@route_orders_bp.post("/api/registries/<int:registry_id>/alerts")
@login_required
@role_required(30)
def api_registry_alert_create(registry_id):
    registry = BusinessRegistry.query.filter_by(id=registry_id, kind="customer", is_active=True).first()
    if not registry:
        return jsonify({"ok": False, "error": "Cliente non valido"}), 404
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"ok": False, "error": "Messaggio avviso obbligatorio"}), 400
    alert = BusinessRegistryAlert(
        registry_id=registry.id,
        message=message[:255],
        start_date=_parse_date(data.get("start_date")),
        end_date=_parse_date(data.get("end_date")),
    )
    db.session.add(alert)
    db.session.commit()
    return jsonify({"ok": True, "alert": alert.to_dict()})


@route_orders_bp.delete("/api/alerts/<int:alert_id>")
@login_required
@role_required(30)
def api_registry_alert_delete(alert_id):
    alert = BusinessRegistryAlert.query.get_or_404(alert_id)
    alert.is_active = False
    db.session.commit()
    return jsonify({"ok": True})
