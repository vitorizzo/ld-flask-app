from __future__ import annotations

import os
from pathlib import Path

import requests
from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

from extensions import db
from models import AppPreference
from tools.log_utils import get_logger


logger = get_logger("import_transfer_config")

PREFERENCE_KEY = "imports.transfer_definitions"
TRACE_RELATIVE_FOLDER = Path("tracciati") / "importazione"

IMPORT_TRANSFER_CATALOG = (
    {
        "code": "articles",
        "label": "Articoli",
        "description": "Archivio articoli TeamSystem",
        "default_source_file": "ARTICOLI.CSV",
        "default_trace_file": "",
    },
    {
        "code": "stock",
        "label": "Giacenze",
        "description": "Disponibilità e quantità di magazzino",
        "default_source_file": "GIACENZE.CSV",
        "default_trace_file": "",
    },
    {
        "code": "barcodes",
        "label": "Codici a barre",
        "description": "Associazioni articolo/barcode",
        "default_source_file": "CODBAR.CSV",
        "default_trace_file": "",
    },
    {
        "code": "customers",
        "label": "Anagrafiche clienti",
        "description": "Anagrafiche clienti TeamSystem",
        "default_source_file": "exp_cli.csv",
        "default_trace_file": "",
    },
    {
        "code": "suppliers",
        "label": "Anagrafiche fornitori",
        "description": "Anagrafiche fornitori TeamSystem",
        "default_source_file": "exp_for.csv",
        "default_trace_file": "",
    },
    {
        "code": "customer_statements",
        "label": "Situazioni contabili clienti",
        "description": "Estratti conto e scadenze clienti TeamSystem",
        "default_source_file": "EC_CLI.CSV",
        "default_trace_file": "tracciato_ec_cli.csv",
    },
)


def _safe_basename(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    normalized = os.path.basename(raw.replace("\\", "/"))
    return normalized if normalized == raw.replace("\\", "/") else ""


def trace_folder():
    folder = Path(current_app.static_folder) / TRACE_RELATIVE_FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def available_trace_files():
    allowed = {".csv", ".txt", ".json", ".xml", ".dat"}
    return sorted(
        (
            path.name
            for path in trace_folder().iterdir()
            if path.is_file() and path.suffix.lower() in allowed
        ),
        key=str.casefold,
    )


def available_export_files():
    folder = current_app.config.get("EXPORT_FOLDER")
    if folder and os.path.isdir(folder):
        return sorted(
            (
                name
                for name in os.listdir(folder)
                if os.path.isfile(os.path.join(folder, name))
            ),
            key=str.casefold,
        )

    base_url = (current_app.config.get("EXPORT_FOLDER_URL") or "").rstrip("/")
    if not base_url:
        return []
    try:
        response = requests.get(f"{base_url}/lista_export", timeout=10)
        response.raise_for_status()
        payload = response.json()
        return sorted(
            {
                os.path.basename(str(item.get("name") or ""))
                for item in payload.get("files", [])
                if _safe_basename(os.path.basename(str(item.get("name") or "")))
            },
            key=str.casefold,
        )
    except Exception:
        logger.exception("Lettura catalogo file export non riuscita url=%s", base_url)
        return []


def _stored_config():
    try:
        row = AppPreference.query.filter_by(key=PREFERENCE_KEY).first()
        return row.value_json if row and isinstance(row.value_json, dict) else {}
    except SQLAlchemyError:
        db.session.rollback()
        logger.warning("Preferenza trasferimenti non disponibile; uso configurazione predefinita")
        return {}


def build_transfer_definitions():
    stored = _stored_config()
    definitions = []
    for item in IMPORT_TRANSFER_CATALOG:
        configured = stored.get(item["code"]) if isinstance(stored.get(item["code"]), dict) else {}
        definitions.append({
            **item,
            "source_file": (
                _safe_basename(configured.get("source_file"))
                or item["default_source_file"]
            ),
            "trace_file": (
                _safe_basename(configured.get("trace_file"))
                or item["default_trace_file"]
            ),
        })
    return definitions


def save_transfer_definitions(form):
    trace_files = set(available_trace_files())
    payload = {}
    for item in IMPORT_TRANSFER_CATALOG:
        code = item["code"]
        source_file = _safe_basename(form.get(f"{code}_source_file"))
        trace_file = _safe_basename(form.get(f"{code}_trace_file"))
        if not source_file:
            raise ValueError(f"Indicare il file sorgente per {item['label']}.")
        if trace_file and trace_file not in trace_files:
            raise ValueError(f"Tracciato non disponibile per {item['label']}: {trace_file}")
        payload[code] = {
            "source_file": source_file,
            "trace_file": trace_file,
        }

    row = AppPreference.query.filter_by(key=PREFERENCE_KEY).first()
    if not row:
        row = AppPreference(
            key=PREFERENCE_KEY,
            category="Importazioni",
            label="Tracciati e file importazione",
            description="Associa ogni importazione al file export e al relativo tracciato.",
            value_type="json",
            sort_order=10,
        )
        db.session.add(row)
    row.value_json = payload
    row.value_text = None
    db.session.commit()
    logger.info("Configurazione trasferimenti importazione aggiornata codes=%s", sorted(payload))
    return payload


def transfer_config(code):
    item = next((entry for entry in build_transfer_definitions() if entry["code"] == code), None)
    if not item:
        raise KeyError(f"Importazione non configurata: {code}")
    return item


def configured_source_file(code):
    return transfer_config(code)["source_file"]


def configured_trace_path(code):
    trace_file = transfer_config(code)["trace_file"]
    return (trace_folder() / trace_file) if trace_file else None
