from datetime import date, time

from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required
from sqlalchemy import or_

from extensions import db
from models import (
    BusinessRegistry,
    BusinessRegistryContact,
    BusinessRegistryContactLink,
    DeliveryRoute,
    DeliveryRouteCustomer,
    RegistryContact,
    RegistryContactPoint,
)
from tools.role_required import role_required


registry_bp = Blueprint("registry", __name__)


def _registry_label(registry):
    if not registry:
        return ""
    return registry.display_name or registry.legal_name or registry.source_code or f"Anagrafica {registry.id}"


def _registry_to_dict(registry, include_contacts=False, include_routes=False):
    data = {
        "id": registry.id,
        "kind": registry.kind,
        "source_code": registry.source_code,
        "display_name": registry.display_name,
        "legal_name": registry.legal_name,
        "vat_number": registry.vat_number,
        "tax_code": registry.tax_code,
        "address": registry.address,
        "zip_code": registry.zip_code,
        "city": registry.city,
        "province": registry.province,
        "display": _registry_label(registry),
    }
    if include_contacts:
        data["legacy_contacts"] = [contact.to_dict() for contact in registry.contacts]
        data["contact_links"] = [
            link.to_dict()
            for link in registry.contact_links
            if link.is_active and link.contact and link.contact.is_active
        ]
    if include_routes:
        active_links = [
            link
            for link in registry.delivery_route_links
            if link.is_active and link.route and link.route.is_active
        ]
        data["route_ids"] = [link.route_id for link in active_links]
        data["routes"] = [
            {"id": link.route_id, "name": link.route.name}
            for link in active_links
        ]
        first_link = active_links[0] if active_links else None
        data["assigned_route_id"] = first_link.route_id if first_link else None
        data["assigned_route_name"] = first_link.route.name if first_link and first_link.route else None
    return data


def _search_registries(kind, q="", limit=80):
    query = BusinessRegistry.query.filter(
        BusinessRegistry.kind == kind,
        BusinessRegistry.is_active.is_(True),
    )
    q = (q or "").strip()
    if q:
        like = f"%{q}%"
        query = query.outerjoin(
            BusinessRegistryContact,
            BusinessRegistryContact.registry_id == BusinessRegistry.id,
        ).filter(or_(
            BusinessRegistry.display_name.ilike(like),
            BusinessRegistry.legal_name.ilike(like),
            BusinessRegistry.vat_number.ilike(like),
            BusinessRegistry.tax_code.ilike(like),
            BusinessRegistry.source_code.ilike(like),
            BusinessRegistryContact.value.ilike(like),
        ))
    return (
        query
        .order_by(BusinessRegistry.display_name.asc(), BusinessRegistry.id.asc())
        .limit(limit)
        .all()
    )


@registry_bp.get("/customer-routes")
@login_required
@role_required(100)
def customer_routes_page():
    return render_template("registry/customer_routes.html")


@registry_bp.get("/customers")
@login_required
@role_required(100)
def customers_book_page():
    return render_template("registry/registry_book.html", kind="customer", title="Rubrica clienti")


@registry_bp.get("/suppliers")
@login_required
@role_required(100)
def suppliers_book_page():
    return render_template("registry/registry_book.html", kind="supplier", title="Rubrica fornitori")


@registry_bp.get("/api/routes/customers")
@login_required
@role_required(100)
def api_route_customers_index():
    q = (request.args.get("q") or "").strip()
    routes = (
        DeliveryRoute.query
        .filter(DeliveryRoute.is_active.is_(True))
        .order_by(DeliveryRoute.name.asc())
        .all()
    )
    customers = _search_registries("customer", q=q, limit=250)
    assigned_customers = (
        BusinessRegistry.query
        .join(DeliveryRouteCustomer, DeliveryRouteCustomer.registry_id == BusinessRegistry.id)
        .join(DeliveryRoute, DeliveryRoute.id == DeliveryRouteCustomer.route_id)
        .filter(
            BusinessRegistry.kind == "customer",
            BusinessRegistry.is_active.is_(True),
            DeliveryRouteCustomer.is_active.is_(True),
            DeliveryRoute.is_active.is_(True),
        )
        .order_by(DeliveryRouteCustomer.sort_order.asc(), BusinessRegistry.display_name.asc(), BusinessRegistry.id.asc())
        .all()
    )
    return jsonify({
        "ok": True,
        "routes": [
            {
                "id": route.id,
                "name": route.name,
                "default_weekday": route.default_weekday,
                "default_time": route.default_time.strftime("%H:%M") if route.default_time else "",
            }
            for route in routes
        ],
        "customers": [
            _registry_to_dict(customer, include_routes=True)
            for customer in customers
        ],
        "assigned_customers": [
            _registry_to_dict(customer, include_routes=True)
            for customer in assigned_customers
        ],
    })


@registry_bp.post("/api/routes")
@login_required
@role_required(100)
def api_routes_create():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "Nome giro obbligatorio"}), 400

    slack_channel_id = (data.get("slack_channel_id") or "").strip() or f"manual-{name.lower().replace(' ', '-')}"
    weekday = int(data.get("default_weekday") or 1)
    if weekday < 1 or weekday > 7:
        weekday = 1
    raw_time = (data.get("default_time") or "09:00").strip()
    try:
        default_time = time.fromisoformat(raw_time)
    except ValueError:
        default_time = time(9, 0)

    route = DeliveryRoute(
        name=name,
        slack_channel_id=slack_channel_id,
        default_weekday=weekday,
        default_time=default_time,
        frequency=(data.get("frequency") or "weekly").strip() or "weekly",
        frequency_anchor_date=date.today(),
        is_active=True,
    )
    db.session.add(route)
    db.session.commit()
    return jsonify({"ok": True, "route": {"id": route.id, "name": route.name}}), 201


@registry_bp.post("/api/routes/<int:route_id>/customers")
@login_required
@role_required(100)
def api_route_customers_replace(route_id):
    route = DeliveryRoute.query.filter_by(id=route_id).first()
    if not route:
        return jsonify({"ok": False, "error": "Giro non trovato"}), 404

    data = request.get_json(silent=True) or {}
    registry_ids = data.get("registry_ids") or []
    if not isinstance(registry_ids, list):
        return jsonify({"ok": False, "error": "registry_ids deve essere una lista"}), 400

    normalized_ids = []
    for value in registry_ids:
        try:
            normalized_ids.append(int(value))
        except (TypeError, ValueError):
            continue
    normalized_ids = list(dict.fromkeys(normalized_ids))

    valid_ids = {
        row.id
        for row in BusinessRegistry.query
        .filter(BusinessRegistry.kind == "customer", BusinessRegistry.id.in_(normalized_ids or [0]))
        .all()
    }

    existing = {link.registry_id: link for link in DeliveryRouteCustomer.query.filter_by(route_id=route.id).all()}
    for link in existing.values():
        link.is_active = False

    for index, registry_id in enumerate(normalized_ids):
        if registry_id not in valid_ids:
            continue
        link = existing.get(registry_id)
        if not link:
            link = DeliveryRouteCustomer(route_id=route.id, registry_id=registry_id)
            db.session.add(link)
        link.is_active = True
        link.sort_order = index

    db.session.commit()
    return jsonify({"ok": True, "route_id": route.id, "registry_ids": [x for x in normalized_ids if x in valid_ids]})


@registry_bp.post("/api/routes/<int:route_id>/customers/<int:registry_id>")
@login_required
@role_required(100)
def api_route_customer_assign(route_id, registry_id):
    route = DeliveryRoute.query.filter_by(id=route_id, is_active=True).first()
    if not route:
        return jsonify({"ok": False, "error": "Giro non trovato"}), 404

    registry = BusinessRegistry.query.filter_by(id=registry_id, kind="customer", is_active=True).first()
    if not registry:
        return jsonify({"ok": False, "error": "Cliente non trovato"}), 404

    data = request.get_json(silent=True) or {}
    replace = bool(data.get("replace"))

    active_links = DeliveryRouteCustomer.query.filter_by(registry_id=registry.id, is_active=True).all()
    other_links = [link for link in active_links if link.route_id != route.id]
    if other_links and not replace:
        return jsonify({
            "ok": False,
            "needs_confirm": True,
            "message": f"Cliente gia' associato al giro {other_links[0].route.name if other_links[0].route else other_links[0].route_id}. Sostituire associazione?",
            "current_routes": [
                {"id": link.route_id, "name": link.route.name if link.route else ""}
                for link in other_links
            ],
        }), 409

    for link in other_links:
        link.is_active = False

    link = DeliveryRouteCustomer.query.filter_by(route_id=route.id, registry_id=registry.id).first()
    if not link:
        max_sort = db.session.query(db.func.coalesce(db.func.max(DeliveryRouteCustomer.sort_order), -1)).filter_by(route_id=route.id, is_active=True).scalar()
        link = DeliveryRouteCustomer(route_id=route.id, registry_id=registry.id, sort_order=int(max_sort or -1) + 1)
        db.session.add(link)
    link.is_active = True

    db.session.commit()
    return jsonify({"ok": True, "route_id": route.id, "registry_id": registry.id})


@registry_bp.delete("/api/routes/<int:route_id>/customers/<int:registry_id>")
@login_required
@role_required(100)
def api_route_customer_delete(route_id, registry_id):
    link = DeliveryRouteCustomer.query.filter_by(route_id=route_id, registry_id=registry_id, is_active=True).first()
    if not link:
        return jsonify({"ok": False, "error": "Associazione non trovata"}), 404
    link.is_active = False
    db.session.commit()
    return jsonify({"ok": True})


@registry_bp.get("/api/registries")
@login_required
@role_required(100)
def api_registries_index():
    kind = (request.args.get("kind") or "customer").strip().lower()
    if kind not in {"customer", "supplier"}:
        return jsonify({"ok": False, "error": "Tipo anagrafica non valido"}), 400
    q = (request.args.get("q") or "").strip()
    registries = _search_registries(kind, q=q, limit=120)
    return jsonify({
        "ok": True,
        "kind": kind,
        "registries": [
            _registry_to_dict(registry, include_contacts=True)
            for registry in registries
        ],
    })


@registry_bp.post("/api/registries/<int:registry_id>/contacts")
@login_required
@role_required(100)
def api_registry_contact_link(registry_id):
    registry = BusinessRegistry.query.filter_by(id=registry_id).first()
    if not registry:
        return jsonify({"ok": False, "error": "Anagrafica non trovata"}), 404

    data = request.get_json(silent=True) or {}
    contact_id = data.get("contact_id")
    contact = None
    if contact_id:
        contact = RegistryContact.query.filter_by(id=contact_id).first()
        if not contact:
            return jsonify({"ok": False, "error": "Contatto non trovato"}), 404
    else:
        display_name = (data.get("display_name") or "").strip()
        if not display_name:
            return jsonify({"ok": False, "error": "Nome contatto obbligatorio"}), 400
        contact = RegistryContact(
            display_name=display_name,
            role=(data.get("role") or "").strip() or None,
            notes=(data.get("notes") or "").strip() or None,
        )
        db.session.add(contact)

        points = data.get("points") or []
        if isinstance(points, list):
            for point in points:
                contact_type = (point.get("contact_type") or point.get("type") or "").strip().lower()
                value = (point.get("value") or "").strip()
                if not contact_type or not value:
                    continue
                contact.points.append(RegistryContactPoint(
                    contact_type=contact_type,
                    value=value,
                    label=(point.get("label") or "").strip() or None,
                    is_primary=bool(point.get("is_primary")),
                ))

    link = BusinessRegistryContactLink.query.filter_by(registry_id=registry.id, contact_id=contact.id).first()
    if not link:
        link = BusinessRegistryContactLink(registry=registry, contact=contact)
        db.session.add(link)
    link.role = (data.get("link_role") or data.get("role") or "").strip() or link.role
    link.notes = (data.get("link_notes") or "").strip() or link.notes
    link.is_primary = bool(data.get("is_primary", link.is_primary))
    link.is_active = True

    db.session.commit()
    return jsonify({"ok": True, "registry": _registry_to_dict(registry, include_contacts=True)})


@registry_bp.delete("/api/registries/<int:registry_id>/contacts/<int:contact_id>")
@login_required
@role_required(100)
def api_registry_contact_unlink(registry_id, contact_id):
    link = BusinessRegistryContactLink.query.filter_by(registry_id=registry_id, contact_id=contact_id).first()
    if not link:
        return jsonify({"ok": False, "error": "Associazione non trovata"}), 404
    link.is_active = False
    db.session.commit()
    return jsonify({"ok": True})
