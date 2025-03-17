from flask import Blueprint, render_template, jsonify, request, abort
from models import Barcode, Articoli, Giacenza, Immagini, SchedeProdotti

# Creazione del blueprint
search_bp = Blueprint('search', __name__, template_folder='../templates')


# Funzione esempio per recuperare il prodotto dal database
def get_product_by_code(cod_art):
    # Logica per accedere al database e recuperare il prodotto
    # Restituisci un dizionario con i dati del prodotto o None se non trovato
    prod = Articoli.query.filter_by(cod_art=cod_art).first()
    immagini = []
    giacenze = Giacenza.query.filter_by(cod_art=cod_art).first()

    for img in Immagini.query.filter_by(cod_art=cod_art).all():
        immagini.append(img.file_img)
    if prod:
        prodotto = {
            "codice": cod_art,
            "descrizione": prod.descrizione,
            "descrizione_aggiuntiva": prod.descrizione_aggiuntiva,
            "prezzo": prod.prezzo,
            "immagini": immagini,
            "inStore": giacenze.giac_neg,
            "www": giacenze.giac_www,
            "scheda_tecnica": SchedeProdotti.query.filter_by(cod_art=cod_art).first()
        }
        return prodotto
    else:
        return None


@search_bp.route('/scheda_articolo/<cod_art>')
def scheda_articolo(cod_art):
    product = get_product_by_code(cod_art)
    if product is None:
        abort(404)  # Prodotto non trovato
    return render_template('scheda_articolo.html', product=product)


@search_bp.route('/ricerca_x_barcode', methods=['GET', 'POST'])
def ricerca_x_barcode():
    return render_template('articoli_codebar.html')


@search_bp.route('/ricerca_x_descrizione', methods=['GET', 'POST'])
def ricerca_x_descrizione():
    return render_template('articoli_description.html')


@search_bp.route('/articolo_by_barcode', methods=['GET'])
def articolo_per_barcode():
    barcode = request.args.get('barcode')
    if not barcode:
        return jsonify({'success': False, 'error': 'Barcode mancante.'})
    cb_esistente = Barcode.query.filter_by(cod_bar=barcode).first()
    if cb_esistente:
#         cod_art = cb_esistente.cod_art
#         art_esistente = Articoli.query.filter_by(cod_art=cod_art).first()
#         descrizione = art_esistente.descrizione + " " + art_esistente.descrizione_aggiuntiva
#         prezzo = art_esistente.prezzo
#         giac_esistente = Giacenza.query.filter_by(cod_art=cod_art).first()
#         instore = giac_esistente.giac_neg
#         isonline = True if giac_esistente.giac_www>0 else False
#         online = giac_esistente.giac_www
#         articolo = {
#             'codice': cod_art,
#             'descrizione': descrizione,
#             'instore': instore,
#             'online': online,
#             'isonline': isonline,
#             'prezzo': prezzo
#         }
        print(f"articolo trovato: \n{cb_esistente.cod_art}")
        return jsonify({'success': True, 'product': cb_esistente.cod_art})
    else:
        print("Articolo non trovato")
        return jsonify({'success': False, 'error': 'Prodotto non trovato.'})


@search_bp.route('/lista_articoli', methods=['GET'])
def lista_articoli():
    filtro = request.args.get('filter', '').strip()
    page = request.args.get('page', 1, type=int)  # Numero della pagina, di default 1
    per_page = request.args.get('per_page', 10, type=int)  # Elementi per pagina, default 10

    query = Articoli.query

    # Filtraggio per descrizione e descrizione_aggiuntiva
    if filtro:
        query = query.filter(
            (Articoli.descrizione.ilike(f"%{filtro}%")) |
            (Articoli.descrizione_aggiuntiva.ilike(f"%{filtro}%"))
        )

    # Paginazione
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    prodotti_json = []

    for p in paginated.items:
        giacenza = Giacenza.query.filter_by(cod_art=p.cod_art).first()  # Recupera giacenza

        prodotto = {
            'codice': p.cod_art,
            'descrizione': p.descrizione,
            'descrizione_aggiuntiva': p.descrizione_aggiuntiva,
            'prezzo': p.prezzo,
            'giacenza': {
                'instore': giacenza.giac_neg if giacenza else 0,  # Se giacenza è None, assegna 0
                'online': giacenza.giac_www if giacenza else 0,
                'isonline': True if giacenza and giacenza.giac_www > 0 else False
            }
        }

        prodotti_json.append(prodotto)

    return jsonify({
        'prodotti': prodotti_json,
        'pagina_corrente': paginated.page,
        'pagine_totali': paginated.pages,
        'totale_prodotti': paginated.total,
        'per_page': per_page
    })
