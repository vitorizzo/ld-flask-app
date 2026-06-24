from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import os

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


def _decimal_number(value, *, default=0):
    if value in (None, ""):
        return default
    try:
        return float(Decimal(str(value).replace(",", ".")))
    except (InvalidOperation, TypeError, ValueError):
        return default


def _bool_value(value, *, default=False):
    if value in (None, ""):
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on", "si"}


def _poleepo_product_payload(data):
    data = data if isinstance(data, dict) else {}
    required = ["sku", "title", "price", "vat_rate", "main_category_id"]
    missing = [field for field in required if str(data.get(field) or "").strip() == ""]
    if missing:
        raise ShippingConnectorError("Campi Poleepo obbligatori mancanti: " + ", ".join(missing))

    main_category_id = int(_decimal_number(data.get("main_category_id"), default=0))
    if main_category_id <= 0:
        raise ShippingConnectorError("Categoria Poleepo non valida")

    body = {
        "sku": str(data.get("sku") or "").strip(),
        "title": str(data.get("title") or "").strip(),
        "price": _decimal_number(data.get("price"), default=0),
        "vat_rate": _decimal_number(data.get("vat_rate"), default=22),
        "quantity": int(_decimal_number(data.get("quantity"), default=0)),
        "active": _bool_value(data.get("active"), default=True),
        "main_category_id": main_category_id,
    }

    for optional_field in ("weight", "width", "height", "depth"):
        if str(data.get(optional_field) or "").strip() != "":
            body[optional_field] = _decimal_number(data.get(optional_field), default=0)
    return body


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

    def import_orders(self, since: datetime | None = None, *, page_size: int = 100, max_pages: int = 50) -> list[dict]:
        token = self.access_token()
        updated_after = _format_poleepo_datetime(since)
        orders = []
        offset = 0
        page_size = min(max(int(page_size or 100), 1), 100)
        max_pages = min(max(int(max_pages or 50), 1), 200)
        for _page in range(max_pages):
            params = {"offset": offset, "max": page_size}
            if updated_after:
                params["updated_after"] = updated_after
            payload = self._request("GET", "/orders", token=token, params=params)
            page_orders = payload.get("data") or []
            if not page_orders:
                break
            orders.extend(page_orders)
            if len(page_orders) < page_size:
                break
            offset += page_size
        return orders

    @property
    def products_path(self):
        configured = self.integration.settings.get("products_path") if self.integration and self.integration.settings else None
        return configured or current_app.config.get("POLEEPO_PRODUCTS_PATH") or "/products"

    @property
    def image_delete_path(self):
        configured = self.integration.settings.get("image_delete_path") if self.integration and self.integration.settings else None
        return configured or current_app.config.get("POLEEPO_IMAGE_DELETE_PATH") or ""

    @property
    def image_upload_path(self):
        configured = self.integration.settings.get("image_upload_path") if self.integration and self.integration.settings else None
        return configured or current_app.config.get("POLEEPO_IMAGE_UPLOAD_PATH") or ""

    def _request_absolute(self, method: str, url: str, *, token: str | None = None, **kwargs):
        if not self.is_configured:
            raise ShippingConnectorNotConfigured("Credenziali Poleepo mancanti")
        headers = kwargs.pop("headers", {}) or {}
        headers.setdefault("Accept", "application/json")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        response = requests.request(
            method,
            url,
            headers=headers,
            timeout=20,
            **kwargs,
        )
        if response.status_code in (200, 202, 204):
            try:
                payload = response.json()
            except ValueError:
                payload = {"success": True, "raw": response.text[:1000]}
            return payload
        try:
            payload = response.json()
        except ValueError:
            payload = {"success": False, "message": response.text[:500]}
        if response.status_code >= 400 or payload.get("success") is False:
            message = payload.get("message") or f"Poleepo HTTP {response.status_code}"
            raise ShippingConnectorError(message)
        return payload

    def import_products(self, *, page_size: int = 100, max_pages: int = 50) -> list[dict]:
        token = self.access_token()
        products = []
        offset = 0
        page_size = min(max(int(page_size or 100), 1), 100)
        max_pages = min(max(int(max_pages or 50), 1), 200)
        for _page in range(max_pages):
            params = {"offset": offset, "max": page_size}
            payload = self._request("GET", self.products_path, token=token, params=params)
            page_products = payload.get("data") or []
            if isinstance(page_products, dict):
                page_products = page_products.get("items") or page_products.get("products") or page_products.get("data") or []
            if not page_products:
                break
            products.extend(page_products)
            if len(page_products) < page_size:
                break
            offset += page_size
        return products

    def shipping_detail(self, shipping_id) -> dict:
        token = self.access_token()
        payload = self._request("GET", f"/shippings/{shipping_id}", token=token)
        return payload.get("data") or {}

    def create_product(self, *, payload=None):
        body = _poleepo_product_payload(payload)
        token = self.access_token()
        response = requests.post(
            f"{self.base_url}/products",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=60,
        )
        try:
            result = response.json()
        except ValueError:
            result = {"success": False, "message": response.text[:500]}
        if response.status_code not in (200, 201, 202) or result.get("success") is False:
            message = result.get("message") or f"Poleepo HTTP {response.status_code}"
            raise ShippingConnectorError(message)

        product = result.get("data") if isinstance(result.get("data"), dict) else result
        product_id = None
        external_url = None
        if isinstance(product, dict):
            product_id = product.get("id") or product.get("product_id") or product.get("external_id")
            external_url = product.get("url") or product.get("permalink") or product.get("link")
        if not product_id:
            raise ShippingConnectorError("Poleepo non ha restituito l'ID del prodotto creato")

        return {
            "product_id": str(product_id),
            "external_url": external_url,
            "raw_payload": result,
            "status_code": response.status_code,
        }

    def update_product(self, *, product_id=None, payload=None):
        if not product_id:
            raise ShippingConnectorError("ID prodotto Poleepo mancante")
        body = _poleepo_product_payload(payload)
        token = self.access_token()
        response = requests.put(
            f"{self.base_url}/products/{product_id}",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=60,
        )
        if response.status_code == 204:
            data = {"success": True}
        else:
            try:
                data = response.json()
            except ValueError:
                data = {"success": response.status_code in (200, 201, 202), "message": response.text[:500]}
        if response.status_code not in (200, 201, 202, 204) or data.get("success") is False:
            message = data.get("message") or f"Poleepo HTTP {response.status_code}"
            raise ShippingConnectorError(message)
        product = data.get("data") if isinstance(data.get("data"), dict) else data
        external_url = None
        if isinstance(product, dict):
            external_url = product.get("url") or product.get("permalink") or product.get("link")
        return {
            "product_id": str(product_id),
            "external_url": external_url,
            "raw_payload": data,
            "status_code": response.status_code,
        }

    def delete_image(self, *, product_id=None, image_id=None, image_url=None):
        token = self.access_token()
        candidates = []

        configured = (self.image_delete_path or "").strip()
        if configured:
            if configured.startswith("http://") or configured.startswith("https://"):
                candidates.append(configured.format(
                    product_id=product_id or "",
                    image_id=image_id or "",
                    image_url=image_url or "",
                ))
            else:
                candidates.append(f"{self.base_url}{configured.format(product_id=product_id or '', image_id=image_id or '', image_url=image_url or '')}")

        if image_url:
            candidates.append(str(image_url).strip())

        if product_id and image_id:
            candidates.extend([
                f"{self.base_url}/products/{product_id}/images/{image_id}",
                f"{self.base_url}/images/products/{product_id}/{image_id}",
                f"{self.base_url}/images/{product_id}/{image_id}",
                f"{self.base_url}/images/{image_id}",
            ])

        last_error = None
        tried = set()
        for candidate in candidates:
            if not candidate or candidate in tried:
                continue
            tried.add(candidate)
            try:
                payload = self._request_absolute("DELETE", candidate, token=token)
                return {
                    "status_code": 200,
                    "remote_url": candidate,
                    "raw_payload": payload,
                }
            except ShippingConnectorError as exc:
                message = str(exc)
                last_error = message
                if any(token in message.lower() for token in ("404", "not found", "405", "method not allowed")):
                    continue
                continue

        raise ShippingConnectorError(last_error or "Delete immagini Poleepo non disponibile")

    def upload_image(self, *, product_id=None, image_path=None, filename=None, mime_type=None, source_url=None):
        token = self.access_token()
        if not product_id:
            raise ShippingConnectorError("ID prodotto Poleepo mancante")
        if not image_path or not os.path.exists(image_path):
            raise ShippingConnectorError(f"Immagine non trovata: {image_path}")

        safe_filename = filename or os.path.basename(image_path)
        content_type = mime_type or "application/octet-stream"
        upload_fields = ["image", "file", "media", "upload"]
        json_fields = ["url", "image_url", "source_url", "remote_url"]
        candidates = []

        configured = (self.image_upload_path or "").strip()
        if configured:
            if configured.startswith("http://") or configured.startswith("https://"):
                candidates.append(configured.format(product_id=product_id, filename=safe_filename))
            else:
                candidates.append(f"{self.base_url}{configured.format(product_id=product_id, filename=safe_filename)}")

        candidates.extend([
            f"{self.base_url}/products/{product_id}/images",
            f"{self.base_url}/products/{product_id}/image",
            f"{self.base_url}/images/products/{product_id}",
            f"{self.base_url}/images/{product_id}",
        ])

        last_error = None
        tried = set()
        attempted = []
        for candidate in candidates:
            if not candidate or candidate in tried:
                continue
            tried.add(candidate)
            for upload_field in upload_fields:
                try:
                    attempted.append({"url": candidate, "field": upload_field, "mode": "multipart"})
                    with open(image_path, "rb") as image_file:
                        response = requests.post(
                            candidate,
                            headers={
                                "Accept": "application/json",
                                "Authorization": f"Bearer {token}",
                            },
                            files={upload_field: (safe_filename, image_file, content_type)},
                            timeout=60,
                        )
                    if response.status_code not in (200, 201, 202, 204):
                        raise ShippingConnectorError(f"Poleepo HTTP {response.status_code}: {response.text[:500]}")
                    try:
                        payload = response.json()
                    except ValueError:
                        payload = {"success": True, "raw": response.text[:1000]}
                    image_id = None
                    remote_url = None
                    if isinstance(payload, dict):
                        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
                        image_id = (
                            data.get("id")
                            or data.get("image_id")
                            or data.get("media_id")
                            or data.get("external_id")
                        )
                        remote_url = (
                            data.get("url")
                            or data.get("remote_url")
                            or data.get("link")
                            or data.get("href")
                        )
                    if not remote_url:
                        remote_url = candidate
                    return {
                        "status_code": response.status_code,
                        "image_id": str(image_id) if image_id is not None else None,
                        "remote_url": remote_url,
                        "raw_payload": payload,
                    }
                except ShippingConnectorError as exc:
                    message = str(exc)
                    last_error = message
                    if any(token in message.lower() for token in ("404", "not found", "405", "method not allowed", "415", "500", "502", "503", "504")):
                        continue
                    continue
                except requests.RequestException as exc:
                    last_error = str(exc)
                    continue

            if source_url:
                for json_field in json_fields:
                    try:
                        attempted.append({"url": candidate, "field": json_field, "mode": "json"})
                        response = requests.post(
                            candidate,
                            headers={
                                "Accept": "application/json",
                                "Authorization": f"Bearer {token}",
                                "Content-Type": "application/json",
                            },
                            json={json_field: source_url, "filename": safe_filename, "product_id": product_id},
                            timeout=60,
                        )
                        if response.status_code not in (200, 201, 202, 204):
                            raise ShippingConnectorError(f"Poleepo HTTP {response.status_code}: {response.text[:500]}")
                        try:
                            payload = response.json()
                        except ValueError:
                            payload = {"success": True, "raw": response.text[:1000]}
                        image_id = None
                        remote_url = None
                        if isinstance(payload, dict):
                            data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
                            image_id = (
                                data.get("id")
                                or data.get("image_id")
                                or data.get("media_id")
                                or data.get("external_id")
                            )
                            remote_url = (
                                data.get("url")
                                or data.get("remote_url")
                                or data.get("link")
                                or data.get("href")
                            )
                        if not remote_url:
                            remote_url = candidate
                        return {
                            "status_code": response.status_code,
                            "image_id": str(image_id) if image_id is not None else None,
                            "remote_url": remote_url,
                            "raw_payload": payload,
                        }
                    except ShippingConnectorError as exc:
                        message = str(exc)
                        last_error = message
                        if any(token in message.lower() for token in ("404", "not found", "405", "method not allowed", "415", "500", "502", "503", "504")):
                            continue
                        continue
                    except requests.RequestException as exc:
                        last_error = str(exc)
                        continue

            try:
                attempted.append({"url": candidate, "field": "binary", "mode": "raw"})
                with open(image_path, "rb") as image_file:
                    response = requests.put(
                        candidate,
                        headers={
                            "Accept": "application/json",
                            "Authorization": f"Bearer {token}",
                            "Content-Type": content_type,
                            "X-Filename": safe_filename,
                        },
                        data=image_file.read(),
                        timeout=60,
                    )
                if response.status_code not in (200, 201, 202, 204):
                    raise ShippingConnectorError(f"Poleepo HTTP {response.status_code}: {response.text[:500]}")
                try:
                    payload = response.json()
                except ValueError:
                    payload = {"success": True, "raw": response.text[:1000]}
                image_id = None
                remote_url = None
                if isinstance(payload, dict):
                    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
                    image_id = (
                        data.get("id")
                        or data.get("image_id")
                        or data.get("media_id")
                        or data.get("external_id")
                    )
                    remote_url = (
                        data.get("url")
                        or data.get("remote_url")
                        or data.get("link")
                        or data.get("href")
                    )
                if not remote_url:
                    remote_url = candidate
                return {
                    "status_code": response.status_code,
                    "image_id": str(image_id) if image_id is not None else None,
                    "remote_url": remote_url,
                    "raw_payload": payload,
                }
            except ShippingConnectorError as exc:
                message = str(exc)
                last_error = message
                if any(token in message.lower() for token in ("404", "not found", "405", "method not allowed", "415", "500", "502", "503", "504")):
                    continue
                continue
            except requests.RequestException as exc:
                last_error = str(exc)
                continue

        attempted_text = ", ".join(
            f"{item.get('mode', 'multipart')}:{item['field']}@{item['url']}" for item in attempted
        )
        suffix = f" | tentativi: {attempted_text}" if attempted_text else ""
        if source_url:
            try:
                attempted.append({"url": f"{self.base_url}/products/{product_id}", "field": "images", "mode": "put-product"})
                payload = self.update_product(
                    product_id=product_id,
                    payload={
                        "images": [
                            {
                                "principal": True,
                                "url": source_url,
                            }
                        ]
                    },
                )
                product = payload.get("data") if isinstance(payload, dict) else {}
                images = product.get("images") if isinstance(product, dict) else None
                image_id = None
                remote_url = source_url
                if isinstance(images, list) and images:
                    first_image = images[0] if isinstance(images[0], dict) else {}
                    image_id = first_image.get("id")
                    remote_url = first_image.get("url") or source_url
                return {
                    "status_code": 200,
                    "image_id": str(image_id) if image_id is not None else None,
                    "remote_url": remote_url,
                    "raw_payload": payload,
                }
            except ShippingConnectorError as exc:
                last_error = str(exc)

        raise ShippingConnectorError((last_error or "Upload immagini Poleepo non disponibile") + suffix)


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
