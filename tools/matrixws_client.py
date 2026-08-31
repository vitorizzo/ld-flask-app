from __future__ import annotations

from dataclasses import dataclass
import re
import time
from typing import Any, Callable
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

    def batch_response_url(self) -> str:
        return f"{self.base_url}/www/matrixws/batch/response"


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


def call_sync(
    config: MatrixWSConfig,
    payload: dict[str, Any],
    *,
    method: str = "POST",
    timeout=(5, 25),
) -> dict[str, Any]:
    url = config.service_url("EVWSSYNC")
    method = str(method or "POST").strip().upper()
    if method not in {"GET", "POST"}:
        raise MatrixWSError("Metodo HTTP MATRIXWS non supportato.", kind="configuration")
    try:
        response = requests.request(
            method,
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
        "method": method,
        "status_code": response.status_code,
        "ok": response.ok,
        "content_type": content_type,
        "json": response_data,
        "text": response_text[:12000] if response_data is None else None,
        "truncated": response_data is None and len(response_text) > 12000,
    }


def call_async(
    config: MatrixWSConfig,
    payload: dict[str, Any],
    *,
    method: str = "POST",
    timeout=(5, 25),
) -> dict[str, Any]:
    """Avvia un'elaborazione MATRIXWS e restituisce la risposta con il batch UUID."""
    return _call_json(
        config,
        config.service_url("EVWSASYNC"),
        payload,
        method=method,
        timeout=timeout,
    )


def call_batch_response(
    config: MatrixWSConfig,
    batch_uuid: str,
    *,
    method: str = "GET",
    timeout=(5, 60),
) -> dict[str, Any]:
    """Legge lo stato o il risultato di un batch MATRIXWS gia' avviato."""
    normalized_uuid = str(batch_uuid or "").strip()
    if not normalized_uuid:
        raise MatrixWSError("Identificativo batch MATRIXWS mancante.", kind="configuration")
    return _call_json(
        config,
        config.batch_response_url(),
        {"batch_uuid": normalized_uuid},
        method=method,
        timeout=timeout,
    )


def extract_batch_uuid(value: Any) -> str | None:
    """Estrae il batch UUID anche quando TeamSystem lo annida nella risposta."""
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized_key = str(key).strip().lower().replace("-", "_")
            if normalized_key in {"batch_uuid", "batchuuid"} and isinstance(nested, str):
                candidate = nested.strip()
                if candidate:
                    return candidate
        for nested in value.values():
            found = extract_batch_uuid(nested)
            if found:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = extract_batch_uuid(nested)
            if found:
                return found
    return None


def is_batch_not_finished(result: dict[str, Any]) -> bool:
    """Riconosce il particolare HTTP 500 usato da MATRIXWS durante il polling."""
    return _contains_text(result.get("json"), "BATCH_NOT_FINISHED") or _contains_text(
        result.get("text"), "BATCH_NOT_FINISHED"
    )


def wait_for_async_result(
    config: MatrixWSConfig,
    payload: dict[str, Any],
    *,
    method: str = "POST",
    start_timeout=(5, 30),
    poll_timeout=(5, 60),
    poll_interval: float = 2.0,
    max_wait: float = 15 * 60,
    progress_callback: Callable[[str, float], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Avvia e attende un batch nel worker, trattando BATCH_NOT_FINISHED come stato transitorio."""
    started = call_async(config, payload, method=method, timeout=start_timeout)
    if started["status_code"] == 401:
        raise MatrixWSError("Secret MATRIXWS scaduto o non autorizzato.", kind="unauthorized")
    batch_uuid = extract_batch_uuid(started.get("json"))
    if not batch_uuid:
        raise MatrixWSError(
            f"Avvio batch MATRIXWS non riuscito (HTTP {started['status_code']}): identificativo batch assente.",
            kind="async_start",
            details={
                "status_code": started["status_code"],
                "response": started.get("json") if started.get("json") is not None else started.get("text"),
            },
        )

    return wait_for_batch_result(
        config,
        batch_uuid,
        poll_timeout=poll_timeout,
        poll_interval=poll_interval,
        max_wait=max_wait,
        progress_callback=progress_callback,
        sleep=sleep,
        monotonic=monotonic,
    )


def wait_for_batch_result(
    config: MatrixWSConfig,
    batch_uuid: str,
    *,
    poll_timeout=(5, 60),
    poll_interval: float = 2.0,
    max_wait: float = 15 * 60,
    progress_callback: Callable[[str, float], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Attende un batch gia' avviato senza coinvolgere la richiesta web che lo ha creato."""
    batch_uuid = str(batch_uuid or "").strip()
    if not batch_uuid:
        raise MatrixWSError("Identificativo batch MATRIXWS mancante.", kind="configuration")

    started_at = monotonic()
    interval = max(float(poll_interval), 0.1)
    deadline = started_at + max(float(max_wait), interval)
    if progress_callback:
        progress_callback(batch_uuid, 0.0)

    while True:
        result = call_batch_response(config, batch_uuid, timeout=poll_timeout)
        elapsed = max(monotonic() - started_at, 0.0)
        if is_batch_not_finished(result):
            if progress_callback:
                progress_callback(batch_uuid, elapsed)
            if monotonic() >= deadline:
                raise MatrixWSError(
                    f"Batch MATRIXWS {batch_uuid} ancora in elaborazione dopo {int(max_wait)} secondi.",
                    kind="async_timeout",
                    details={"batch_uuid": batch_uuid, "elapsed": elapsed},
                )
            sleep(interval)
            continue
        if result["status_code"] == 401:
            raise MatrixWSError("Secret MATRIXWS scaduto durante il polling.", kind="unauthorized")
        if not result["ok"]:
            raise MatrixWSError(
                f"Lettura batch MATRIXWS fallita con HTTP {result['status_code']}.",
                kind="async_response",
                details={
                    "batch_uuid": batch_uuid,
                    "status_code": result["status_code"],
                    "response": result.get("json") if result.get("json") is not None else result.get("text"),
                },
            )
        if progress_callback:
            progress_callback(batch_uuid, elapsed)
        return {**result, "batch_uuid": batch_uuid, "elapsed": elapsed}


def _contains_text(value: Any, expected: str) -> bool:
    target = expected.upper()
    if isinstance(value, dict):
        return any(_contains_text(key, expected) or _contains_text(nested, expected) for key, nested in value.items())
    if isinstance(value, list):
        return any(_contains_text(nested, expected) for nested in value)
    return target in str(value or "").upper()


def _call_json(
    config: MatrixWSConfig,
    url: str,
    payload: dict[str, Any],
    *,
    method: str,
    timeout,
) -> dict[str, Any]:
    method = str(method or "POST").strip().upper()
    if method not in {"GET", "POST"}:
        raise MatrixWSError("Metodo HTTP MATRIXWS non supportato.", kind="configuration")
    try:
        response = requests.request(
            method,
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

    try:
        response_data = response.json()
    except ValueError:
        response_data = None
    response_text = response.text or ""
    return {
        "url": url,
        "method": method,
        "status_code": response.status_code,
        "ok": response.ok,
        "content_type": response.headers.get("Content-Type", ""),
        "json": response_data,
        "text": response_text[:12000] if response_data is None else None,
        "truncated": response_data is None and len(response_text) > 12000,
    }
