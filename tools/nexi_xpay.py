from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import requests
from flask import current_app


SANDBOX_BASE_URL = "https://xpaysandbox.nexigroup.com/api/phoenix-0.0/psp/api"
PRODUCTION_BASE_URL = "https://xpay.nexigroup.com/api/phoenix-0.0/psp/api"


class NexiXPayError(RuntimeError):
    """Errore sicuro da mostrare all'utente senza esporre credenziali o payload sensibili."""


class NexiXPayUncertainError(NexiXPayError):
    """La richiesta potrebbe essere stata acquisita dal provider: non e' sicuro ripeterla."""


@dataclass(frozen=True)
class HostedPaymentPageResult:
    hosted_page: str
    security_token: str


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
