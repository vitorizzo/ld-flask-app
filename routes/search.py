from flask import Blueprint, render_template, jsonify, request
from models import Barcode, Articoli, Giacenza

# Creazione del blueprint
search_bp = Blueprint('search', __name__, template_folder='../templates')


@search_bp.route('/ricerca_x_barcode', methods=['GET', 'POST'])
def ricerca_x_barcode():
    return render_template('articoli.html')


@search_bp.route('/articolo_by_barcode', methods=['GET'])
def articolo_per_barcode():
    barcode = request.args.get('barcode')
    if not barcode:
        return jsonify({'success': False, 'error': 'Barcode mancante.'})
    cb_esistente = Barcode.query.filter_by(cod_bar=barcode).first()
    if cb_esistente:
        cod_art = cb_esistente.cod_art
        art_esistente = Articoli.query.filter_by(cod_art=cod_art).first()
        descrizione = art_esistente.descrizione + " " + art_esistente.descrizione_aggiuntiva
        prezzo = art_esistente.prezzo
        giac_esistente = Giacenza.query.filter_by(cod_art=cod_art).first()
        instore = giac_esistente.giac_neg
        isonline = True if giac_esistente.giac_www>0 else False
        online = giac_esistente.giac_www
        articolo = {
            'codice': cod_art,
            'descrizione': descrizione,
            'instore': instore,
            'online': online,
            'isonline': isonline,
            'prezzo': prezzo
        }
        print(f"articolo trovato: \n{articolo}")
        return jsonify({'success': True, 'product': articolo})
    else:
        print("Articolo non trovato")
        return jsonify({'success': False, 'error': 'Prodotto non trovato.'})
