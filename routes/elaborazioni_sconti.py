from flask import Blueprint, render_template, request, jsonify
from math import prod

# Creazione del blueprint
sconti_bp = Blueprint('sconti', __name__, template_folder='../templates')


# Funzione per calcolare lo sconto equivalente
def calcola_sconto_equivalente(sconti):
    equivalente = 1 - prod([1 - s / 100 for s in sconti])
    return round(equivalente * 100, 2)


# Funzione per calcolare lo sconto equivalente
def calcola_sconto_merce(val_acquisto, val_omaggio):
    if val_acquisto <= 0:
        raise ValueError("Il valore dell'acquisto deve essere maggiore di zero.")
    sc_merce = 100 * val_omaggio / (val_omaggio + val_acquisto)
    return round(sc_merce, 2)


# Funzione per calcolare lo sconto complementare
def calcola_sconto_complementare(sconto_finale, sconti_fissi):
    complemento = 1 - (1 - sconto_finale / 100) / prod([1 - s / 100 for s in sconti_fissi])
    return round(complemento * 100, 2)


def calcola_sconto_combinazione(acquistati, omaggio):
    sconto_combinazione = 100 * omaggio / (omaggio + acquistati)
    return round(sconto_combinazione, 2)


# Rotta principale per la pagina HTML
@sconti_bp.route('/elaborazione-sconti')
def elaborazione_sconti():
    return render_template('functions/elaborazione_sconti.html')


# Endpoint per calcolare lo sconto equivalente ad una combinazione
@sconti_bp.route('/calcola-sconto-combinazioni', methods=['POST'])
def calcola_sconto_combinazione_endpoint():
    data = request.json  # Ottieni il JSON completo dalla richiesta
    acquistati = data.get('acquistati')  # Estrarre il valore di 'acquistati'
    omaggio = data.get('omaggio')  # Estrarre il valore di 'omaggio'

    # Assicurati che i valori siano validi
    if acquistati is None or omaggio is None:
        return jsonify({'error': 'I campi acquistati e omaggio sono obbligatori.'}), 400
    risultato = calcola_sconto_combinazione(acquistati, omaggio)
    return jsonify({'sconto_combinazione': risultato})


@sconti_bp.route('/calcola-sconto-merce', methods=['POST'])
def calcola_sconto_merce_endpoint():
    data = request.json  # Ottieni il JSON completo dalla richiesta
    val_merce_acquistata = data.get('val_acquisto')  # Estrarre il valore di 'acquistati'
    val_merce_omaggio = data.get('val_omaggio')  # Estrarre il valore di 'omaggio'

    # Assicurati che i valori siano validi
    if val_merce_acquistata is None or val_merce_omaggio is None:
        return jsonify({'error': 'I campi merce acquistata e merce omaggio sono obbligatori.'}), 400
    risultato = calcola_sconto_merce(val_merce_acquistata, val_merce_omaggio)
    return jsonify({'sconto_merce': risultato})


# Endpoint per calcolare lo sconto equivalente
@sconti_bp.route('/calcola-sconto-equivalente', methods=['POST'])
def calcola_sconto_equivalente_endpoint():
    sconti = request.json.get('sconti', [])
    risultato = calcola_sconto_equivalente(sconti)
    return jsonify({'sconto_equivalente': risultato})


# Endpoint per calcolare lo sconto complementare
@sconti_bp.route('/calcola-sconto-complementare', methods=['POST'])
def calcola_sconto_complementare_endpoint():
    sconto_finale = request.json.get('sconto_finale', 0)
    sconti_fissi = request.json.get('sconti_fissi', [])
    risultato = calcola_sconto_complementare(sconto_finale, sconti_fissi)
    return jsonify({'sconto_complementare': risultato})
