from flask import Blueprint, render_template, request, jsonify
from math import prod

# Creazione del blueprint
sconti_bp = Blueprint('sconti', __name__, template_folder='../templates')

# Funzione per calcolare lo sconto equivalente
def calcola_sconto_equivalente(sconti):
    equivalente = 1 - prod([1 - s / 100 for s in sconti])
    return round(equivalente * 100, 2)

# Funzione per calcolare lo sconto complementare
def calcola_sconto_complementare(sconto_finale, sconti_fissi):
    complemento = 1 - (1 - sconto_finale / 100) / prod([1 - s / 100 for s in sconti_fissi])
    return round(complemento * 100, 2)

# Rotta principale per la pagina HTML
@sconti_bp.route('/elaborazione-sconti')
def elaborazione_sconti():
    return render_template('functions/elaborazione_sconti.html')

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
