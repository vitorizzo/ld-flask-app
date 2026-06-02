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
    default_tracking_url = "https://api.brt.it/rest/v1/tracking/parcelID/{tracking_number}"

    def _tracking_url(self, account, tracking_number: str):
        configured = (account.extra_config or {}).get("tracking_url") or account.base_url or self.default_tracking_url
        if "{parcel_id}" in configured:
            return configured.format(parcel_id=tracking_number, tracking_number=tracking_number)
        if "{tracking_number}" in configured:
            return configured.format(tracking_number=tracking_number, parcel_id=tracking_number)
        return configured.rstrip("/") + f"/{tracking_number}"

    def track(self, tracking_number: str) -> TrackingResult:
        if not self.accounts:
            raise ShippingConnectorNotConfigured("Nessun account BRT configurato")

        last_error = None
        for account in self.accounts:
            if not account.username or not account.password_encrypted:
                continue
            url = self._tracking_url(account, tracking_number)
            try:
                response = requests.get(
                    url,
                    headers={
                        "Accept": "application/json",
                        "userID": account.username,
                        "password": account.password_encrypted,
                    },
                    timeout=20,
                )
            except requests.RequestException as exc:
                last_error = str(exc)
                continue
            try:
                payload = response.json()
            except ValueError:
                payload = {"raw": response.text[:1000]}
            if response.status_code >= 400:
                last_error = f"BRT HTTP {response.status_code}"
                continue
            result = _normalize_brt_tracking(payload)
            execution = ((payload.get("ttParcelIdResponse") or {}).get("executionMessage") or {})
            if execution.get("severity") == "ERROR" and result.status == "unknown":
                code = execution.get("codeDesc") or execution.get("code") or "Errore BRT"
                last_error = str(code)
                continue
            return result

        raise ShippingConnectorError(last_error or "Tracking BRT non disponibile")


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

    def shipping_detail(self, shipping_id) -> dict:
        token = self.access_token()
        payload = self._request("GET", f"/shippings/{shipping_id}", token=token)
        return payload.get("data") or {}


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


def _parse_brt_event_datetime(date_value, time_value):
    date_raw = str(date_value or "").strip()
    time_raw = str(time_value or "").strip()
    if not date_raw:
        return None
    candidates = [
        f"{date_raw} {time_raw}".strip(),
        date_raw,
    ]
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%d.%m.%Y %H.%M",
        "%d.%m.%Y %H.%M.%S",
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d.%m.%Y",
    ]
    for candidate in candidates:
        for fmt in formats:
            try:
                return datetime.strptime(candidate, fmt)
            except ValueError:
                continue
    return None


def _shipment_status_from_text(value):
    text = str(value or "").strip().lower()
    if not text:
        return "unknown", "Sconosciuto"
    if "in consegna" in text or "messa in consegna" in text:
        return "out_for_delivery", "In consegna"
    if "disponibile per il ritiro" in text or "fermopoint" in text:
        return "out_for_delivery", "Disponibile per ritiro"
    if "consegn" in text:
        return "delivered", "Consegnata"
    if any(token in text for token in ("giacenza", "mancata", "non consegn", "errore", "anomalia", "respinta")):
        return "exception", "Problema"
    if any(token in text for token in ("partita", "ritirata", "transito", "hub", "filiale", "affidata")):
        return "in_transit", "In transito"
    return "unknown", value


def _normalize_brt_tracking(payload):
    response = payload.get("ttParcelIdResponse") if isinstance(payload, dict) else {}
    response = response or {}
    shipment_data = ((response.get("bolla") or {}).get("dati_spedizione") or {})
    status_text = " ".join(
        str(piece or "").strip()
        for piece in [
            shipment_data.get("descrizione_stato_sped_parte1"),
            shipment_data.get("descrizione_stato_sped_parte2"),
            shipment_data.get("stato_sped_parte1"),
            shipment_data.get("stato_sped_parte2"),
        ]
        if str(piece or "").strip()
    )
    events = []
    for wrapper in response.get("lista_eventi") or []:
        event = wrapper.get("evento") if isinstance(wrapper, dict) else {}
        if not event or not any(event.values()):
            continue
        description = str(event.get("descrizione") or "").strip()
        event_status, _ = _shipment_status_from_text(description)
        events.append({
            "event_at": _parse_brt_event_datetime(event.get("data"), event.get("ora")),
            "status": event_status,
            "location": event.get("filiale") or None,
            "description": description,
            "raw_payload": event,
        })
    if events and not status_text:
        status_text = events[0].get("description") or ""
    status, status_label = _shipment_status_from_text(status_text)
    return TrackingResult(status=status, status_label=status_label, events=events, raw_payload=payload)


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
