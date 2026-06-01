from datetime import datetime

from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required

from extensions import db
from models import CourierIntegration, ExternalOrder, Shipment, ShipmentTrackingEvent
from tools.role_required import role_required
from tools.shipping_connectors import (
    ShippingConnectorError,
    ShippingConnectorNotConfigured,
    connector_for,
    courier_options,
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
    integration = CourierIntegration.query.filter_by(code="poleepo").first()
    if not integration or not integration.is_enabled:
        return jsonify({"ok": False, "error": "Integrazione Poleepo non configurata"}), 409
    return jsonify({"ok": False, "error": "Import Poleepo pronto per il collegamento API, ma mancano specifiche e credenziali"}), 409
