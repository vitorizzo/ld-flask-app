import hashlib
import mimetypes
import os
from datetime import datetime

from sqlalchemy.exc import SQLAlchemyError
from flask import Blueprint, current_app, render_template, jsonify, request, abort, url_for, Response
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename
import requests
from requests.auth import HTTPBasicAuth

from extensions import db
from models import (
    Barcode,
    Articoli,
    Giacenza,
    Immagini,
    ProductAsset,
    CourierIntegration,
    ProductPlatformField,
    ProductPlatformLink,
    SchedeProdotti,
    Inventario,
    InventarioRiga,
    InventarioExport,
)
from routes.tools import clean_text
from tools.ps_util import (
    create_product as prestashop_create_product,
    delete_product_image as prestashop_delete_product_image,
    get_category_options as prestashop_get_category_options,
    get_tax_rule_group_options as prestashop_get_tax_rule_group_options,
    upload_product_image as prestashop_upload_product_image,
)
from tools.shipping_connectors import PoleepoConnector, ShippingConnectorError, ShippingConnectorNotConfigured
from tools.log_utils import log_task, get_logger
from sqlalchemy import or_


logger = get_logger('search')

search_bp = Blueprint('search', __name__, template_folder='../templates')

PRODUCT_IMAGE_PLATFORMS = {
    "prestashop": {"label": "Prestashop", "enabled": True, "icon": "fa-solid fa-store"},
    "poleepo": {"label": "Poleepo", "enabled": True, "icon": "fa-solid fa-cloud-arrow-up"},
    "ebay": {"label": "Ebay", "enabled": False, "icon": "fa-brands fa-ebay"},
    "amazon": {"label": "Amazon", "enabled": False, "icon": "fa-brands fa-amazon"},
    "ldapp": {"label": "LDApp", "enabled": True, "icon": "fa-solid fa-folder-open"},
}
ALLOWED_PRODUCT_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
OFFICE_ROLE_WEIGHT = 40
POLEEPO_CATEGORY_OPTIONS_CACHE = {"loaded_at": None, "options": []}
PRODUCT_PUBLICATION_SCHEMAS = {
    "prestashop": {
        "label": "Prestashop",
        "fields": [
            {"name": "reference", "label": "Riferimento / SKU", "type": "text", "required": True, "source": "cod_art"},
            {"name": "name", "label": "Nome prodotto", "type": "text", "required": True, "source": "descrizione"},
            {"name": "description_short", "label": "Descrizione breve", "type": "textarea", "required": False, "source": "scheda_short"},
            {"name": "description", "label": "Descrizione lunga", "type": "textarea", "required": False, "source": "scheda_tecnica"},
            {"name": "price", "label": "Prezzo", "type": "decimal", "required": True, "source": "prezzo"},
            {"name": "active", "label": "Attivo", "type": "bool", "required": False, "source": "default_false"},
            {"name": "available_for_order", "label": "Disponibile ordine", "type": "bool", "required": False, "source": "default_true"},
            {"name": "show_price", "label": "Mostra prezzo", "type": "bool", "required": False, "source": "default_true"},
            {
                "name": "id_category_default",
                "label": "Categoria default Prestashop",
                "type": "select",
                "required": True,
                "source": "manual",
                "options_source": "prestashop_categories",
                "help": "Categoria principale in cui verra' creato il prodotto su Prestashop.",
            },
            {
                "name": "id_tax_rules_group",
                "label": "Regola IVA Prestashop",
                "type": "select",
                "required": False,
                "source": "manual",
                "options_source": "prestashop_tax_rule_groups",
                "help": "Regola IVA Prestashop. Se lasciata vuota, Prestashop applichera' il proprio default.",
            },
        ],
    },
    "poleepo": {
        "label": "Poleepo",
        "fields": [
            {"name": "sku", "label": "SKU", "type": "text", "required": True, "source": "cod_art"},
            {"name": "title", "label": "Nome prodotto", "type": "text", "required": True, "source": "descrizione_full"},
            {"name": "description", "label": "Descrizione", "type": "textarea", "required": False, "source": "scheda_tecnica"},
            {"name": "price", "label": "Prezzo", "type": "decimal", "required": True, "source": "prezzo"},
            {"name": "vat_rate", "label": "IVA", "type": "decimal", "required": True, "source": "default_vat_22"},
            {"name": "barcode", "label": "Barcode principale", "type": "text", "required": False, "source": "barcode_primary"},
            {"name": "quantity", "label": "Quantita' online", "type": "integer", "required": False, "source": "giac_www"},
            {"name": "active", "label": "Attivo", "type": "bool", "required": False, "source": "default_true"},
            {
                "name": "main_category_id",
                "label": "Categoria Poleepo",
                "type": "select",
                "required": True,
                "source": "poleepo_default_category",
                "options_source": "poleepo_categories",
                "help": "Categoria principale Poleepo. La lista mostra ID e descrizione quando ricavabili dai prodotti gia' presenti.",
            },
        ],
    },
}


def _can_manage_product_images():
    return bool(current_user.is_authenticated and (current_user.max_role_weight or 0) >= OFFICE_ROLE_WEIGHT)


def _can_publish_product_to_platform(platform_key, platform_links):
    config = PRODUCT_IMAGE_PLATFORMS.get(platform_key)
    if not config or not config.get("enabled") or platform_key == "ldapp":
        return False
    link = platform_links.get(platform_key)
    return not link or link.status in ("absent", "error") or not link.external_id


def _can_update_product_on_platform(platform_key, platform_links):
    config = PRODUCT_IMAGE_PLATFORMS.get(platform_key)
    if not config or not config.get("enabled") or platform_key == "ldapp":
        return False
    if platform_key != "poleepo":
        return False
    link = platform_links.get(platform_key)
    return bool(link and link.status not in ("absent", "error") and link.external_id)


def _product_publication_source_value(source, articolo, scheda, barcodes, giacenze):
    if source == "cod_art":
        return articolo.cod_art or ""
    if source == "descrizione":
        return articolo.descrizione or ""
    if source == "descrizione_aggiuntiva":
        return articolo.descrizione_aggiuntiva or ""
    if source == "descrizione_full":
        return " - ".join(
            piece.strip()
            for piece in [articolo.descrizione or "", articolo.descrizione_aggiuntiva or ""]
            if piece and piece.strip()
        )
    if source == "scheda_short":
        return (scheda.short if scheda else None) or articolo.descrizione_aggiuntiva or ""
    if source == "scheda_tecnica":
        return (scheda.descrizione if scheda else None) or articolo.descrizione_aggiuntiva or articolo.descrizione or ""
    if source == "prezzo":
        return "" if articolo.prezzo is None else str(articolo.prezzo)
    if source == "barcode_primary":
        return barcodes[0].cod_bar if barcodes else ""
    if source == "giac_www":
        return str(giacenze.giac_www if giacenze else 0)
    if source == "default_vat_22":
        return "22"
    if source == "poleepo_default_category":
        return str(current_app.config.get("POLEEPO_DEFAULT_CATEGORY_ID") or "8360")
    if source == "default_true":
        return "1"
    if source == "default_false":
        return "0"
    return ""


def _poleepo_remote_field_value(remote_product, field_name):
    if not isinstance(remote_product, dict) or field_name not in remote_product:
        return None
    value = remote_product.get(field_name)
    if isinstance(value, dict):
        if field_name == "type":
            return value.get("name") or value.get("id") or ""
        return value.get("name") or value.get("value") or value.get("id") or ""
    if isinstance(value, list):
        return ", ".join(
            str(item.get("name") or item.get("title") or item.get("id") or item)
            for item in value
        )
    if isinstance(value, bool):
        return "1" if value else "0"
    return value


def _humanize_field_name(name):
    return str(name or "").replace("_", " ").strip().title()


def _remote_image_url(image):
    if isinstance(image, str):
        return image
    if not isinstance(image, dict):
        return None
    for key in ("url", "remote_url", "src", "href", "link", "image", "preview_url"):
        value = image.get(key)
        if value:
            return str(value)
    image_id = image.get("id")
    if image_id:
        return f"https://app.poleepo.cloud/image/show/{image_id}.jpeg"
    return None


def _serialize_remote_images(remote_product):
    if not isinstance(remote_product, dict):
        return []
    images = remote_product.get("images") or []
    if isinstance(images, dict):
        images = images.get("data") or images.get("items") or images.get("images") or []
    if not isinstance(images, list):
        return []
    serialized = []
    for index, image in enumerate(images):
        url = _remote_image_url(image)
        if not url:
            continue
        label = None
        image_id = None
        if isinstance(image, dict):
            label = image.get("title") or image.get("name") or image.get("filename")
            image_id = image.get("id")
        serialized.append({
            "id": image_id or index,
            "url": url,
            "label": label or f"Immagine {index + 1}",
            "source_platform": "poleepo",
        })
    return serialized


def _product_identity_value(articolo):
    return " | ".join(
        str(piece or "").strip().lower()
        for piece in [articolo.descrizione, articolo.descrizione_aggiuntiva]
        if str(piece or "").strip()
    )


def _validate_distinct_source_product(target_articolo, source_articolo):
    if not source_articolo:
        raise ValueError("Articolo origine non trovato")
    if source_articolo.cod_art == target_articolo.cod_art:
        raise ValueError("L'articolo origine deve avere un codice diverso")
    if _product_identity_value(source_articolo) == _product_identity_value(target_articolo):
        raise ValueError("Descrizione e descrizione aggiuntiva devono identificare prodotti diversi")


def _product_publication_schema(platform_key):
    schema = PRODUCT_PUBLICATION_SCHEMAS.get(platform_key)
    if not schema:
        raise ValueError("Piattaforma non supportata per la pubblicazione prodotto")
    return schema


def _product_publication_field_options(platform_key, spec):
    source = spec.get("options_source")
    if not source:
        return [], None
    try:
        if platform_key == "prestashop" and source == "prestashop_categories":
            return prestashop_get_category_options(), None
        if platform_key == "prestashop" and source == "prestashop_tax_rule_groups":
            return prestashop_get_tax_rule_group_options(), None
        if platform_key == "poleepo" and source == "poleepo_categories":
            return _poleepo_category_options(), None
    except Exception as exc:
        logger.warning("Opzioni %s non disponibili: %s", source, exc)
        if platform_key == "poleepo" and source == "poleepo_categories":
            default_option = _poleepo_default_category_option()
            return ([default_option] if default_option else []), str(exc)
        return [], str(exc)
    return [], None


def _poleepo_category_label_from_product(product):
    if not isinstance(product, dict):
        return None
    path = product.get("main_category_path")
    if isinstance(path, list):
        path = " / ".join(str(piece) for piece in path if str(piece or "").strip())
    if isinstance(path, dict):
        path = path.get("name") or path.get("path") or path.get("title")
    if path and str(path).strip():
        return str(path).strip()
    category = product.get("main_category") or product.get("category")
    if isinstance(category, dict):
        return category.get("name") or category.get("path") or category.get("title")
    if isinstance(category, str) and category.strip():
        return category.strip()
    return None


def _poleepo_category_option(value, label=None):
    value = str(value or "").strip()
    if not value:
        return None
    label = str(label or "").strip()
    if label:
        return {"value": value, "label": f"{value} - {label}"}
    return {"value": value, "label": f"{value} - descrizione non disponibile"}


def _poleepo_default_category_option():
    default_id = str(current_app.config.get("POLEEPO_DEFAULT_CATEGORY_ID") or "8360").strip()
    default_label = str(current_app.config.get("POLEEPO_DEFAULT_CATEGORY_LABEL") or "").strip()
    if not default_label and default_id == "8360":
        default_label = "NON CATEGORIZZATO"
    return _poleepo_category_option(default_id, default_label)


def _poleepo_category_options():
    loaded_at = POLEEPO_CATEGORY_OPTIONS_CACHE.get("loaded_at")
    if loaded_at and (datetime.utcnow() - loaded_at).total_seconds() < 1800:
        return list(POLEEPO_CATEGORY_OPTIONS_CACHE.get("options") or [])

    integration = CourierIntegration.query.filter_by(code="poleepo").first()
    connector = PoleepoConnector(integration=integration)
    products = connector.import_products(page_size=100, max_pages=10)
    categories = {}
    for product in products:
        category_id = product.get("main_category_id")
        if category_id in (None, ""):
            continue
        value = str(category_id).strip()
        label = _poleepo_category_label_from_product(product)
        if value not in categories or label:
            categories[value] = label or categories.get(value)

    default_option = _poleepo_default_category_option()
    if default_option:
        categories.setdefault(default_option["value"], default_option["label"].split(" - ", 1)[1])

    options = [
        _poleepo_category_option(value, label)
        for value, label in sorted(categories.items(), key=lambda item: (item[1] or "", item[0]))
    ]
    options = [option for option in options if option]
    POLEEPO_CATEGORY_OPTIONS_CACHE["loaded_at"] = datetime.utcnow()
    POLEEPO_CATEGORY_OPTIONS_CACHE["options"] = options
    return list(options)


def _ensure_field_value_option(options, value, label=None):
    value = str(value or "").strip()
    if not value:
        return options
    if any(str(option.get("value")) == value for option in options):
        return options
    option = _poleepo_category_option(value, label)
    if option:
        return [option] + list(options or [])
    return options


def _build_product_publication_draft(
    articolo,
    platform_key,
    *,
    include_options=True,
    platform_link=None,
    prefer_saved=False,
):
    schema = _product_publication_schema(platform_key)
    scheda = SchedeProdotti.query.filter_by(cod_art=articolo.cod_art).first()
    barcodes = Barcode.query.filter_by(cod_art=articolo.cod_art).order_by(Barcode.cod_bar.asc()).all()
    giacenze = Giacenza.query.filter_by(cod_art=articolo.cod_art).first()
    remote_product = None
    if platform_key == "poleepo" and platform_link and platform_link.external_id:
        try:
            integration = CourierIntegration.query.filter_by(code="poleepo").first()
            remote_product = PoleepoConnector(integration=integration).product_detail(platform_link.external_id)
        except Exception as exc:
            logger.warning("Dettaglio prodotto Poleepo non disponibile per %s: %s", articolo.cod_art, exc)
            payload = platform_link.raw_payload if isinstance(platform_link.raw_payload, dict) else {}
            remote_product = payload.get("data") if isinstance(payload.get("data"), dict) else None
    saved_rows = {
        (row.field_name, row.language or ""): row
        for row in ProductPlatformField.query.filter_by(cod_art=articolo.cod_art, platform=platform_key).all()
    }
    fields = []
    for spec in schema["fields"]:
        language = spec.get("language", "")
        saved = saved_rows.get((spec["name"], language))
        mapped_value = _product_publication_source_value(spec.get("source"), articolo, scheda, barcodes, giacenze)
        remote_value = _poleepo_remote_field_value(remote_product, spec["name"]) if platform_key == "poleepo" else None
        if prefer_saved and saved and saved.value_text is not None:
            value = saved.value_text
        elif remote_value is not None:
            value = remote_value
        elif saved and saved.value_text is not None:
            value = saved.value_text
        else:
            value = mapped_value
        options, options_error = _product_publication_field_options(platform_key, spec) if include_options else ([], None)
        help_text = spec.get("help") or ""
        if platform_key == "poleepo" and spec["name"] == "main_category_id":
            category_label = None
            if isinstance(remote_product, dict):
                category_label = _poleepo_category_label_from_product(remote_product)
            if options:
                options = _ensure_field_value_option(options, value, category_label)
            if category_label:
                help_text = f"Categoria remota: {category_label}"
            elif str(value or "").strip():
                help_text = "Categoria Poleepo: descrizione non disponibile per questo ID. Verificare prima di pubblicare."
        if remote_value is not None:
            help_text = "Valore letto dal prodotto remoto Poleepo."
            if str(mapped_value or "").strip() and str(mapped_value or "").strip() != str(value or "").strip():
                help_text += f" Valore LDApp attuale: {mapped_value}"
            if platform_key == "poleepo" and spec["name"] == "main_category_id":
                category_label = _poleepo_category_label_from_product(remote_product)
                if category_label:
                    help_text += f" Categoria: {category_label}"
                else:
                    help_text += " Categoria: descrizione non disponibile."
        fields.append({
            "name": spec["name"],
            "label": spec["label"],
            "type": spec.get("type", "text"),
            "required": bool(spec.get("required")),
            "source": spec.get("source") or "manual",
            "language": language,
            "value": "" if value is None else str(value),
            "mapped_value": "" if mapped_value is None else str(mapped_value),
            "saved": bool(saved),
            "missing": bool(spec.get("required")) and not str(value or "").strip(),
            "options": options,
            "options_error": options_error,
            "help": help_text,
        })
    if platform_key == "poleepo" and isinstance(remote_product, dict):
        existing_names = {field["name"] for field in fields}
        readonly_fields = [
            ("id", "ID Poleepo"),
            ("type", "Tipo"),
            ("price_with_tax", "Prezzo IVA inclusa"),
            ("sales", "Vendite"),
            ("main_category_path", "Percorso categoria"),
            ("creation_date", "Data creazione"),
            ("update_date", "Data aggiornamento"),
            ("images", "Immagini remote"),
            ("provisions", "Disponibilita' remote"),
            ("tags", "Tag"),
        ]
        for name, label in readonly_fields:
            if name in existing_names or name not in remote_product:
                continue
            remote_value = _poleepo_remote_field_value(remote_product, name)
            fields.append({
                "name": name,
                "label": label,
                "type": "readonly",
                "required": False,
                "source": "poleepo_remote",
                "language": "",
                "value": "" if remote_value is None else str(remote_value),
                "mapped_value": "",
                "saved": True,
                "missing": False,
                "options": [],
                "options_error": None,
                "help": "Campo letto dal prodotto remoto Poleepo. Non viene modificato da questa operazione.",
                "readonly": True,
            })
        existing_names = {field["name"] for field in fields}
        for name in sorted(remote_product.keys()):
            if name in existing_names or name == "images":
                continue
            remote_value = _poleepo_remote_field_value(remote_product, name)
            fields.append({
                "name": name,
                "label": _humanize_field_name(name),
                "type": "readonly",
                "required": False,
                "source": "poleepo_remote",
                "language": "",
                "value": "" if remote_value is None else str(remote_value),
                "mapped_value": "",
                "saved": True,
                "missing": False,
                "options": [],
                "options_error": None,
                "help": "Campo presente su Poleepo. Non e' ancora mappato per l'update.",
                "readonly": True,
            })
    return {
        "platform": platform_key,
        "label": schema["label"],
        "cod_art": articolo.cod_art,
        "fields": fields,
        "missing_required": [field["name"] for field in fields if field["missing"]],
        "images": {
            "poleepo": _serialize_remote_images(remote_product),
            "ldapp": _product_ldapp_image_preview(articolo),
        } if platform_key == "poleepo" else {},
    }


def _save_product_publication_draft(articolo, platform_key, fields):
    schema = _product_publication_schema(platform_key)
    allowed = {
        (field["name"], field.get("language", "")): field
        for field in schema["fields"]
    }
    saved = []
    for field in fields or []:
        name = str(field.get("name") or "").strip()
        language = str(field.get("language") or "").strip()
        if (name, language) not in allowed:
            continue
        value = field.get("value")
        row = ProductPlatformField.query.filter_by(
            cod_art=articolo.cod_art,
            platform=platform_key,
            field_name=name,
            language=language,
        ).first()
        if not row:
            row = ProductPlatformField(
                cod_art=articolo.cod_art,
                id_art=articolo.id_art,
                platform=platform_key,
                field_name=name,
                language=language,
            )
            db.session.add(row)
        row.id_art = articolo.id_art
        row.value_text = "" if value is None else str(value)
        row.value_json = {
            "schema_source": allowed[(name, language)].get("source") or "manual",
            "saved_from": "publication_draft",
        }
        row.last_sync_at = datetime.utcnow()
        saved.append(row)
    return saved


def _publication_fields_to_payload(draft):
    return {
        field["name"]: field["value"]
        for field in draft.get("fields", [])
    }


def _publish_product_to_platform(articolo, platform_key, draft):
    if draft.get("missing_required"):
        raise ValueError("Campi obbligatori mancanti: " + ", ".join(draft["missing_required"]))

    payload = _publication_fields_to_payload(draft)
    if platform_key == "prestashop":
        result = prestashop_create_product(payload)
        link = ProductPlatformLink.query.filter_by(cod_art=articolo.cod_art, platform=platform_key).first()
        if not link:
            link = ProductPlatformLink(
                cod_art=articolo.cod_art,
                id_art=articolo.id_art,
                platform=platform_key,
            )
            db.session.add(link)
        link.id_art = articolo.id_art
        link.external_id = result["product_id"]
        link.external_url = result.get("external_url")
        link.status = "present"
        link.last_sync_at = datetime.utcnow()
        link.last_error = None
        link.raw_payload = result.get("raw_payload")
        return {
            "platform": platform_key,
            "external_id": link.external_id,
            "external_url": link.external_url,
            "raw_payload": result.get("raw_payload"),
        }
    if platform_key == "poleepo":
        integration = CourierIntegration.query.filter_by(code="poleepo").first()
        connector = PoleepoConnector(integration=integration)
        result = connector.create_product(payload=payload)
        link = ProductPlatformLink.query.filter_by(cod_art=articolo.cod_art, platform=platform_key).first()
        if not link:
            link = ProductPlatformLink(
                cod_art=articolo.cod_art,
                id_art=articolo.id_art,
                platform=platform_key,
            )
            db.session.add(link)
        link.id_art = articolo.id_art
        link.external_id = result["product_id"]
        link.external_url = result.get("external_url")
        link.status = "present"
        link.last_sync_at = datetime.utcnow()
        link.last_error = None
        link.raw_payload = result.get("raw_payload")
        return {
            "platform": platform_key,
            "external_id": link.external_id,
            "external_url": link.external_url,
            "raw_payload": result.get("raw_payload"),
        }

    raise NotImplementedError(f"Pubblicazione prodotto su {platform_key} non ancora disponibile")


def _update_product_on_platform(articolo, platform_key, draft, platform_link):
    if draft.get("missing_required"):
        raise ValueError("Campi obbligatori mancanti: " + ", ".join(draft["missing_required"]))
    if not platform_link or not platform_link.external_id:
        raise ValueError("Prodotto remoto non collegato alla piattaforma selezionata")

    payload = _publication_fields_to_payload(draft)
    if platform_key == "poleepo":
        integration = CourierIntegration.query.filter_by(code="poleepo").first()
        connector = PoleepoConnector(integration=integration)
        result = connector.update_product(product_id=platform_link.external_id, payload=payload)
        platform_link.id_art = articolo.id_art
        platform_link.status = "present"
        platform_link.last_sync_at = datetime.utcnow()
        platform_link.last_error = None
        platform_link.raw_payload = result.get("raw_payload")
        if result.get("external_url"):
            platform_link.external_url = result.get("external_url")
        return {
            "platform": platform_key,
            "external_id": platform_link.external_id,
            "external_url": platform_link.external_url,
            "raw_payload": result.get("raw_payload"),
        }

    raise NotImplementedError(f"Modifica prodotto su {platform_key} non ancora disponibile")


def _asset_public_url(asset):
    if asset.source_platform != "ldapp" and asset.remote_url and asset.id:
        return url_for("search.product_image_preview", cod_art=asset.cod_art, asset_id=asset.id)
    if asset.local_path:
        return url_for("static", filename=asset.local_path)
    return asset.remote_url


def _product_asset_family_key(asset):
    metadata = asset.metadata_json if isinstance(asset.metadata_json, dict) else {}
    family_key = metadata.get("family_key")
    if family_key:
        return str(family_key)
    if metadata.get("published_from_asset_id") is not None:
        return f"asset:{metadata.get('published_from_asset_id')}"
    if asset.content_hash:
        return f"hash:{asset.content_hash}"
    if asset.source_platform == "ldapp" and asset.local_path:
        return f"ldapp:{asset.local_path}"
    if asset.remote_url:
        return f"remote:{asset.remote_url}"
    if asset.local_path:
        return f"local:{asset.local_path}"
    return f"asset:{asset.id}"


def _product_asset_platform_label(platform_key):
    return PRODUCT_IMAGE_PLATFORMS.get(platform_key or "", {}).get("label", platform_key or "ldapp")


def _product_asset_group_summary(assets):
    platforms = []
    seen = set()
    ordered_platforms = list(PRODUCT_IMAGE_PLATFORMS.keys())
    for platform_key in ordered_platforms:
        if any(asset.source_platform == platform_key for asset in assets):
            label = _product_asset_platform_label(platform_key)
            if label not in seen:
                platforms.append(label)
                seen.add(label)
    for asset in assets:
        label = _product_asset_platform_label(asset.source_platform)
        if label not in seen:
            platforms.append(label)
            seen.add(label)
    return " | ".join(platforms)


def _serialize_product_asset(asset):
    return {
        "id": asset.id,
        "url": _asset_public_url(asset),
        "file_img": asset.original_filename,
        "source_platform": asset.source_platform,
        "source_platform_label": _product_asset_platform_label(asset.source_platform),
        "source_external_id": asset.source_external_id,
        "is_primary": bool(asset.is_primary),
        "sort_order": asset.sort_order,
        "family_key": _product_asset_family_key(asset),
        "family_summary": None,
    }


def _sync_product_asset_family_key(asset, family_key):
    metadata = dict(asset.metadata_json or {})
    metadata["family_key"] = family_key
    asset.metadata_json = metadata


def _platform_image_slots(images):
    grouped = {}
    for image in images:
        platform = image.get("source_platform") or "ldapp"
        if platform in {"legacy", "manual"}:
            platform = "ldapp"
        grouped.setdefault(platform, []).append(image)

    return [
        {
            "key": key,
            "label": config["label"],
            "enabled": config["enabled"],
            "icon": config["icon"],
            "images": grouped.get(key, []),
            "primary_image": next(
                (image for image in grouped.get(key, []) if image.get("is_primary")),
                (grouped.get(key) or [None])[0],
            ),
        }
        for key, config in PRODUCT_IMAGE_PLATFORMS.items()
    ]


def _safe_product_image_filename(cod_art, filename):
    original = secure_filename(filename or "")
    _, ext = os.path.splitext(original)
    ext = ext.lower()
    if ext not in ALLOWED_PRODUCT_IMAGE_EXTENSIONS:
        return None
    safe_code = secure_filename(cod_art) or "product"
    return f"{safe_code}_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}{ext}"


def _product_image_local_path(asset):
    if not asset or not asset.local_path:
        return None
    if os.path.isabs(asset.local_path):
        return asset.local_path
    return os.path.join(current_app.static_folder, asset.local_path)


def _product_asset_response_headers(asset):
    headers = {
        "Cache-Control": "private, max-age=60",
    }
    if asset and asset.original_filename:
        headers["Content-Disposition"] = f'inline; filename="{asset.original_filename}"'
    return headers


def _proxy_remote_product_asset(asset):
    if not asset or not asset.remote_url:
        return None

    request_kwargs = {
        "stream": True,
        "timeout": 30,
    }
    prestashop_key = current_app.config.get("PS_KEY") or os.getenv("PRESTASHOP_KEY")
    if prestashop_key and asset.source_platform == "prestashop":
        request_kwargs["auth"] = HTTPBasicAuth(prestashop_key, "")

    upstream = requests.get(asset.remote_url, **request_kwargs)
    if upstream.status_code != 200:
        return None

    content_type = upstream.headers.get("Content-Type") or asset.mime_type or "application/octet-stream"
    content_length = upstream.headers.get("Content-Length")

    def generate():
        try:
            for chunk in upstream.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk
        finally:
            upstream.close()

    response = Response(generate(), mimetype=content_type, direct_passthrough=True)
    if content_length:
        response.headers["Content-Length"] = content_length
    response.headers.update(_product_asset_response_headers(asset))
    return response


def _download_remote_product_asset_to_ldapp(asset, target_cod_art):
    if not asset or not asset.remote_url:
        return None

    request_kwargs = {"timeout": 30}
    prestashop_key = current_app.config.get("PS_KEY") or os.getenv("PRESTASHOP_KEY")
    if prestashop_key and asset.source_platform == "prestashop":
        request_kwargs["auth"] = HTTPBasicAuth(prestashop_key, "")

    upstream = requests.get(asset.remote_url, **request_kwargs)
    if upstream.status_code != 200:
        raise ValueError(f"Download immagine remota non riuscito: HTTP {upstream.status_code}")

    content_type = upstream.headers.get("Content-Type") or asset.mime_type or "image/jpeg"
    extension = mimetypes.guess_extension(content_type.split(";", 1)[0].strip()) or ""
    if extension == ".jpe":
        extension = ".jpg"
    if extension not in ALLOWED_PRODUCT_IMAGE_EXTENSIONS:
        original_ext = os.path.splitext(asset.original_filename or "")[1].lower()
        extension = original_ext if original_ext in ALLOWED_PRODUCT_IMAGE_EXTENSIONS else ".jpg"

    safe_code = secure_filename(target_cod_art) or "product"
    filename = f"{safe_code}_copied_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}{extension}"
    relative_path = f"images/products/ldapp/{filename}"
    target_dir = os.path.join(current_app.static_folder, "images", "products", "ldapp")
    os.makedirs(target_dir, exist_ok=True)
    target_path = os.path.join(target_dir, filename)
    with open(target_path, "wb") as image_file:
        image_file.write(upstream.content)

    return {
        "relative_path": relative_path,
        "filename": filename,
        "content_hash": hashlib.sha256(upstream.content).hexdigest(),
        "mime_type": content_type.split(";", 1)[0].strip(),
    }


def _sync_product_asset_for_platform(articolo, source_asset, platform_key, remote_url, source_external_id):
    source_family_key = _product_asset_family_key(source_asset)
    asset = ProductAsset.query.filter_by(
        cod_art=articolo.cod_art,
        asset_type="image",
        source_platform=platform_key,
        local_path=source_asset.local_path,
    ).first()
    if not asset:
        asset = ProductAsset(
            cod_art=articolo.cod_art,
            id_art=articolo.id_art,
            asset_type="image",
            source_platform=platform_key,
            local_path=source_asset.local_path,
            remote_url=remote_url,
            source_external_id=source_external_id,
            original_filename=source_asset.original_filename,
            content_hash=source_asset.content_hash,
            mime_type=source_asset.mime_type,
            is_primary=source_asset.is_primary,
            sort_order=source_asset.sort_order,
            metadata_json={
                "family_key": source_family_key,
                "published_from_asset_id": source_asset.id,
                "published_at": datetime.utcnow().isoformat(),
            },
        )
        db.session.add(asset)
    else:
        asset.id_art = articolo.id_art
        asset.remote_url = remote_url
        asset.source_external_id = source_external_id
        asset.original_filename = source_asset.original_filename
        asset.content_hash = source_asset.content_hash
        asset.mime_type = source_asset.mime_type
        asset.is_primary = source_asset.is_primary
        asset.sort_order = source_asset.sort_order
        metadata = dict(asset.metadata_json or {})
        metadata.update(
            {
                "family_key": source_family_key,
                "published_from_asset_id": source_asset.id,
                "published_at": datetime.utcnow().isoformat(),
            }
        )
        asset.metadata_json = metadata
    return asset


def _copy_product_asset_to_article(target_articolo, source_asset):
    if not source_asset or source_asset.asset_type != "image":
        raise ValueError("Immagine sorgente non valida")
    if source_asset.cod_art == target_articolo.cod_art:
        raise ValueError("L'immagine appartiene gia' a questo articolo")
    if not source_asset.local_path and not source_asset.remote_url:
        raise ValueError("L'immagine sorgente non ha un percorso copiabile")

    local_path = source_asset.local_path
    original_filename = source_asset.original_filename
    content_hash = source_asset.content_hash
    mime_type = source_asset.mime_type
    if not local_path and source_asset.remote_url:
        downloaded = _download_remote_product_asset_to_ldapp(source_asset, target_articolo.cod_art)
        local_path = downloaded["relative_path"]
        original_filename = original_filename or downloaded["filename"]
        content_hash = downloaded["content_hash"]
        mime_type = downloaded["mime_type"]

    metadata = dict(source_asset.metadata_json or {})
    metadata.update({
        "copied_from_asset_id": source_asset.id,
        "copied_from_cod_art": source_asset.cod_art,
        "copied_at": datetime.utcnow().isoformat(),
    })

    asset = ProductAsset.query.filter_by(
        cod_art=target_articolo.cod_art,
        asset_type="image",
        source_platform="ldapp",
        local_path=local_path,
    ).first()
    if not asset:
        asset = ProductAsset(
            cod_art=target_articolo.cod_art,
            id_art=target_articolo.id_art,
            asset_type="image",
            source_platform="ldapp",
            source_external_id=None,
            local_path=local_path,
            remote_url=source_asset.remote_url if not local_path else None,
            original_filename=original_filename,
            content_hash=content_hash,
            mime_type=mime_type,
            is_primary=False,
            sort_order=source_asset.sort_order,
            metadata_json=metadata,
        )
        db.session.add(asset)
    else:
        asset.id_art = target_articolo.id_art
        asset.original_filename = original_filename or asset.original_filename
        asset.content_hash = content_hash or asset.content_hash
        asset.mime_type = mime_type or asset.mime_type
        asset.metadata_json = metadata
    return asset


def _copy_product_sheet_to_article(target_articolo, source_articolo, overwrite=False):
    if not target_articolo or not source_articolo:
        raise ValueError("Articolo origine o destinazione non valido")
    if target_articolo.cod_art == source_articolo.cod_art:
        raise ValueError("L'articolo origine deve avere un codice diverso")

    source_sheet = SchedeProdotti.query.filter_by(cod_art=source_articolo.cod_art).first()
    if not source_sheet or not ((source_sheet.descrizione or "").strip() or (source_sheet.short or "").strip()):
        return None, "missing_source"

    target_sheet = SchedeProdotti.query.filter_by(cod_art=target_articolo.cod_art).first()
    if target_sheet and not overwrite and ((target_sheet.descrizione or "").strip() or (target_sheet.short or "").strip()):
        return target_sheet, "skipped_existing"

    if not target_sheet:
        target_sheet = SchedeProdotti(
            cod_art=target_articolo.cod_art,
            id_art=target_articolo.id_art,
        )
        db.session.add(target_sheet)
    else:
        target_sheet.id_art = target_articolo.id_art

    target_sheet.descrizione = source_sheet.descrizione
    target_sheet.short = source_sheet.short
    return target_sheet, "copied"


def _copy_product_barcodes_to_article(target_articolo, source_articolo, overwrite=False):
    source_barcodes = Barcode.query.filter_by(cod_art=source_articolo.cod_art).order_by(Barcode.cod_bar.asc()).all()
    if not source_barcodes:
        return [], "missing_source"

    target_barcodes = Barcode.query.filter_by(cod_art=target_articolo.cod_art).order_by(Barcode.cod_bar.asc()).all()
    if target_barcodes and not overwrite:
        return target_barcodes, "skipped_existing"

    if overwrite:
        for barcode in target_barcodes:
            db.session.delete(barcode)
        db.session.flush()

    copied = []
    existing_values = {
        row.cod_bar
        for row in Barcode.query.filter(Barcode.cod_bar.in_([row.cod_bar for row in source_barcodes])).all()
        if row.cod_art == target_articolo.cod_art
    }
    for source_barcode in source_barcodes:
        if source_barcode.cod_bar in existing_values:
            continue
        barcode = Barcode(
            cod_bar=source_barcode.cod_bar,
            cod_art=target_articolo.cod_art,
            id_art=target_articolo.id_art,
        )
        db.session.add(barcode)
        copied.append(barcode)
    return copied, "copied" if copied else "skipped_existing"


def _product_local_copy_preview(articolo, image_limit=8):
    barcodes = Barcode.query.filter_by(cod_art=articolo.cod_art).order_by(Barcode.cod_bar.asc()).all()
    assets = (
        ProductAsset.query
        .filter_by(cod_art=articolo.cod_art, asset_type="image")
        .order_by(ProductAsset.is_primary.desc(), ProductAsset.sort_order.asc(), ProductAsset.id.asc())
        .limit(image_limit)
        .all()
    )
    images = [
        _serialize_product_asset(asset)
        for asset in assets
        if asset.local_path or asset.remote_url
    ]
    return {
        "barcodes": [row.cod_bar for row in barcodes],
        "images": images,
    }


def _product_ldapp_image_preview(articolo, image_limit=20):
    return _product_local_copy_preview(articolo, image_limit=image_limit).get("images") or []


def _publish_product_image_to_platform(articolo, source_asset, platform_key, platform_link):
    if platform_key == "prestashop":
        local_path = _product_image_local_path(source_asset)
        if not local_path and source_asset.remote_url:
            downloaded = _download_remote_product_asset_to_ldapp(source_asset, articolo.cod_art)
            source_asset.local_path = downloaded["relative_path"]
            source_asset.original_filename = source_asset.original_filename or downloaded["filename"]
            source_asset.content_hash = downloaded["content_hash"]
            source_asset.mime_type = downloaded["mime_type"]
            db.session.flush()
            local_path = _product_image_local_path(source_asset)
        if not local_path:
            raise ValueError("L'immagine selezionata non ha un file locale pubblicabile.")
        result = prestashop_upload_product_image(
            platform_link.external_id,
            local_path,
            filename=source_asset.original_filename or os.path.basename(local_path),
            mime_type=source_asset.mime_type,
        )
        published_asset = _sync_product_asset_for_platform(
            articolo,
            source_asset,
            platform_key,
            result["remote_url"],
            result["image_id"],
        )
        platform_link.last_sync_at = datetime.utcnow()
        platform_link.last_error = None
        return {
            "asset": _serialize_product_asset(published_asset),
            "remote_url": result["remote_url"],
            "image_id": result["image_id"],
            "raw_payload": result["raw_payload"],
        }

    if platform_key == "poleepo":
        local_path = _product_image_local_path(source_asset)
        if not local_path and source_asset.remote_url:
            downloaded = _download_remote_product_asset_to_ldapp(source_asset, articolo.cod_art)
            source_asset.local_path = downloaded["relative_path"]
            source_asset.original_filename = source_asset.original_filename or downloaded["filename"]
            source_asset.content_hash = downloaded["content_hash"]
            source_asset.mime_type = downloaded["mime_type"]
            db.session.flush()
            local_path = _product_image_local_path(source_asset)
        if not local_path:
            raise ValueError("L'immagine selezionata non ha un file locale pubblicabile.")
        poleepo_integration = CourierIntegration.query.filter_by(code="poleepo").first()
        connector = PoleepoConnector(integration=poleepo_integration)
        result = connector.upload_image(
            product_id=platform_link.external_id,
            image_path=local_path,
            filename=source_asset.original_filename or os.path.basename(local_path),
            mime_type=source_asset.mime_type,
            source_url=url_for("static", filename=source_asset.local_path, _external=True),
        )
        published_asset = _sync_product_asset_for_platform(
            articolo,
            source_asset,
            platform_key,
            result["remote_url"],
            result["image_id"],
        )
        platform_link.last_sync_at = datetime.utcnow()
        platform_link.last_error = None
        return {
            "asset": _serialize_product_asset(published_asset),
            "remote_url": result["remote_url"],
            "image_id": result["image_id"],
            "raw_payload": result["raw_payload"],
        }

    raise NotImplementedError(f"Pubblicazione immagini su {platform_key} non ancora disponibile")


def _delete_product_image_from_platform(articolo, asset, platform_key, platform_link):
    if platform_key == "prestashop":
        if not asset.source_external_id:
            raise ValueError("L'immagine Prestashop non ha un identificativo remoto valido.")
        if not platform_link or not platform_link.external_id:
            raise ValueError("Prodotto Prestashop non presente")
        return prestashop_delete_product_image(platform_link.external_id, asset.source_external_id)

    if platform_key == "poleepo":
        if not asset.source_external_id:
            raise ValueError("L'immagine Poleepo non ha un identificativo remoto valido.")
        if not platform_link or not platform_link.external_id:
            raise ValueError("Prodotto Poleepo non presente")
        poleepo_integration = CourierIntegration.query.filter_by(code="poleepo").first()
        connector = PoleepoConnector(integration=poleepo_integration)
        return connector.delete_image(
            product_id=platform_link.external_id,
            image_id=asset.source_external_id,
            image_url=asset.remote_url,
        )

    raise NotImplementedError(f"Cancellazione immagini su {platform_key} non ancora disponibile")


def _product_asset_group_assets(cod_art, asset):
    family_key = _product_asset_family_key(asset)
    candidates = (
        ProductAsset.query
        .filter_by(cod_art=cod_art, asset_type="image")
        .all()
    )
    return [row for row in candidates if _product_asset_family_key(row) == family_key]


@log_task(logger)
def get_product_by_code(cod_art):
    prod = Articoli.query.filter_by(cod_art=cod_art).first()
    asset_rows = (
        ProductAsset.query
        .filter_by(cod_art=cod_art, asset_type="image")
        .order_by(ProductAsset.is_primary.desc(), ProductAsset.sort_order.asc(), ProductAsset.id.asc())
        .all()
    )
    family_groups = {}
    for asset in asset_rows:
        family_groups.setdefault(_product_asset_family_key(asset), []).append(asset)

    immagini = []
    for asset in asset_rows:
        if not asset.local_path and not asset.remote_url:
            continue
        serialized = _serialize_product_asset(asset)
        group_assets = family_groups.get(serialized["family_key"], [asset])
        serialized["family_summary"] = _product_asset_group_summary(group_assets)
        serialized["group_asset_ids"] = [row.id for row in group_assets]
        serialized["group_platforms"] = []
        seen_platforms = set()
        for platform_key in PRODUCT_IMAGE_PLATFORMS.keys():
            if any(row.source_platform == platform_key for row in group_assets):
                serialized["group_platforms"].append(platform_key)
                seen_platforms.add(platform_key)
        for row in group_assets:
            if row.source_platform and row.source_platform not in seen_platforms:
                serialized["group_platforms"].append(row.source_platform)
                seen_platforms.add(row.source_platform)
        immagini.append(serialized)

    if not immagini:
        immagini = [
            {
                "id": None,
                "url": url_for("static", filename=f"images/products/{img.file_img}"),
                "file_img": img.file_img,
                "source_platform": "legacy",
                "source_platform_label": "Legacy",
                "source_external_id": None,
                "is_primary": False,
                "sort_order": 0,
                "family_key": f"legacy:{img.file_img}",
                "family_summary": "Legacy",
                "group_asset_ids": [],
                "group_platforms": ["legacy"],
            }
            for img in Immagini.query.filter_by(cod_art=cod_art).all()
        ]
    giacenze = Giacenza.query.filter_by(cod_art=cod_art).first()

    if prod:
        scheda = SchedeProdotti.query.filter_by(cod_art=cod_art).first()
        scheda_art = clean_text(scheda.descrizione) if scheda else "---"
        barcode_rows = Barcode.query.filter_by(cod_art=cod_art).order_by(Barcode.cod_bar.asc()).all()
        platform_links = {
            row.platform: row
            for row in ProductPlatformLink.query.filter_by(cod_art=cod_art).all()
        }
        platforms = [
            {
                "key": key,
                "label": config["label"],
                "active": key in platform_links and platform_links[key].status not in ("absent", "error"),
                "supported": config["enabled"],
                "status": platform_links[key].status if key in platform_links else "absent",
                "external_id": platform_links[key].external_id if key in platform_links else None,
                "can_publish_product": _can_publish_product_to_platform(key, platform_links),
                "can_update_product": _can_update_product_on_platform(key, platform_links),
            }
            for key, config in PRODUCT_IMAGE_PLATFORMS.items()
            if key != "ldapp"
        ]
        return {
            "cod_art": cod_art,
            "barcodes": [row.cod_bar for row in barcode_rows],
            "platforms": platforms,
            "publishable_platforms": [platform for platform in platforms if platform["can_publish_product"]],
            "editable_platforms": [platform for platform in platforms if platform["can_update_product"]],
            "image_slots": _platform_image_slots(immagini),
            "can_manage_images": _can_manage_product_images(),
            "can_publish_products": _can_manage_product_images(),
            "descrizione": prod.descrizione,
            "descrizione_aggiuntiva": prod.descrizione_aggiuntiva,
            "prezzo": prod.prezzo,
            "immagini": immagini,
            "inStore": giacenze.giac_neg if giacenze else 0,
            "www": giacenze.giac_www if giacenze else 0,
            "scheda_tecnica": scheda_art
        }
    else:
        return None


@search_bp.route('/scheda_articolo/<cod_art>')
@login_required
def scheda_articolo(cod_art):
    logger.info(f">>> Chiamata a /scheda_articolo/{cod_art}")
    product = get_product_by_code(cod_art)
    if product is None:
        logger.warning(f"Articolo {cod_art} non trovato - abort 404")
        abort(404)
    return render_template('scheda_articolo.html', product=product)


@search_bp.get('/scheda_articolo/<cod_art>/publish/<platform_key>/draft')
@login_required
def product_publication_draft(cod_art, platform_key):
    if not _can_manage_product_images():
        return jsonify({"ok": False, "error": "Accesso negato"}), 403

    articolo = Articoli.query.filter_by(cod_art=cod_art).first()
    if not articolo:
        return jsonify({"ok": False, "error": "Articolo non trovato."}), 404

    platform_key = (platform_key or "").strip().lower()
    platform_links = {link.platform: link for link in ProductPlatformLink.query.filter_by(cod_art=cod_art).all()}
    if not (
        _can_publish_product_to_platform(platform_key, platform_links)
        or _can_update_product_on_platform(platform_key, platform_links)
    ):
        return jsonify({"ok": False, "error": "Piattaforma non pubblicabile o modificabile."}), 400

    try:
        draft = _build_product_publication_draft(
            articolo,
            platform_key,
            include_options=True,
            platform_link=platform_links.get(platform_key),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "draft": draft})


@search_bp.post('/scheda_articolo/<cod_art>/publish/<platform_key>/draft')
@login_required
def save_product_publication_draft(cod_art, platform_key):
    if not _can_manage_product_images():
        return jsonify({"ok": False, "error": "Accesso negato"}), 403

    articolo = Articoli.query.filter_by(cod_art=cod_art).first()
    if not articolo:
        return jsonify({"ok": False, "error": "Articolo non trovato."}), 404

    platform_key = (platform_key or "").strip().lower()
    platform_links = {link.platform: link for link in ProductPlatformLink.query.filter_by(cod_art=cod_art).all()}
    if not (
        _can_publish_product_to_platform(platform_key, platform_links)
        or _can_update_product_on_platform(platform_key, platform_links)
    ):
        return jsonify({"ok": False, "error": "Piattaforma non pubblicabile o modificabile."}), 400

    payload = request.get_json(silent=True) or {}
    try:
        saved_rows = _save_product_publication_draft(articolo, platform_key, payload.get("fields") or [])
        db.session.commit()
        draft = _build_product_publication_draft(
            articolo,
            platform_key,
            include_options=False,
            platform_link=platform_links.get(platform_key),
            prefer_saved=True,
        )
        return jsonify({"ok": True, "saved": len(saved_rows), "draft": draft})
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        logger.exception("Errore salvataggio bozza pubblicazione %s per %s", platform_key, cod_art)
        return jsonify({"ok": False, "error": str(exc)}), 500


@search_bp.get('/scheda_articolo/<cod_art>/publish/<platform_key>/copy-candidates')
@login_required
def product_publication_copy_candidates(cod_art, platform_key):
    if not _can_manage_product_images():
        return jsonify({"ok": False, "error": "Accesso negato"}), 403

    target_articolo = Articoli.query.filter_by(cod_art=cod_art).first()
    if not target_articolo:
        return jsonify({"ok": False, "error": "Articolo non trovato."}), 404

    platform_key = (platform_key or "").strip().lower()
    if platform_key != "poleepo":
        return jsonify({"ok": False, "error": "Copia valori disponibile solo per Poleepo."}), 400

    target_links = {link.platform: link for link in ProductPlatformLink.query.filter_by(cod_art=cod_art).all()}
    if not _can_update_product_on_platform(platform_key, target_links):
        return jsonify({"ok": False, "error": "Prodotto corrente non modificabile su Poleepo."}), 400

    query = (request.args.get("q") or "").strip()
    if len(query) < 2:
        return jsonify({"ok": True, "items": []})

    articles = (
        Articoli.query
        .join(ProductPlatformLink, ProductPlatformLink.cod_art == Articoli.cod_art)
        .filter(
            ProductPlatformLink.platform == platform_key,
            ProductPlatformLink.status.notin_(["absent", "error"]),
            ProductPlatformLink.external_id.isnot(None),
            Articoli.cod_art != cod_art,
            or_(
                Articoli.cod_art.ilike(f"%{query}%"),
                Articoli.descrizione.ilike(f"%{query}%"),
                Articoli.descrizione_aggiuntiva.ilike(f"%{query}%"),
            ),
        )
        .order_by(Articoli.cod_art.asc())
        .limit(20)
        .all()
    )

    target_identity = _product_identity_value(target_articolo)
    items = []
    for articolo in articles:
        if _product_identity_value(articolo) == target_identity:
            continue
        link = ProductPlatformLink.query.filter_by(cod_art=articolo.cod_art, platform=platform_key).first()
        items.append({
            "cod_art": articolo.cod_art,
            "descrizione": articolo.descrizione or "",
            "descrizione_aggiuntiva": articolo.descrizione_aggiuntiva or "",
            "external_id": link.external_id if link else None,
            "local_copy": _product_local_copy_preview(articolo),
        })
    return jsonify({"ok": True, "items": items})


@search_bp.get('/scheda_articolo/<cod_art>/publish/<platform_key>/copy-values')
@login_required
def product_publication_copy_values(cod_art, platform_key):
    if not _can_manage_product_images():
        return jsonify({"ok": False, "error": "Accesso negato"}), 403

    target_articolo = Articoli.query.filter_by(cod_art=cod_art).first()
    if not target_articolo:
        return jsonify({"ok": False, "error": "Articolo non trovato."}), 404

    platform_key = (platform_key or "").strip().lower()
    if platform_key != "poleepo":
        return jsonify({"ok": False, "error": "Copia valori disponibile solo per Poleepo."}), 400

    target_links = {link.platform: link for link in ProductPlatformLink.query.filter_by(cod_art=cod_art).all()}
    if not _can_update_product_on_platform(platform_key, target_links):
        return jsonify({"ok": False, "error": "Prodotto corrente non modificabile su Poleepo."}), 400

    source_cod_art = (request.args.get("source_cod_art") or "").strip()
    source_articolo = Articoli.query.filter_by(cod_art=source_cod_art).first()
    try:
        _validate_distinct_source_product(target_articolo, source_articolo)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    source_link = ProductPlatformLink.query.filter_by(cod_art=source_cod_art, platform=platform_key).first()
    if not _can_update_product_on_platform(platform_key, {platform_key: source_link}):
        return jsonify({"ok": False, "error": "Articolo origine non collegato a Poleepo."}), 400

    try:
        draft = _build_product_publication_draft(
            source_articolo,
            platform_key,
            include_options=False,
            platform_link=source_link,
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    editable_fields = [
        field for field in draft.get("fields", [])
        if not field.get("readonly")
    ]
    return jsonify({
        "ok": True,
        "source": {
            "cod_art": source_articolo.cod_art,
            "descrizione": source_articolo.descrizione or "",
            "descrizione_aggiuntiva": source_articolo.descrizione_aggiuntiva or "",
            "external_id": source_link.external_id,
        },
        "fields": editable_fields,
        "local_copy": {
            "can_copy_sheet": bool(SchedeProdotti.query.filter_by(cod_art=source_cod_art).first()),
            **_product_local_copy_preview(source_articolo, image_limit=20),
        },
    })


@search_bp.post('/scheda_articolo/<cod_art>/copy-local-data')
@login_required
def copy_product_local_data(cod_art):
    if not _can_manage_product_images():
        return jsonify({"ok": False, "error": "Accesso negato"}), 403

    target_articolo = Articoli.query.filter_by(cod_art=cod_art).first()
    if not target_articolo:
        return jsonify({"ok": False, "error": "Articolo non trovato."}), 404

    payload = request.get_json(silent=True) or {}
    source_cod_art = (payload.get("source_cod_art") or "").strip()
    source_articolo = Articoli.query.filter_by(cod_art=source_cod_art).first()
    try:
        _validate_distinct_source_product(target_articolo, source_articolo)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    results = {}
    try:
        copied_assets = []
        raw_asset_ids = payload.get("asset_ids") or []
        if isinstance(raw_asset_ids, (int, str)):
            raw_asset_ids = [raw_asset_ids]
        asset_ids = []
        for raw_asset_id in raw_asset_ids:
            try:
                asset_id = int(raw_asset_id)
            except (TypeError, ValueError):
                continue
            if asset_id not in asset_ids:
                asset_ids.append(asset_id)
        if asset_ids:
            source_assets = (
                ProductAsset.query
                .filter(ProductAsset.id.in_(asset_ids), ProductAsset.asset_type == "image")
                .all()
            )
            assets_by_id = {asset.id: asset for asset in source_assets}
            for asset_id in asset_ids:
                source_asset = assets_by_id.get(asset_id)
                if not source_asset:
                    continue
                if source_asset.cod_art != source_articolo.cod_art:
                    raise ValueError("Una immagine selezionata non appartiene all'articolo origine")
                copied_assets.append(_copy_product_asset_to_article(target_articolo, source_asset))
            results["images"] = {
                "status": "copied" if copied_assets else "missing_source",
                "copied": len(copied_assets),
                "assets": [_serialize_product_asset(asset) for asset in copied_assets],
            }
        if payload.get("copy_sheet", True):
            sheet, status = _copy_product_sheet_to_article(
                target_articolo,
                source_articolo,
                overwrite=bool(payload.get("overwrite_sheet")),
            )
            results["sheet"] = {
                "status": status,
                "copied": status == "copied",
                "has_sheet": bool(sheet),
            }
        if payload.get("copy_barcodes", True):
            barcodes, status = _copy_product_barcodes_to_article(
                target_articolo,
                source_articolo,
                overwrite=bool(payload.get("overwrite_barcodes")),
            )
            results["barcodes"] = {
                "status": status,
                "copied": len(barcodes) if status == "copied" else 0,
                "values": [row.cod_bar for row in barcodes],
            }
        db.session.commit()
        return jsonify({"ok": True, "results": results})
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        logger.exception("Errore copia dati locali da %s a %s", source_cod_art, cod_art)
        return jsonify({"ok": False, "error": str(exc)}), 500


@search_bp.post('/scheda_articolo/<cod_art>/publish/<platform_key>')
@login_required
def publish_product_to_platform(cod_art, platform_key):
    if not _can_manage_product_images():
        return jsonify({"ok": False, "error": "Accesso negato"}), 403

    articolo = Articoli.query.filter_by(cod_art=cod_art).first()
    if not articolo:
        return jsonify({"ok": False, "error": "Articolo non trovato."}), 404

    platform_key = (platform_key or "").strip().lower()
    platform_links = {link.platform: link for link in ProductPlatformLink.query.filter_by(cod_art=cod_art).all()}
    if not _can_publish_product_to_platform(platform_key, platform_links):
        return jsonify({"ok": False, "error": "Articolo gia' presente o piattaforma non pubblicabile."}), 400

    payload = request.get_json(silent=True) or {}
    try:
        if payload.get("fields"):
            _save_product_publication_draft(articolo, platform_key, payload.get("fields") or [])
            db.session.flush()
        draft = _build_product_publication_draft(
            articolo,
            platform_key,
            include_options=False,
            platform_link=platform_links.get(platform_key),
            prefer_saved=True,
        )
        result = _publish_product_to_platform(articolo, platform_key, draft)
        db.session.commit()
        return jsonify({"ok": True, "result": result})
    except NotImplementedError as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 400
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        logger.exception("Errore pubblicazione prodotto su %s per %s", platform_key, cod_art)
        return jsonify({"ok": False, "error": str(exc)}), 500


@search_bp.post('/scheda_articolo/<cod_art>/publish/<platform_key>/update')
@login_required
def update_product_on_platform(cod_art, platform_key):
    if not _can_manage_product_images():
        return jsonify({"ok": False, "error": "Accesso negato"}), 403

    articolo = Articoli.query.filter_by(cod_art=cod_art).first()
    if not articolo:
        return jsonify({"ok": False, "error": "Articolo non trovato."}), 404

    platform_key = (platform_key or "").strip().lower()
    platform_links = {link.platform: link for link in ProductPlatformLink.query.filter_by(cod_art=cod_art).all()}
    if not _can_update_product_on_platform(platform_key, platform_links):
        return jsonify({"ok": False, "error": "Prodotto non presente o piattaforma non modificabile."}), 400

    payload = request.get_json(silent=True) or {}
    try:
        if payload.get("fields"):
            _save_product_publication_draft(articolo, platform_key, payload.get("fields") or [])
            db.session.flush()
        draft = _build_product_publication_draft(
            articolo,
            platform_key,
            include_options=False,
            platform_link=platform_links.get(platform_key),
            prefer_saved=True,
        )
        result = _update_product_on_platform(articolo, platform_key, draft, platform_links.get(platform_key))
        db.session.commit()
        return jsonify({"ok": True, "result": result})
    except NotImplementedError as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 400
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        logger.exception("Errore modifica prodotto su %s per %s", platform_key, cod_art)
        return jsonify({"ok": False, "error": str(exc)}), 500


@search_bp.post('/scheda_articolo/<cod_art>/images')
@login_required
def upload_product_image(cod_art):
    if not _can_manage_product_images():
        return jsonify({"ok": False, "error": "Accesso negato"}), 403

    articolo = Articoli.query.filter_by(cod_art=cod_art).first()
    if not articolo:
        return jsonify({"ok": False, "error": "Articolo non trovato."}), 404

    uploaded = request.files.get("image")
    if not uploaded or not uploaded.filename:
        return jsonify({"ok": False, "error": "Nessuna immagine selezionata."}), 400

    filename = _safe_product_image_filename(cod_art, uploaded.filename)
    if not filename:
        return jsonify({"ok": False, "error": "Formato immagine non consentito."}), 400

    target_dir = os.path.join(current_app.static_folder, "images", "products", "ldapp")
    os.makedirs(target_dir, exist_ok=True)
    target_path = os.path.join(target_dir, filename)
    uploaded.save(target_path)

    with open(target_path, "rb") as saved_file:
        content_hash = hashlib.sha256(saved_file.read()).hexdigest()

    relative_path = f"images/products/ldapp/{filename}"
    asset = ProductAsset.query.filter_by(
        cod_art=cod_art,
        asset_type="image",
        source_platform="ldapp",
        content_hash=content_hash,
    ).first()
    if not asset:
        max_sort = (
            db.session.query(db.func.max(ProductAsset.sort_order))
            .filter_by(cod_art=cod_art, asset_type="image")
            .scalar()
            or 0
        )
        asset = ProductAsset(
            cod_art=cod_art,
            id_art=articolo.id_art,
            asset_type="image",
            source_platform="ldapp",
            local_path=relative_path,
            original_filename=uploaded.filename,
            content_hash=content_hash,
            mime_type=uploaded.mimetype or mimetypes.guess_type(filename)[0],
            sort_order=max_sort + 1,
        )
        db.session.add(asset)
        db.session.flush()
        _sync_product_asset_family_key(asset, f"asset:{asset.id}")
    else:
        if os.path.exists(target_path) and asset.local_path != relative_path:
            os.remove(target_path)
        asset.local_path = asset.local_path or relative_path
        asset.original_filename = asset.original_filename or uploaded.filename
        asset.mime_type = asset.mime_type or uploaded.mimetype or mimetypes.guess_type(filename)[0]
        if not (asset.metadata_json or {}).get("family_key"):
            _sync_product_asset_family_key(asset, f"asset:{asset.id}")

    db.session.commit()
    return jsonify({"ok": True, "asset": _serialize_product_asset(asset)})


@search_bp.get('/scheda_articolo/<cod_art>/images/copy-candidates')
@login_required
def product_image_copy_candidates(cod_art):
    if not _can_manage_product_images():
        return jsonify({"ok": False, "error": "Accesso negato"}), 403

    query = (request.args.get("q") or "").strip()
    if len(query) < 2:
        return jsonify({"ok": True, "items": []})

    articles = (
        Articoli.query
        .filter(
            Articoli.cod_art != cod_art,
            or_(
                Articoli.cod_art.ilike(f"%{query}%"),
                Articoli.descrizione.ilike(f"%{query}%"),
                Articoli.descrizione_aggiuntiva.ilike(f"%{query}%"),
            )
        )
        .order_by(Articoli.cod_art.asc())
        .limit(20)
        .all()
    )

    items = []
    for articolo in articles:
        assets = (
            ProductAsset.query
            .filter_by(cod_art=articolo.cod_art, asset_type="image")
            .order_by(ProductAsset.is_primary.desc(), ProductAsset.sort_order.asc(), ProductAsset.id.asc())
            .limit(12)
            .all()
        )
        images = [
            _serialize_product_asset(asset)
            for asset in assets
            if asset.local_path or asset.remote_url
        ]
        if not images:
            continue
        items.append({
            "cod_art": articolo.cod_art,
            "descrizione": articolo.descrizione or "",
            "descrizione_aggiuntiva": articolo.descrizione_aggiuntiva or "",
            "images": images,
        })

    return jsonify({"ok": True, "items": items})


@search_bp.post('/scheda_articolo/<cod_art>/images/copy')
@login_required
def copy_product_image(cod_art):
    if not _can_manage_product_images():
        return jsonify({"ok": False, "error": "Accesso negato"}), 403

    target_articolo = Articoli.query.filter_by(cod_art=cod_art).first()
    if not target_articolo:
        return jsonify({"ok": False, "error": "Articolo non trovato."}), 404

    payload = request.get_json(silent=True) or {}
    raw_asset_ids = payload.get("asset_ids")
    if raw_asset_ids is None:
        raw_asset_ids = [payload.get("asset_id")]
    if not isinstance(raw_asset_ids, list):
        return jsonify({"ok": False, "error": "Selezione immagini non valida."}), 400

    source_asset_ids = []
    for raw_asset_id in raw_asset_ids:
        try:
            source_asset_id = int(raw_asset_id)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "Immagine sorgente non valida."}), 400
        if source_asset_id not in source_asset_ids:
            source_asset_ids.append(source_asset_id)

    if not source_asset_ids:
        return jsonify({"ok": False, "error": "Seleziona almeno una immagine."}), 400

    source_assets = (
        ProductAsset.query
        .filter(ProductAsset.id.in_(source_asset_ids), ProductAsset.asset_type == "image")
        .all()
    )
    assets_by_id = {asset.id: asset for asset in source_assets}
    missing_ids = [asset_id for asset_id in source_asset_ids if asset_id not in assets_by_id]
    if missing_ids:
        return jsonify({"ok": False, "error": "Una o piu' immagini sorgente non sono state trovate."}), 404

    try:
        copied_assets = [
            _copy_product_asset_to_article(target_articolo, assets_by_id[source_asset_id])
            for source_asset_id in source_asset_ids
        ]
        db.session.commit()
        serialized_assets = [_serialize_product_asset(asset) for asset in copied_assets]
        return jsonify({
            "ok": True,
            "asset": serialized_assets[0] if serialized_assets else None,
            "assets": serialized_assets,
            "copied": len(serialized_assets),
        })
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        logger.exception("Errore copia immagini verso %s", cod_art)
        return jsonify({"ok": False, "error": str(exc)}), 500


@search_bp.route('/scheda_articolo/<cod_art>/images/<int:asset_id>/preview')
@login_required
def product_image_preview(cod_art, asset_id):
    asset = ProductAsset.query.filter_by(id=asset_id, cod_art=cod_art, asset_type="image").first()
    if not asset:
        abort(404)

    if asset.source_platform != "ldapp" and asset.remote_url:
        proxied = _proxy_remote_product_asset(asset)
        if proxied:
            return proxied

    local_path = _product_image_local_path(asset)
    if local_path and os.path.exists(local_path):
        return current_app.send_static_file(asset.local_path)

    abort(404)


@search_bp.post('/scheda_articolo/<cod_art>/images/publish')
@login_required
def publish_product_image(cod_art):
    if not _can_manage_product_images():
        return jsonify({"ok": False, "error": "Accesso negato"}), 403

    articolo = Articoli.query.filter_by(cod_art=cod_art).first()
    if not articolo:
        return jsonify({"ok": False, "error": "Articolo non trovato."}), 404

    payload = request.get_json(silent=True) or {}
    asset_id = payload.get("asset_id") or request.form.get("asset_id")
    requested_platforms = payload.get("platforms") or request.form.getlist("platforms")
    if isinstance(requested_platforms, str):
        requested_platforms = [requested_platforms]
    requested_platforms = [str(platform).strip().lower() for platform in requested_platforms if str(platform).strip()]
    requested_platforms = list(dict.fromkeys(requested_platforms))

    if not asset_id:
        return jsonify({"ok": False, "error": "Immagine non selezionata."}), 400
    if not requested_platforms:
        return jsonify({"ok": False, "error": "Nessuna piattaforma selezionata."}), 400

    try:
        asset_id = int(asset_id)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Riferimento immagine non valido."}), 400

    source_asset = ProductAsset.query.filter_by(id=asset_id, cod_art=cod_art, asset_type="image").first()
    if not source_asset:
        return jsonify({"ok": False, "error": "Immagine non trovata."}), 404

    if not (source_asset.metadata_json or {}).get("family_key"):
        _sync_product_asset_family_key(source_asset, f"asset:{source_asset.id}")
        db.session.flush()

    link_map = {link.platform: link for link in ProductPlatformLink.query.filter_by(cod_art=cod_art).all()}
    results = {}
    any_success = False

    try:
        for platform_key in requested_platforms:
            config = PRODUCT_IMAGE_PLATFORMS.get(platform_key)
            if not config:
                results[platform_key] = {"ok": False, "error": "Piattaforma sconosciuta"}
                continue
            if platform_key == "ldapp":
                results[platform_key] = {"ok": False, "error": "LDApp è solo sorgente locale"}
                continue
            if not config["enabled"]:
                results[platform_key] = {"ok": False, "error": "Pubblicazione non ancora disponibile"}
                continue
            platform_link = link_map.get(platform_key)
            if not platform_link or platform_link.status in ("absent", "error") or not platform_link.external_id:
                results[platform_key] = {"ok": False, "error": "Articolo non presente su questa piattaforma"}
                continue
            try:
                publish_result = _publish_product_image_to_platform(articolo, source_asset, platform_key, platform_link)
                results[platform_key] = {"ok": True, **publish_result}
                any_success = True
            except NotImplementedError as exc:
                results[platform_key] = {"ok": False, "error": str(exc)}
            except Exception as exc:
                logger.exception("Errore pubblicazione immagine su %s per %s", platform_key, cod_art)
                platform_link.last_error = str(exc)
                results[platform_key] = {"ok": False, "error": str(exc)}
        db.session.commit()
    except SQLAlchemyError as exc:
        db.session.rollback()
        logger.exception("Errore DB nella pubblicazione immagini per %s", cod_art)
        return jsonify({"ok": False, "error": str(exc)}), 500

    status_code = 200 if any_success else 400
    return jsonify({"ok": any_success, "results": results}), status_code


@search_bp.post('/scheda_articolo/<cod_art>/images/<int:asset_id>/primary')
@login_required
def set_product_image_primary(cod_art, asset_id):
    if not _can_manage_product_images():
        return jsonify({"ok": False, "error": "Accesso negato"}), 403

    asset = ProductAsset.query.filter_by(id=asset_id, cod_art=cod_art, asset_type="image").first()
    if not asset:
        return jsonify({"ok": False, "error": "Immagine non trovata."}), 404

    family_assets = _product_asset_group_assets(cod_art, asset)
    if not family_assets:
        family_assets = [asset]

    try:
        family_key = _product_asset_family_key(asset)
        for row in ProductAsset.query.filter_by(cod_art=cod_art, asset_type="image").all():
            row.is_primary = _product_asset_family_key(row) == family_key
        db.session.commit()
        return jsonify({"ok": True, "asset_id": asset.id, "family_key": family_key})
    except Exception as exc:
        db.session.rollback()
        logger.exception("Errore impostazione primary immagine per %s", cod_art)
        return jsonify({"ok": False, "error": str(exc)}), 500


@search_bp.post('/scheda_articolo/<cod_art>/images/delete')
@login_required
def delete_product_images(cod_art):
    if not _can_manage_product_images():
        return jsonify({"ok": False, "error": "Accesso negato"}), 403

    articolo = Articoli.query.filter_by(cod_art=cod_art).first()
    if not articolo:
        return jsonify({"ok": False, "error": "Articolo non trovato."}), 404

    payload = request.get_json(silent=True) or {}
    raw_asset_ids = payload.get("asset_ids") or []
    if isinstance(raw_asset_ids, (int, str)):
        raw_asset_ids = [raw_asset_ids]

    asset_ids = []
    for raw_id in raw_asset_ids:
        try:
            asset_ids.append(int(raw_id))
        except (TypeError, ValueError):
            continue
    asset_ids = list(dict.fromkeys(asset_ids))

    if not asset_ids:
        return jsonify({"ok": False, "error": "Nessuna immagine selezionata."}), 400

    assets = (
        ProductAsset.query
        .filter(ProductAsset.cod_art == cod_art, ProductAsset.asset_type == "image", ProductAsset.id.in_(asset_ids))
        .all()
    )
    if not assets:
        return jsonify({"ok": False, "error": "Immagini non trovate."}), 404

    platform_links = {
        row.platform: row
        for row in ProductPlatformLink.query.filter_by(cod_art=cod_art).all()
    }
    results = {}
    deleted_asset_ids = set()
    local_paths_to_consider = set()

    try:
        for asset in assets:
            platform_key = asset.source_platform or "ldapp"
            if platform_key == "ldapp":
                local_path = _product_image_local_path(asset)
                if local_path:
                    local_paths_to_consider.add(local_path)
                db.session.delete(asset)
                results[str(asset.id)] = {"ok": True, "deleted": "ldapp"}
                deleted_asset_ids.add(asset.id)
                continue

            if platform_key in {"prestashop", "poleepo"} and asset.source_external_id:
                platform_link = platform_links.get(platform_key)
                if not platform_link or not platform_link.external_id:
                    results[str(asset.id)] = {"ok": False, "error": f"Prodotto {platform_key.capitalize()} non presente"}
                    continue
                try:
                    _delete_product_image_from_platform(articolo, asset, platform_key, platform_link)
                except (ShippingConnectorNotConfigured, ShippingConnectorError, NotImplementedError, ValueError) as exc:
                    results[str(asset.id)] = {"ok": False, "error": str(exc)}
                    continue
                except Exception as exc:
                    logger.exception("Errore cancellazione immagine su %s per %s", platform_key, cod_art)
                    results[str(asset.id)] = {"ok": False, "error": str(exc)}
                    continue

            db.session.delete(asset)
            results[str(asset.id)] = {"ok": True, "deleted": platform_key}
            deleted_asset_ids.add(asset.id)

        if local_paths_to_consider:
            remaining_local_refs = {
                row.local_path
                for row in ProductAsset.query.filter(
                    ProductAsset.cod_art == cod_art,
                    ProductAsset.asset_type == "image",
                    ProductAsset.id.notin_(deleted_asset_ids),
                    ProductAsset.local_path.in_(list(local_paths_to_consider)),
                ).all()
                if row.local_path
            }
            for local_path in list(local_paths_to_consider):
                if local_path in remaining_local_refs:
                    continue
                abs_path = os.path.join(current_app.static_folder, local_path)
                if os.path.exists(abs_path):
                    try:
                        os.remove(abs_path)
                    except Exception as exc:
                        results[local_path] = {"ok": False, "error": str(exc)}

        db.session.commit()
        return jsonify({"ok": True, "results": results})
    except Exception as exc:
        db.session.rollback()
        logger.exception("Errore eliminazione immagini per %s", cod_art)
        return jsonify({"ok": False, "error": str(exc)}), 500


@search_bp.route('/ricerca_x_barcode', methods=['GET', 'POST'])
@login_required
def ricerca_x_barcode():
    logger.info(">>> Chiamata a /ricerca_x_barcode")
    return render_template('articoli_codebar.html')


@search_bp.route('/ricerca_x_descrizione', methods=['GET', 'POST'])
@login_required
def ricerca_x_descrizione():
    logger.info(">>> Chiamata a /ricerca_x_descrizione")
    return render_template('articoli_description.html')


@search_bp.route('/dati_articolo/<cod_art>', methods=['GET'])
@login_required
def dati_articolo(cod_art):
    logger.info(f">>> Chiamata a /dati_articolo/{cod_art}")
    articolo = Articoli.query.filter_by(cod_art=cod_art).first()

    if not articolo:
        return jsonify({'success': False, 'error': 'Articolo non trovato.'})

    immagini = [img.file_img for img in Immagini.query.filter_by(cod_art=cod_art).all()]
    giacenze = Giacenza.query.filter_by(cod_art=cod_art).first()
    scheda = SchedeProdotti.query.filter_by(cod_art=cod_art).first()

    return jsonify({
        'success': True,
        'cod_art': articolo.cod_art,
        'descrizione': articolo.descrizione,
        'descrizione_aggiuntiva': articolo.descrizione_aggiuntiva,
        'prezzo': articolo.prezzo,
        'immagini': immagini,
        'giacenza': {
            'inStore': giacenze.giac_neg if giacenze else 0,
            'online': giacenze.giac_www if giacenze else 0
        },
        'scheda_tecnica': clean_text(scheda.descrizione) if scheda else "---",
        'ppc': articolo.ppc if hasattr(articolo, 'ppc') else 1,
        'cpp': articolo.cpp if hasattr(articolo, 'cpp') else 1
    })


@search_bp.route('/dati_articolo_by_barcode', methods=['GET'])
@login_required
def dati_articolo_by_barcode():
    barcode = request.args.get('barcode')
    if not barcode:
        return jsonify({'success': False, 'error': 'Barcode mancante'})

    cb = Barcode.query.filter_by(cod_bar=barcode).first()
    if not cb:
        return jsonify({'success': False, 'error': 'Prodotto non trovato per barcode'})
    logger.info(f"Codice articolo trovato per barcode {barcode}: {cb.cod_art}")
    articolo = Articoli.query.filter_by(cod_art=cb.cod_art).first()
    logger.info(f"Articolo trovato per codice articolo {cb.cod_art}: {articolo}")

    if not articolo:
        return jsonify({'success': False, 'error': 'Articolo non trovato'})

    return jsonify({
        'success': True,
        'cod_art': articolo.cod_art,
        'descrizione': articolo.descrizione,
        'descrizione_aggiuntiva': articolo.descrizione_aggiuntiva,
        'cpp': articolo.cpp or 1,
        'ppc': articolo.ppc or 1
    })


@search_bp.route('/articolo_by_barcode', methods=['GET'])
@login_required
def articolo_per_barcode():
    barcode = request.args.get('barcode')
    logger.info(f">>> Chiamata a /articolo_by_barcode con barcode={barcode}")
    if not barcode:
        logger.warning("Barcode mancante nella richiesta")
        return jsonify({'success': False, 'error': 'Barcode mancante.'})
    cb_esistente = Barcode.query.filter_by(cod_bar=barcode).first()
    if cb_esistente:
        logger.info(f"Articolo trovato per barcode {barcode}: {cb_esistente.cod_art}")
        return jsonify({'success': True, 'product': cb_esistente.cod_art})
    else:
        logger.warning(f"Nessun articolo trovato per barcode {barcode}")
        return jsonify({'success': False, 'error': 'Prodotto non trovato.'})


@search_bp.route('/lista_articoli', methods=['GET'])
@login_required
def lista_articoli():
    filtro = request.args.get('filter', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    stock_only = request.args.get('stock_only', '1') not in ('0', 'false', 'False')
    per_page = max(1, min(per_page, 100))

    logger.info(f">>> Chiamata a /lista_articoli | filtro='{filtro}', page={page}, per_page={per_page}, stock_only={stock_only}")

    query = Articoli.query
    if filtro:
        query = query.filter(
            (Articoli.descrizione.ilike(f"%{filtro}%")) |
            (Articoli.descrizione_aggiuntiva.ilike(f"%{filtro}%")) |
            (Articoli.cod_art.ilike(f"%{filtro}%"))
        )

    if stock_only:
        query = query.join(Giacenza, Giacenza.cod_art == Articoli.cod_art).filter(
            (Giacenza.giac_neg > 0) | (Giacenza.giac_www > 0)
        )

    query = query.order_by(Articoli.descrizione.asc(), Articoli.cod_art.asc())
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)
    prodotti_json = []

    for p in paginated.items:
        giacenza = Giacenza.query.filter_by(cod_art=p.cod_art).first()
        prodotti_json.append({
            'cod_art': p.cod_art,
            'descrizione': p.descrizione,
            'descrizione_aggiuntiva': p.descrizione_aggiuntiva,
            'prezzo': p.prezzo,
            'giacenza': {
                'instore': giacenza.giac_neg if giacenza else 0,
                'online': giacenza.giac_www if giacenza else 0,
                'isonline': giacenza.giac_www > 0 if giacenza else False
            }
        })

    logger.info(f"Risultati trovati: {len(prodotti_json)} articoli (pagina {paginated.page} di {paginated.pages})")

    return jsonify({
        'prodotti': prodotti_json,
        'pagina_corrente': paginated.page,
        'pagine_totali': paginated.pages,
        'totale_prodotti': paginated.total,
        'per_page': per_page
    })


@search_bp.route('/barcode_by_codart/<cod_art>')
@login_required
def barcode_by_codart(cod_art):
    codice_bar = Barcode.query.filter_by(cod_art=cod_art).first()
    if codice_bar:
        return jsonify(success=True, barcode=codice_bar.cod_bar)
    else:
        return jsonify(success=False)


@search_bp.route('/articoli_by_barcode_multipli_funz', methods=['GET'])
@login_required
def articoli_by_barcode_multipli_funz():
    barcode = request.args.get('barcode')
    if not barcode:
        return jsonify({'success': False, 'error': 'Barcode mancante'})

    cb = Barcode.query.filter_by(cod_bar=barcode).first()
    if not cb:
        return jsonify({'success': False, 'error': 'Nessun articolo associato al barcode'})

    codice_base = cb.cod_art.split("-")[0]
    condizioni = or_(
        Articoli.cod_art == codice_base,
        Articoli.cod_art.like(f"{codice_base}-%")
    )
    articoli = Articoli.query.filter(condizioni).order_by(Articoli.cod_art.desc()).all()

    lista = [{
        "cod_art": a.cod_art,
        "descrizione": a.descrizione,
        "cpp": a.cpp or 1,
        "ppc": a.ppc or 1
    } for a in articoli]

    return jsonify({'success': True, 'lista_articoli': lista})


def serialize_articolo(articolo):
    return {
        'cod_art': articolo.cod_art,
        'descrizione': articolo.descrizione,
        'descrizione_aggiuntiva': articolo.descrizione_aggiuntiva,
        'cpp': articolo.cpp or 1,
        'ppc': articolo.ppc or 1
    }


@search_bp.route('/articoli_by_barcode_multipli', methods=['GET'])
@login_required
def articoli_by_barcode_multipli():
    barcode = request.args.get('barcode')
    if not barcode:
        return jsonify({'success': False, 'error': 'Barcode mancante'})

    cb = Barcode.query.filter_by(cod_bar=barcode).first()
    if not cb:
        return jsonify({'success': False, 'error': 'Nessun articolo associato al barcode'})

    codice_articolo = cb.cod_art
    codice_prefisso = codice_articolo.split('-')[0]

    # Caso 1: codice senza "-", verifica se ha varianti
    if '-' not in codice_articolo:
        varianti = Articoli.query.filter(Articoli.cod_art.like(f"{codice_prefisso}-%")).all()
        if not varianti:
            # Nessuna variante → restituisci direttamente l'articolo
            articolo = Articoli.query.filter_by(cod_art=codice_articolo).first()
            if articolo:
                return jsonify({
                    'success': True,
                    'singolo': True,
                    'articolo': {
                        'cod_art': articolo.cod_art,
                        'descrizione': articolo.descrizione,
                        'descrizione_aggiuntiva': articolo.descrizione_aggiuntiva,
                        'cpp': articolo.cpp or 1,
                        'ppc': articolo.ppc or 1
                    }
                })
            return jsonify({'success': False, 'error': 'Articolo non trovato nel database'})

        # Ha varianti → includi anche l'articolo base
        articoli_simili = [Articoli.query.filter_by(cod_art=codice_prefisso).first()] + varianti

    else:
        # Caso 2: codice con "-", trova tutte le varianti e l'articolo base
        articoli_simili = Articoli.query.filter(
            or_(
                Articoli.cod_art == codice_prefisso,
                Articoli.cod_art.like(f"{codice_prefisso}-%")
            )
        ).all()

    if not articoli_simili:
        return jsonify({'success': False, 'error': 'Nessuna variante trovata per il codice'})

    if len(articoli_simili) == 1:
        a = articoli_simili[0]
        return jsonify({
            'success': True,
            'singolo': True,
            'articolo': {
                'cod_art': a.cod_art,
                'descrizione': a.descrizione,
                'descrizione_aggiuntiva': a.descrizione_aggiuntiva,
                'cpp': a.cpp or 1,
                'ppc': a.ppc or 1
            }
        })

    return jsonify({'success': True, 'singolo': False,
                    'articoli': [serialize_articolo(a) for a in articoli_simili]})


@search_bp.route('/articoli_by_barcode', methods=['GET'])
@login_required
def articoli_by_barcode():
    barcode = request.args.get('barcode')
    if not barcode:
        return jsonify({'success': False, 'error': 'Barcode mancante'})

    barcode_entry = Barcode.query.filter_by(cod_bar=barcode).first()
    if not barcode_entry:
        return jsonify({'success': False, 'error': 'Nessun articolo trovato per questo barcode'})

    # Ricavo prefisso codice (es. VB07550 da VB07550-24)
    prefisso = barcode_entry.cod_art.split('-')[0]

    articoli = Articoli.query.filter(Articoli.cod_art.ilike(f"{prefisso}-%")).all()

    return jsonify({'success': True, 'articoli': serialize_articolo(articoli)})


@search_bp.route('/riepilogo_varianti/<cod_art>')
@login_required
def riepilogo_varianti(cod_art):
    # Estrai prefisso (es. VB07550)
    codice_base = cod_art.split('-')[0]

    # Articoli con lo stesso prefisso
    articoli_varianti = Articoli.query.filter(
        or_(
            Articoli.cod_art == codice_base,
            Articoli.cod_art.like(f"{codice_base}-%")
        )
    ).all()

    # Ottieni inventario attivo da query param
    inventario_id = request.args.get("inventario_id", type=int)
    if not inventario_id:
        return jsonify({"success": False, "error": "Inventario non specificato."}), 400

    varianti_data = []
    for art in articoli_varianti:
        cod = art.cod_art

        giacenza = InventarioExport.query.filter_by(articolo_id=cod).first()
        rilevate = db.session.query(
            db.func.sum(InventarioRiga.quantita_inserita)
        ).filter_by(inventario_id=inventario_id, articolo_id=cod).scalar() or 0

        giac = giacenza.giacenza if giacenza else 0
        diff = rilevate - giac

        varianti_data.append({
            "cod_art": cod,
            "giacenza": giac,
            "rilevata": rilevate,
            "differenza": diff
        })

    return jsonify({"success": True, "varianti": varianti_data})


@search_bp.route('/immagine_articolo/<cod_art>')
@login_required
def immagine_articolo(cod_art):
    immagini = Immagini.query.filter_by(cod_art=cod_art).all()
    print(f"🔍 Immagini trovate per {cod_art}: {[img.file_img for img in immagini]}")
    if immagini:
        img_urls = [url_for('static', filename=f'images/products/{img.file_img}') for img in immagini]
    else:
        img_urls = [url_for('static', filename='images/no_image.png')]
    return jsonify({"img_urls": img_urls})
