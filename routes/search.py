import hashlib
import mimetypes
import os
from datetime import datetime

from flask import Blueprint, current_app, render_template, jsonify, request, abort, url_for
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from extensions import db
from models import (
    Barcode,
    Articoli,
    Giacenza,
    Immagini,
    ProductAsset,
    ProductPlatformLink,
    SchedeProdotti,
    Inventario,
    InventarioRiga,
    InventarioExport,
)
from routes.tools import clean_text
from tools.log_utils import log_task, get_logger
from sqlalchemy import or_


logger = get_logger('search')

search_bp = Blueprint('search', __name__, template_folder='../templates')

PRODUCT_IMAGE_PLATFORMS = {
    "prestashop": {"label": "Prestashop", "enabled": False, "icon": "fa-solid fa-store"},
    "poleepo": {"label": "Poleepo", "enabled": False, "icon": "fa-solid fa-cloud-arrow-up"},
    "ebay": {"label": "Ebay", "enabled": False, "icon": "fa-brands fa-ebay"},
    "amazon": {"label": "Amazon", "enabled": False, "icon": "fa-brands fa-amazon"},
    "ldapp": {"label": "LDApp", "enabled": True, "icon": "fa-solid fa-folder-open"},
}
ALLOWED_PRODUCT_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
OFFICE_ROLE_WEIGHT = 40


def _can_manage_product_images():
    return bool(current_user.is_authenticated and (current_user.max_role_weight or 0) >= OFFICE_ROLE_WEIGHT)


def _asset_public_url(asset):
    return url_for("static", filename=asset.local_path) if asset.local_path else asset.remote_url


def _serialize_product_asset(asset):
    return {
        "id": asset.id,
        "url": _asset_public_url(asset),
        "file_img": asset.original_filename,
        "source_platform": asset.source_platform,
        "source_external_id": asset.source_external_id,
        "is_primary": bool(asset.is_primary),
        "sort_order": asset.sort_order,
    }


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
            "primary_image": (grouped.get(key) or [None])[0],
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


@log_task(logger)
def get_product_by_code(cod_art):
    prod = Articoli.query.filter_by(cod_art=cod_art).first()
    asset_rows = (
        ProductAsset.query
        .filter_by(cod_art=cod_art, asset_type="image")
        .order_by(ProductAsset.is_primary.desc(), ProductAsset.sort_order.asc(), ProductAsset.id.asc())
        .all()
    )
    immagini = [_serialize_product_asset(asset) for asset in asset_rows if asset.local_path or asset.remote_url]
    if not immagini:
        immagini = [
            {
                "id": None,
                "url": url_for("static", filename=f"images/products/{img.file_img}"),
                "file_img": img.file_img,
                "source_platform": "legacy",
                "source_external_id": None,
                "is_primary": False,
                "sort_order": 0,
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
    else:
        if os.path.exists(target_path) and asset.local_path != relative_path:
            os.remove(target_path)
        asset.local_path = asset.local_path or relative_path
        asset.original_filename = asset.original_filename or uploaded.filename
        asset.mime_type = asset.mime_type or uploaded.mimetype or mimetypes.guess_type(filename)[0]

    db.session.commit()
    return jsonify({"ok": True, "asset": _serialize_product_asset(asset)})


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
