from datetime import datetime

from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required

from extensions import db
from models import CourierAccount, CourierIntegration, ExternalOrder, Shipment, ShipmentTrackingEvent
from tools.log_utils import get_logger
from tools.push_notifications import send_shipment_push_to_staff
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
logger = get_logger("shipping")
NOTIFIABLE_SHIPMENT_STATUSES = {"out_for_delivery", "delivered", "exception"}


def _parse_datetime(value):
    if not value:
        return None
    return datetime.fromisoformat(str(value).strip())


def _parse_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _account_payload(account):
    return account.to_dict()


def _courier_code_from_poleepo(value):
    raw = str(value or "").strip().upper()
    if raw.startswith("BRT"):
        return "brt"
    if raw.startswith("GLS"):
        return "gls"
    if raw.startswith("DHL"):
        return "dhl"
    return raw.lower() or "unknown"


def _address_from_poleepo(address):
    if not isinstance(address, dict):
        return None
    pieces = [
        address.get("address"),
        address.get("postcode"),
        address.get("city"),
        address.get("state_iso"),
        address.get("country_iso"),
    ]
    return ", ".join(str(piece).strip() for piece in pieces if str(piece or "").strip()) or None


def _recipient_from_poleepo(address):
    if not isinstance(address, dict):
        return None
    return " ".join(
        str(piece).strip()
        for piece in [address.get("name"), address.get("surname")]
        if str(piece or "").strip()
    ) or None


def _parse_poleepo_shipping_ids(raw_payload):
    shippings = (raw_payload or {}).get("shippings") or []
    if not isinstance(shippings, list):
        return []
    ids = []
    for item in shippings:
        if isinstance(item, dict):
            value = item.get("id")
        else:
            value = item
        if value is not None and str(value).strip():
            ids.append(str(value).strip())
    return ids


def _default_courier_account(courier_code):
    return (
        CourierAccount.query.filter_by(courier_code=courier_code, account_type="webservice", is_enabled=True).order_by(CourierAccount.id).first()
        or CourierAccount.query.filter_by(courier_code=courier_code, is_enabled=True).order_by(CourierAccount.id).first()
    )


def _shipment_tracking_number(shipping_data):
    return str(
        shipping_data.get("parcel_id")
        or shipping_data.get("tracking_code")
        or shipping_data.get("tracking")
        or shipping_data.get("id")
        or ""
    ).strip()


def _upsert_shipment_from_poleepo(order, shipping_data):
    courier_code = _courier_code_from_poleepo(shipping_data.get("carrier"))
    if courier_code not in {item["code"] for item in courier_options()}:
        return None, False
    tracking_number = _shipment_tracking_number(shipping_data)
    if not tracking_number:
        return None, False
    shipment = Shipment.query.filter_by(courier_code=courier_code, tracking_number=tracking_number).first()
    created = False
    if not shipment:
        shipment = Shipment(courier_code=courier_code, tracking_number=tracking_number)
        db.session.add(shipment)
        created = True
    account = _default_courier_account(courier_code)
    shipment.courier_account_id = shipment.courier_account_id or (account.id if account else None)
    shipment.courier_name = next((item["name"] for item in courier_options() if item["code"] == courier_code), courier_code.upper())
    shipment.source = "poleepo"
    shipment.external_order_id = order.external_id
    shipment.reference = shipping_data.get("reference") or order.order_number
    shipment.customer_name = order.customer_name
    shipment.recipient_name = _recipient_from_poleepo(shipping_data.get("delivery_address")) or order.recipient_name
    shipment.recipient_address = _address_from_poleepo(shipping_data.get("delivery_address")) or order.recipient_address
    shipment.shipped_at = _parse_datetime(shipping_data.get("creation_date"))
    shipment.raw_payload = {"poleepo_shipping": shipping_data}
    return shipment, created


def _sync_order_shipments_from_poleepo(connector, order):
    imported = 0
    updated = 0
    errors = []
    for shipping_id in _parse_poleepo_shipping_ids(order.raw_payload):
        try:
            shipping_data = connector.shipping_detail(shipping_id)
            shipment, created = _upsert_shipment_from_poleepo(order, shipping_data)
            if not shipment:
                continue
            imported += 1 if created else 0
            updated += 0 if created else 1
        except Exception as exc:
            errors.append({"shipping_id": shipping_id, "error": str(exc)})
    return {"imported": imported, "updated": updated, "errors": errors}


def _notify_shipment_status_change(shipment, previous_status):
    if shipment.status == previous_status or shipment.status not in NOTIFIABLE_SHIPMENT_STATUSES:
        return None
    titles = {
        "out_for_delivery": "Spedizione in consegna",
        "delivered": "Spedizione consegnata",
        "exception": "Problema spedizione",
    }
    try:
        return send_shipment_push_to_staff(shipment, title=titles.get(shipment.status, "Spedizione aggiornata"))
    except Exception:
        logger.exception("Invio push spedizione fallito shipment_id=%s", shipment.id)
        return None


def _accounts_for_shipment(shipment):
    accounts = []
    if shipment.courier_account_id:
        account = CourierAccount.query.filter_by(id=shipment.courier_account_id, is_enabled=True).first()
        if account:
            accounts.append(account)
    accounts_query = CourierAccount.query.filter(
        CourierAccount.courier_code == shipment.courier_code,
        CourierAccount.is_enabled.is_(True),
    )
    if shipment.courier_account_id:
        accounts_query = accounts_query.filter(CourierAccount.id != shipment.courier_account_id)
    accounts.extend(accounts_query.order_by(CourierAccount.account_type, CourierAccount.name).all())
    return accounts


def _refresh_shipment_tracking(shipment):
    integration = CourierIntegration.query.filter_by(code=shipment.courier_code).first()
    previous_status = shipment.status
    result = connector_for(shipment.courier_code, integration, accounts=_accounts_for_shipment(shipment)).track(shipment.tracking_number)
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
    return previous_status


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


@shipping_bp.get("/api/courier-accounts")
@login_required
@role_required(30)
def api_courier_accounts():
    courier = (request.args.get("courier") or "").strip().lower()
    query = CourierAccount.query
    if courier:
        query = query.filter(CourierAccount.courier_code == courier)
    accounts = query.order_by(CourierAccount.courier_code, CourierAccount.account_type, CourierAccount.name).all()
    return jsonify({"ok": True, "accounts": [_account_payload(account) for account in accounts]})


@shipping_bp.post("/api/courier-accounts")
@login_required
@role_required(30)
def api_save_courier_account():
    data = request.get_json(silent=True) or {}
    account_id = _parse_int(data.get("id"))
    courier_code = (data.get("courier_code") or "").strip().lower()
    account_type = (data.get("account_type") or "").strip().lower()
    name = (data.get("name") or "").strip()
    if courier_code not in {item["code"] for item in courier_options()}:
        return jsonify({"ok": False, "error": "Corriere non valido"}), 400
    if account_type not in {"portal", "webservice"}:
        return jsonify({"ok": False, "error": "Tipo account non valido"}), 400
    if not name:
        return jsonify({"ok": False, "error": "Nome account mancante"}), 400

    account = CourierAccount.query.get(account_id) if account_id else None
    if not account:
        account = CourierAccount()
        db.session.add(account)
    account.courier_code = courier_code
    account.account_type = account_type
    account.name = name
    account.base_url = (data.get("base_url") or "").strip() or None
    account.username = (data.get("username") or "").strip() or None
    password = data.get("password")
    if password:
        account.password_encrypted = str(password)
    account.extra_config = data.get("extra_config") if isinstance(data.get("extra_config"), dict) else {}
    account.is_enabled = bool(data.get("is_enabled", True))
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": f"Errore salvataggio account corriere: {exc}"}), 500
    return jsonify({"ok": True, "account": _account_payload(account)})


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
    account_id = _parse_int(data.get("courier_account_id"))
    account = None
    if account_id:
        account = CourierAccount.query.filter_by(id=account_id, courier_code=courier_code).first()
        if not account:
            return jsonify({"ok": False, "error": "Account corriere non valido"}), 400
    shipment.courier_name = next((item["name"] for item in courier_options() if item["code"] == courier_code), courier_code.upper())
    shipment.courier_account_id = account.id if account else None
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
    try:
        previous_status = _refresh_shipment_tracking(shipment)
    except ShippingConnectorNotConfigured as exc:
        shipment.last_error = str(exc)
        db.session.commit()
        return jsonify({"ok": False, "error": str(exc), "shipment": shipment.to_dict()}), 409
    except ShippingConnectorError as exc:
        shipment.last_error = str(exc)
        db.session.commit()
        return jsonify({"ok": False, "error": str(exc), "shipment": shipment.to_dict()}), 502

    db.session.commit()
    push_result = _notify_shipment_status_change(shipment, previous_status)
    return jsonify({"ok": True, "shipment": shipment.to_dict(), "notification": push_result})


@shipping_bp.post("/api/shipments/refresh-open")
@login_required
@role_required(30)
def api_refresh_open_shipments():
    data = request.get_json(silent=True) or {}
    limit = min(max(_parse_int(data.get("limit")) or 50, 1), 200)
    shipments = (
        Shipment.query
        .filter(Shipment.status.notin_(["delivered"]))
        .order_by(Shipment.last_tracking_at.asc().nullsfirst(), Shipment.updated_at.asc())
        .limit(limit)
        .all()
    )
    refreshed = 0
    errors = []
    changed = []
    for shipment in shipments:
        try:
            previous_status = _refresh_shipment_tracking(shipment)
            refreshed += 1
            if shipment.status != previous_status:
                changed.append((shipment.id, previous_status, shipment.status))
        except (ShippingConnectorNotConfigured, ShippingConnectorError) as exc:
            shipment.last_error = str(exc)
            errors.append({"shipment_id": shipment.id, "error": str(exc)})
        except Exception as exc:
            shipment.last_error = str(exc)
            errors.append({"shipment_id": shipment.id, "error": str(exc)})
    db.session.commit()
    notifications = []
    for shipment_id, previous_status, _new_status in changed:
        shipment = Shipment.query.get(shipment_id)
        if shipment:
            notifications.append(_notify_shipment_status_change(shipment, previous_status))
    return jsonify({"ok": True, "refreshed": refreshed, "changed": len(changed), "errors": errors[:20], "notifications": notifications})


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


@shipping_bp.post("/api/poleepo/sync-shipments")
@login_required
@role_required(30)
def api_poleepo_sync_shipments():
    data = request.get_json(silent=True) or {}
    limit = _parse_int(data.get("limit")) or 100
    connector = PoleepoConnector()
    orders = (
        ExternalOrder.query.filter_by(source="poleepo")
        .order_by(ExternalOrder.updated_at.desc(), ExternalOrder.id.desc())
        .limit(min(max(limit, 1), 300))
        .all()
    )
    imported = 0
    updated = 0
    errors = []
    try:
        for order in orders:
            result = _sync_order_shipments_from_poleepo(connector, order)
            imported += result["imported"]
            updated += result["updated"]
            errors.extend({"order_id": order.id, **item} for item in result["errors"])
        db.session.commit()
    except ShippingConnectorNotConfigured as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 409
    except ShippingConnectorError as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 502
    except Exception as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": f"Errore sincronizzazione spedizioni Poleepo: {exc}"}), 500
    return jsonify({"ok": True, "imported": imported, "updated": updated, "errors": errors[:20]})


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
    shipments_imported = 0
    shipments_updated = 0
    shipment_errors = []
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
            shipment_result = _sync_order_shipments_from_poleepo(connector, order)
            shipments_imported += shipment_result["imported"]
            shipments_updated += shipment_result["updated"]
            shipment_errors.extend({"order_id": order.id, **item} for item in shipment_result["errors"])
        if integration:
            integration.last_sync_at = now
            integration.is_enabled = True
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": f"Errore salvataggio ordini Poleepo: {exc}"}), 500
    return jsonify({
        "ok": True,
        "imported": imported,
        "updated": updated,
        "total": len(remote_orders),
        "shipments_imported": shipments_imported,
        "shipments_updated": shipments_updated,
        "shipment_errors": shipment_errors[:20],
    })
