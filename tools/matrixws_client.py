from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any
from urllib.parse import quote, urlparse

import requests


class MatrixWSError(RuntimeError):
    """Errore di configurazione o trasporto MATRIXWS privo di credenziali."""

    def __init__(self, message: str, *, kind: str = "request", details: Any = None):
        super().__init__(message)
        self.kind = kind
        self.details = details


@dataclass(frozen=True)
class MatrixWSConfig:
    base_url: str
    environment: str
    start: str
    application: str
    secret: str

    @classmethod
    def from_app_config(cls, config) -> "MatrixWSConfig":
        result = cls(
            base_url=str(config.get("MATRIXWS_BASE_URL") or "").strip().rstrip("/"),
            environment=str(config.get("MATRIXWS_ENVIRONMENT") or "").strip(),
            start=str(config.get("MATRIXWS_START") or "").strip(),
            application=str(config.get("MATRIXWS_APPLICATION") or "").strip(),
            secret=str(config.get("MATRIXWS_SECRET") or "").strip(),
        )
        result.validate()
        return result

    def validate(self) -> None:
        missing = [
            label
            for label, value in (
                ("server", self.base_url),
                ("ambiente", self.environment),
                ("start", self.start),
                ("applicativo", self.application),
                ("secret", self.secret),
            )
            if not value
        ]
        if missing:
            raise MatrixWSError(
                f"Configurazione MATRIXWS incompleta: {', '.join(missing)}.",
                kind="configuration",
            )

        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise MatrixWSError(
                "Indirizzo server MATRIXWS non valido: usa un URL http:// o https:// completo.",
                kind="configuration",
            )
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise MatrixWSError(
                "L'indirizzo server MATRIXWS deve contenere solo protocollo e host, senza percorsi o parametri.",
                kind="configuration",
            )

    def service_url(self, dispatcher: str) -> str:
        parts = (
            self.environment,
            self.start.lower(),
            self.application.upper(),
            "service_mws",
            dispatcher,
        )
        encoded = "/".join(quote(part, safe="-_.~") for part in parts)
        return f"{self.base_url}/www/lynfaws/{encoded}"

    def secret_renewal_url(self) -> str:
        return f"{self.base_url}/www/pg/pg_public/open_public?function=pgsecrenew"


def _raise_transport_error(exc: requests.RequestException) -> None:
    if isinstance(exc, requests.exceptions.SSLError):
        raise MatrixWSError(
            "Connessione TLS non valida. Il certificato potrebbe non corrispondere all'indirizzo IP: prova il nome DNS Tailscale del server.",
            kind="tls",
        ) from exc
    if isinstance(exc, requests.exceptions.ConnectTimeout):
        raise MatrixWSError("Timeout durante la connessione al server MATRIXWS.", kind="timeout") from exc
    if isinstance(exc, requests.exceptions.ReadTimeout):
        raise MatrixWSError("Il server MATRIXWS non ha risposto entro il tempo previsto.", kind="timeout") from exc
    if isinstance(exc, requests.exceptions.ConnectionError):
        raise MatrixWSError(
            "Server MATRIXWS non raggiungibile dal server applicativo. Verifica indirizzo, Tailscale e porta HTTPS.",
            kind="connection",
        ) from exc
    raise MatrixWSError("Errore di comunicazione con MATRIXWS.", kind="request") from exc


def _extract_renewed_secret(data: Any, response_text: str) -> str | None:
    known_keys = {"secret", "newsecret", "new_secret", "token", "authorization", "bearer"}

    def is_secret_key(key: Any) -> bool:
        normalized = str(key).strip().lower().replace("-", "_")
        return (
            normalized in known_keys
            or "secret" in normalized
            or normalized.endswith("token")
        )

    def find(value: Any) -> str | None:
        if isinstance(value, dict):
            for key, nested in value.items():
                if is_secret_key(key) and isinstance(nested, str):
                    return nested.strip()
            for nested in value.values():
                if isinstance(nested, (dict, list)):
                    found = find(nested)
                    if found:
                        return found
        elif isinstance(value, list):
            for nested in value:
                if isinstance(nested, (dict, list)):
                    found = find(nested)
                    if found:
                        return found
        return None

    if isinstance(data, str):
        candidate = data.strip()
    elif data is not None:
        candidate = find(data)
    else:
        candidate = response_text.strip().strip('"')
    if candidate:
        candidate = re.sub(r"^Bearer\s+", "", candidate.strip(), flags=re.IGNORECASE)
    if not candidate or len(candidate) < 32 or len(candidate) > 4096 or any(char.isspace() for char in candidate):
        return None
    return candidate


def _safe_response_shape(value: Any, *, depth: int = 0) -> Any:
    if depth >= 4:
        return "..."
    if isinstance(value, dict):
        return {str(key): _safe_response_shape(nested, depth=depth + 1) for key, nested in value.items()}
    if isinstance(value, list):
        return [_safe_response_shape(nested, depth=depth + 1) for nested in value[:5]]
    if isinstance(value, str):
        return {"type": "string", "length": len(value)}
    if value is None:
        return {"type": "null"}
    return {"type": type(value).__name__}


def renew_secret(config: MatrixWSConfig, *, timeout=(5, 20)) -> str:
    try:
        response = requests.request(
            "GET",
            config.secret_renewal_url(),
            headers={
                "Authorization": f"Bearer {config.secret}",
                "Accept": "application/json",
            },
            timeout=timeout,
        )
    except requests.RequestException as exc:
        _raise_transport_error(exc)

    if not response.ok:
        raise MatrixWSError(
            f"Rinnovo secret rifiutato da TeamSystem (HTTP {response.status_code}).",
            kind="renewal",
        )

    try:
        response_data = response.json()
    except ValueError:
        response_data = None
    renewed_secret = _extract_renewed_secret(response_data, response.text or "")
    if not renewed_secret:
        raise MatrixWSError(
            "TeamSystem ha risposto al rinnovo senza un nuovo secret riconoscibile.",
            kind="renewal_response",
            details={
                "content_type": response.headers.get("Content-Type", ""),
                "structure": _safe_response_shape(response_data)
                if response_data is not None
                else {"type": "text", "length": len(response.text or "")},
            },
        )
    if renewed_secret == config.secret:
        raise MatrixWSError(
            "TeamSystem ha restituito lo stesso secret scaduto durante il rinnovo.",
            kind="renewal_response",
        )
    return renewed_secret


def call_sync(config: MatrixWSConfig, payload: dict[str, Any], *, timeout=(5, 25)) -> dict[str, Any]:
    url = config.service_url("EVWSSYNC")
    try:
        response = requests.request(
            "GET",
            url,
            headers={
                "Authorization": f"Bearer {config.secret}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        _raise_transport_error(exc)

    content_type = response.headers.get("Content-Type", "")
    try:
        response_data = response.json()
    except ValueError:
        response_data = None

    response_text = response.text or ""
    return {
        "url": url,
        "status_code": response.status_code,
        "ok": response.ok,
        "content_type": content_type,
        "json": response_data,
        "text": response_text[:12000] if response_data is None else None,
        "truncated": response_data is None and len(response_text) > 12000,
    }
