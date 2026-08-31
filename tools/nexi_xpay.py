from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import requests
from flask import current_app


SANDBOX_BASE_URL = "https://xpaysandbox.nexigroup.com/api/phoenix-0.0/psp/api"
PRODUCTION_BASE_URL = "https://xpay.nexigroup.com/api/phoenix-0.0/psp/api"
CLASSIC_SANDBOX_URL = "https://int-ecommerce.nexi.it/ecomm/ecomm/DispatcherServlet"
CLASSIC_PRODUCTION_URL = "https://ecommerce.nexi.it/ecomm/ecomm/DispatcherServlet"


class NexiXPayError(RuntimeError):
    """Errore sicuro da mostrare all'utente senza esporre credenziali o payload sensibili."""


class NexiXPayUncertainError(NexiXPayError):
    """La richiesta potrebbe essere stata acquisita dal provider: non e' sicuro ripeterla."""


@dataclass(frozen=True)
class HostedPaymentPageResult:
    hosted_page: str
    security_token: str


@dataclass(frozen=True)
class PayByLinkResult:
    link_id: str
    payment_url: str
    security_token: str
    expiration_date: str | None
    status: str | None


class NexiXPayClassic:
    """Firma e valida il flusso redirect XPay/Pagamento Semplice."""

    def __init__(self, alias: str, mac_key: str, environment: str = "sandbox"):
        self.alias = str(alias or "").strip()
        self.mac_key = str(mac_key or "").strip()
        normalized_environment = str(environment or "sandbox").strip().lower()
        self.environment = "production" if normalized_environment in {"production", "prod"} else "sandbox"
        self.endpoint = CLASSIC_PRODUCTION_URL if self.environment == "production" else CLASSIC_SANDBOX_URL
        if not self.alias or not self.mac_key:
            raise NexiXPayError("Nexi XPay non e' configurato: mancano Alias o chiave MAC.")

    @classmethod
    def from_app(cls):
        return cls(
            alias=current_app.config.get("NEXI_XPAY_ALIAS"),
            mac_key=current_app.config.get("NEXI_XPAY_MAC_KEY"),
            environment=current_app.config.get("NEXI_XPAY_ENVIRONMENT", "sandbox"),
        )

    @staticmethod
    def _sha1(value: str) -> str:
        return hashlib.sha1(value.encode("utf-8")).hexdigest()

    def request_mac(self, order_id: str, currency: str, amount: str) -> str:
        message = f"codTrans={order_id}divisa={currency}importo={amount}{self.mac_key}"
        return self._sha1(message)

    def response_mac(self, values: dict[str, Any]) -> str:
        message = (
            f"codTrans={values.get('codTrans', '')}"
            f"esito={values.get('esito', '')}"
            f"importo={values.get('importo', '')}"
            f"divisa={values.get('divisa', '')}"
            f"data={values.get('data', '')}"
            f"orario={values.get('orario', '')}"
            f"codAut={values.get('codAut', '')}"
            f"{self.mac_key}"
        )
        return self._sha1(message)

    def verify_response(self, values: dict[str, Any]) -> bool:
        supplied = str(values.get("mac") or "").strip().lower()
        return bool(supplied) and hmac.compare_digest(supplied, self.response_mac(values).lower())

    def payment_form(self, *, order_id: str, amount: str, result_url: str, cancel_url: str,
                     notification_url: str, email: str | None = None, description: str | None = None):
        fields = {
            "alias": self.alias,
            "importo": str(amount),
            "divisa": "EUR",
            "codTrans": str(order_id),
            "url": str(result_url),
            "url_back": str(cancel_url),
            "urlpost": str(notification_url),
            "languageId": "ITA",
        }
        if email:
            fields["mail"] = str(email)[:150]
        if description:
            fields["descrizione"] = str(description)[:2000]
        fields["mac"] = self.request_mac(fields["codTrans"], fields["divisa"], fields["importo"])
        return self.endpoint, fields


class NexiXPayClient:
    def __init__(self, api_key: str, environment: str = "sandbox", timeout: tuple[int, int] = (8, 25), session=None):
        self.api_key = str(api_key or "").strip()
        normalized_environment = str(environment or "sandbox").strip().lower()
        self.environment = "production" if normalized_environment in {"production", "prod"} else "sandbox"
        self.base_url = PRODUCTION_BASE_URL if self.environment == "production" else SANDBOX_BASE_URL
        self.timeout = timeout
        self.session = session or requests.Session()
        if not self.api_key:
            raise NexiXPayError("Nexi XPay non e' configurato: manca la API key.")

    @classmethod
    def from_app(cls):
        return cls(
            api_key=current_app.config.get("NEXI_XPAY_API_KEY"),
            environment=current_app.config.get("NEXI_XPAY_ENVIRONMENT", "sandbox"),
        )

    def _headers(self) -> dict[str, str]:
        return {
            "X-Api-Key": self.api_key,
            "Correlation-Id": str(uuid4()),
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _error_message(response) -> str:
        try:
            payload = response.json()
        except (ValueError, TypeError):
            payload = None
        descriptions = []
        if isinstance(payload, dict):
            for item in payload.get("errors") or []:
                if isinstance(item, dict) and item.get("description"):
                    descriptions.append(str(item["description"])[:240])
        detail = "; ".join(descriptions[:3])
        return f"Nexi XPay ha rifiutato la richiesta (HTTP {response.status_code})" + (f": {detail}" if detail else ".")

    def _request(self, method: str, path: str, *, json: dict[str, Any] | None = None):
        try:
            response = self.session.request(
                method,
                f"{self.base_url}/{path.lstrip('/')}",
                headers=self._headers(),
                json=json,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise NexiXPayUncertainError(
                "Nexi XPay non e' raggiungibile e l'esito della richiesta non e' certo. Non ripetere il pagamento."
            ) from exc
        if response.status_code < 200 or response.status_code >= 300:
            if response.status_code >= 500:
                raise NexiXPayUncertainError(
                    "Nexi XPay ha restituito un errore temporaneo e l'esito della richiesta non e' certo. "
                    "Non ripetere il pagamento."
                )
            raise NexiXPayError(self._error_message(response))
        return response

    def create_hosted_payment(self, payload: dict[str, Any]) -> HostedPaymentPageResult:
        response = self._request("POST", "v1/orders/hpp", json=payload)
        try:
            body = response.json()
            result = HostedPaymentPageResult(
                hosted_page=str(body["hostedPage"]),
                security_token=str(body["securityToken"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise NexiXPayUncertainError("Nexi XPay ha restituito una risposta incompleta. Non ripetere il pagamento.") from exc
        if not result.hosted_page.startswith("https://") or not result.security_token:
            raise NexiXPayUncertainError("Nexi XPay ha restituito una pagina di pagamento non valida. Non ripetere il pagamento.")
        return result

    def create_paybylink(self, payload: dict[str, Any]) -> PayByLinkResult:
        response = self._request("POST", "v2/orders/paybylink", json=payload)
        try:
            body = response.json()
            payment_link = body["paymentLink"]
            result = PayByLinkResult(
                link_id=str(payment_link["linkId"]),
                payment_url=str(payment_link["link"]),
                security_token=str(body["securityToken"]),
                expiration_date=str(payment_link.get("expirationDate") or "") or None,
                status=str(payment_link.get("status") or "") or None,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise NexiXPayUncertainError(
                "Nexi XPay ha restituito una risposta PayByLink incompleta. Non generare un secondo link."
            ) from exc
        if not result.link_id or not result.payment_url.startswith("https://") or not result.security_token:
            raise NexiXPayUncertainError(
                "Nexi XPay ha restituito un PayByLink non valido. Non generare un secondo link."
            )
        return result

    def get_order(self, order_id: str) -> dict[str, Any]:
        safe_order_id = quote(str(order_id or "").strip(), safe="")
        if not safe_order_id:
            raise NexiXPayError("Identificativo ordine XPay mancante.")
        response = self._request("GET", f"v1/orders/{safe_order_id}")
        try:
            body = response.json()
        except (TypeError, ValueError) as exc:
            raise NexiXPayError("Nexi XPay ha restituito uno stato ordine non valido.") from exc
        if not isinstance(body, dict):
            raise NexiXPayError("Nexi XPay ha restituito uno stato ordine non valido.")
        return body
