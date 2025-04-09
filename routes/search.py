from flask import Blueprint, render_template, jsonify, request, abort
from models import Barcode, Articoli, Giacenza, Immagini, SchedeProdotti
from routes.tools import clean_text
from tools.log_utils import log_task, get_logger
from sqlalchemy import or_


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
            "cod_art": cod_art,
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
def barcode_by_codart(cod_art):
    codice_bar = Barcode.query.filter_by(cod_art=cod_art).first()
    if codice_bar:
        return jsonify(success=True, barcode=codice_bar.cod_bar)
    else:
        return jsonify(success=False)


@search_bp.route('/articoli_by_barcode_multipli_funz', methods=['GET'])
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
