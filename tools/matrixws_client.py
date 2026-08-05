from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlparse

import requests


class MatrixWSError(RuntimeError):
    """Errore di configurazione o trasporto MATRIXWS privo di credenziali."""

    def __init__(self, message: str, *, kind: str = "request"):
        super().__init__(message)
        self.kind = kind


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
    except requests.exceptions.SSLError as exc:
        raise MatrixWSError(
            "Connessione TLS non valida. Il certificato potrebbe non corrispondere all'indirizzo IP: prova il nome DNS Tailscale del server.",
            kind="tls",
        ) from exc
    except requests.exceptions.ConnectTimeout as exc:
        raise MatrixWSError("Timeout durante la connessione al server MATRIXWS.", kind="timeout") from exc
    except requests.exceptions.ReadTimeout as exc:
        raise MatrixWSError("Il server MATRIXWS non ha risposto entro il tempo previsto.", kind="timeout") from exc
    except requests.exceptions.ConnectionError as exc:
        raise MatrixWSError(
            "Server MATRIXWS non raggiungibile dal server applicativo. Verifica indirizzo, Tailscale e porta HTTPS.",
            kind="connection",
        ) from exc
    except requests.RequestException as exc:
        raise MatrixWSError("Errore di comunicazione con MATRIXWS.", kind="request") from exc

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
