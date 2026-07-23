import csv
import hashlib
import os
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import selectinload

from tools.ps_util import get_product_ids, get_product_images, get_product_payload
from extensions import db
from models import (
    Articoli,
    Barcode,
    BusinessRegistry,
    BusinessRegistryContact,
    CashCustomer,
    CashCustomerAlias,
    CourierIntegration,
    Giacenza,
    Importazione,
    ProductAsset,
    ProductPlatformField,
    ProductPlatformLink,
)
from flask import jsonify
from tools.log_utils import log_task, get_logger

logger = get_logger('importazioni')


def _sha256_text(value) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if raw == "":
        return None
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _find_conflict_rule(conflict_type, entity_key, field, csv_value, db_value):
    from models import ImportConflictResolution

    db_hash = _sha256_text(db_value)
    csv_hash = _sha256_text(csv_value)

    always_rule = (
        ImportConflictResolution.query
        .filter_by(
            type=conflict_type,
            entity_key=str(entity_key),
            field=str(field),
            mode="ALWAYS",
        )
        .order_by(ImportConflictResolution.created_at.desc(), ImportConflictResolution.id.desc())
        .first()
    )
    if always_rule:
        return always_rule

    return (
        ImportConflictResolution.query
        .filter_by(
            type=conflict_type,
            entity_key=str(entity_key),
            field=str(field),
            mode="CONDITIONAL",
            db_value_hash=db_hash,
            csv_value_hash=csv_hash,
        )
        .order_by(ImportConflictResolution.created_at.desc(), ImportConflictResolution.id.desc())
        .first()
    )


def _apply_import_conflict_resolution_if_available(conflict_type, entity_key, csv_obj, db_obj, articolo, counters):
    fields = sorted(set(list((csv_obj or {}).keys()) + list((db_obj or {}).keys())))
    if not fields:
        return False

    rules = [
        _find_conflict_rule(conflict_type, entity_key, field, csv_obj.get(field), db_obj.get(field))
        for field in fields
    ]
    if any(rule is None for rule in rules):
        return False

    actions = {rule.action for rule in rules}
    if len(actions) != 1:
        return False

    action = actions.pop()
    if action == "KEEP_DB":
        counters["unchanged"] += 1
        return True

    if action == "KEEP_CSV":
        if "descrizione" in csv_obj:
            articolo.descrizione = csv_obj.get("descrizione")
        if "descrizione_aggiuntiva" in csv_obj:
            articolo.descrizione_aggiuntiva = csv_obj.get("descrizione_aggiuntiva")
        if "prezzo" in csv_obj:
            articolo.prezzo = csv_obj.get("prezzo")
        counters["updated"] += 1
        return True

    return False


def _add_import_conflict_once(run, conflict_type, payload, counters):
    from models import ImportConflict

    existing = (
        ImportConflict.query
        .filter(
            ImportConflict.status == "pending",
            ImportConflict.type == conflict_type,
            ImportConflict.payload == payload,
        )
        .first()
    )
    if existing:
        counters["skipped"] += 1
        return existing, False

    conflict = ImportConflict(
        run_id=run.id,
        type=conflict_type,
        payload=payload,
        status="pending",
        created_at=datetime.utcnow(),
    )
    db.session.add(conflict)
    counters["conflicts"] += 1
    return conflict, True


def _first_value(payload, *keys):
    for key in keys:
        value = payload.get(key) if isinstance(payload, dict) else None
        if value is not None and str(value).strip() != "":
            return value
    return None


def _first_nested_value(payload, *paths):
    for path in paths:
        value = payload
        for key in path:
            value = value.get(key) if isinstance(value, dict) else None
            if value is None:
                break
        if value is not None and str(value).strip() != "":
            return value
    return None


def _normalize_poleepo_product(product):
    external_id = _first_value(product, "id", "product_id", "external_id", "reference_id")
    cod_art = _first_value(product, "sku", "reference", "code", "cod_art", "source_id", "barcode")
    name = _first_value(product, "name", "title", "description", "label") or cod_art
    description = _first_value(product, "description", "long_description", "body", "html_description")
    short_description = _first_value(product, "short_description", "subtitle", "summary")
    price = _first_value(product, "price", "sell_price", "sale_price", "regular_price")
    external_url = _first_value(product, "url", "permalink", "link")

    images = []
    raw_images = _first_value(product, "images", "pictures", "media", "image")
    if isinstance(raw_images, str):
        images.append({"url": raw_images, "id": None, "filename": raw_images.rsplit("/", 1)[-1]})
    elif isinstance(raw_images, dict):
        url = _first_value(raw_images, "url", "src", "link")
        if url:
            images.append({
                "url": url,
                "id": _first_value(raw_images, "id", "image_id"),
                "filename": _first_value(raw_images, "filename", "name") or url.rsplit("/", 1)[-1],
            })
    elif isinstance(raw_images, list):
        for image in raw_images:
            if isinstance(image, str):
                images.append({"url": image, "id": None, "filename": image.rsplit("/", 1)[-1]})
            elif isinstance(image, dict):
                url = _first_value(image, "url", "src", "link")
                if url:
                    images.append({
                        "url": url,
                        "id": _first_value(image, "id", "image_id"),
                        "filename": _first_value(image, "filename", "name") or url.rsplit("/", 1)[-1],
                    })

    return {
        "external_id": str(external_id).strip() if external_id is not None else "",
        "cod_art": str(cod_art).strip() if cod_art is not None else "",
        "name": str(name).strip() if name is not None else "",
        "description": str(description or ""),
        "short_description": str(short_description or ""),
        "price": price,
        "external_url": external_url,
        "images": images,
        "raw_payload": product,
    }


def _decimal_or_zero(value):
    if value is None or value == "":
        return Decimal("0")
    if isinstance(value, dict):
        value = _first_value(value, "amount", "value", "price", "tax_included")
    try:
        return Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _upsert_platform_field(cod_art, platform, field_name, value_text, source_external_id=None, language="it"):
    field = ProductPlatformField.query.filter_by(
        cod_art=cod_art,
        platform=platform,
        field_name=field_name,
        language=language or "",
    ).first()
    if not field:
        field = ProductPlatformField(
            cod_art=cod_art,
            platform=platform,
            field_name=field_name,
            language=language or "",
        )
        db.session.add(field)
    field.value_text = value_text or ""
    field.source_external_id = str(source_external_id) if source_external_id is not None else None
    field.last_sync_at = datetime.utcnow()


def _upsert_remote_asset(cod_art, platform, image, sort_order=0):
    remote_url = image.get("url")
    if not remote_url:
        return None
    asset = ProductAsset.query.filter_by(
        cod_art=cod_art,
        asset_type="image",
        source_platform=platform,
        remote_url=remote_url,
    ).first()
    if not asset:
        asset = ProductAsset(
            cod_art=cod_art,
            asset_type="image",
            source_platform=platform,
            remote_url=remote_url,
        )
        db.session.add(asset)
    asset.source_external_id = str(image.get("id")) if image.get("id") is not None else None
    asset.original_filename = image.get("filename") or asset.original_filename
    asset.sort_order = sort_order
    return asset


def clean_text(text):
    if text:
        return text.encode('ascii', 'ignore').decode('ascii')
    return text


def _clean_registry_text(value):
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _clean_zero_value(value):
    value = _clean_registry_text(value)
    if not value:
        return None
    compact = re.sub(r"\D", "", value)
    if compact and set(compact) == {"0"}:
        return None
    if value in {"00000", "000000", "0000000", "00000000", "000000000", "000000000000000000"}:
        return None
    return value


def _field(row, index):
    return row[index].strip() if index < len(row) and row[index] is not None else ""


def _normalize_phone(*parts):
    joined = "".join(_clean_registry_text(part) or "" for part in parts)
    digits = re.sub(r"\D", "", joined)
    if not digits or set(digits) == {"0"} or len(digits) < 5:
        return None
    return digits


def _normalize_email(value):
    value = _clean_registry_text(value)
    if not value or "@" not in value:
        return None
    value = value.strip().strip(";,.").lower()
    return value if "@" in value else None


def _email_contact_type(value):
    lowered = (value or "").lower()
    if any(marker in lowered for marker in ("pec.", "legalmail", "postacertificata", "@pec")):
        return "pec"
    return "email"


def _split_vat_tax(primary_value, alternate_value=None):
    vat_number = None
    tax_code = None

    for value in (primary_value, alternate_value):
        value = _clean_zero_value(value)
        if not value:
            continue
        compact = re.sub(r"\s+", "", value).upper()
        digits = re.sub(r"\D", "", compact)
        if compact.isdigit() and len(digits) == 11 and not vat_number:
            vat_number = compact
        elif not tax_code:
            tax_code = compact

    return vat_number, tax_code


def _upsert_registry_contact(registry, contact_type, value, label=None, source_column=None, is_primary=False):
    if not value:
        return False

    existing = next(
        (
            contact
            for contact in registry.contacts
            if contact.contact_type == contact_type and contact.value == value
        ),
        None,
    )
    if existing:
        existing.label = label or existing.label
        existing.source_column = source_column or existing.source_column
        existing.is_primary = bool(existing.is_primary or is_primary)
        return False

    db.session.add(BusinessRegistryContact(
        registry=registry,
        contact_type=contact_type,
        value=value,
        label=label,
        source_column=source_column,
        is_primary=bool(is_primary),
    ))
    return True


def _sync_cash_customer_from_registry(registry, customer_by_code=None, customer_by_vat=None):
    if registry.kind != "customer":
        return None, False

    customer = None
    if registry.source_code:
        customer = (customer_by_code or {}).get(registry.source_code)
        if customer is None and customer_by_code is None:
            customer = CashCustomer.query.filter_by(codice_cliente=registry.source_code).first()
    if not customer and registry.vat_number:
        customer = (customer_by_vat or {}).get(registry.vat_number)
        if customer is None and customer_by_vat is None:
            customer = CashCustomer.query.filter_by(partita_iva=registry.vat_number).first()

    created = False
    if not customer:
        customer = CashCustomer(
            display_name=registry.display_name,
            ragione_sociale=registry.legal_name,
            partita_iva=registry.vat_number,
            codice_cliente=registry.source_code,
        )
        db.session.add(customer)
        created = True
    else:
        customer.display_name = registry.display_name or customer.display_name
        customer.ragione_sociale = registry.legal_name or customer.ragione_sociale
        customer.partita_iva = registry.vat_number or customer.partita_iva
        customer.codice_cliente = registry.source_code or customer.codice_cliente

    alias_value = registry.legal_name or registry.display_name
    if alias_value:
        exists = any(alias.alias == alias_value for alias in customer.aliases)
        if not exists:
            customer.aliases.append(CashCustomerAlias(alias=alias_value, alias_type="business"))

    if customer_by_code is not None and registry.source_code:
        customer_by_code[registry.source_code] = customer
    if customer_by_vat is not None and registry.vat_number:
        customer_by_vat[registry.vat_number] = customer

    return customer, created


def _parse_registry_row(row, kind):
    source_code = _clean_zero_value(_field(row, 2))
    legal_name = _clean_registry_text(_field(row, 3))
    if not source_code or not legal_name:
        return None

    vat_or_tax = _clean_zero_value(_field(row, 8))
    alternate_tax = _clean_zero_value(_field(row, 9))
    vat_number, tax_code = _split_vat_tax(vat_or_tax, alternate_tax)

    payload = {
        "source_record_type": _clean_registry_text(_field(row, 0)),
        "source_company_code": _clean_registry_text(_field(row, 1)),
        "columns": {
            "0": _clean_registry_text(_field(row, 0)),
            "1": _clean_registry_text(_field(row, 1)),
            "2": source_code,
            "3": legal_name,
            "4": _clean_registry_text(_field(row, 4)),
            "5": _clean_registry_text(_field(row, 5)),
            "6": _clean_registry_text(_field(row, 6)),
            "7": _clean_registry_text(_field(row, 7)),
            "8": vat_or_tax,
            "9": alternate_tax,
            "52": _clean_registry_text(_field(row, 52)),
            "53": _clean_registry_text(_field(row, 53)),
            "54": _clean_registry_text(_field(row, 54)),
            "55": _clean_registry_text(_field(row, 55)),
            "130": _clean_registry_text(_field(row, 130)),
            "160": _clean_registry_text(_field(row, 160)),
            "203": _clean_registry_text(_field(row, 203)),
        },
    }

    return {
        "kind": kind,
        "source": "teamsystem",
        "source_record_type": _clean_registry_text(_field(row, 0)),
        "source_company_code": _clean_registry_text(_field(row, 1)),
        "source_code": source_code,
        "display_name": legal_name,
        "legal_name": legal_name,
        "vat_number": vat_number,
        "tax_code": tax_code,
        "address": _clean_registry_text(_field(row, 4)) or _clean_registry_text(_field(row, 163)),
        "zip_code": _clean_zero_value(_field(row, 5)),
        "city": _clean_registry_text(_field(row, 6)),
        "province": _clean_registry_text(_field(row, 7)),
        "country": "IT",
        "source_payload": payload,
        "contacts": [
            ("phone", _normalize_phone(_field(row, 52), _field(row, 53)), "telefono", "52+53", True),
            ("fax", _normalize_phone(_field(row, 54), _field(row, 55)), "fax", "54+55", False),
            ("mobile", _normalize_phone(_field(row, 130)), "cellulare", "130", False),
        ],
        "emails": [
            (_normalize_email(_field(row, 160)), "email/pec principale", "160", True),
            (_normalize_email(_field(row, 203)), "email/pec alternativa", "203", False),
        ],
    }


def _import_registry_file(file_name, kind, task_id=None, task_name="Importazione anagrafiche", progress_offset=0, progress_span=50):
    from routes.esportazioni_teamsystem import serve_risorsa
    from tools.redis_utils import update_task, status_string

    file_csv = serve_risorsa(file_name)
    logger.info("File anagrafiche %s: %s", kind, file_csv)

    counters = {
        "created": 0,
        "updated": 0,
        "unchanged": 0,
        "contacts_created": 0,
        "cash_customers_created": 0,
        "skipped": 0,
        "total_rows": 0,
    }

    with open(file_csv, "r", encoding="utf-8-sig", errors="ignore", newline="") as csvfile:
        rows = list(csv.reader(csvfile, delimiter="\t"))

    parsed_rows = []
    for row in rows:
        parsed = _parse_registry_row(row, kind)
        if parsed:
            parsed_rows.append(parsed)
        else:
            counters["skipped"] += 1

    source_codes = [parsed["source_code"] for parsed in parsed_rows]
    registry_by_key = {
        (registry.kind, registry.source, registry.source_code): registry
        for registry in BusinessRegistry.query.filter(
            BusinessRegistry.kind == kind,
            BusinessRegistry.source == "teamsystem",
            BusinessRegistry.source_code.in_(source_codes or [""]),
        ).all()
    }

    customer_by_code = None
    customer_by_vat = None
    if kind == "customer":
        vat_numbers = [parsed["vat_number"] for parsed in parsed_rows if parsed.get("vat_number")]
        customers = (
            CashCustomer.query.options(selectinload(CashCustomer.aliases))
            .filter(
                db.or_(
                    CashCustomer.codice_cliente.in_(source_codes or [""]),
                    CashCustomer.partita_iva.in_(vat_numbers or [""]),
                )
            )
            .all()
        )
        customer_by_code = {customer.codice_cliente: customer for customer in customers if customer.codice_cliente}
        customer_by_vat = {customer.partita_iva: customer for customer in customers if customer.partita_iva}

    counters["total_rows"] = len(rows)
    logger.info("Import anagrafiche %s: lette %s righe da %s", kind, counters["total_rows"], file_csv)
    with db.session.no_autoflush:
        for index, parsed in enumerate(parsed_rows):
            registry_key = (kind, parsed["source"], parsed["source_code"])
            registry = registry_by_key.get(registry_key)

            created = False
            if not registry:
                registry = BusinessRegistry(
                    kind=kind,
                    source=parsed["source"],
                    source_code=parsed["source_code"],
                    display_name=parsed["display_name"],
                    legal_name=parsed["legal_name"],
                )
                db.session.add(registry)
                registry_by_key[registry_key] = registry
                created = True

            changed = created
            for field in (
                "source_record_type",
                "source_company_code",
                "display_name",
                "legal_name",
                "vat_number",
                "tax_code",
                "address",
                "zip_code",
                "city",
                "province",
                "country",
                "source_payload",
            ):
                value = parsed[field]
                if getattr(registry, field) != value:
                    setattr(registry, field, value)
                    changed = True
            registry.is_active = True

            for contact_type, value, label, source_column, is_primary in parsed["contacts"]:
                if _upsert_registry_contact(registry, contact_type, value, label, source_column, is_primary):
                    counters["contacts_created"] += 1

            for value, label, source_column, is_primary in parsed["emails"]:
                if value:
                    contact_type = _email_contact_type(value)
                    if _upsert_registry_contact(registry, contact_type, value, label, source_column, is_primary):
                        counters["contacts_created"] += 1

            if kind == "customer":
                _, customer_created = _sync_cash_customer_from_registry(registry, customer_by_code, customer_by_vat)
                if customer_created:
                    counters["cash_customers_created"] += 1

            if created:
                counters["created"] += 1
            elif changed:
                counters["updated"] += 1
            else:
                counters["unchanged"] += 1

            if index % 100 == 0:
                progress = progress_offset + int((index / max(len(rows), 1)) * progress_span)
                update_task(task_id, task_name, progress, status_string["update"])
                db.session.flush()

    db.session.flush()

    logger.info("Import anagrafiche %s completato: %s", kind, counters)
    return counters


@log_task(logger)
def import_anagrafiche(task_id=None):
    from tools.redis_utils import update_task, clear_task_status, status_string

    task_name = "Importazione anagrafiche TeamSystem"
    update_task(task_id, task_name, 0, status_string["start"])
    logger.info(">>> Entrata nella funzione: import_anagrafiche()")

    summary = {}
    try:
        db.create_all()
        summary["customers"] = _import_registry_file(
            "exp_cli.csv",
            "customer",
            task_id=task_id,
            task_name=task_name,
            progress_offset=0,
            progress_span=50,
        )
        db.session.flush()
        summary["suppliers"] = _import_registry_file(
            "exp_for.csv",
            "supplier",
            task_id=task_id,
            task_name=task_name,
            progress_offset=50,
            progress_span=50,
        )
        db.session.commit()
        update_task(task_id, task_name, 100, status_string["end"])
        if task_id:
            clear_task_status(task_id)
        registra_importazione("anagrafiche", esito=True)
        return {"success": True, "message": "Anagrafiche importate con successo", "summary": summary}
    except Exception as e:
        logger.exception("Errore durante l'importazione anagrafiche:")
        db.session.rollback()
        update_task(task_id, task_name, 0, status_string["error"], e)
        registra_importazione("anagrafiche", esito=False, messaggio=str(e))
        return {"success": False, "error": str(e), "summary": summary}


@log_task(logger)
def import_estratti_conto_clienti(task_id=None):
    """Verifica la disponibilità dell'export TeamSystem in attesa del parser."""
    from routes.esportazioni_teamsystem import serve_risorsa
    from tools.redis_utils import clear_task_status, status_string, update_task

    task_name = "Importazione estratti conto clienti TeamSystem"
    file_name = "ec_cli.csv"
    update_task(task_id, task_name, 0, status_string["start"])
    logger.info(">>> Verifica file estratti conto clienti: %s", file_name)

    try:
        file_path = serve_risorsa(file_name)
        file_size = os.path.getsize(file_path)
        if file_size <= 0:
            raise ValueError(f"Il file {file_name} è vuoto")

        message = (
            f"File {file_name} disponibile ({file_size} byte); "
            "elaborazione non ancora implementata"
        )
        update_task(task_id, task_name, 100, status_string["end"])
        if task_id:
            clear_task_status(task_id)
        registra_importazione("estratti_conto_clienti", esito=True, messaggio=message)
        return {
            "success": True,
            "processed": False,
            "file_name": file_name,
            "file_size": file_size,
            "message": message,
        }
    except Exception as e:
        logger.exception("Errore durante la verifica degli estratti conto clienti:")
        update_task(task_id, task_name, 0, status_string["error"], e)
        registra_importazione("estratti_conto_clienti", esito=False, messaggio=str(e))
        return {
            "success": False,
            "processed": False,
            "file_name": file_name,
            "error": str(e),
        }


@log_task(logger)
def import_ps(task_id=None):
    from tools.redis_utils import update_task, status_string

    task_name = "Importazione dati da Prestashop"
    update_task(task_id, task_name, 0, status_string['start'])
    logger.info(">>> Entrata nella funzione: import_ps()")
    logger.info("Importazione Prestashop avviata...")
    counters = {
        "created": 0,
        "existing": 0,
        "images": 0,
        "skipped": 0,
        "total_rows": 0,
    }

    try:
        product_ids = get_product_ids()
        total_rows = len(product_ids)
        counters["total_rows"] = total_rows

        if total_rows == 0:
            update_task(task_id, task_name, 100, status_string['end'])
            registra_importazione("prestashop", esito=True)
            return {
                "success": True,
                "message": "Nessun prodotto Prestashop da importare",
                "progress": 100,
                "summary": counters,
            }

        for index, product_id in enumerate(product_ids):
            prodotto = get_product_payload(product_id)
            if not prodotto:
                counters["skipped"] += 1
                if index % 10 == 0:
                    progresso = int(((index + 1) / total_rows) * 100)
                    update_task(task_id, task_name, progresso, status_string['update'])
                continue

            cod_art = prodotto['cod_art']
            pid = prodotto['id']
            platform_link = ProductPlatformLink.query.filter_by(cod_art=cod_art, platform="prestashop").first()
            if not platform_link:
                platform_link = ProductPlatformLink(cod_art=cod_art, platform="prestashop")
                db.session.add(platform_link)
            platform_link.external_id = str(pid)
            platform_link.external_url = prodotto.get("external_url")
            platform_link.status = "present"
            platform_link.last_sync_at = datetime.utcnow()
            platform_link.last_error = None
            platform_link.raw_payload = prodotto.get("raw_payload")

            existing_articolo = Articoli.query.filter_by(cod_art=cod_art).first()
            if not existing_articolo:
                nuovo_articolo = Articoli(
                    cod_art=cod_art,
                    descrizione=prodotto['name'],
                    prezzo=float(prodotto['price'])
                )
                db.session.add(nuovo_articolo)
                db.session.flush()
                platform_link.id_art = nuovo_articolo.id_art
                counters["created"] += 1
                logger.info(f"Articolo {cod_art} inserito.")
            else:
                counters["existing"] += 1
                platform_link.id_art = existing_articolo.id_art
                logger.info(f"Articolo {cod_art} già presente, salto inserimento.")

            p_images = get_product_images(pid, cod_art)
            prodotto['images'] = p_images
            counters["images"] += len(p_images)

            if index % 10 == 0:
                progresso = int(((index + 1) / total_rows) * 100)
                update_task(task_id, task_name, progresso, status_string['update'])

            logger.info(f"Prodotto {cod_art} importato: {prodotto['name']} con {len(p_images)} immagini.")

        db.session.commit()
        update_task(task_id, task_name, 100, status_string['end'])
        registra_importazione("prestashop", esito=True)
        return {
            "success": True,
            "message": "Dati Prestashop importati con successo",
            "progress": 100,
            "summary": counters,
        }

    except Exception as e:
        logger.exception("Errore durante l'importazione Prestashop")
        db.session.rollback()
        update_task(task_id, task_name, 0, status_string['error'], e)
        registra_importazione("prestashop", esito=False, messaggio=str(e))
        return {"success": False, "error": str(e), "summary": counters}


@log_task(logger)
def import_poleepo_products(task_id=None, options=None):
    from tools.redis_utils import update_task, status_string
    from tools.shipping_connectors import PoleepoConnector, ShippingConnectorError, ShippingConnectorNotConfigured

    options = options or {}
    task_name = "Importazione prodotti da Poleepo"
    update_task(task_id, task_name, 0, status_string["start"])

    counters = {
        "created": 0,
        "existing": 0,
        "links": 0,
        "fields": 0,
        "assets": 0,
        "skipped": 0,
        "errors": 0,
        "total_rows": 0,
    }

    try:
        integration = CourierIntegration.query.filter_by(code="poleepo").first()
        if not integration:
            integration = CourierIntegration(code="poleepo", name="Poleepo", is_enabled=True)
            db.session.add(integration)
            db.session.flush()

        connector = PoleepoConnector(integration=integration)
        remote_products = connector.import_products(
            page_size=options.get("page_size", 100),
            max_pages=options.get("max_pages", 50),
        )
        counters["total_rows"] = len(remote_products)

        if not remote_products:
            registra_importazione("poleepo_prodotti", esito=True, messaggio="Nessun prodotto Poleepo da importare")
            update_task(task_id, task_name, 100, status_string["end"])
            return {"success": True, "message": "Nessun prodotto Poleepo da importare", "summary": counters}

        for index, raw_product in enumerate(remote_products, start=1):
            try:
                prodotto = _normalize_poleepo_product(raw_product)
                cod_art = prodotto["cod_art"]
                external_id = prodotto["external_id"]
                if not cod_art:
                    counters["skipped"] += 1
                    continue

                articolo = Articoli.query.filter_by(cod_art=cod_art).first()
                if not articolo:
                    articolo = Articoli(
                        cod_art=cod_art,
                        descrizione=prodotto["name"] or cod_art,
                        prezzo=_decimal_or_zero(prodotto["price"]),
                    )
                    db.session.add(articolo)
                    db.session.flush()
                    counters["created"] += 1
                else:
                    counters["existing"] += 1

                link = ProductPlatformLink.query.filter_by(cod_art=cod_art, platform="poleepo").first()
                if not link:
                    link = ProductPlatformLink(cod_art=cod_art, platform="poleepo")
                    db.session.add(link)
                    counters["links"] += 1
                link.id_art = articolo.id_art
                link.external_id = external_id or None
                link.external_url = prodotto["external_url"]
                link.status = "present"
                link.last_sync_at = datetime.utcnow()
                link.last_error = None
                link.raw_payload = prodotto["raw_payload"]

                if prodotto["description"]:
                    _upsert_platform_field(cod_art, "poleepo", "description", prodotto["description"], external_id)
                    counters["fields"] += 1
                if prodotto["short_description"]:
                    _upsert_platform_field(cod_art, "poleepo", "description_short", prodotto["short_description"], external_id)
                    counters["fields"] += 1

                for image_index, image in enumerate(prodotto["images"]):
                    if _upsert_remote_asset(cod_art, "poleepo", image, image_index):
                        counters["assets"] += 1

            except Exception as item_exc:
                counters["errors"] += 1
                logger.exception("Errore import prodotto Poleepo: %s", item_exc)

            if task_id and (index == 1 or index % 10 == 0 or index == len(remote_products)):
                progress = int((index / max(len(remote_products), 1)) * 100)
                update_task(task_id, task_name, progress, status_string["update"])

            if index % 50 == 0:
                db.session.commit()

        integration.last_sync_at = datetime.utcnow()
        integration.is_enabled = True
        db.session.commit()
        registra_importazione("poleepo_prodotti", esito=True, messaggio=str(counters))
        update_task(task_id, task_name, 100, status_string["end"])
        return {"success": True, "message": "Prodotti Poleepo importati", "summary": counters}

    except (ShippingConnectorNotConfigured, ShippingConnectorError) as e:
        db.session.rollback()
        update_task(task_id, task_name, 0, status_string["error"], e)
        registra_importazione("poleepo_prodotti", esito=False, messaggio=str(e))
        return {"success": False, "error": str(e), "summary": counters}
    except Exception as e:
        db.session.rollback()
        logger.exception("Errore durante l'importazione prodotti Poleepo")
        update_task(task_id, task_name, 0, status_string["error"], e)
        registra_importazione("poleepo_prodotti", esito=False, messaggio=str(e))
        return {"success": False, "error": str(e), "summary": counters}


@log_task(logger)
def import_articoli(task_id=None):
    from datetime import datetime
    from routes.esportazioni_teamsystem import serve_risorsa
    from tools.redis_utils import update_task, status_string, clear_task_status
    from models import ImportRun, ImportConflict  # se l'import nel tuo progetto è diverso, adegua

    task_name = "Importazione articoli"
    update_task(task_id, task_name, 0, status_string['start'])
    logger.info(">>> Entrata nella funzione: import_articoli()")
    logger.info("Importazione articoli avviata...")

    db.create_all()

    file_csv = serve_risorsa("ARTICOLI.CSV")
    logger.info(f"File CSV: {file_csv}")

    run = None
    counters = {
        "created": 0,
        "updated": 0,
        "unchanged": 0,
        "conflicts": 0,
        "skipped": 0,
        "total_rows": 0,
    }

    try:
        # Crea ImportRun
        run = ImportRun(
            task_id=str(task_id) if task_id else "manual",
            file_name="ARTICOLI.CSV",
            started_at=datetime.utcnow(),
        )
        db.session.add(run)
        db.session.flush()  # ottieni run.id

        with open(file_csv, 'r', encoding='utf-8', errors='ignore') as csvfile:
            reader = list(csv.reader(csvfile, delimiter='\t'))
            total_rows = len(reader)
            counters["total_rows"] = max(total_rows - 1, 0)
            logger.info(f"Righe totali: {total_rows}")

            if total_rows <= 1:
                raise Exception("Il file CSV non contiene dati validi")

            with db.session.no_autoflush:
                for index, row in enumerate(reader):
                    if index == 0:
                        continue  # header

                    if len(row) < 4:
                        counters["skipped"] += 1
                        continue

                    cod_art = clean_text(row[0])
                    descrizione = clean_text(row[1])
                    descrizione_aggiuntiva = clean_text(row[2])
                    prezzo = float(row[3][:-2] + "." + row[3][-2:]) if row[3].strip() else 0.0

                    if not cod_art or not descrizione:
                        counters["skipped"] += 1
                        continue

                    # 1) lookup per codice
                    articolo_by_code = Articoli.query.filter_by(cod_art=cod_art).first()

                    # 2) lookup per identità descrittiva (descrizione + descrizione_aggiuntiva)
                    articolo_by_desc = Articoli.query.filter_by(
                        descrizione=descrizione,
                        descrizione_aggiuntiva=descrizione_aggiuntiva
                    ).first()

                    if articolo_by_code is None:
                        # 1) cod_art nuovo
                        if articolo_by_desc is None:
                            # 1. cod_art nuovo e descr+agg non esistono -> insert sicuro
                            nuovo_articolo = Articoli(
                                cod_art=cod_art,
                                descrizione=descrizione,
                                descrizione_aggiuntiva=descrizione_aggiuntiva,
                                prezzo=prezzo
                            )
                            db.session.add(nuovo_articolo)
                            counters["created"] += 1
                        else:
                            # 1a) cod_art nuovo ma descr+agg esistono -> conflitto
                            _add_import_conflict_once(
                                run,
                                "DESCRIZIONE_DIVERGENTE",
                                {
                                    "cod_art_csv": cod_art,
                                    "descrizione_csv": descrizione,
                                    "descrizione_aggiuntiva_csv": descrizione_aggiuntiva,
                                    "prezzo_csv": prezzo,
                                    "match_db": {
                                        "cod_art": articolo_by_desc.cod_art,
                                        "descrizione": articolo_by_desc.descrizione,
                                        "descrizione_aggiuntiva": articolo_by_desc.descrizione_aggiuntiva,
                                        "prezzo": float(articolo_by_desc.prezzo) if articolo_by_desc.prezzo is not None else None,
                                    }
                                },
                                counters,
                            )

                    else:
                        # cod_art esiste: controlla che identità descrittiva combaci
                        same_desc = (articolo_by_code.descrizione == descrizione)
                        same_desc_add = (articolo_by_code.descrizione_aggiuntiva == descrizione_aggiuntiva)

                        if not (same_desc and same_desc_add):
                            # codice esistente ma descrizione discordante -> risoluzione automatica o conflitto
                            conflict_payload = {
                                "cod_art": cod_art,
                                "csv": {
                                    "descrizione": descrizione,
                                    "descrizione_aggiuntiva": descrizione_aggiuntiva,
                                    "prezzo": prezzo,
                                },
                                "db": {
                                    "descrizione": articolo_by_code.descrizione,
                                    "descrizione_aggiuntiva": articolo_by_code.descrizione_aggiuntiva,
                                    "prezzo": float(articolo_by_code.prezzo) if articolo_by_code.prezzo is not None else None,
                                }
                            }
                            if not _apply_import_conflict_resolution_if_available(
                                "CODICE_RIASSEGNATO_O_DESC_DISCORDANTE",
                                cod_art,
                                conflict_payload["csv"],
                                conflict_payload["db"],
                                articolo_by_code,
                                counters,
                            ):
                                _add_import_conflict_once(
                                    run,
                                    "CODICE_RIASSEGNATO_O_DESC_DISCORDANTE",
                                    conflict_payload,
                                    counters,
                                )
                        else:
                            # identità combacia -> update prezzo se diverso
                            prezzo_db = float(articolo_by_code.prezzo) if articolo_by_code.prezzo is not None else 0.0
                            if prezzo_db != prezzo:
                                articolo_by_code.prezzo = prezzo
                                counters["updated"] += 1
                            else:
                                counters["unchanged"] += 1

                    # progresso
                    if index % 50 == 0:
                        progresso = int((index / total_rows) * 100)
                        update_task(task_id, task_name, progresso, status_string['update'])

        # chiudi run
        run.finished_at = datetime.utcnow()
        run.summary = counters

        db.session.commit()
        update_task(task_id, task_name, 100, status_string['end'])
        logger.info("Articoli importati con successo!")
        logger.info(f"Summary import articoli: {counters}")

        if task_id:
            clear_task_status(task_id)
        registra_importazione("articoli", esito=True)
        return {'message': 'Articoli importati con successo!', 'progress': 100, 'summary': counters}

    except Exception as e:
        logger.exception("Errore durante l'importazione degli Articoli:")
        db.session.rollback()

        try:
            # prova a registrare esito sul run se esiste
            if run is not None:
                run.finished_at = datetime.utcnow()
                run.summary = {**counters, "error": str(e)}
                db.session.add(run)
                db.session.commit()
        except Exception:
            db.session.rollback()

        update_task(task_id, task_name, 0, status_string['error'], e)
        registra_importazione("articoli", esito=False, messaggio=str(e))
        return {'success': False, 'error': str(e)}



@log_task(logger)
def import_giacenze(task_id=None):
    from routes.esportazioni_teamsystem import serve_risorsa
    from tools.redis_utils import update_task, clear_task_status, status_string
    task_name = "Importazione giacenze da gestionale"
    update_task(task_id, task_name, 0, status_string['start'])
    logger.info(">>> Entrata nella funzione: import_giacenze()")
    logger.info("Importazione giacenze avviata...")
    db.create_all()
    db.session.query(Giacenza).delete()
    db.session.commit()
    logger.info("Tabella giacenze svuotata.")

    file_csv = serve_risorsa("GIACENZE.CSV")
    logger.info(f"File CSV: {file_csv}")
    try:
        with open(file_csv, 'r', encoding='utf-8', errors='ignore') as csvfile:
            reader = list(csv.reader(csvfile, delimiter='\t'))
            total_rows = len(reader)
            logger.info(f"Righe totali: {total_rows}")

            with db.session.no_autoflush:
                for index, row in enumerate(reader):
                    if index > 0 and len(row) >= 4:
                        cod_art = clean_text(row[0])
                        giacenza = int(clean_text(row[1])[:-2])
                        deposito = int(clean_text(row[2])[:-2])
                        tipo_valore = int(clean_text(row[3])[:-2])

                        if cod_art and tipo_valore == 1 and giacenza != 0:
                            giacenza_esistente = Giacenza.query.filter_by(cod_art=cod_art).first()
                            if giacenza_esistente:
                                modifiche = []
                                match deposito:
                                    case 0:
                                        if giacenza_esistente.giac_neg == 0:
                                            setattr(giacenza_esistente, "giac_neg", giacenza)
                                        else:
                                            modifiche.append((cod_art, "giac_neg", giacenza_esistente.giac_neg,
                                                              giacenza))
                                    case 400:
                                        if giacenza_esistente.giac_www == 0:
                                            setattr(giacenza_esistente, "giac_www", giacenza)
                                        else:
                                            modifiche.append((cod_art, "giac_www", giacenza_esistente.giac_www,
                                                              giacenza))
                                if modifiche:
                                    for articolo, campo, valore_vecchio, valore_nuovo in modifiche:
                                        scelta = input(f"Differenza trovata per il campo {campo} dell'articolo "
                                                       f"{articolo}: vecchio='{valore_vecchio}', "
                                                       f" nuovo='{valore_nuovo}'. "
                                                       f"(v=vecchio, n=nuovo): ").strip().lower()
                                        if scelta == 'n':
                                            setattr(giacenza_esistente, campo, valore_nuovo)
                            else:
                                giac_neg = 0
                                giac_www = 0
                                match deposito:
                                    case 0: giac_neg = giacenza
                                    case 400: giac_www = giacenza

                                nuova_giacenza = Giacenza(
                                    cod_art=cod_art,
                                    giac_neg=giac_neg,
                                    giac_www=giac_www,
                                )
                                db.session.add(nuova_giacenza)
                                db.session.flush()
                    # 🔁 Aggiorna progresso ogni 50 righe
                    if index % 50 == 0:
                        progresso = int((index / total_rows) * 100)
                        update_task(task_id, task_name, progresso, status_string['update'])
        logger.info("Ciclo di filtraggio terminato!")
        db.session.commit()
        update_task(task_id, task_name, 100, status_string['end'])
        logger.info("Giacenze importate con successo!")
        if task_id:
            clear_task_status(task_id)
        registra_importazione("giacenze", esito=True)
        return jsonify({'message': 'Giacenze importate con successo!', 'progress': 100}), 200
    except Exception as e:
        logger.exception("Errore durante l'importazione delle Giacenze:")
        db.session.rollback()
        update_task(task_id, task_name, 0, status_string['error'], e)
        registra_importazione("giacenze", esito=False, messaggio=str(e))
        return jsonify({'success': False, 'error': str(e)}), 500


@log_task(logger)
def import_barcode(task_id=None):
    result = run_import_barcode(task_id)
    status_code = 200 if result.get("success", True) else 500
    return jsonify(result), status_code


def run_import_barcode(task_id=None):
    from routes.esportazioni_teamsystem import serve_risorsa
    from tools.redis_utils import update_task, clear_task_status, status_string
    task_name = "Importazione codici a barre articoli da gestionale"
    update_task(task_id, task_name, 0, status_string['start'])
    logger.info(">>> Entrata nella funzione: run_import_barcode()")
    logger.info("Importazione codici a barre avviata...")
    db.create_all()
    counters = {
        "inserted": 0,
        "duplicates": 0,
        "missing_article": 0,
        "skipped": 0,
        "total_rows": 0,
    }
    try:
        file_csv = serve_risorsa("CODBAR.CSV")
        logger.info(f"File CSV: {file_csv}")
        with open(file_csv, 'r', encoding='utf-8', errors='ignore') as csvfile:
            reader = list(csv.reader(csvfile, delimiter='\t'))
            total_rows = len(reader)
            counters["total_rows"] = max(total_rows - 1, 0)
            logger.info(f"Righe totali: {total_rows}")

            barcode_rows = []
            seen_keys = set()

            with db.session.no_autoflush:
                for index, row in enumerate(reader):
                    if index > 0 and len(row) >= 4:
                        cod_bar = clean_text(row[3]).strip()
                        cod_art = clean_text(row[0]).strip()
                        if cod_bar and cod_art:
                            unique_key = (cod_bar, cod_art)
                            if unique_key in seen_keys:
                                counters["duplicates"] += 1
                                continue
                            seen_keys.add(unique_key)
                            barcode_rows.append({
                                "cod_bar": cod_bar,
                                "cod_art": cod_art,
                            })
                        else:
                            counters["skipped"] += 1
                    elif index > 0:
                        counters["skipped"] += 1
                    # 🔁 Aggiorna progresso ogni 50 righe
                    if index % 500 == 0:
                        progresso = int((index / max(total_rows, 1)) * 80)
                        update_task(task_id, task_name, progresso, status_string['update'])
        db.session.query(Barcode).delete()
        logger.info("Tabella codici a barre svuotata.")
        if barcode_rows:
            db.session.execute(Barcode.__table__.insert(), barcode_rows)
            db.session.execute(db.text("""
                UPDATE barcode
                SET id_art = articoli.id_art
                FROM articoli
                WHERE barcode.cod_art = articoli.cod_art
            """))
            counters["missing_article"] = db.session.execute(db.text("""
                SELECT COUNT(*)
                FROM barcode
                WHERE id_art IS NULL
            """)).scalar() or 0
        counters["inserted"] = len(barcode_rows)
        db.session.commit()
        logger.info("Codici a Barre importati con successo!")
        logger.info("Summary import barcode: %s", counters)
        update_task(task_id, task_name, 100, status_string['end'])
        if task_id:
            clear_task_status(task_id)
        registra_importazione("barcode", esito=True)
        return {
            'success': True,
            'message': 'Codici a Barre importati con successo!',
            'progress': 100,
            'summary': counters,
        }
    except Exception as e:
        logger.exception("Errore durante l'importazione dei codici a barre:")
        db.session.rollback()
        update_task(task_id, task_name, 0, status_string['error'], e)
        registra_importazione("barcode", esito=False, messaggio=str(e))
        return {'success': False, 'error': str(e)}


def registra_importazione(modulo, esito=True, messaggio=None):
    if messaggio is not None:
        messaggio = str(messaggio)
        if len(messaggio) > 255:
            messaggio = messaggio[:252] + "..."
    try:
        db.session.rollback()
    except Exception:
        db.session.remove()
    try:
        nuova_import = Importazione(
            modulo=modulo,
            timestamp=datetime.now(),
            esito=esito,
            messaggio=messaggio
        )
        db.session.add(nuova_import)
        db.session.commit()
    except Exception:
        logger.exception("Errore durante la registrazione dello storico importazioni")
        db.session.rollback()
