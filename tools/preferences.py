from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flask import current_app, has_app_context
from sqlalchemy.exc import SQLAlchemyError

from extensions import db
from models import AppPreference


@dataclass(frozen=True)
class PreferenceDefinition:
    key: str
    category: str
    label: str
    value_type: str = "text"
    default: Any = None
    description: str = ""
    config_key: str | None = None
    sort_order: int = 0

    @property
    def is_secret(self) -> bool:
        return (self.value_type or "text").lower() == "secret"


PREFERENCE_CATEGORY_ORDER = [
    "TeamSystem MATRIXWS",
    "Prestashop",
    "Poleepo",
    "Trello",
    "Slack",
    "Facebook",
    "Instagram",
    "Notifiche push",
    "Permessi e ruoli",
]

PREFERENCE_DEFINITIONS: list[PreferenceDefinition] = [
    PreferenceDefinition(
        key="matrixws.base_url",
        category="TeamSystem MATRIXWS",
        label="Indirizzo server",
        default="",
        description="URL base del server TeamSystem/Polyedro raggiungibile via Tailscale, senza slash finale.",
        config_key="MATRIXWS_BASE_URL",
        sort_order=10,
    ),
    PreferenceDefinition(
        key="matrixws.environment",
        category="TeamSystem MATRIXWS",
        label="Ambiente",
        default="",
        description="Nome dell'ambiente TS Azienda usato nel percorso dei servizi MATRIXWS.",
        config_key="MATRIXWS_ENVIRONMENT",
        sort_order=20,
    ),
    PreferenceDefinition(
        key="matrixws.start",
        category="TeamSystem MATRIXWS",
        label="Start",
        default="",
        description="Nome della start TeamSystem; nel percorso MATRIXWS viene normalmente usato in minuscolo.",
        config_key="MATRIXWS_START",
        sort_order=30,
    ),
    PreferenceDefinition(
        key="matrixws.application",
        category="TeamSystem MATRIXWS",
        label="Applicativo",
        default="MULTI",
        description="Nome dell'applicativo TeamSystem usato nel percorso dei servizi.",
        config_key="MATRIXWS_APPLICATION",
        sort_order=40,
    ),
    PreferenceDefinition(
        key="matrixws.secret",
        category="TeamSystem MATRIXWS",
        label="Secret Bearer",
        value_type="secret",
        default="",
        description="Secret generato da Gestione Secret MATRIXWS; viene conservato cifrato e non viene mostrato dopo il salvataggio.",
        config_key="MATRIXWS_SECRET",
        sort_order=50,
    ),
    PreferenceDefinition(
        key="prestashop.url",
        category="Prestashop",
        label="URL Prestashop",
        default="",
        description="Base URL del webservice Prestashop, senza slash finale.",
        config_key="PS_URL",
        sort_order=10,
    ),
    PreferenceDefinition(
        key="prestashop.key",
        category="Prestashop",
        label="Webservice key",
        value_type="secret",
        default="",
        description="Chiave API del webservice Prestashop.",
        config_key="PS_KEY",
        sort_order=20,
    ),
    PreferenceDefinition(
        key="prestashop.user",
        category="Prestashop",
        label="Utente Prestashop",
        default="",
        description="Utente tecnico, se richiesto dal webservice.",
        config_key="PS_USER",
        sort_order=30,
    ),
    PreferenceDefinition(
        key="prestashop.password",
        category="Prestashop",
        label="Password Prestashop",
        value_type="secret",
        default="",
        description="Password tecnica o vuota, se il webservice usa solo key.",
        config_key="PS_PSWD",
        sort_order=40,
    ),
    PreferenceDefinition(
        key="prestashop.image_upload_path",
        category="Prestashop",
        label="Path upload immagini",
        default="",
        description="Override facoltativo del path immagini Prestashop.",
        config_key="PS_IMAGE_UPLOAD_PATH",
        sort_order=50,
    ),
    PreferenceDefinition(
        key="prestashop.image_delete_path",
        category="Prestashop",
        label="Path delete immagini",
        default="",
        description="Override facoltativo del path di cancellazione immagini Prestashop.",
        config_key="PS_IMAGE_DELETE_PATH",
        sort_order=60,
    ),
    PreferenceDefinition(
        key="poleepo.url",
        category="Poleepo",
        label="URL Poleepo",
        default="",
        description="Base URL dell'API Poleepo.",
        config_key="POLEEPO_URL",
        sort_order=10,
    ),
    PreferenceDefinition(
        key="poleepo.client_id",
        category="Poleepo",
        label="Client ID Poleepo",
        value_type="secret",
        default="",
        description="Bearer client id / access key Poleepo.",
        config_key="POLEEPO_PKEY",
        sort_order=20,
    ),
    PreferenceDefinition(
        key="poleepo.client_secret",
        category="Poleepo",
        label="Client secret Poleepo",
        value_type="secret",
        default="",
        description="Bearer client secret Poleepo.",
        config_key="POLEEPO_PPKEY",
        sort_order=30,
    ),
    PreferenceDefinition(
        key="poleepo.products_path",
        category="Poleepo",
        label="Path prodotti",
        default="/products",
        description="Path usato per le API prodotti Poleepo.",
        config_key="POLEEPO_PRODUCTS_PATH",
        sort_order=40,
    ),
    PreferenceDefinition(
        key="poleepo.image_upload_path",
        category="Poleepo",
        label="Path upload immagini",
        default="",
        description="Path preferito per la pubblicazione immagini Poleepo.",
        config_key="POLEEPO_IMAGE_UPLOAD_PATH",
        sort_order=50,
    ),
    PreferenceDefinition(
        key="poleepo.image_delete_path",
        category="Poleepo",
        label="Path delete immagini",
        default="",
        description="Path preferito per la cancellazione immagini Poleepo.",
        config_key="POLEEPO_IMAGE_DELETE_PATH",
        sort_order=60,
    ),
    PreferenceDefinition(
        key="trello.key",
        category="Trello",
        label="API key Trello",
        value_type="secret",
        default="",
        description="API key per l'integrazione Trello.",
        config_key="TRELLO_KEY",
        sort_order=10,
    ),
    PreferenceDefinition(
        key="trello.secret",
        category="Trello",
        label="Secret Trello",
        value_type="secret",
        default="",
        description="Secret Trello usato per callback e firma.",
        config_key="TRELLO_SECRET",
        sort_order=20,
    ),
    PreferenceDefinition(
        key="trello.token",
        category="Trello",
        label="Token Trello",
        value_type="secret",
        default="",
        description="Token di accesso Trello.",
        config_key="TRELLO_TOKEN",
        sort_order=30,
    ),
    PreferenceDefinition(
        key="slack.signing_secret",
        category="Slack",
        label="Signing secret Slack",
        value_type="secret",
        default="",
        description="Secret usato per validare le richieste Slack.",
        config_key="SLACK_SIGNING_SECRET",
        sort_order=10,
    ),
    PreferenceDefinition(
        key="slack.bot_token",
        category="Slack",
        label="Bot token Slack",
        value_type="secret",
        default="",
        description="Token bot Slack per notifiche e azioni.",
        config_key="SLACK_BOT_TOKEN",
        sort_order=20,
    ),
    PreferenceDefinition(
        key="facebook.app_id",
        category="Facebook",
        label="Meta App ID",
        default="",
        description="App ID Meta usato per la pubblicazione sulla pagina Facebook.",
        config_key="META_APP_ID",
        sort_order=10,
    ),
    PreferenceDefinition(
        key="facebook.app_secret",
        category="Facebook",
        label="Meta App secret",
        value_type="secret",
        default="",
        description="App secret Meta. Necessario per rinnovo/verifica token quando verra' attivata l'integrazione completa.",
        config_key="META_APP_SECRET",
        sort_order=20,
    ),
    PreferenceDefinition(
        key="facebook.page_id",
        category="Facebook",
        label="Facebook Page ID",
        default="",
        description="ID della pagina Facebook aziendale su cui pubblicare.",
        config_key="META_PAGE_ID",
        sort_order=30,
    ),
    PreferenceDefinition(
        key="facebook.page_access_token",
        category="Facebook",
        label="Page access token",
        value_type="secret",
        default="",
        description="Token pagina con permessi di pubblicazione.",
        config_key="META_PAGE_ACCESS_TOKEN",
        sort_order=40,
    ),
    PreferenceDefinition(
        key="facebook.graph_api_version",
        category="Facebook",
        label="Graph API version",
        default="v24.0",
        description="Versione Graph API Meta da usare nelle chiamate.",
        config_key="META_GRAPH_API_VERSION",
        sort_order=50,
    ),
    PreferenceDefinition(
        key="facebook.events_auto_publish",
        category="Facebook",
        label="Auto-pubblica eventi",
        value_type="bool",
        default=False,
        description="Se abilitato, i task Celery tenteranno la pubblicazione automatica dei post eventi su Facebook.",
        config_key="META_FACEBOOK_EVENTS_AUTO_PUBLISH",
        sort_order=60,
    ),
    PreferenceDefinition(
        key="instagram.account_id",
        category="Instagram",
        label="Instagram Business Account ID",
        default="",
        description="ID dell'account Instagram Business/Creator collegato alla pagina Facebook.",
        config_key="META_INSTAGRAM_ACCOUNT_ID",
        sort_order=10,
    ),
    PreferenceDefinition(
        key="instagram.events_auto_publish",
        category="Instagram",
        label="Auto-pubblica eventi",
        value_type="bool",
        default=False,
        description="Se abilitato, i task Celery tenteranno la pubblicazione automatica dei post eventi su Instagram.",
        config_key="META_INSTAGRAM_EVENTS_AUTO_PUBLISH",
        sort_order=20,
    ),
    PreferenceDefinition(
        key="instagram.default_hashtags",
        category="Instagram",
        label="Hashtag default",
        default="#ldenoteca #eventi #degustazione",
        description="Hashtag aggiunti alle caption Instagram generate per gli eventi.",
        config_key="META_INSTAGRAM_DEFAULT_HASHTAGS",
        sort_order=30,
    ),
    PreferenceDefinition(
        key="vapid.public_key",
        category="Notifiche push",
        label="VAPID public key",
        default="",
        description="Chiave pubblica VAPID per le push web.",
        config_key="VAPID_PUBLIC_KEY",
        sort_order=10,
    ),
    PreferenceDefinition(
        key="vapid.private_key",
        category="Notifiche push",
        label="VAPID private key",
        value_type="secret",
        default="",
        description="Chiave privata VAPID.",
        config_key="VAPID_PRIVATE_KEY",
        sort_order=20,
    ),
    PreferenceDefinition(
        key="vapid.private_key_file",
        category="Notifiche push",
        label="File chiave privata VAPID",
        default="",
        description="Path del file chiave privata VAPID, se usato.",
        config_key="VAPID_PRIVATE_KEY_FILE",
        sort_order=30,
    ),
    PreferenceDefinition(
        key="vapid.subject",
        category="Notifiche push",
        label="VAPID subject",
        default="mailto:admin@ldenoteca.it",
        description="Subject VAPID, tipicamente una mail di contatto.",
        config_key="VAPID_SUBJECT",
        sort_order=40,
    ),
    PreferenceDefinition(
        key="permissions.office_role_weight",
        category="Permessi e ruoli",
        label="Peso ruolo Office",
        value_type="int",
        default=40,
        description="Soglia minima per le funzioni di gestione immagini e altre azioni Office.",
        config_key="OFFICE_ROLE_WEIGHT",
        sort_order=10,
    ),
]


def get_preference_definitions() -> list[PreferenceDefinition]:
    order_index = {name: idx for idx, name in enumerate(PREFERENCE_CATEGORY_ORDER)}
    return sorted(
        PREFERENCE_DEFINITIONS,
        key=lambda item: (order_index.get(item.category, 999), item.sort_order, item.label.lower()),
    )


def get_definition_map() -> dict[str, PreferenceDefinition]:
    return {item.key: item for item in PREFERENCE_DEFINITIONS}


def get_definition_by_config_key() -> dict[str, PreferenceDefinition]:
    return {
        item.config_key: item
        for item in PREFERENCE_DEFINITIONS
        if item.config_key
    }


def get_preference_base_config(app=None) -> dict[str, Any]:
    app = app or current_app._get_current_object()
    runtime = app.extensions.setdefault("ldapp_runtime_preferences", {})
    base = runtime.get("base_config")
    if base is None:
        base = {}
        for item in PREFERENCE_DEFINITIONS:
            if item.config_key:
                base[item.config_key] = app.config.get(item.config_key, item.default)
        runtime["base_config"] = base
    return base


def _coerce_definition_value(definition: PreferenceDefinition, row: AppPreference | None, base_config: dict[str, Any] | None = None):
    base_config = base_config or {}
    if row is not None:
        return row.python_value()

    if definition.config_key and definition.config_key in base_config:
        return base_config[definition.config_key]

    return definition.default


def build_preferences_sections(app=None) -> list[dict[str, Any]]:
    app = app or current_app._get_current_object()
    base_config = get_preference_base_config(app)
    try:
        rows = {
            row.key: row
            for row in AppPreference.query.order_by(
                AppPreference.category.asc(),
                AppPreference.sort_order.asc(),
                AppPreference.key.asc(),
            ).all()
        }
    except Exception:
        return []

    sections: list[dict[str, Any]] = []
    current_category = None
    current_items: list[dict[str, Any]] = []

    for definition in get_preference_definitions():
        if definition.category != current_category:
            if current_items:
                sections.append({"category": current_category, "items": current_items})
            current_category = definition.category
            current_items = []

        row = rows.get(definition.key)
        current_value = _coerce_definition_value(definition, row, base_config)
        source = "db" if row is not None else "env/default"
        current_items.append(
            {
                "key": definition.key,
                "category": definition.category,
                "label": definition.label,
                "description": definition.description,
                "value_type": definition.value_type,
                "config_key": definition.config_key,
                "sort_order": definition.sort_order,
                "stored": row is not None,
                "source": source,
                "current_value": current_value,
                "form_value": row.form_value() if row is not None else ("" if definition.is_secret or current_value is None else current_value),
                "is_secret": definition.is_secret,
                "input_type": "password" if definition.is_secret else (
                    "number" if definition.value_type in {"int", "float"} else "text"
                ),
                "step": "any" if definition.value_type == "float" else None,
                "placeholder": "Lascia vuoto per mantenere" if definition.is_secret else "",
            }
        )

    if current_items:
        sections.append({"category": current_category, "items": current_items})

    return sections


def _ensure_preference_row(definition: PreferenceDefinition) -> AppPreference:
    row = AppPreference.query.filter_by(key=definition.key).first()
    if row is None:
        row = AppPreference(
            key=definition.key,
            category=definition.category,
            label=definition.label,
            description=definition.description,
            value_type=definition.value_type,
            sort_order=definition.sort_order,
        )
        db.session.add(row)
    else:
        row.category = definition.category
        row.label = definition.label
        row.description = definition.description
        row.value_type = definition.value_type
        row.sort_order = definition.sort_order
    return row


def save_preferences_from_form(form) -> list[str]:
    definition_map = get_definition_map()
    changed_keys: list[str] = []

    try:
        for key, definition in definition_map.items():
            if key not in form:
                continue

            if definition.value_type == "bool":
                raw_values = form.getlist(key)
                raw_value = raw_values[-1] if raw_values else "0"
                normalized = str(raw_value).strip().lower() in {"1", "true", "yes", "on"}
                row = _ensure_preference_row(definition)
                row.value_text = "1" if normalized else "0"
                row.value_json = None
                row.secret_value = None
                changed_keys.append(key)
                continue

            raw_value = form.get(key)
            raw_value = raw_value.strip() if isinstance(raw_value, str) else raw_value

            if definition.is_secret:
                if not raw_value:
                    continue
                row = _ensure_preference_row(definition)
                row.secret_value = str(raw_value)
                row.value_text = None
                row.value_json = None
                changed_keys.append(key)
                continue

            if raw_value in (None, ""):
                row = AppPreference.query.filter_by(key=definition.key).first()
                if row is not None:
                    db.session.delete(row)
                    changed_keys.append(key)
                continue

            row = _ensure_preference_row(definition)
            if definition.value_type == "int":
                row.value_text = str(int(raw_value))
                row.value_json = None
                row.secret_value = None
            elif definition.value_type == "float":
                row.value_text = str(float(raw_value))
                row.value_json = None
                row.secret_value = None
            else:
                row.value_text = str(raw_value)
                row.value_json = None
                row.secret_value = None
            changed_keys.append(key)

        db.session.commit()
        return changed_keys
    except Exception:
        db.session.rollback()
        return []


def load_preferences_into_app_config(app=None) -> list[str]:
    app = app or current_app._get_current_object()
    base_config = get_preference_base_config(app)
    changed_config_keys: list[str] = []

    try:
        rows = {row.key: row for row in AppPreference.query.all()}
    except Exception:
        return []

    for definition in PREFERENCE_DEFINITIONS:
        if not definition.config_key:
            continue

        app.config[definition.config_key] = base_config.get(definition.config_key, definition.default)
        row = rows.get(definition.key)
        if row is None:
            continue

        app.config[definition.config_key] = row.python_value()
        changed_config_keys.append(definition.config_key)

    return changed_config_keys
