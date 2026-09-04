import mimetypes
import os
from datetime import date, datetime, time, timedelta

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload, load_only
from werkzeug.utils import secure_filename

from extensions import db
from models import (
    BusinessRegistry,
    CustomerOrder,
    CustomerOrderDeliveryOption,
    CustomerOrderRevision,
    CustomerRouteOrderReminder,
    DeliveryRouteCustomer,
    RouteOrderBoardEntry,
    SlackOrder,
)
from tools.role_required import role_required
from tools.customer_memberships import (
    ACCESS_MANAGEMENT,
    active_customer_memberships,
    customer_registry_for_user,
    user_has_customer_capability,
)


customer_orders_bp = Blueprint("customer_orders", __name__)


CUSTOMER_ORDER_STATUS_LABELS = {
    "received": "Ordine ricevuto",
    "published": "Ordine ricevuto",
    "changed": "Modifica ricevuta",
    "acquisito": "Ordine ricevuto",
    "listato": "In preparazione",
    "preparato": "Preparato",
    "controllato": "Controllato",
    "in_consegna": "In consegna",
    "inconsegna": "In consegna",
    "evaso": "Evaso",
    "annullato": "Annullato",
    "annullata": "Annullato",
    "cancellato": "Cancellato",
    "cancelled": "Cancellato",
}

CUSTOMER_ORDER_STATUS_RANKS = {
    "received": 1,
    "published": 1,
    "changed": 1,
    "acquisito": 1,
    "listato": 2,
    "preparato": 3,
    "controllato": 4,
    "in_consegna": 5,
    "inconsegna": 5,
    "evaso": 6,
}

CUSTOMER_ORDER_TERMINAL_STATUSES = {"evaso", "annullato", "annullata", "cancellato", "cancelled"}


def _active_role_names():
    if not current_user.is_authenticated:
        return set()
    return {getattr(role, "name", "").strip().lower() for role in current_user.active_roles or []}


def _can_create_customer_order():
    if not current_user.is_authenticated:
        return False
    role_names = _active_role_names()
    return "dev" in role_names or (
        "customer_horeca" in role_names
        and user_has_customer_capability(current_user, ACCESS_MANAGEMENT)
    )


def _is_developer():
    return "dev" in _active_role_names()


def _customer_label(registry):
    return registry.display_name or registry.legal_name or registry.source_code or f"Cliente {registry.id}"


def _upload_folder():
    folder = os.path.join(current_app.static_folder, "uploads", "customer_orders", datetime.utcnow().strftime("%Y%m%d"))
    os.makedirs(folder, exist_ok=True)
    return folder


def _public_upload_path(abs_path):
    rel = os.path.relpath(abs_path, current_app.static_folder).replace(os.sep, "/")
    return f"/static/{rel}"


def _static_rel_path(abs_path):
    return os.path.relpath(abs_path, current_app.static_folder).replace(os.sep, "/")


def _save_files():
    saved = []
    files = []
    for field_name, values in request.files.lists():
        for value in values:
            files.append((field_name, value))
    for field_name, file in files:
        if not file or not getattr(file, "filename", ""):
            continue
        filename = secure_filename(file.filename) or f"allegato-{len(saved) + 1}{mimetypes.guess_extension(file.mimetype or '') or ''}"
        target = os.path.join(_upload_folder(), f"{datetime.utcnow().strftime('%H%M%S%f')}_{filename}")
        file.save(target)
        size = os.path.getsize(target)
        content_type = file.mimetype or mimetypes.guess_type(filename)[0] or ""
        attachment_type = "audio" if content_type.startswith("audio/") or field_name == "audio" else "image" if content_type.startswith("image/") else "file"
        saved.append({
            "id": f"customer-order-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}-{len(saved) + 1}",
            "source": "customer_order",
            "field": field_name,
            "attachment_type": attachment_type,
            "name": filename,
            "title": filename,
            "filename": filename,
            "mimetype": content_type,
            "content_type": content_type,
            "filetype": os.path.splitext(filename)[1].lstrip(".").lower(),
            "size": size,
            "size_label": _format_bytes(size),
            "is_image": content_type.startswith("image/"),
            "is_audio": content_type.startswith("audio/"),
            "url": _public_upload_path(target),
            "static_path": _static_rel_path(target),
        })
    return saved


def _format_bytes(size):
    value = float(size or 0)
    units = ["B", "KB", "MB", "GB"]
    index = 0
    while value >= 1024 and index < len(units) - 1:
        value /= 1024
        index += 1
    decimals = 0 if index == 0 else 1
    return f"{value:.{decimals}f} {units[index]}"


def _parse_int(value):
    try:
        if value is None or str(value).strip() == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _selected_delivery_option():
    option_id = _parse_int(request.form.get("delivery_option_id"))
    if not option_id:
        return None
    return CustomerOrderDeliveryOption.query.filter_by(id=option_id, is_active=True).first()


def _selectable_customer_registries(is_developer):
    if is_developer:
        return (
            BusinessRegistry.query
            .options(load_only(
                BusinessRegistry.id,
                BusinessRegistry.display_name,
                BusinessRegistry.legal_name,
                BusinessRegistry.source_code,
            ))
            .filter_by(kind="customer", is_active=True)
            .order_by(BusinessRegistry.display_name.asc(), BusinessRegistry.id.asc())
            .all()
        )
    memberships = active_customer_memberships(current_user, capability=ACCESS_MANAGEMENT)
    registries = [membership.registry for membership in memberships]
    legacy_registry = customer_registry_for_user(current_user, capability=ACCESS_MANAGEMENT)
    if not registries and legacy_registry is not None:
        registries = [legacy_registry]
    return registries


def _customer_registry(registry_id=None, *, is_developer=None, registries=None):
    is_developer = _is_developer() if is_developer is None else is_developer
    if is_developer:
        if registries is not None:
            selected = next((item for item in registries if item.id == registry_id), None)
            return selected or (registries[0] if registry_id is None and registries else None)
        if registry_id is None:
            return None
        return BusinessRegistry.query.filter_by(id=registry_id, kind="customer", is_active=True).first()
    return customer_registry_for_user(current_user, registry_id, capability=ACCESS_MANAGEMENT)


def _customer_order_status(code):
    normalized = (code or "received").strip().lower()
    return {
        "code": normalized,
        "label": CUSTOMER_ORDER_STATUS_LABELS.get(normalized, normalized.replace("_", " ").capitalize()),
        "rank": CUSTOMER_ORDER_STATUS_RANKS.get(normalized, 1),
        "terminal": normalized in CUSTOMER_ORDER_TERMINAL_STATUSES,
        "cancelled": normalized in {"annullato", "annullata", "cancellato", "cancelled"},
    }


def _effective_customer_order_status(order):
    return _customer_order_status(order.slack_order.status if order.slack_order else order.status)


def _parse_date(value, fallback):
    try:
        return date.fromisoformat((value or "").strip())
    except (TypeError, ValueError):
        return fallback


def _linked_slack_order(entry):
    if not entry.slack_channel_id or not entry.slack_message_ts:
        return None
    return SlackOrder.query.filter_by(
        slack_channel_id=entry.slack_channel_id,
        slack_message_ts=entry.slack_message_ts,
    ).first()


def _customer_order_rows(registry, date_from, date_to):
    """Build a customer-safe order history using only exact registry links/keys."""
    rows = []
    seen_slack_ids = set()
    seen_message_keys = set()

    app_orders = (
        CustomerOrder.query
        .options(
            joinedload(CustomerOrder.slack_order),
            joinedload(CustomerOrder.route),
            joinedload(CustomerOrder.delivery_option),
        )
        .filter(
            CustomerOrder.registry_id == registry.id,
            CustomerOrder.created_at >= datetime.combine(date_from, time.min),
            CustomerOrder.created_at <= datetime.combine(date_to, time.max),
        )
        .order_by(CustomerOrder.created_at.desc(), CustomerOrder.id.desc())
        .all()
    )
    for order in app_orders:
        linked = order.slack_order
        if linked:
            seen_slack_ids.add(linked.id)
            seen_message_keys.add((linked.slack_channel_id, linked.slack_message_ts))
        status = _effective_customer_order_status(order)
        rows.append({
            "key": f"app-{order.id}",
            "reference": f"Ordine #{order.id}",
            "source_label": "LDApp",
            "created_at": order.created_at,
            "order_date": linked.order_date if linked else order.created_at.date(),
            "planned_delivery_at": linked.planned_delivery_at if linked else None,
            "route": order.route.name if order.route else "",
            "status": status,
            "text": order.order_text or (linked.raw_text if linked else "") or "",
            "attachments": order.attachments or [],
            "delivery_label": order.delivery_option.label if order.delivery_option else "",
            "delivery_value": order.delivery_option_value or "",
            "updated_at": linked.updated_at if linked else order.updated_at,
        })

    entries = (
        RouteOrderBoardEntry.query
        .options(joinedload(RouteOrderBoardEntry.route))
        .filter(
            RouteOrderBoardEntry.registry_id == registry.id,
            RouteOrderBoardEntry.board_date >= date_from,
            RouteOrderBoardEntry.board_date <= date_to,
            RouteOrderBoardEntry.sent_at.isnot(None),
        )
        .order_by(RouteOrderBoardEntry.board_date.desc(), RouteOrderBoardEntry.id.desc())
        .all()
    )
    for entry in entries:
        message_key = (entry.slack_channel_id, entry.slack_message_ts)
        if message_key in seen_message_keys:
            continue
        linked = _linked_slack_order(entry)
        if linked and linked.id in seen_slack_ids:
            continue
        if linked:
            seen_slack_ids.add(linked.id)
            seen_message_keys.add(message_key)
        status = _customer_order_status(linked.status if linked else entry.status)
        rows.append({
            "key": f"board-{entry.id}",
            "reference": f"Ordine {entry.board_date.strftime('%d/%m/%Y')}",
            "source_label": "Ordine registrato",
            "created_at": entry.sent_at or entry.created_at,
            "order_date": linked.order_date if linked else entry.board_date,
            "planned_delivery_at": entry.planned_delivery_at,
            "route": entry.route.name if entry.route else "",
            "status": status,
            "text": entry.order_note or (linked.raw_text if linked else "") or "",
            "attachments": entry.order_attachments or [],
            "delivery_label": "",
            "delivery_value": "",
            "updated_at": linked.updated_at if linked else entry.updated_at,
        })

    source_code = str(registry.source_code or "").strip()
    # Gli ordini pubblicati dall'app usano sempre source_code quando presente.
    # Non mescoliamo source_code e PK interna: lo stesso numero potrebbe
    # appartenere come codice gestionale a un'altra anagrafica.
    exact_keys = {source_code} if source_code else {str(registry.id)}
    slack_orders = (
        SlackOrder.query
        .options(joinedload(SlackOrder.route))
        .filter(
            SlackOrder.customer_key.in_(tuple(exact_keys)),
            SlackOrder.order_date >= date_from,
            SlackOrder.order_date <= date_to,
        )
        .order_by(SlackOrder.order_date.desc(), SlackOrder.created_at.desc(), SlackOrder.id.desc())
        .all()
    )
    for order in slack_orders:
        if order.id in seen_slack_ids:
            continue
        rows.append({
            "key": f"slack-{order.id}",
            "reference": f"Ordine #{order.id}",
            "source_label": "Ordine registrato",
            "created_at": order.created_at,
            "order_date": order.order_date,
            "planned_delivery_at": order.planned_delivery_at,
            "route": order.route.name if order.route else "",
            "status": _customer_order_status(order.status),
            "text": order.raw_text or "",
            "attachments": [],
            "delivery_label": "",
            "delivery_value": "",
            "updated_at": order.updated_at,
        })
    rows.sort(key=lambda item: (item["created_at"] or datetime.min, item["key"]), reverse=True)
    return rows


def _customer_route(registry, route_id=None):
    query = (
        DeliveryRouteCustomer.query
        .filter_by(registry_id=registry.id, is_active=True)
    )
    if route_id:
        query = query.filter(DeliveryRouteCustomer.route_id == route_id)
    link = query.order_by(DeliveryRouteCustomer.sort_order.asc(), DeliveryRouteCustomer.id.asc()).first()
    return link.route if link else None


def _delivery_options():
    return (
        CustomerOrderDeliveryOption.query
        .filter(CustomerOrderDeliveryOption.is_active.is_(True))
        .order_by(CustomerOrderDeliveryOption.sort_order.asc(), CustomerOrderDeliveryOption.label.asc())
        .all()
    )


def _order_access(order):
    if (current_user.max_role_weight or 0) >= 30:
        return True
    return customer_registry_for_user(
        current_user,
        order.registry_id,
        capability=ACCESS_MANAGEMENT,
    ) is not None


@customer_orders_bp.get("/")
@login_required
def index():
    if not _can_create_customer_order():
        flash("Account non abilitato alla gestione ordini dei clienti associati.", "warning")
        return redirect(url_for("home"))
    is_developer = _is_developer()
    registries = _selectable_customer_registries(is_developer)
    requested_registry_id = request.args.get("customer", type=int)
    registry = _customer_registry(
        requested_registry_id,
        is_developer=is_developer,
        registries=registries,
    )
    requested_route_id = request.args.get("route", type=int)
    selected_route = _customer_route(registry, requested_route_id) if registry else None
    orders = []
    if registry:
        orders = (
            CustomerOrder.query
            .options(joinedload(CustomerOrder.slack_order))
            .filter(CustomerOrder.registry_id == registry.id)
            .order_by(CustomerOrder.created_at.desc(), CustomerOrder.id.desc())
            .limit(20)
            .all()
        )
    return render_template(
        "customer_orders/index.html",
        registry=registry,
        route=selected_route,
        delivery_options=_delivery_options(),
        orders=orders,
        effective_order_status=_effective_customer_order_status,
        is_developer=is_developer,
        registries=registries,
        suggested_delivery_date=_parse_date(request.args.get("delivery_date"), None),
    )


def _customer_reminder(public_id):
    reminder = CustomerRouteOrderReminder.query.filter_by(public_id=public_id).first_or_404()
    if reminder.user_id != current_user.id:
        return None
    registry = customer_registry_for_user(
        current_user,
        reminder.registry_id,
        capability=ACCESS_MANAGEMENT,
    )
    if registry is None:
        return None
    return reminder


@customer_orders_bp.get("/reminders/<public_id>/order")
@login_required
def open_route_reminder_order(public_id):
    reminder = _customer_reminder(public_id)
    if reminder is None:
        flash("Promemoria non disponibile per questo account.", "danger")
        return redirect(url_for("home"))
    if reminder.action == "skipped":
        flash("Per questo passaggio hai gia' scelto di saltare il giro.", "info")
    return redirect(url_for(
        "customer_orders.index",
        customer=reminder.registry_id,
        route=reminder.route_id,
        delivery_date=reminder.delivery_date.isoformat(),
    ))


@customer_orders_bp.route("/reminders/<public_id>/skip", methods=["GET", "POST"])
@login_required
def skip_route_reminder(public_id):
    reminder = _customer_reminder(public_id)
    if reminder is None:
        flash("Promemoria non disponibile per questo account.", "danger")
        return redirect(url_for("home"))

    link = DeliveryRouteCustomer.query.filter_by(
        route_id=reminder.route_id,
        registry_id=reminder.registry_id,
        is_active=True,
    ).first()
    if link is None:
        flash("Il cliente non appartiene piu' a questo giro.", "warning")
        return redirect(url_for("customer_orders.index", customer=reminder.registry_id))

    entry = RouteOrderBoardEntry.query.filter_by(
        route_id=reminder.route_id,
        registry_id=reminder.registry_id,
        board_date=reminder.delivery_date,
    ).first()
    if request.method == "POST":
        from tools.customer_route_reminders import _blocked_registries, _delivery_for_date

        schedule_base = datetime.combine(reminder.delivery_date - timedelta(days=1), time.min)
        planned_delivery_at = _delivery_for_date(
            reminder.route,
            reminder.delivery_date,
            local_now=schedule_base,
        ) or datetime.combine(reminder.delivery_date, reminder.route.default_time)
        blocked = reminder.registry_id in _blocked_registries(
            reminder.route,
            [link],
            planned_delivery_at,
        )
        if blocked and not (entry and entry.status == "salta_giro"):
            flash("Il giro non puo' essere saltato: risulta gia' un ordine.", "warning")
            return redirect(url_for("customer_orders.index", customer=reminder.registry_id))
        if not entry:
            entry = RouteOrderBoardEntry(
                route_id=reminder.route_id,
                registry_id=reminder.registry_id,
                board_date=reminder.delivery_date,
                planned_delivery_at=planned_delivery_at,
            )
            db.session.add(entry)
        entry.status = "salta_giro"
        entry.order_note = "Giro saltato dal cliente tramite promemoria LDApp."
        reminder.status = "acted"
        reminder.action = "skipped"
        reminder.acted_at = datetime.now().astimezone()
        db.session.commit()
        flash("Giro saltato. La bacheca ordini e' stata aggiornata.", "success")
        return redirect(url_for("customer_orders.index", customer=reminder.registry_id))

    return render_template(
        "customer_orders/skip_route.html",
        reminder=reminder,
        entry=entry,
        customer_label=_customer_label(reminder.registry),
    )


@customer_orders_bp.get("/status")
@login_required
def status():
    if not _can_create_customer_order():
        flash("Account non abilitato alla gestione ordini dei clienti associati.", "warning")
        return redirect(url_for("home"))

    is_developer = _is_developer()
    registries = _selectable_customer_registries(is_developer)
    requested_registry_id = request.args.get("customer", type=int) or request.args.get("registry_id", type=int)
    registry = _customer_registry(
        requested_registry_id,
        is_developer=is_developer,
        registries=registries,
    )
    today = date.today()
    date_from = _parse_date(request.args.get("date_from"), today - timedelta(days=180))
    date_to = _parse_date(request.args.get("date_to"), today)
    if date_from > date_to:
        date_from, date_to = date_to, date_from

    rows = _customer_order_rows(registry, date_from, date_to) if registry else []
    return render_template(
        "customer_orders/status.html",
        registry=registry,
        registries=registries,
        is_developer=is_developer,
        rows=rows,
        date_from=date_from,
        date_to=date_to,
    )


@customer_orders_bp.post("/")
@login_required
def create():
    if not _can_create_customer_order():
        flash("Account non abilitato alla gestione ordini dei clienti associati.", "warning")
        return redirect(url_for("home"))
    is_developer = _is_developer()
    requested_registry_id = request.form.get("registry_id", type=int)
    registry = _customer_registry(requested_registry_id, is_developer=is_developer)
    if not registry:
        flash("Il tuo account non e' ancora associato a un'anagrafica cliente.", "warning")
        return redirect(url_for("customer_orders.index"))
    requested_route_id = request.form.get("route_id", type=int)
    route = _customer_route(registry, requested_route_id)
    delivery_option = _selected_delivery_option()
    order_text = (request.form.get("order_text") or "").strip()
    attachments = _save_files()
    if not order_text and not attachments:
        flash("Inserisci un testo ordine o almeno un allegato.", "warning")
        return redirect(url_for("customer_orders.index", customer=registry.id))

    order = CustomerOrder(
        user_id=current_user.id,
        registry_id=registry.id,
        route_id=route.id if route else None,
        delivery_option_id=delivery_option.id if delivery_option else None,
        delivery_option_value=(request.form.get("delivery_option_value") or "").strip() or None,
        order_text=order_text or None,
        attachments=attachments,
        status="received",
    )
    db.session.add(order)
    db.session.flush()
    db.session.add(CustomerOrderRevision(
        order_id=order.id,
        user_id=current_user.id,
        change_type="created",
        order_text=order.order_text,
        attachments=attachments,
        delivery_option_id=order.delivery_option_id,
        delivery_option_value=order.delivery_option_value,
    ))
    try:
        from routes.route_orders import publish_customer_order
        publish_customer_order(order)
        if order.route_board_entry:
            reminders = CustomerRouteOrderReminder.query.filter_by(
                user_id=current_user.id,
                registry_id=order.registry_id,
                route_id=order.route_id,
                delivery_date=order.route_board_entry.board_date,
            ).all()
            for reminder in reminders:
                reminder.status = "acted"
                reminder.action = "ordered"
                reminder.acted_at = datetime.now().astimezone()
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception("Pubblicazione ordine Horeca fallita")
        flash(f"Ordine non inviato alla bacheca: {exc}", "danger")
        return redirect(url_for("customer_orders.index", customer=registry.id))
    flash("Ordine inviato.", "success")
    return redirect(url_for("customer_orders.index", customer=registry.id))


@customer_orders_bp.post("/<int:order_id>/revise")
@login_required
def revise(order_id):
    order = CustomerOrder.query.get_or_404(order_id)
    if not _order_access(order):
        flash("Accesso negato.", "danger")
        return redirect(url_for("customer_orders.index"))
    change_type = (request.form.get("change_type") or "addition").strip()
    if change_type not in {"addition", "replacement"}:
        change_type = "addition"
    delivery_option = _selected_delivery_option()
    order_text = (request.form.get("order_text") or "").strip()
    attachments = _save_files()
    if not order_text and not attachments:
        flash("Inserisci una nota o un allegato.", "warning")
        return redirect(url_for("customer_orders.index", customer=order.registry_id))

    if change_type == "replacement":
        order.order_text = order_text or order.order_text
        order.attachments = attachments or order.attachments
    else:
        order.order_text = "\n\n".join(part for part in [order.order_text, order_text] if part)
        order.attachments = (order.attachments or []) + attachments
    if delivery_option:
        order.delivery_option_id = delivery_option.id
        order.delivery_option_value = (request.form.get("delivery_option_value") or "").strip() or None
    order.status = "changed"
    db.session.add(CustomerOrderRevision(
        order_id=order.id,
        user_id=current_user.id,
        change_type=change_type,
        order_text=order_text,
        attachments=attachments,
        delivery_option_id=delivery_option.id if delivery_option else None,
        delivery_option_value=(request.form.get("delivery_option_value") or "").strip() or None,
    ))
    db.session.commit()
    flash("Modifica ordine registrata.", "success")
    return redirect(url_for("customer_orders.index", customer=order.registry_id))


@customer_orders_bp.get("/manage")
@login_required
@role_required(30)
def manage():
    orders = (
        CustomerOrder.query
        .order_by(CustomerOrder.created_at.desc(), CustomerOrder.id.desc())
        .limit(100)
        .all()
    )
    return render_template("customer_orders/manage.html", orders=orders, customer_label=_customer_label)
