import logging

from flask import Blueprint, render_template, request, jsonify
from math import prod
from tools.log_utils import log_task, get_logger

# Logger per il modulo elaborazioni_sconti
# logger = get_logger("sconti")  # crea automaticamente il file sconti.log
print("🧩 MODULO elaborazioni_sconti.py IMPORTATO")
logger = get_logger("sconti", level=logging.DEBUG)
logger.debug("🧪 Logger 'sconti' inizializzato correttamente - test DEBUG")
logger.info("🧪 Logger 'sconti' inizializzato correttamente - test INFO")

sconti_bp = Blueprint('sconti', __name__, template_folder='../templates')


def calcola_sconto_equivalente(sconti):
    logger.debug(f"Calcolo sconto equivalente da: {sconti}")
    equivalente = 1 - prod([1 - s / 100 for s in sconti])
    return round(equivalente * 100, 2)


def calcola_sconto_merce(val_acquisto, val_omaggio):
    if val_acquisto <= 0:
        logger.error("Valore acquisto <= 0 nel calcolo sconto merce.")
        raise ValueError("Il valore dell'acquisto deve essere maggiore di zero.")
    logger.debug(f"Calcolo sconto merce da: acquisto={val_acquisto}, omaggio={val_omaggio}")
    sc_merce = 100 * val_omaggio / (val_omaggio + val_acquisto)
    return round(sc_merce, 2)


def calcola_sconto_complementare(sconto_finale, sconti_fissi):
    logger.debug(f"Calcolo sconto complementare da: finale={sconto_finale}, fissi={sconti_fissi}")
    complemento = 1 - (1 - sconto_finale / 100) / prod([1 - s / 100 for s in sconti_fissi])
    return round(complemento * 100, 2)


def calcola_sconto_combinazione(acquistati, omaggio):
    logger.debug(f"Calcolo sconto combinazione da: acquistati={acquistati}, omaggio={omaggio}")
    sconto_combinazione = 100 * omaggio / (omaggio + acquistati)
    return round(sconto_combinazione, 2)


@sconti_bp.route('/elaborazione-sconti')
@log_task(logger)
def elaborazione_sconti():
    print(f"🔍 Handler nel logger 'sconti': {logger.handlers}")
    logger.debug(f"Caricamento pagina elaborazione sconti")
    return render_template('functions/elaborazione_sconti.html')


@sconti_bp.route('/test-log')
def test_log_sconti():
    logger.debug("🔥 Questo è un log di DEBUG dal server Flask")
    logger.info("📘 Questo è un log di INFO dal server Flask")
    return "Log test inviati al logger 'sconti'"


@sconti_bp.route('/calcola-sconto-combinazioni', methods=['POST'])
@log_task(logger)
def calcola_sconto_combinazione_endpoint():
    data = request.json
    acquistati = data.get('acquistati')
    omaggio = data.get('omaggio')

    if acquistati is None or omaggio is None:
        logger.warning("Parametri mancanti nel calcolo sconto combinazione.")
        return jsonify({'error': 'I campi acquistati e omaggio sono obbligatori.'}), 400

    risultato = calcola_sconto_combinazione(acquistati, omaggio)
    return jsonify({'sconto_combinazione': risultato})


@sconti_bp.route('/calcola-sconto-merce', methods=['POST'])
@log_task(logger)
def calcola_sconto_merce_endpoint():
    data = request.json
    val_merce_acquistata = data.get('val_acquisto')
    val_merce_omaggio = data.get('val_omaggio')
    logger.debug("Test log DEBUG sconti — valore acquisto = %s", str(val_merce_acquistata))
    logger.info("Test log INFO sconti — valore omaggio = %s", str(val_merce_omaggio))
    logger.warning("⚠️ Test WARNING — questo log deve apparire sempre!")
    # logger.debug(f"Valore Merce Acquistata = {val_merce_acquistata}")
    # logger.debug(f"Valore Merce Omaggio = {val_merce_omaggio}")
    print(f"Valore Merce Acquistata = {val_merce_acquistata}")
    print(f"Valore Merce Omaggio = {val_merce_omaggio}")
    if val_merce_acquistata is None or val_merce_omaggio is None:
        logger.warning("Parametri mancanti nel calcolo sconto merce.")
        return jsonify({'error': 'I campi merce acquistata e merce omaggio sono obbligatori.'}), 400

    try:
        logger.debug(f"Merce acquistata: {val_merce_acquistata} \nMerce omaggio: {val_merce_omaggio}")
        risultato = calcola_sconto_merce(val_merce_acquistata, val_merce_omaggio)
        return jsonify({'sconto_merce': risultato})
    except ValueError as e:
        logger.exception("Errore nel calcolo sconto merce:")
        return jsonify({'error': str(e)}), 400


@sconti_bp.route('/calcola-sconto-equivalente', methods=['POST'])
@log_task(logger)
def calcola_sconto_equivalente_endpoint():
    sconti = request.json.get('sconti', [])
    risultato = calcola_sconto_equivalente(sconti)
    return jsonify({'sconto_equivalente': risultato})


@sconti_bp.route('/calcola-sconto-complementare', methods=['POST'])
@log_task(logger)
def calcola_sconto_complementare_endpoint():
    sconto_finale = request.json.get('sconto_finale', 0)
    sconti_fissi = request.json.get('sconti_fissi', [])
    risultato = calcola_sconto_complementare(sconto_finale, sconti_fissi)
    return jsonify({'sconto_complementare': risultato})
