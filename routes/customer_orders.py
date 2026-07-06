import mimetypes
import os
from datetime import datetime

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from extensions import db
from models import (
    BusinessRegistry,
    CustomerOrder,
    CustomerOrderDeliveryOption,
    CustomerOrderRevision,
    DeliveryRouteCustomer,
)
from tools.role_required import role_required


customer_orders_bp = Blueprint("customer_orders", __name__)


def _active_role_names():
    if not current_user.is_authenticated:
        return set()
    return {getattr(role, "name", "").strip().lower() for role in current_user.active_roles or []}


def _can_create_customer_order():
    if not current_user.is_authenticated:
        return False
    return "customer_horeca" in _active_role_names() or (current_user.max_role_weight or 0) >= 30


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


def _customer_registry():
    registry = getattr(current_user, "customer_registry", None)
    if registry and registry.kind == "customer" and registry.is_active:
        return registry
    return None


def _customer_route(registry):
    link = (
        DeliveryRouteCustomer.query
        .filter_by(registry_id=registry.id, is_active=True)
        .order_by(DeliveryRouteCustomer.sort_order.asc(), DeliveryRouteCustomer.id.asc())
        .first()
    )
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
    return order.user_id == current_user.id


@customer_orders_bp.get("/")
@login_required
def index():
    if not _can_create_customer_order():
        flash("Funzione disponibile per clienti Horeca.", "warning")
        return redirect(url_for("home"))
    registry = _customer_registry()
    orders = []
    if registry:
        orders = (
            CustomerOrder.query
            .filter(CustomerOrder.registry_id == registry.id)
            .order_by(CustomerOrder.created_at.desc(), CustomerOrder.id.desc())
            .limit(20)
            .all()
        )
    return render_template(
        "customer_orders/index.html",
        registry=registry,
        route=_customer_route(registry) if registry else None,
        delivery_options=_delivery_options(),
        orders=orders,
    )


@customer_orders_bp.post("/")
@login_required
def create():
    if not _can_create_customer_order():
        flash("Funzione disponibile per clienti Horeca.", "warning")
        return redirect(url_for("home"))
    registry = _customer_registry()
    if not registry:
        flash("Il tuo account non e' ancora associato a un'anagrafica cliente.", "warning")
        return redirect(url_for("customer_orders.index"))
    route = _customer_route(registry)
    delivery_option = CustomerOrderDeliveryOption.query.filter_by(id=request.form.get("delivery_option_id"), is_active=True).first()
    order_text = (request.form.get("order_text") or "").strip()
    attachments = _save_files()
    if not order_text and not attachments:
        flash("Inserisci un testo ordine o almeno un allegato.", "warning")
        return redirect(url_for("customer_orders.index"))

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
    db.session.commit()
    flash("Ordine inviato.", "success")
    return redirect(url_for("customer_orders.index"))


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
    delivery_option = CustomerOrderDeliveryOption.query.filter_by(id=request.form.get("delivery_option_id"), is_active=True).first()
    order_text = (request.form.get("order_text") or "").strip()
    attachments = _save_files()
    if not order_text and not attachments:
        flash("Inserisci una nota o un allegato.", "warning")
        return redirect(url_for("customer_orders.index"))

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
    return redirect(url_for("customer_orders.index"))


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
