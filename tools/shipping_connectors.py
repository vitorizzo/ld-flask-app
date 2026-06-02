from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import requests
from flask import current_app


class ShippingConnectorError(RuntimeError):
    pass


class ShippingConnectorNotConfigured(ShippingConnectorError):
    pass


@dataclass
class TrackingResult:
    status: str
    status_label: str
    events: list[dict]
    raw_payload: dict


class BaseCourierConnector:
    code = ""
    name = ""

    def __init__(self, integration=None, accounts=None):
        self.integration = integration
        self.accounts = accounts or []

    @property
    def is_configured(self):
        return bool(self.integration and self.integration.is_enabled and self.integration.credentials) or bool(self.accounts)

    def track(self, tracking_number: str) -> TrackingResult:
        if not self.accounts:
            raise ShippingConnectorNotConfigured(f"Nessun account {self.name} configurato")
        raise ShippingConnectorNotConfigured(f"Tracking {self.name} non ancora collegato al web service reale")


class BrtConnector(BaseCourierConnector):
    code = "brt"
    name = "BRT"


class GlsConnector(BaseCourierConnector):
    code = "gls"
    name = "GLS"


class DhlConnector(BaseCourierConnector):
    code = "dhl"
    name = "DHL"


COURIER_CONNECTORS = {
    BrtConnector.code: BrtConnector,
    GlsConnector.code: GlsConnector,
    DhlConnector.code: DhlConnector,
}


def courier_options():
    return [{"code": cls.code, "name": cls.name} for cls in COURIER_CONNECTORS.values()]


def connector_for(code: str, integration=None, accounts=None):
    cls = COURIER_CONNECTORS.get((code or "").strip().lower())
    if not cls:
        raise ShippingConnectorError("Corriere non supportato")
    return cls(integration=integration, accounts=accounts)


def _format_poleepo_datetime(value: datetime | None):
    if not value:
        return None
    if value.tzinfo:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.replace(microsecond=0).isoformat() + "Z"


class PoleepoConnector:
    code = "poleepo"
    name = "Poleepo"

    def __init__(self, integration=None):
        self.integration = integration

    @property
    def is_configured(self):
        return bool(self.base_url and self.client_id and self.client_secret)

    @property
    def base_url(self):
        configured = self.integration.base_url if self.integration and self.integration.base_url else None
        return (configured or current_app.config.get("POLEEPO_URL") or "").rstrip("/")

    @property
    def credentials(self):
        stored = self.integration.credentials if self.integration and self.integration.credentials else {}
        return {
            "client_id": stored.get("client_id") or current_app.config.get("POLEEPO_PKEY") or "",
            "client_secret": stored.get("client_secret") or current_app.config.get("POLEEPO_PPKEY") or "",
        }

    @property
    def client_id(self):
        return self.credentials["client_id"]

    @property
    def client_secret(self):
        return self.credentials["client_secret"]

    def _request(self, method: str, path: str, *, token: str | None = None, **kwargs):
        if not self.is_configured:
            raise ShippingConnectorNotConfigured("Credenziali Poleepo mancanti")
        headers = kwargs.pop("headers", {}) or {}
        headers.setdefault("Accept", "application/json")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        response = requests.request(
            method,
            f"{self.base_url}{path}",
            headers=headers,
            timeout=20,
            **kwargs,
        )
        try:
            payload = response.json()
        except ValueError:
            payload = {"success": False, "message": response.text[:500]}
        if response.status_code >= 400 or payload.get("success") is False:
            message = payload.get("message") or f"Poleepo HTTP {response.status_code}"
            raise ShippingConnectorError(message)
        return payload

    def access_token(self):
        payload = self._request(
            "POST",
            "/oauth/access_token",
            json={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant": "client_credentials",
            },
        )
        token = ((payload.get("data") or {}).get("access_token") or "").strip()
        if not token:
            raise ShippingConnectorError("Access token Poleepo non presente nella risposta")
        return token

    def import_orders(self, since: datetime | None = None) -> list[dict]:
        token = self.access_token()
        params = {"offset": 0, "max": 100}
        updated_after = _format_poleepo_datetime(since)
        if updated_after:
            params["updated_after"] = updated_after
        payload = self._request("GET", "/orders", token=token, params=params)
        return payload.get("data") or []


def _join_name(*parts):
    return " ".join(str(part).strip() for part in parts if str(part or "").strip())


def _address_text(address):
    if not isinstance(address, dict):
        return ""
    pieces = [
        address.get("address"),
        address.get("postcode") or address.get("zip"),
        address.get("city"),
        address.get("state_iso") or address.get("province"),
        address.get("country_iso") or address.get("country"),
    ]
    return ", ".join(str(piece).strip() for piece in pieces if str(piece or "").strip())


def _parse_decimal(value):
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _parse_remote_datetime(value):
    if not value:
        return None
    raw = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed


def normalize_poleepo_order(order: dict) -> dict:
    customer = order.get("customer") if isinstance(order.get("customer"), dict) else {}
    address = order.get("delivery_address") if isinstance(order.get("delivery_address"), dict) else {}
    customer_name = _join_name(
        customer.get("firstname") or customer.get("name"),
        customer.get("lastname") or customer.get("surname"),
    )
    external_id = str(order.get("id") or order.get("order_id") or order.get("reference_id") or "").strip()
    status = order.get("status")
    if isinstance(status, dict):
        status_value = status.get("name") or status.get("id") or "imported"
    else:
        status_value = status or "imported"
    return {
        "source": "poleepo",
        "external_id": external_id,
        "order_number": str(order.get("reference_id") or order.get("order_id") or order.get("source_id") or external_id),
        "status": str(status_value),
        "customer_name": customer_name or None,
        "recipient_name": customer_name or None,
        "recipient_address": _address_text(address) or None,
        "order_total": _parse_decimal(order.get("total_price") or order.get("total")),
        "currency": str(order.get("currency") or "EUR")[:3],
        "ordered_at": _parse_remote_datetime(order.get("order_date") or order.get("creation_date")),
        "raw_payload": order,
    }
