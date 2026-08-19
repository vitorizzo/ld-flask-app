import logging
import mimetypes
import os
from datetime import date, datetime, time, timedelta

from flask import Blueprint, current_app, jsonify, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import or_
from sqlalchemy.orm import joinedload
from werkzeug.utils import secure_filename

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
from tools.slack_processor import SlackProcessor
from tools.push_notifications import send_order_push_to_staff
from tools.log_utils import get_logger


route_orders_bp = Blueprint("route_orders", __name__)
logger = get_logger("route_orders", level=logging.DEBUG)

BOARD_STATUSES = [
    {"code": "da_chiamare", "label": "Da chiamare"},
    {"code": "ordine_fatto", "label": "Ordine fatto"},
    {"code": "richiamare", "label": "Richiamare"},
    {"code": "salta_giro", "label": "Salta il giro"},
    {"code": "chiama_lui", "label": "Chiama lui"},
    {"code": "non_risponde", "label": "Non risponde"},
    {"code": "annullato", "label": "Ordine annullato"},
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
    _reset_documents_for_customer_orders(
        entry.slack_channel_id,
        order.customer_key,
        exclude_order_id=order.id,
        via="route_order_board",
        reason="new_route_order_same_customer",
    )
    db.session.add(SlackOrderEvent(
        order_id=order.id,
        type="created",
        payload={"via": "route_order_board", "board_entry_id": entry.id},
    ))
    return order


def _set_list_done_reaction(entry, enabled):
    if not entry.slack_channel_id or not entry.slack_message_ts:
        raise RuntimeError("channel/ts Slack mancanti")
    reaction = _status_reaction("listato", "white_check_mark")
    if enabled:
        SlackProcessor().execute_actions(
            [{"action_type": "addReaction", "config_json": {"reaction": reaction}}],
            {"channel": entry.slack_channel_id, "ts": entry.slack_message_ts},
        )
    else:
        api = SlackAPI(SlackAPIConfig(bot_token=current_app.config.get("SLACK_BOT_TOKEN", "") or ""))
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


def _upload_folder():
    folder = os.path.join(current_app.static_folder, "uploads", "route_orders", datetime.utcnow().strftime("%Y%m%d"))
    os.makedirs(folder, exist_ok=True)
    return folder


def _static_rel_path(abs_path):
    return os.path.relpath(abs_path, current_app.static_folder).replace(os.sep, "/")


def _public_upload_path(abs_path):
    return f"/static/{_static_rel_path(abs_path)}"


def _save_uploaded_files(files):
    saved = []
    for file in files:
        if not file:
            continue
        raw_filename = file.filename or f"allegato-{len(saved) + 1}{mimetypes.guess_extension(file.mimetype or '') or ''}"
        filename = secure_filename(raw_filename) or f"allegato-{len(saved) + 1}"
        target = os.path.join(_upload_folder(), f"{datetime.utcnow().strftime('%H%M%S%f')}_{filename}")
        file.save(target)
        saved.append({
            "id": f"route-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}-{len(saved) + 1}",
            "source": "route_board",
            "name": filename,
            "title": filename,
            "filename": filename,
            "mimetype": file.mimetype,
            "content_type": file.mimetype,
            "filetype": os.path.splitext(filename)[1].lstrip(".").lower(),
            "size": os.path.getsize(target),
            "is_image": (file.mimetype or "").startswith("image/"),
            "url": _public_upload_path(target),
            "static_path": _static_rel_path(target),
        })
    return saved


def _files_from_request():
    files = []
    for _, values in request.files.lists():
        files.extend(values)
    return files


def _attachment_abs_path(file_info):
    rel = (file_info.get("static_path") or "").strip().replace("\\", "/")
    if not rel and (file_info.get("url") or "").startswith("/static/"):
        rel = file_info["url"][len("/static/"):]
    if (
        not rel.startswith("uploads/route_orders/")
        and not rel.startswith("uploads/shared_orders/")
        and not rel.startswith("uploads/customer_orders/")
    ):
        return None
    candidate = os.path.abspath(os.path.join(current_app.static_folder, rel))
    static_root = os.path.abspath(current_app.static_folder)
    if not candidate.startswith(static_root + os.sep) or not os.path.exists(candidate):
        return None
    return candidate


def _upload_attachments_to_slack(api, channel_id, thread_ts, attachments):
    for file_info in attachments or []:
        abs_path = _attachment_abs_path(file_info)
        if not abs_path:
            raise RuntimeError(f"allegato non trovato: {file_info.get('filename') or file_info.get('name') or 'file'}")
        filename = file_info.get("filename") or file_info.get("name") or os.path.basename(abs_path)
        api.upload_file(channel_id, abs_path, title=filename, filename=filename, thread_ts=thread_ts)


def _add_attachment_event(order, attachments, via="route_order_board"):
    if not order or not attachments:
        return
    db.session.add(SlackOrderEvent(
        order_id=order.id,
        type="note",
        payload={
            "text": "Allegati ordine",
            "attachments": attachments,
            "via": via,
        },
    ))


def _reset_document_issued(order, *, via, reason):
    if not order or not getattr(order, "document_issued", False):
        return
    order.document_issued = False
    order.document_issued_at = None
    db.session.add(SlackOrderEvent(
        order_id=order.id,
        type="note",
        payload={
            "text": "Documento riportato da emettere per nuova aggiunta ordine",
            "via": via,
            "reason": reason,
        },
    ))


def _reset_documents_for_customer_orders(channel_id, customer_key, *, exclude_order_id=None, via, reason):
    if not channel_id or not customer_key:
        return
    query = SlackOrder.query.filter(
        SlackOrder.slack_channel_id == channel_id,
        SlackOrder.customer_key == customer_key,
        SlackOrder.document_issued.is_(True),
    )
    if exclude_order_id:
        query = query.filter(SlackOrder.id != exclude_order_id)
    for order in query.all():
        _reset_document_issued(order, via=via, reason=reason)


def _board_status_for_order(order):
    status = (order.status or "").strip()
    if status in {"acquisito", "listato", "preparato", "controllato", "in_consegna", "inconsegna", "evaso"}:
        return "ordine_fatto"
    if status == "annullato":
        return "annullato"
    if status in {item["code"] for item in BOARD_STATUSES}:
        return "ordine_fatto"
    return status or "ordine_fatto"


def _order_status_label(status_code):
    labels = {
        "acquisito": "Acquisito",
        "listato": "Listato",
        "preparato": "Preparato",
        "controllato": "Controllato",
        "in_consegna": "In consegna",
        "inconsegna": "In consegna",
        "evaso": "Evaso",
        "annullato": "Annullato",
        "cancellato": "Cancellato",
    }
    status = OrderStatus.query.filter_by(code=status_code).first()
    return status.label if status else labels.get((status_code or "").strip(), status_code or "")


def _order_to_dict(order):
    return {
        "id": order.id,
        "route_id": order.route_id,
        "customer_display": order.customer_display,
        "customer_key": order.customer_key,
        "order_date": order.order_date.isoformat() if order.order_date else None,
        "planned_delivery_at": order.planned_delivery_at.isoformat() if order.planned_delivery_at else None,
        "status": order.status,
        "status_label": _order_status_label(order.status),
        "board_status": _board_status_for_order(order),
        "raw_text": order.raw_text or "",
        "document_issued": bool(getattr(order, "document_issued", False)),
        "document_issued_at": order.document_issued_at.isoformat() if getattr(order, "document_issued_at", None) else None,
        "slack_channel_id": order.slack_channel_id,
        "slack_message_ts": order.slack_message_ts,
    }


def _registry_for_order(order):
    key = str(order.customer_key or "").strip()
    registry = None
    if key:
        registry = BusinessRegistry.query.filter_by(kind="customer", source_code=key, is_active=True).first()
        if not registry and key.isdigit():
            registry = BusinessRegistry.query.filter_by(id=int(key), kind="customer", is_active=True).first()
    if not registry:
        registry = (
            BusinessRegistry.query
            .filter(
                BusinessRegistry.kind == "customer",
                BusinessRegistry.is_active.is_(True),
                or_(
                    BusinessRegistry.display_name == order.customer_display,
                    BusinessRegistry.legal_name == order.customer_display,
                ),
            )
            .order_by(BusinessRegistry.id.asc())
            .first()
        )
    return registry


def _route_orders_for_board(route_id, board_date):
    return (
        SlackOrder.query
        .filter(
            SlackOrder.route_id == route_id,
            or_(
                SlackOrder.order_date >= board_date,
                SlackOrder.planned_delivery_at >= datetime.combine(board_date, time.min),
            ),
            SlackOrder.status.notin_(["cancellato"]),
        )
        .order_by(SlackOrder.created_at.asc(), SlackOrder.id.asc())
        .all()
    )


def _orders_for_customers(route_id, registry_ids, board_date):
    if not registry_ids:
        return {}
    registry_id_set = set(registry_ids)
    orders = _route_orders_for_board(route_id, board_date)
    out = {}
    for order in orders:
        registry = _registry_for_order(order)
        if registry and registry.id in registry_id_set:
            out.setdefault(registry.id, []).append(_order_to_dict(order))
    return out


def _unmatched_orders_for_customers(route_id, registry_ids, board_date):
    if not registry_ids:
        return []
    registry_id_set = set(registry_ids)
    orders = _route_orders_for_board(route_id, board_date)
    unmatched = []
    for order in orders:
        registry = _registry_for_order(order)
        if registry and registry.id in registry_id_set:
            continue
        unmatched.append(_order_to_dict(order))
    return unmatched


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


def _format_direct_message(registry, note, planned_delivery_at=None):
    lines = [f"*{_label_registry(registry)}*"]
    if note:
        lines.append(note.strip())
    if planned_delivery_at:
        lines.append(f"Consegna: {planned_delivery_at.strftime('%d/%m/%Y')}")
    return "\n".join(lines)


def publish_customer_order(order):
    """Pubblica una CustomerOrder una sola volta sulla bacheca e su Slack."""
    if order.slack_order_id:
        return order.slack_order

    registry = order.registry
    route = order.route
    channel_id = (route.slack_channel_id or "").strip() if route else ""
    if not registry or not route or not channel_id:
        raise RuntimeError("Il cliente non e' associato a un giro con canale Slack configurato")

    planned_delivery_at = None
    option = order.delivery_option
    option_value = (order.delivery_option_value or "").strip()
    if option and option.code == "data_consegna" and option_value:
        try:
            planned_delivery_at = _parse_datetime(option_value, route.default_time or time(9, 0))
        except (TypeError, ValueError):
            planned_delivery_at = None
    planned_delivery_at = planned_delivery_at or _next_delivery_dt(route)
    if not planned_delivery_at:
        raise RuntimeError("Data del prossimo giro non determinabile")

    note_lines = [(order.order_text or "").strip()]
    if option:
        delivery_label = option.label
        if option_value:
            delivery_label = f"{delivery_label}: {option_value}"
        note_lines.append(f"Richiesta consegna: {delivery_label}")
    note = "\n".join(line for line in note_lines if line)
    message_text = _format_direct_message(registry, note, planned_delivery_at)

    bot_token = current_app.config.get("SLACK_BOT_TOKEN", "") or ""
    if not bot_token:
        raise RuntimeError("SLACK_BOT_TOKEN mancante")
    api = SlackAPI(SlackAPIConfig(bot_token=bot_token))
    response = api.post_message(
        channel_id,
        message_text,
        client_msg_id=f"ldapp-customer-order-{order.id}",
    )
    ts = response.get("ts") or (response.get("message") or {}).get("ts")
    if not ts:
        raise RuntimeError("Slack non ha restituito il timestamp del messaggio")

    attachments = order.attachments or []
    _upload_attachments_to_slack(api, channel_id, ts, attachments)

    slack_order = SlackOrder(
        route_id=route.id,
        slack_channel_id=channel_id,
        customer_display=_label_registry(registry),
        customer_key=registry.source_code or str(registry.id),
        order_date=datetime.utcnow().date(),
        planned_delivery_at=planned_delivery_at,
        status="acquisito",
        raw_text=message_text,
        slack_message_ts=ts,
        slack_thread_ts=ts,
        has_issues=False,
    )
    db.session.add(slack_order)
    db.session.flush()
    _reset_documents_for_customer_orders(
        channel_id,
        slack_order.customer_key,
        exclude_order_id=slack_order.id,
        via="customer_horeca_app",
        reason="new_customer_horeca_order",
    )
    db.session.add(SlackOrderEvent(
        order_id=slack_order.id,
        type="created",
        payload={
            "via": "customer_horeca_app",
            "customer_order_id": order.id,
            "attachments": attachments,
        },
    ))

    board_date = planned_delivery_at.date()
    entry = RouteOrderBoardEntry.query.filter_by(
        route_id=route.id,
        registry_id=registry.id,
        board_date=board_date,
    ).first()
    if not entry:
        entry = RouteOrderBoardEntry(
            route_id=route.id,
            registry_id=registry.id,
            board_date=board_date,
            planned_delivery_at=planned_delivery_at,
        )
        db.session.add(entry)
    entry.status = "ordine_fatto"
    entry.order_note = note or entry.order_note
    entry.order_attachments = attachments
    entry.slack_channel_id = channel_id
    entry.slack_message_ts = ts
    entry.slack_thread_ts = ts
    entry.sent_at = datetime.utcnow()
    db.session.flush()

    order.route_board_entry_id = entry.id
    order.slack_order_id = slack_order.id
    order.status = "published"
    return slack_order


@route_orders_bp.get("/board")
@login_required
@role_required(30)
def board_page():
    return render_template("route_orders/board.html", statuses=BOARD_STATUSES)


@route_orders_bp.get("/history")
@login_required
@role_required(30)
def order_history_page():
    today = date.today()
    default_from = today - timedelta(days=30)

    def query_date(name, fallback):
        raw = (request.args.get(name) or "").strip()
        if not raw:
            return fallback
        try:
            return date.fromisoformat(raw)
        except ValueError:
            return fallback

    date_from = query_date("date_from", default_from)
    date_to = query_date("date_to", today)
    if date_from > date_to:
        date_from, date_to = date_to, date_from

    search = (request.args.get("q") or "").strip()[:160]
    route_id = request.args.get("route_id", type=int)
    status = (request.args.get("status") or "").strip()[:40]
    origin = (request.args.get("origin") or "all").strip()
    if origin not in {"all", "console", "slack"}:
        origin = "all"
    posting = (request.args.get("posting") or "all").strip()
    if posting not in {"all", "posted", "pending"}:
        posting = "all"
    page = max(request.args.get("page", default=1, type=int) or 1, 1)
    per_page = 50
    fetch_limit = 2001
    rows = []
    board_status_labels = {item["code"]: item["label"] for item in BOARD_STATUSES}
    operational_status_labels = {
        "acquisito": "Acquisito",
        "listato": "Listato",
        "preparato": "Preparato",
        "controllato": "Controllato",
        "in_consegna": "In consegna",
        "inconsegna": "In consegna",
        "evaso": "Evaso",
        "annullato": "Annullato",
        "cancellato": "Cancellato",
    }
    operational_status_labels.update({
        item.code: item.label
        for item in OrderStatus.query.order_by(OrderStatus.order_index.asc(), OrderStatus.id.asc()).all()
    })
    status_options = {**board_status_labels, **operational_status_labels}

    entries = []
    if origin in {"all", "console"}:
        entry_date = db.func.coalesce(
            db.func.date(RouteOrderBoardEntry.sent_at),
            RouteOrderBoardEntry.board_date,
        )
        entry_query = (
            RouteOrderBoardEntry.query
            .options(
                joinedload(RouteOrderBoardEntry.route),
                joinedload(RouteOrderBoardEntry.registry),
            )
            .filter(entry_date >= date_from, entry_date <= date_to)
        )
        if route_id:
            entry_query = entry_query.filter(RouteOrderBoardEntry.route_id == route_id)
        if posting == "posted":
            entry_query = entry_query.filter(RouteOrderBoardEntry.sent_at.isnot(None))
        elif posting == "pending":
            entry_query = entry_query.filter(RouteOrderBoardEntry.sent_at.is_(None))
        if search:
            like = f"%{search}%"
            entry_query = entry_query.join(RouteOrderBoardEntry.registry).filter(or_(
                BusinessRegistry.display_name.ilike(like),
                BusinessRegistry.legal_name.ilike(like),
                BusinessRegistry.source_code.ilike(like),
                RouteOrderBoardEntry.order_note.ilike(like),
            ))
        entries = (
            entry_query
            .order_by(entry_date.desc(), RouteOrderBoardEntry.id.desc())
            .limit(fetch_limit)
            .all()
        )

    linked_orders = {}
    linked_channels = {entry.slack_channel_id for entry in entries if entry.slack_channel_id}
    linked_timestamps = {entry.slack_message_ts for entry in entries if entry.slack_message_ts}
    if linked_channels and linked_timestamps:
        candidates = SlackOrder.query.filter(
            SlackOrder.slack_channel_id.in_(linked_channels),
            SlackOrder.slack_message_ts.in_(linked_timestamps),
        ).all()
        linked_orders = {
            (order.slack_channel_id, order.slack_message_ts): order
            for order in candidates
        }

    for entry in entries:
        registry = entry.registry
        linked_order = linked_orders.get((entry.slack_channel_id, entry.slack_message_ts))
        effective_status = linked_order.status if linked_order else entry.status
        if status and status not in {entry.status, effective_status}:
            continue
        effective_date = (entry.sent_at.date() if entry.sent_at else entry.board_date)
        rows.append({
            "kind": "console",
            "id": entry.id,
            "date": effective_date,
            "sort_at": entry.sent_at or datetime.combine(effective_date, time.min),
            "customer": _label_registry(registry) if registry else f"Cliente {entry.registry_id}",
            "customer_key": registry.source_code if registry else "",
            "route": entry.route.name if entry.route else "",
            "status": effective_status,
            "status_label": status_options.get(effective_status, effective_status),
            "text": entry.order_note or (linked_order.raw_text if linked_order else "") or "",
            "planned_delivery_at": entry.planned_delivery_at,
            "board_date": entry.board_date,
            "sent_at": entry.sent_at,
            "posted": bool(entry.sent_at and entry.slack_message_ts),
            "slack_order_id": linked_order.id if linked_order else None,
            "slack_message_ts": entry.slack_message_ts,
            "source_label": "Console",
        })

    slack_orders = []
    if origin in {"all", "slack"} and posting != "pending":
        linked_entry_exists = db.session.query(RouteOrderBoardEntry.id).filter(
            RouteOrderBoardEntry.slack_channel_id == SlackOrder.slack_channel_id,
            RouteOrderBoardEntry.slack_message_ts == SlackOrder.slack_message_ts,
        ).exists()
        slack_query = (
            SlackOrder.query
            .options(joinedload(SlackOrder.route))
            .filter(
                SlackOrder.order_date >= date_from,
                SlackOrder.order_date <= date_to,
                ~linked_entry_exists,
            )
        )
        if route_id:
            slack_query = slack_query.filter(SlackOrder.route_id == route_id)
        if status:
            slack_query = slack_query.filter(SlackOrder.status == status)
        if search:
            like = f"%{search}%"
            slack_query = slack_query.filter(or_(
                SlackOrder.customer_display.ilike(like),
                SlackOrder.customer_key.ilike(like),
                SlackOrder.raw_text.ilike(like),
            ))
        slack_orders = (
            slack_query
            .order_by(SlackOrder.order_date.desc(), SlackOrder.created_at.desc(), SlackOrder.id.desc())
            .limit(fetch_limit)
            .all()
        )

    event_origins = {}
    if slack_orders:
        created_events = (
            SlackOrderEvent.query
            .filter(
                SlackOrderEvent.order_id.in_([order.id for order in slack_orders]),
                SlackOrderEvent.type == "created",
            )
            .order_by(SlackOrderEvent.created_at.asc(), SlackOrderEvent.id.asc())
            .all()
        )
        for event in created_events:
            event_origins.setdefault(event.order_id, (event.payload or {}).get("via"))

    source_labels = {
        "route_order_board_direct": "Ordine diretto",
        "customer_horeca_app": "Inserisci ordine",
        "route_order_board": "Console",
    }
    for order in slack_orders:
        via = event_origins.get(order.id)
        rows.append({
            "kind": "slack",
            "id": order.id,
            "date": order.order_date,
            "sort_at": order.created_at or datetime.combine(order.order_date, time.min),
            "customer": order.customer_display,
            "customer_key": order.customer_key,
            "route": order.route.name if order.route else "",
            "status": order.status,
            "status_label": status_options.get(order.status, order.status),
            "text": order.raw_text or "",
            "planned_delivery_at": order.planned_delivery_at,
            "board_date": None,
            "sent_at": order.created_at,
            "posted": True,
            "slack_order_id": order.id,
            "slack_message_ts": order.slack_message_ts,
            "source_label": source_labels.get(via, "Slack / integrazione"),
        })

    rows.sort(key=lambda row: (row["sort_at"], row["id"]), reverse=True)
    total = len(rows)
    pages = max((total + per_page - 1) // per_page, 1)
    page = min(page, pages)
    visible_rows = rows[(page - 1) * per_page:page * per_page]
    truncated = len(entries) >= fetch_limit or len(slack_orders) >= fetch_limit

    routes = DeliveryRoute.query.order_by(DeliveryRoute.name.asc()).all()

    filters = {
        "q": search,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "route_id": route_id or "",
        "status": status,
        "origin": origin,
        "posting": posting,
    }
    return render_template(
        "route_orders/history.html",
        rows=visible_rows,
        total=total,
        page=page,
        pages=pages,
        routes=routes,
        status_options=status_options,
        filters=filters,
        truncated=truncated,
    )


@route_orders_bp.get("/api/board")
@login_required
@role_required(30)
def api_board():
    route_id = request.args.get("route_id", type=int)
    only_with_orders = request.args.get("only_with_orders") in {"1", "true", "yes"}
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
    orders_by_registry = _orders_for_customers(selected_route.id, registry_ids, board_date)
    unmatched_orders = _unmatched_orders_for_customers(selected_route.id, registry_ids, board_date)

    alerts_by_registry = {}
    for alert in _visible_alerts_query(registry_ids, date.today()):
        alerts_by_registry.setdefault(alert.registry_id, []).append(alert)

    rows = []
    for customer in customers:
        entry = _entry_for_customer(entries_by_registry, customer.id, board_date)
        customer_orders = orders_by_registry.get(customer.id, [])
        if only_with_orders and not customer_orders:
            continue
        rows.append({
            "id": customer.id,
            "display": _label_registry(customer),
            "source_code": customer.source_code,
            "city": customer.city,
            "phones": _phone_contacts(customer),
            "alerts": [alert.to_dict() for alert in alerts_by_registry.get(customer.id, [])],
            "entry": _entry_to_dict(entry),
            "orders": customer_orders,
        })

    return jsonify({
        "ok": True,
        "routes": [_route_to_dict(route) for route in routes],
        "route": _route_to_dict(selected_route),
        "next_delivery_at": next_delivery.isoformat(),
        "upcoming_delivery_dates": [value.isoformat() for value in _upcoming_delivery_dates(selected_route)],
        "statuses": BOARD_STATUSES,
        "customers": rows,
        "unmatched_orders": unmatched_orders,
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


@route_orders_bp.get("/api/customers")
@login_required
@role_required(30)
def api_customers():
    q = (request.args.get("q") or "").strip()
    query = BusinessRegistry.query.filter(BusinessRegistry.kind == "customer", BusinessRegistry.is_active.is_(True))
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
    customers = query.order_by(BusinessRegistry.display_name.asc(), BusinessRegistry.id.asc()).limit(40).all()
    return jsonify({
        "ok": True,
        "customers": [{
            "id": customer.id,
            "display": _label_registry(customer),
            "source_code": customer.source_code,
            "city": customer.city,
        } for customer in customers],
    })


@route_orders_bp.post("/api/entries/<int:entry_id>/attachments")
@login_required
@role_required(30)
def api_entry_attachments(entry_id):
    entry = RouteOrderBoardEntry.query.get_or_404(entry_id)
    saved = _save_uploaded_files(_files_from_request())
    if not saved:
        return jsonify({"ok": False, "error": "Nessun file ricevuto"}), 400
    entry.order_attachments = (entry.order_attachments or []) + saved
    db.session.commit()
    return jsonify({"ok": True, "entry": entry.to_dict(), "attachments": entry.order_attachments or []})


@route_orders_bp.post("/api/orders/<int:order_id>/attachments")
@login_required
@role_required(30)
def api_order_attachments(order_id):
    order = SlackOrder.query.get_or_404(order_id)
    saved = _save_uploaded_files(_files_from_request())
    if not saved:
        return jsonify({"ok": False, "error": "Nessun file ricevuto"}), 400
    bot_token = current_app.config.get("SLACK_BOT_TOKEN", "") or ""
    if bot_token and order.slack_channel_id and order.slack_message_ts:
        try:
            _upload_attachments_to_slack(SlackAPI(SlackAPIConfig(bot_token=bot_token)), order.slack_channel_id, order.slack_message_ts, saved)
        except Exception as exc:
            db.session.rollback()
            return jsonify({"ok": False, "error": f"Allegati non caricati su Slack: {exc}"}), 502
    _reset_document_issued(order, via="route_order_board_attachment", reason="attachments_added")
    _add_attachment_event(order, saved, via="route_order_board")
    db.session.commit()
    return jsonify({"ok": True, "order": _order_to_dict(order), "attachments": saved})


@route_orders_bp.post("/api/orders/<int:order_id>/document")
@login_required
@role_required(30)
def api_order_document(order_id):
    order = SlackOrder.query.get_or_404(order_id)
    data = request.get_json(silent=True) or {}
    issued = bool(data.get("document_issued"))
    old_value = bool(getattr(order, "document_issued", False))
    order.document_issued = issued
    order.document_issued_at = datetime.utcnow() if issued else None
    db.session.add(SlackOrderEvent(
        order_id=order.id,
        type="note",
        payload={"text": "Documento emesso" if issued else "Documento da emettere", "via": "route_order_board", "from": old_value, "to": issued},
    ))
    db.session.commit()
    return jsonify({"ok": True, "order": _order_to_dict(order)})


@route_orders_bp.post("/api/orders/<int:order_id>/status")
@login_required
@role_required(30)
def api_order_status(order_id):
    order = SlackOrder.query.get_or_404(order_id)
    data = request.get_json(silent=True) or {}
    requested_status = (data.get("status") or "").strip()
    new_status = requested_status
    if requested_status == "ordine_fatto":
        new_status = "listato" if order.status == "listato" else "acquisito"
    valid_codes = {status["code"] for status in BOARD_STATUSES}
    valid_codes.update(code for code, in db.session.query(OrderStatus.code).all())
    valid_codes.update({"acquisito", "listato", "controllato", "evaso"})
    if requested_status not in valid_codes and new_status not in valid_codes:
        return jsonify({"ok": False, "error": "Stato non valido"}), 400
    old_status = order.status
    if old_status != new_status:
        order.status = new_status
        if new_status == "evaso":
            order.evaded_at = datetime.utcnow()
        if new_status in {"annullato", "cancellato", "evaso"} and not order.closed_at:
            order.closed_at = datetime.utcnow()
        db.session.add(SlackOrderEvent(
            order_id=order.id,
            type="status_change",
            payload={"from": old_status, "to": new_status, "requested": requested_status, "via": "route_order_board"},
        ))
        db.session.commit()
        try:
            SlackProcessor().sync_order_status_reactions(order, old_status_code=old_status, new_status_code=new_status)
        except Exception:
            logger.exception("Sync reaction status failed order_id=%s", order.id)
    return jsonify({"ok": True, "order": _order_to_dict(order)})


@route_orders_bp.post("/api/orders/<int:order_id>/delivery")
@login_required
@role_required(30)
def api_order_delivery(order_id):
    order = SlackOrder.query.get_or_404(order_id)
    data = request.get_json(silent=True) or {}
    target_dt = _parse_datetime(data.get("planned_delivery_at"), time(9, 0))
    if not target_dt:
        return jsonify({"ok": False, "error": "Data consegna non valida"}), 400
    old_iso = order.planned_delivery_at.isoformat() if order.planned_delivery_at else None
    order.planned_delivery_at = target_dt
    db.session.add(SlackOrderEvent(
        order_id=order.id,
        type="delivery_manual",
        payload={
            "old_planned_delivery_at": old_iso,
            "new_planned_delivery_at": target_dt.isoformat(),
            "via": "route_order_board",
        },
    ))
    db.session.commit()
    return jsonify({"ok": True, "order": _order_to_dict(order)})


@route_orders_bp.post("/api/orders/<int:order_id>/customer")
@login_required
@role_required(30)
def api_order_customer(order_id):
    order = SlackOrder.query.get_or_404(order_id)
    data = request.get_json(silent=True) or {}
    registry = BusinessRegistry.query.filter_by(id=data.get("registry_id"), kind="customer", is_active=True).first()
    if not registry:
        return jsonify({"ok": False, "error": "Cliente non valido"}), 404

    old_payload = {
        "customer_display": order.customer_display,
        "customer_key": order.customer_key,
        "route_id": order.route_id,
    }
    order.customer_display = _label_registry(registry)
    order.customer_key = registry.source_code or str(registry.id)
    requested_route_id = data.get("route_id")
    if requested_route_id:
        route = DeliveryRoute.query.filter_by(id=requested_route_id, is_active=True).first()
        if route:
            order.route_id = route.id
            link = DeliveryRouteCustomer.query.filter_by(route_id=route.id, registry_id=registry.id).first()
            if link:
                link.is_active = True
            else:
                max_sort = (
                    db.session.query(db.func.coalesce(db.func.max(DeliveryRouteCustomer.sort_order), -1))
                    .filter_by(route_id=route.id, is_active=True)
                    .scalar()
                )
                db.session.add(DeliveryRouteCustomer(
                    route_id=route.id,
                    registry_id=registry.id,
                    sort_order=int(max_sort or -1) + 1,
                    is_active=True,
                ))
    db.session.add(SlackOrderEvent(
        order_id=order.id,
        type="customer_link",
        payload={
            "from": old_payload,
            "to": {
                "registry_id": registry.id,
                "customer_display": order.customer_display,
                "customer_key": order.customer_key,
                "route_id": order.route_id,
            },
            "via": "route_order_board",
        },
    ))
    db.session.commit()
    return jsonify({"ok": True, "order": _order_to_dict(order)})


@route_orders_bp.post("/api/orders/bulk-status")
@login_required
@role_required(30)
def api_orders_bulk_status():
    data = request.get_json(silent=True) or {}
    ids = [int(value) for value in (data.get("order_ids") or []) if str(value).isdigit()]
    target_status = (data.get("status") or "evaso").strip()
    if not ids:
        return jsonify({"ok": False, "error": "Nessun ordine selezionato"}), 400
    valid_status = OrderStatus.query.filter_by(code=target_status).first()
    if not valid_status:
        return jsonify({"ok": False, "error": "Stato non valido"}), 400
    orders = SlackOrder.query.filter(SlackOrder.id.in_(ids), SlackOrder.status != target_status).all()
    for order in orders:
        old_status = order.status
        order.status = target_status
        if target_status == "evaso":
            order.evaded_at = datetime.utcnow()
        if valid_status.is_terminal and not order.closed_at:
            order.closed_at = datetime.utcnow()
        db.session.add(SlackOrderEvent(
            order_id=order.id,
            type="status_change",
            payload={"from": old_status, "to": target_status, "via": "route_order_board_bulk"},
        ))
    db.session.commit()
    for order in orders:
        try:
            SlackProcessor().sync_order_status_reactions(order, old_status_code=None, new_status_code=target_status)
        except Exception:
            logger.exception("Sync reaction bulk failed order_id=%s", order.id)
    return jsonify({"ok": True, "updated": len(orders)})


@route_orders_bp.post("/api/direct-orders")
@login_required
@role_required(30)
def api_direct_order_create():
    registry = BusinessRegistry.query.filter_by(id=request.form.get("registry_id", type=int), kind="customer", is_active=True).first()
    if not registry:
        return jsonify({"ok": False, "error": "Cliente non valido"}), 404
    note = (request.form.get("order_note") or "").strip()
    if not note:
        return jsonify({"ok": False, "error": "Testo ordine mancante"}), 400
    planned_delivery_at = _parse_datetime(request.form.get("planned_delivery_at"), time(9, 0))
    direct_route, channel_id = _direct_order_route()
    if not channel_id:
        return jsonify({"ok": False, "error": "Canale diretto Carsoli non configurato"}), 400
    bot_token = current_app.config.get("SLACK_BOT_TOKEN", "") or ""
    if not bot_token:
        return jsonify({"ok": False, "error": "SLACK_BOT_TOKEN mancante"}), 503
    attachments = _save_uploaded_files(_files_from_request())
    message_text = _format_direct_message(registry, note, planned_delivery_at)
    api = SlackAPI(SlackAPIConfig(bot_token=bot_token))
    try:
        response = api.post_message(channel_id, message_text)
    except Exception as exc:
        logger.exception("Invio Slack ordine diretto fallito")
        return jsonify({"ok": False, "error": f"Invio Slack fallito: {exc}"}), 502
    ts = response.get("ts") or (response.get("message") or {}).get("ts")
    if not ts:
        return jsonify({"ok": False, "error": f"Slack non ha restituito il timestamp del messaggio: {response}"}), 502
    try:
        _upload_attachments_to_slack(api, channel_id, ts, attachments)
    except Exception as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": f"Ordine inviato, ma allegati non caricati su Slack: {exc}"}), 502
    order = SlackOrder(
        route_id=direct_route.id if direct_route else None,
        slack_channel_id=channel_id,
        customer_display=_label_registry(registry),
        customer_key=registry.source_code or str(registry.id),
        order_date=datetime.utcnow().date(),
        planned_delivery_at=planned_delivery_at,
        status="acquisito",
        raw_text=message_text,
        slack_message_ts=ts,
        slack_thread_ts=ts,
        has_issues=False,
    )
    db.session.add(order)
    db.session.flush()
    _reset_documents_for_customer_orders(
        channel_id,
        order.customer_key,
        exclude_order_id=order.id,
        via="route_order_board_direct",
        reason="new_direct_order_same_customer",
    )
    db.session.add(SlackOrderEvent(
        order_id=order.id,
        type="created",
        payload={"ts": ts, "text": message_text, "attachments": attachments, "via": "route_order_board_direct"},
    ))
    db.session.commit()
    try:
        send_order_push_to_staff(order, title="Nuovo ordine diretto", body=_label_registry(registry))
    except Exception:
        logger.exception("Invio push ordine diretto fallito")
    return jsonify({"ok": True, "order": _order_to_dict(order)})


@route_orders_bp.get("/api/direct-orders")
@login_required
@role_required(30)
def api_direct_orders():
    direct_route, channel_id = _direct_order_route()
    if not channel_id:
        return jsonify({"ok": True, "orders": []})
    orders = (
        SlackOrder.query
        .filter(
            SlackOrder.slack_channel_id == channel_id,
            or_(
                SlackOrder.order_date >= date.today(),
                SlackOrder.planned_delivery_at >= datetime.combine(date.today(), time.min),
            ),
            SlackOrder.status.notin_(["cancellato"]),
        )
        .order_by(SlackOrder.created_at.desc(), SlackOrder.id.desc())
        .limit(80)
        .all()
    )
    registry_ids = []
    groups = {}
    loose_index = 0
    for order in orders:
        registry = _registry_for_order(order)
        if registry:
            key = f"registry:{registry.id}"
            registry_ids.append(registry.id)
            if key not in groups:
                groups[key] = {
                    "id": registry.id,
                    "display": _label_registry(registry),
                    "source_code": registry.source_code,
                    "city": registry.city,
                    "phones": _phone_contacts(registry),
                    "alerts": [],
                    "orders": [],
                }
        else:
            loose_index += 1
            key = f"order:{loose_index}"
            groups[key] = {
                "id": None,
                "display": order.customer_display,
                "source_code": order.customer_key,
                "city": "",
                "phones": [],
                "alerts": [],
                "orders": [],
            }
        groups[key]["orders"].append(_order_to_dict(order))

    alerts_by_registry = {}
    for alert in _visible_alerts_query(registry_ids, date.today()):
        alerts_by_registry.setdefault(alert.registry_id, []).append(alert)
    for group in groups.values():
        if group["id"]:
            group["alerts"] = [alert.to_dict() for alert in alerts_by_registry.get(group["id"], [])]

    return jsonify({"ok": True, "customers": list(groups.values()), "orders": [_order_to_dict(order) for order in orders]})


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
    try:
        response = api.post_message(route.slack_channel_id, _format_slack_message(registry, entry))
    except Exception as exc:
        logger.exception("Invio Slack ordine giro fallito entry_id=%s", entry.id)
        return jsonify({"ok": False, "error": f"Invio Slack fallito: {exc}"}), 502
    ts = response.get("ts") or (response.get("message") or {}).get("ts")
    if not ts:
        return jsonify({"ok": False, "error": f"Slack non ha restituito il timestamp del messaggio: {response}"}), 502
    try:
        _upload_attachments_to_slack(api, route.slack_channel_id, ts, entry.order_attachments or [])
    except Exception as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": f"Ordine inviato, ma allegati non caricati su Slack: {exc}"}), 502
    entry.slack_channel_id = route.slack_channel_id
    entry.slack_message_ts = ts
    entry.slack_thread_ts = ts
    entry.sent_at = datetime.utcnow()
    entry.status = "ordine_fatto"
    target_status = "listato" if entry.list_done else "acquisito"
    if entry.list_done and ts:
        try:
            _set_list_done_reaction(entry, True)
        except Exception as exc:
            db.session.rollback()
            return jsonify({"ok": False, "error": f"Ordine inviato, ma reaction lista fatta non applicata: {exc}"}), 502
    order = _ensure_slack_order(entry, target_status)
    _add_attachment_event(order, entry.order_attachments or [], via="route_order_board")
    db.session.commit()
    try:
        send_order_push_to_staff(order, title="Nuovo ordine giro", body=_label_registry(registry))
    except Exception:
        logger.exception("Invio push ordine giro fallito")
    return jsonify({"ok": True, "entry": entry.to_dict()})


@route_orders_bp.post("/api/entries/<int:entry_id>/cancel")
@login_required
@role_required(30)
def api_cancel_order(entry_id):
    entry = RouteOrderBoardEntry.query.get_or_404(entry_id)
    if not entry.slack_channel_id or not entry.slack_message_ts:
        entry.order_note = None
        entry.list_done = False
        entry.status = "annullato"
        db.session.commit()
        return jsonify({"ok": True, "entry": entry.to_dict()})

    bot_token = current_app.config.get("SLACK_BOT_TOKEN", "") or ""
    if not bot_token:
        return jsonify({"ok": False, "error": "SLACK_BOT_TOKEN mancante"}), 503
    api = SlackAPI(SlackAPIConfig(bot_token=bot_token))
    try:
        if entry.list_done:
            api.remove_reaction(entry.slack_channel_id, entry.slack_message_ts, _status_reaction("listato", "white_check_mark"))
        SlackProcessor().execute_actions(
            [{"action_type": "addReaction", "config_json": {"reaction": _status_reaction("annullato", "x")}}],
            {"channel": entry.slack_channel_id, "ts": entry.slack_message_ts},
        )
    except Exception as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": f"Reaction annullamento non applicata: {exc}"}), 502

    entry.order_note = None
    entry.list_done = False
    entry.status = "annullato"
    order = _ensure_slack_order(entry, "annullato")
    if order and not order.closed_at:
        order.closed_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True, "entry": entry.to_dict()})


@route_orders_bp.delete("/api/entries/<int:entry_id>")
@login_required
@role_required(30)
def api_delete_order(entry_id):
    entry = RouteOrderBoardEntry.query.get_or_404(entry_id)
    channel_id = entry.slack_channel_id
    message_ts = entry.slack_message_ts
    slack_warning = None
    slack_action = None
    orders = []
    if channel_id and message_ts:
        orders = (
            SlackOrder.query
            .filter_by(slack_channel_id=channel_id, slack_message_ts=message_ts)
            .order_by(SlackOrder.id.desc())
            .all()
        )

    if channel_id and message_ts:
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
                    channel_id,
                    message_ts,
                    actor,
                )
                slack_action = result.get("action")
                if result.get("warning"):
                    slack_warning = f"Ordine marcato su Slack con avviso parziale: {result['warning']}"
            except Exception as exc:
                slack_warning = f"Messaggio Slack non cancellato: {exc}"
                logger.exception("Delete Slack message failed channel=%s ts=%s", channel_id, message_ts)
        else:
            slack_warning = "SLACK_BOT_TOKEN mancante: cancellazione locale eseguita"

    for order in orders:
        db.session.delete(order)

    linked_entries = []
    if channel_id and message_ts:
        linked_entries = RouteOrderBoardEntry.query.filter_by(slack_channel_id=channel_id, slack_message_ts=message_ts).all()
    if not linked_entries:
        linked_entries = [entry]
    for linked_entry in linked_entries:
        db.session.delete(linked_entry)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("Local order delete failed entry_id=%s", entry_id)
        return jsonify({"ok": False, "error": "Eliminazione locale dell'ordine non riuscita"}), 500
    payload = {"ok": True, "slack_action": slack_action}
    if slack_warning:
        payload["warning"] = slack_warning
    return jsonify(payload)


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
