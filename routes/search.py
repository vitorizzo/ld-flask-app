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
    ProductPlatformLink,
    SchedeProdotti,
    Inventario,
    InventarioRiga,
    InventarioExport,
)
from routes.tools import clean_text
from tools.ps_util import (
    delete_product_image as prestashop_delete_product_image,
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


def _can_manage_product_images():
    return bool(current_user.is_authenticated and (current_user.max_role_weight or 0) >= OFFICE_ROLE_WEIGHT)


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


def _publish_product_image_to_platform(articolo, source_asset, platform_key, platform_link):
    if platform_key == "prestashop":
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
            }
            for key, config in PRODUCT_IMAGE_PLATFORMS.items()
            if key != "ldapp"
        ]
        return {
            "cod_art": cod_art,
            "barcodes": [row.cod_bar for row in barcode_rows],
            "platforms": platforms,
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

    logger.info(f">>> Chiamata a /lista_articoli | filtro='{filtro}', page={page}, per_page={per_page}")

    query = Articoli.query
    if filtro:
        query = query.filter(
            (Articoli.descrizione.ilike(f"%{filtro}%")) |
            (Articoli.descrizione_aggiuntiva.ilike(f"%{filtro}%"))
        )

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
