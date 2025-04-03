from flask import Blueprint, render_template, jsonify, request, abort
from models import Barcode, Articoli, Giacenza, Immagini, SchedeProdotti
from routes.tools import clean_text
from tools.log_utils import log_task, get_logger

logger = get_logger('search')

search_bp = Blueprint('search', __name__, template_folder='../templates')


@log_task(logger)
def get_product_by_code(cod_art):
    prod = Articoli.query.filter_by(cod_art=cod_art).first()
    immagini = [img.file_img for img in Immagini.query.filter_by(cod_art=cod_art).all()]
    giacenze = Giacenza.query.filter_by(cod_art=cod_art).first()

    if prod:
        scheda = SchedeProdotti.query.filter_by(cod_art=cod_art).first()
        scheda_art = clean_text(scheda.descrizione) if scheda else "---"
        return {
            "codice": cod_art,
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
def scheda_articolo(cod_art):
    logger.info(f">>> Chiamata a /scheda_articolo/{cod_art}")
    product = get_product_by_code(cod_art)
    if product is None:
        logger.warning(f"Articolo {cod_art} non trovato - abort 404")
        abort(404)
    return render_template('scheda_articolo.html', product=product)


@search_bp.route('/ricerca_x_barcode', methods=['GET', 'POST'])
def ricerca_x_barcode():
    logger.info(">>> Chiamata a /ricerca_x_barcode")
    return render_template('articoli_codebar.html')


@search_bp.route('/ricerca_x_descrizione', methods=['GET', 'POST'])
def ricerca_x_descrizione():
    logger.info(">>> Chiamata a /ricerca_x_descrizione")
    return render_template('articoli_description.html')


@search_bp.route('/dati_articolo/<cod_art>', methods=['GET'])
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
        'codice': articolo.cod_art,
        'descrizione': articolo.descrizione,
        'descrizione_aggiuntiva': articolo.descrizione_aggiuntiva,
        'prezzo': articolo.prezzo,
        'immagini': immagini,
        'giacenza': {
            'inStore': giacenze.giac_neg if giacenze else 0,
            'online': giacenze.giac_www if giacenze else 0
        },
        'scheda_tecnica': clean_text(scheda.descrizione) if scheda else "---",
        'ppc': articolo.pezzi_per_collo if hasattr(articolo, 'pezzi_per_collo') else 1,
        'cpp': articolo.colli_per_pedana if hasattr(articolo, 'colli_per_pedana') else 1
    })


@search_bp.route('/articolo_by_barcode', methods=['GET'])
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
            'codice': p.cod_art,
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
