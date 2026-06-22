import os
import mimetypes
import re
import time
import unicodedata
from pprint import pprint
import requests
from requests.auth import HTTPBasicAuth
from flask import current_app, has_app_context
from extensions import db
from models import Immagini, Sincro, SchedeProdotti, ProductAsset, ProductPlatformField
from dotenv import load_dotenv
from pathlib import Path
import xmltodict
import xml.etree.ElementTree as ET
from tools.log_utils import get_logger

logger = get_logger('ps_util')

basedir = Path(__file__).resolve().parent.parent
load_dotenv(basedir / '.env', override=False)
load_dotenv(basedir / '.env.local', override=True)
load_dotenv(basedir / '.env.defaults', override=False)

IMAGES_FOLDER = basedir / 'static' / 'images' / 'products'
IMAGES_FOLDER.mkdir(parents=True, exist_ok=True)
_OPTIONS_CACHE_TTL_SECONDS = 1800
_OPTIONS_CACHE = {}


def _runtime_value(config_key, env_key, default=None):
    if has_app_context():
        value = current_app.config.get(config_key)
        if value not in (None, ""):
            return value

    value = os.getenv(env_key)
    if value not in (None, ""):
        return value
    return default


def _prestashop_url():
    return (_runtime_value("PS_URL", "PRESTASHOP_URL", "") or "").rstrip("/")


def _prestashop_key():
    return _runtime_value("PS_KEY", "PRESTASHOP_KEY", "")


def _bool_text(value, default=False):
    if value in (None, ""):
        return "1" if default else "0"
    return "1" if str(value).strip().lower() in {"1", "true", "yes", "on", "si", "sì"} else "0"


def _slugify_prestashop(value):
    raw = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = raw.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text).strip("-").lower()
    return slug or "prodotto"


def _set_text(parent, tag, value):
    child = ET.SubElement(parent, tag)
    child.text = "" if value is None else str(value)
    return child


def _set_language_text(parent, tag, value, language_id="1"):
    node = ET.SubElement(parent, tag)
    language = ET.SubElement(node, "language")
    language.set("id", str(language_id or "1"))
    language.text = "" if value is None else str(value)
    return node


def _prestashop_external_url(product_id):
    ps_url = _prestashop_url()
    return f"{ps_url}/products/{product_id}" if ps_url and product_id else None


def _cached_options(cache_key, loader):
    now = time.time()
    cached = _OPTIONS_CACHE.get(cache_key)
    if cached and now - cached["ts"] < _OPTIONS_CACHE_TTL_SECONDS:
        return cached["value"]
    value = loader()
    _OPTIONS_CACHE[cache_key] = {"ts": now, "value": value}
    return value


def _get_prestashop_resource(resource, *, display="full", limit=None):
    ps_url = _prestashop_url()
    ps_key = _prestashop_key()
    if not ps_url or not ps_key:
        raise RuntimeError("Prestashop non configurato")
    params = {"ws_key": ps_key, "display": display}
    if limit:
        params["limit"] = limit
    response = requests.get(
        f"{ps_url}/{resource}",
        auth=HTTPBasicAuth(ps_key, ""),
        params=params,
        timeout=60,
    )
    response.raise_for_status()
    return xmltodict.parse(response.content)


def _ensure_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _language_text(value):
    if isinstance(value, dict):
        language = value.get("language")
        if isinstance(language, list):
            return next((item.get("#text", "") for item in language if item.get("#text")), "")
        if isinstance(language, dict):
            return language.get("#text", "") or ""
        return value.get("#text", "") or ""
    return str(value or "")


def get_category_options():
    def load():
        payload = _get_prestashop_resource("categories")
        categories = _ensure_list((payload.get("prestashop") or {}).get("categories", {}).get("category"))
        options = []
        for category in categories:
            if not isinstance(category, dict):
                continue
            category_id = category.get("id") or category.get("@id")
            name = _language_text(category.get("name")) or f"Categoria {category_id}"
            if category_id:
                options.append({"value": str(category_id), "label": f"{category_id} - {name}"})
        return sorted(options, key=lambda item: item["label"].lower())

    return _cached_options("categories", load)


def get_tax_rule_group_options():
    def load():
        payload = _get_prestashop_resource("tax_rule_groups")
        groups = _ensure_list((payload.get("prestashop") or {}).get("tax_rule_groups", {}).get("tax_rule_group"))
        options = []
        for group in groups:
            if not isinstance(group, dict):
                continue
            group_id = group.get("id") or group.get("@id")
            name = group.get("name") or f"Regola IVA {group_id}"
            active = group.get("active")
            if group_id and str(active).strip() not in {"0", "False", "false"}:
                options.append({"value": str(group_id), "label": f"{group_id} - {name}"})
        return sorted(options, key=lambda item: item["label"].lower())

    return _cached_options("tax_rule_groups", load)


def create_product(payload):
    ps_url = _prestashop_url()
    ps_key = _prestashop_key()
    if not ps_url or not ps_key:
        raise RuntimeError("Prestashop non configurato")

    data = payload if isinstance(payload, dict) else {}
    required = ["reference", "name", "price", "id_category_default"]
    missing = [field for field in required if not str(data.get(field) or "").strip()]
    if missing:
        raise ValueError("Campi Prestashop obbligatori mancanti: " + ", ".join(missing))

    prestashop = ET.Element("prestashop")
    product = ET.SubElement(prestashop, "product")
    _set_text(product, "reference", data.get("reference"))
    _set_language_text(product, "name", data.get("name"))
    _set_language_text(product, "link_rewrite", data.get("link_rewrite") or _slugify_prestashop(data.get("name")))
    _set_language_text(product, "description_short", data.get("description_short") or "")
    _set_language_text(product, "description", data.get("description") or "")
    _set_text(product, "price", data.get("price"))
    _set_text(product, "active", _bool_text(data.get("active"), default=False))
    _set_text(product, "available_for_order", _bool_text(data.get("available_for_order"), default=True))
    _set_text(product, "show_price", _bool_text(data.get("show_price"), default=True))
    _set_text(product, "id_category_default", data.get("id_category_default"))
    if str(data.get("id_tax_rules_group") or "").strip():
        _set_text(product, "id_tax_rules_group", data.get("id_tax_rules_group"))

    associations = ET.SubElement(product, "associations")
    categories = ET.SubElement(associations, "categories")
    category = ET.SubElement(categories, "category")
    _set_text(category, "id", data.get("id_category_default"))

    body = ET.tostring(prestashop, encoding="utf-8", xml_declaration=True)
    response = requests.post(
        f"{ps_url}/products",
        auth=HTTPBasicAuth(ps_key, ""),
        params={"ws_key": ps_key},
        data=body,
        headers={"Content-Type": "application/xml"},
        timeout=60,
    )
    if response.status_code not in (200, 201):
        raise RuntimeError(f"Prestashop HTTP {response.status_code}: {response.text[:1000]}")

    try:
        parsed = xmltodict.parse(response.content)
    except Exception:
        parsed = {"raw": response.text[:1000]}

    product_node = (parsed.get("prestashop") or {}).get("product") if isinstance(parsed, dict) else {}
    product_id = None
    if isinstance(product_node, dict):
        product_id = product_node.get("id") or product_node.get("@id")
    if isinstance(product_id, dict):
        product_id = product_id.get("#text")
    if not product_id:
        try:
            root = ET.fromstring(response.content)
            id_node = root.find(".//product/id")
            product_id = id_node.text if id_node is not None else None
        except Exception:
            product_id = None
    if not product_id:
        raise RuntimeError("Prestashop non ha restituito l'ID del prodotto creato")

    return {
        "product_id": str(product_id),
        "external_url": _prestashop_external_url(product_id),
        "raw_payload": parsed,
        "status_code": response.status_code,
    }


def get_product_by_code(cod_art):
    logger.info(f"get_product_by_code(): Cerco il prodotto con codice {cod_art}")
    try:
        ps_url = _prestashop_url()
        ps_key = _prestashop_key()
        response = requests.get(f"{ps_url}/products/?ws_key={ps_key}&filter[reference]={cod_art}")
        if response.status_code == 200:
            root = ET.fromstring(response.text)
            product = root.find(".//product")
            if product is not None and "id" in product.attrib:
                p_info = get_product_details(product.attrib["id"])
                return p_info['description']
    except ET.ParseError:
        logger.exception("Errore durante il parsing XML nella get_product_by_code")
    except Exception as e:
        logger.exception("Errore generico nella get_product_by_code")
    return None

def get_product_details(product_id):
    ps_url = _prestashop_url()
    ps_key = _prestashop_key()
    url = f"{ps_url}/products/{product_id}?ws_key={ps_key}"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            root = ET.fromstring(response.text)
            name = root.find(".//name/language")
            description = root.find(".//description/language")
            price = root.find(".//price")
            reference = root.find(".//reference")

            return {
                "id": product_id,
                "reference": reference.text if reference is not None else None,
                "name": name.text if name is not None else None,
                "description": description.text if description is not None else None,
                "price": price.text if price is not None else None,
            }
    except ET.ParseError:
        logger.exception("Errore durante il parsing XML nella get_product_details")
    except Exception as e:
        logger.exception("Errore generico nella get_product_details")
    return None


def get_product_ids():
    logger.info("get_product_ids(): Recupero lista ID prodotti da Prestashop")
    ps_url = _prestashop_url()
    ps_key = _prestashop_key()
    response = requests.get(f"{ps_url}/products", params={'ws_key': ps_key})
    response.raise_for_status()
    products_data = xmltodict.parse(response.content)
    products = products_data['prestashop']['products']['product']
    if not isinstance(products, list):
        products = [products]
    return [product['@id'] for product in products]


def get_product_payload(product_id):
    ps_url = _prestashop_url()
    ps_key = _prestashop_key()
    prod_response = requests.get(f"{ps_url}/products/{product_id}", params={'ws_key': ps_key})
    prod_response.raise_for_status()
    prod_info = xmltodict.parse(prod_response.content)
    prod_data = prod_info['prestashop']['product']

    lang_name = prod_data['name']['language']
    name = next((item.get('#text', '') for item in lang_name if item.get('@id') == '1'), lang_name[0].get('#text', '')) if isinstance(lang_name, list) else lang_name.get('#text', '')

    cod_art = prod_data.get('reference')
    if not cod_art or not cod_art.strip():
        logger.warning(f"Prodotto {product_id} senza reference, salto.")
        return None
    cod_art = cod_art.strip()

    description = get_product_descriptions(product_id)

    return {
        'id': product_id,
        'name': name,
        'price': prod_data['price'],
        'cod_art': cod_art,
        'description': description,
        'external_url': prod_data.get('@xlink:href'),
        'raw_payload': prod_data,
    }


def get_all_products():
    logger.info("get_all_products(): Inizio recupero lista prodotti da Prestashop")
    db.create_all()
    for product_id in get_product_ids():
        product = get_product_payload(product_id)
        if product:
            yield product


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


def _upsert_product_asset(cod_art, source_platform, local_path=None, remote_url=None, source_external_id=None, filename=None):
    query = ProductAsset.query.filter_by(
        cod_art=cod_art,
        asset_type="image",
        source_platform=source_platform,
    )
    if local_path:
        asset = query.filter_by(local_path=local_path).first()
    elif remote_url:
        asset = query.filter_by(remote_url=remote_url).first()
    else:
        asset = None
    if not asset:
        asset = ProductAsset(
            cod_art=cod_art,
            asset_type="image",
            source_platform=source_platform,
            local_path=local_path,
            remote_url=remote_url,
        )
        db.session.add(asset)
    asset.source_external_id = str(source_external_id) if source_external_id is not None else None
    asset.original_filename = filename or asset.original_filename


def get_product_descriptions(product_id):
    logger.info(f"get_product_descriptions(): Recupero descrizione per prodotto {product_id}")
    ps_url = _prestashop_url()
    ps_key = _prestashop_key()
    response = requests.get(f"{ps_url}/products/{product_id}", params={'ws_key': ps_key})
    response.raise_for_status()
    prod_info = xmltodict.parse(response.content)
    prod_data = prod_info['prestashop']['product']
    cod_art = prod_data.get('reference')
    if not cod_art or not cod_art.strip():
        logger.warning(f"Prodotto {product_id} senza reference, salto salvataggio scheda.")
        return ["", ""]
    cod_art = cod_art.strip()

    lang_desc = prod_data.get('description', {}).get('language', '')
    lang_short_desc = prod_data.get('description_short', {}).get('language', '')

    if not lang_desc and cod_art:
        return ["", ""]

    description = next((item.get('#text', '') for item in lang_desc if item.get('@id') == '1'), lang_desc[0].get('#text', '')) if isinstance(lang_desc, list) else lang_desc.get('#text', '')
    description_short = next((item.get('#text', '') for item in lang_short_desc if item.get('@id') == '1'), lang_short_desc[0].get('#text', '')) if isinstance(lang_short_desc, list) else lang_short_desc.get('#text', '')
    _upsert_platform_field(cod_art, "prestashop", "description", description, source_external_id=product_id)
    _upsert_platform_field(cod_art, "prestashop", "description_short", description_short, source_external_id=product_id)

    if not SchedeProdotti.query.filter_by(cod_art=cod_art).first():
        db.session.add(SchedeProdotti(descrizione=description, short=description_short, cod_art=cod_art))
        logger.info(f"Salvata nuova scheda prodotto per {cod_art}")
    else:
        logger.info(f"Record per {cod_art} già esistente, nessun inserimento")

    return [description, description_short]

def get_product_images(product_id, cod_art):
    logger.info(f"get_product_images(): Recupero immagini per prodotto {product_id}")
    images = []

    ps_url = _prestashop_url()
    ps_key = _prestashop_key()
    images_response = requests.get(f"{ps_url}/images/products/{product_id}", auth=HTTPBasicAuth(ps_key, ''), params={'ws_key': ps_key})
    if images_response.status_code == 200:
        images_info = xmltodict.parse(images_response.content)
        declinations = images_info.get('prestashop', {}).get('image', {}).get('declination', [])
        if not isinstance(declinations, list):
            declinations = [declinations]
        for img in declinations:
            image_id = img['@id']
            image_url = f"{ps_url}/images/products/{product_id}/{image_id}"
            image_response = requests.get(image_url, auth=HTTPBasicAuth(ps_key, ''), params={'ws_key': ps_key})
            if image_response.status_code == 200:
                file_name = f"{product_id}_{image_id}.jpg"
                file_path = IMAGES_FOLDER / file_name
                if not file_path.exists():
                    with open(file_path, 'wb') as f:
                        f.write(image_response.content)
                    logger.info(f"Salvata immagine: {file_name}")
                else:
                    logger.debug(f"Immagine già presente: {file_name}")

                if not Immagini.query.filter_by(file_img=file_name, cod_art=cod_art).first():
                    db.session.add(Immagini(file_img=file_name, cod_art=cod_art))
                else:
                    logger.debug(f"Record Immagini già presente per {file_name} - {cod_art}")
                _upsert_product_asset(
                    cod_art,
                    "prestashop",
                    local_path=f"images/products/{file_name}",
                    remote_url=image_url,
                    source_external_id=image_id,
                    filename=file_name,
                )
                images.append(file_name)
            else:
                logger.warning(f"Errore nel recupero immagine {image_id}: HTTP {image_response.status_code}")
    elif images_response.status_code == 404:
        logger.warning(f"Prodotto {product_id} non ha immagini (404)")
    else:
        logger.error(f"Errore recupero immagini prodotto {product_id}: {images_response.status_code}")

    return images


def upload_product_image(product_id, image_path, *, filename=None, mime_type=None):
    ps_url = _prestashop_url()
    ps_key = _prestashop_key()
    if not ps_url or not ps_key:
        raise RuntimeError("Prestashop non configurato")
    if not image_path or not os.path.exists(image_path):
        raise FileNotFoundError(f"Immagine non trovata: {image_path}")

    safe_filename = filename or os.path.basename(image_path)
    guessed_mime = mime_type or mimetypes.guess_type(safe_filename)[0] or "application/octet-stream"
    url = f"{ps_url}/images/products/{product_id}"

    with open(image_path, "rb") as image_file:
        response = requests.post(
            url,
            auth=HTTPBasicAuth(ps_key, ""),
            params={"ws_key": ps_key},
            files={"image": (safe_filename, image_file, guessed_mime)},
            timeout=60,
        )

    if response.status_code not in (200, 201):
        raise RuntimeError(f"Prestashop HTTP {response.status_code}: {response.text[:500]}")

    try:
        payload = xmltodict.parse(response.content)
    except Exception:
        payload = {"raw": response.text[:1000]}

    image_node = (payload.get("prestashop") or {}).get("image") if isinstance(payload, dict) else None
    image_id = None
    if isinstance(image_node, dict):
        image_id = image_node.get("id") or image_node.get("@id")

    return {
        "image_id": str(image_id) if image_id is not None else None,
        "remote_url": f"{ps_url}/images/products/{product_id}/{image_id}" if image_id is not None else url,
        "raw_payload": payload,
        "status_code": response.status_code,
    }


def delete_product_image(product_id, image_id):
    ps_url = _prestashop_url()
    ps_key = _prestashop_key()
    if not ps_url or not ps_key:
        raise RuntimeError("Prestashop non configurato")
    if not product_id or not image_id:
        raise ValueError("Prestashop image identifiers missing")

    url = f"{ps_url}/images/products/{product_id}/{image_id}"
    response = requests.delete(
        url,
        auth=HTTPBasicAuth(ps_key, ""),
        params={"ws_key": ps_key},
        timeout=60,
    )

    if response.status_code not in (200, 202, 204):
        raise RuntimeError(f"Prestashop HTTP {response.status_code}: {response.text[:500]}")

    return {
        "status_code": response.status_code,
        "remote_url": url,
        "raw_payload": response.text[:1000],
    }
