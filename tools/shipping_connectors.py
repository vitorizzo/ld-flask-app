from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


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

    def __init__(self, integration=None):
        self.integration = integration

    @property
    def is_configured(self):
        return bool(self.integration and self.integration.is_enabled and self.integration.credentials)

    def track(self, tracking_number: str) -> TrackingResult:
        raise ShippingConnectorNotConfigured(f"Connettore {self.name} non configurato")


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


def connector_for(code: str, integration=None):
    cls = COURIER_CONNECTORS.get((code or "").strip().lower())
    if not cls:
        raise ShippingConnectorError("Corriere non supportato")
    return cls(integration=integration)


class PoleepoConnector:
    code = "poleepo"
    name = "Poleepo"

    def __init__(self, integration=None):
        self.integration = integration

    @property
    def is_configured(self):
        return bool(self.integration and self.integration.is_enabled and self.integration.credentials)

    def import_orders(self, since: datetime | None = None) -> list[dict]:
        raise ShippingConnectorNotConfigured("Connettore Poleepo non configurato")
