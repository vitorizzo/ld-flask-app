from datetime import datetime

from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required

from extensions import db
from models import CourierIntegration, ExternalOrder, Shipment, ShipmentTrackingEvent
from tools.role_required import role_required
from tools.shipping_connectors import (
    PoleepoConnector,
    ShippingConnectorError,
    ShippingConnectorNotConfigured,
    connector_for,
    courier_options,
    normalize_poleepo_order,
)


shipping_bp = Blueprint("shipping", __name__)


def _parse_datetime(value):
    if not value:
        return None
    return datetime.fromisoformat(str(value).strip())


def _shipment_query():
    query = Shipment.query
    q = (request.args.get("q") or "").strip()
    courier = (request.args.get("courier") or "").strip().lower()
    status = (request.args.get("status") or "").strip()
    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(
                Shipment.tracking_number.ilike(like),
                Shipment.customer_name.ilike(like),
                Shipment.recipient_name.ilike(like),
                Shipment.external_order_id.ilike(like),
                Shipment.reference.ilike(like),
            )
        )
    if courier:
        query = query.filter(Shipment.courier_code == courier)
    if status:
        query = query.filter(Shipment.status == status)
    return query


@shipping_bp.get("/")
@login_required
@role_required(30)
def index():
    return render_template("shipping/index.html", couriers=courier_options())


@shipping_bp.get("/api/shipments")
@login_required
@role_required(30)
def api_shipments():
    shipments = (
        _shipment_query()
        .order_by(Shipment.updated_at.desc(), Shipment.id.desc())
        .limit(200)
        .all()
    )
    return jsonify({"ok": True, "shipments": [shipment.to_dict() for shipment in shipments]})


@shipping_bp.post("/api/shipments")
@login_required
@role_required(30)
def api_create_shipment():
    data = request.get_json(silent=True) or {}
    courier_code = (data.get("courier_code") or "").strip().lower()
    tracking_number = (data.get("tracking_number") or "").strip()
    if courier_code not in {item["code"] for item in courier_options()}:
        return jsonify({"ok": False, "error": "Corriere non valido"}), 400
    if not tracking_number:
        return jsonify({"ok": False, "error": "Tracking mancante"}), 400

    shipment = Shipment.query.filter_by(courier_code=courier_code, tracking_number=tracking_number).first()
    if not shipment:
        shipment = Shipment(courier_code=courier_code, tracking_number=tracking_number)
        db.session.add(shipment)
    shipment.courier_name = next((item["name"] for item in courier_options() if item["code"] == courier_code), courier_code.upper())
    shipment.customer_name = (data.get("customer_name") or "").strip() or None
    shipment.recipient_name = (data.get("recipient_name") or "").strip() or None
    shipment.recipient_address = (data.get("recipient_address") or "").strip() or None
    shipment.external_order_id = (data.get("external_order_id") or "").strip() or None
    shipment.reference = (data.get("reference") or "").strip() or None
    shipment.source = (data.get("source") or "manual").strip() or "manual"
    shipment.shipped_at = _parse_datetime(data.get("shipped_at"))
    db.session.commit()
    return jsonify({"ok": True, "shipment": shipment.to_dict()})


@shipping_bp.get("/api/shipments/<int:shipment_id>")
@login_required
@role_required(30)
def api_shipment_detail(shipment_id):
    shipment = Shipment.query.get_or_404(shipment_id)
    return jsonify({
        "ok": True,
        "shipment": shipment.to_dict(),
        "events": [event.to_dict() for event in sorted(shipment.tracking_events, key=lambda item: item.event_at or item.created_at, reverse=True)],
    })


@shipping_bp.post("/api/shipments/<int:shipment_id>/refresh")
@login_required
@role_required(30)
def api_refresh_shipment(shipment_id):
    shipment = Shipment.query.get_or_404(shipment_id)
    integration = CourierIntegration.query.filter_by(code=shipment.courier_code).first()
    try:
        result = connector_for(shipment.courier_code, integration).track(shipment.tracking_number)
    except ShippingConnectorNotConfigured as exc:
        shipment.last_error = str(exc)
        db.session.commit()
        return jsonify({"ok": False, "error": str(exc), "shipment": shipment.to_dict()}), 409
    except ShippingConnectorError as exc:
        shipment.last_error = str(exc)
        db.session.commit()
        return jsonify({"ok": False, "error": str(exc), "shipment": shipment.to_dict()}), 502

    shipment.status = result.status
    shipment.status_label = result.status_label
    shipment.last_tracking_at = datetime.utcnow()
    shipment.last_error = None
    shipment.raw_payload = result.raw_payload
    for item in result.events:
        db.session.add(ShipmentTrackingEvent(
            shipment_id=shipment.id,
            event_at=item.get("event_at"),
            status=item.get("status"),
            location=item.get("location"),
            description=item.get("description"),
            raw_payload=item,
        ))
    db.session.commit()
    return jsonify({"ok": True, "shipment": shipment.to_dict()})


@shipping_bp.get("/api/external-orders")
@login_required
@role_required(30)
def api_external_orders():
    q = (request.args.get("q") or "").strip()
    query = ExternalOrder.query.filter_by(source="poleepo")
    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(
                ExternalOrder.external_id.ilike(like),
                ExternalOrder.order_number.ilike(like),
                ExternalOrder.customer_name.ilike(like),
                ExternalOrder.recipient_name.ilike(like),
            )
        )
    orders = query.order_by(ExternalOrder.ordered_at.desc().nullslast(), ExternalOrder.id.desc()).limit(200).all()
    return jsonify({"ok": True, "orders": [order.to_dict() for order in orders]})


@shipping_bp.post("/api/poleepo/import")
@login_required
@role_required(30)
def api_poleepo_import():
    try:
        data = request.get_json(silent=True) or {}
        integration = CourierIntegration.query.filter_by(code="poleepo").first()
        if not integration:
            integration = CourierIntegration(code="poleepo", name="Poleepo", is_enabled=True)
            db.session.add(integration)
            db.session.flush()
        latest_sync = (
            ExternalOrder.query.filter_by(source="poleepo")
            .order_by(ExternalOrder.last_sync_at.desc().nullslast(), ExternalOrder.updated_at.desc())
            .first()
        )
        since = None
        if not data.get("force_full") and latest_sync and latest_sync.last_sync_at:
            since = latest_sync.last_sync_at
        connector = PoleepoConnector(integration=integration)
        remote_orders = connector.import_orders(since=since)
    except ShippingConnectorNotConfigured as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 409
    except ShippingConnectorError as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 502

    imported = 0
    updated = 0
    now = datetime.utcnow()
    try:
        for remote_order in remote_orders:
            normalized = normalize_poleepo_order(remote_order)
            if not normalized["external_id"]:
                continue
            order = ExternalOrder.query.filter_by(source="poleepo", external_id=normalized["external_id"]).first()
            if not order:
                order = ExternalOrder(source="poleepo", external_id=normalized["external_id"])
                db.session.add(order)
                imported += 1
            else:
                updated += 1
            order.order_number = normalized["order_number"]
            order.status = normalized["status"]
            order.customer_name = normalized["customer_name"]
            order.recipient_name = normalized["recipient_name"]
            order.recipient_address = normalized["recipient_address"]
            order.order_total = normalized["order_total"]
            order.currency = normalized["currency"]
            order.ordered_at = normalized["ordered_at"]
            order.raw_payload = normalized["raw_payload"]
            order.last_sync_at = now
        if integration:
            integration.last_sync_at = now
            integration.is_enabled = True
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": f"Errore salvataggio ordini Poleepo: {exc}"}), 500
    return jsonify({"ok": True, "imported": imported, "updated": updated, "total": len(remote_orders)})
