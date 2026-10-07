import logging

from flask import Blueprint, render_template, request, jsonify
from math import isfinite, prod
from tools.log_utils import log_task, get_logger
from tools.auth_manager import role_required
import tools.role_required as rr
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Logger per il modulo elaborazioni_sconti
# logger = get_logger("sconti")  # crea automaticamente il file sconti.log

logger = get_logger("sconti", level=logging.DEBUG)
logger.debug("Logger 'sconti' inizializzato correttamente - test DEBUG")

sconti_bp = Blueprint('sconti', __name__, template_folder='../templates')


def _number(value, label, *, minimum=0, maximum=None, positive=False, integer=False):
    try:
        finite = not isinstance(value, bool) and isinstance(value, (int, float)) and isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError(f"{label}: inserisci un numero valido.")
    if value < minimum or (positive and value == 0):
        raise ValueError(f"{label}: il valore deve essere {'maggiore di zero' if positive else 'zero o positivo'}.")
    if maximum is not None and value > maximum:
        raise ValueError(f"{label}: il valore non puo' superare {maximum}.")
    if integer and value != int(value):
        raise ValueError(f"{label}: inserisci un numero intero di pezzi.")
    return value


def _discounts(values, *, complementary=False):
    if not isinstance(values, list) or (not values and not complementary):
        raise ValueError("Inserisci almeno uno sconto.")
    for value in values:
        _number(value, "Sconto", maximum=100)
        if complementary and value == 100:
            raise ValueError("Con uno sconto gia' applicato del 100% non e' possibile calcolare lo sconto aggiuntivo.")
    return values


def _request_data():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("Dati del calcolo non validi. Controlla i campi e riprova.")
    return data


@sconti_bp.errorhandler(ValueError)
def invalid_calculation(error):
    return jsonify({'error': str(error)}), 400


def calcola_sconto_equivalente(sconti):
    _discounts(sconti)
    logger.debug(f"Calcolo sconto equivalente da: {sconti}")
    equivalente = 1 - prod([1 - s / 100 for s in sconti])
    return round(equivalente * 100, 2)


def calcola_sconto_merce(val_acquisto, val_omaggio):
    _number(val_acquisto, "Valore merce pagata", positive=True)
    _number(val_omaggio, "Valore merce in omaggio")
    if not isfinite(val_acquisto + val_omaggio):
        raise ValueError("Il valore totale della merce e' troppo grande.")
    if val_acquisto <= 0:
        logger.error("Valore acquisto <= 0 nel calcolo sconto merce.")
        raise ValueError("Il valore dell'acquisto deve essere maggiore di zero.")
    logger.debug(f"Calcolo sconto merce da: acquisto={val_acquisto}, omaggio={val_omaggio}")
    sc_merce = 100 * val_omaggio / (val_omaggio + val_acquisto)
    return round(sc_merce, 2)


def calcola_sconto_complementare(sconto_finale, sconti_fissi):
    _number(sconto_finale, "Sconto totale desiderato", maximum=100)
    _discounts(sconti_fissi, complementary=True)
    logger.debug(f"Calcolo sconto complementare da: finale={sconto_finale}, fissi={sconti_fissi}")
    residuo = prod([1 - s / 100 for s in sconti_fissi])
    if residuo == 0:
        raise ValueError("Gli sconti gia' applicati lasciano un valore troppo piccolo per calcolare lo sconto aggiuntivo.")
    complemento = 1 - (1 - sconto_finale / 100) / residuo
    if not isfinite(complemento * 100):
        raise ValueError("La combinazione degli sconti non consente un risultato valido.")
    return round(complemento * 100, 2)


def calcola_sconto_combinazione(acquistati, omaggio):
    _number(acquistati, "Pezzi pagati", positive=True, integer=True)
    _number(omaggio, "Pezzi in omaggio", integer=True)
    if not isfinite(acquistati + omaggio):
        raise ValueError("Il numero totale di pezzi e' troppo grande.")
    logger.debug(f"Calcolo sconto combinazione da: acquistati={acquistati}, omaggio={omaggio}")
    sconto_combinazione = 100 * omaggio / (omaggio + acquistati)
    return round(sconto_combinazione, 2)


@role_required(40)
@log_task(logger)
@sconti_bp.route('/elaborazione-sconti')
def elaborazione_sconti():
    logger.debug(f"Caricamento pagina elaborazione sconti")
    return render_template('functions/elaborazione_sconti.html')


@sconti_bp.route("/test-roles")
@rr.role_required(min_weight=40, roles=["staff"])
def test_roles():
    return "Accesso consentito alla route di test"


@role_required(40)
@sconti_bp.route('/test-log')
def test_log_sconti():
    logger.debug("ðŸ”¥ Questo Ã¨ un log di DEBUG dal server Flask")
    logger.info("ðŸ“˜ Questo Ã¨ un log di INFO dal server Flask")
    return "Log test inviati al logger 'sconti'"


@sconti_bp.route('/calcola-sconto-combinazioni', methods=['POST'])
def calcola_sconto_combinazione_endpoint():
    data = _request_data()
    acquistati = data.get('acquistati')
    omaggio = data.get('omaggio')

    if acquistati is None or omaggio is None:
        logger.warning("Parametri mancanti nel calcolo sconto combinazione.")
        return jsonify({'error': 'I campi acquistati e omaggio sono obbligatori.'}), 400

    risultato = calcola_sconto_combinazione(acquistati, omaggio)
    return jsonify({'sconto_combinazione': risultato})


@sconti_bp.route('/calcola-sconto-merce', methods=['POST'])
def calcola_sconto_merce_endpoint():
    data = _request_data()
    val_merce_acquistata = data.get('val_acquisto')
    val_merce_omaggio = data.get('val_omaggio')
    # logger.debug(f"Valore Merce Acquistata = {val_merce_acquistata}")
    # logger.debug(f"Valore Merce Omaggio = {val_merce_omaggio}")
    if val_merce_acquistata is None or val_merce_omaggio is None:
        logger.warning("Parametri mancanti nel calcolo sconto merce.")
        return jsonify({'error': 'I campi merce acquistata e merce omaggio sono obbligatori.'}), 400

    try:
        logger.debug(f"Merce acquistata: {val_merce_acquistata} \nMerce omaggio: {val_merce_omaggio}")
        risultato = calcola_sconto_merce(val_merce_acquistata, val_merce_omaggio)
        return jsonify({'sconto_merce': risultato})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@sconti_bp.route('/calcola-sconto-equivalente', methods=['POST'])
def calcola_sconto_equivalente_endpoint():
    sconti = _request_data().get('sconti', [])
    risultato = calcola_sconto_equivalente(sconti)
    return jsonify({'sconto_equivalente': risultato})


@sconti_bp.route('/calcola-sconto-complementare', methods=['POST'])
def calcola_sconto_complementare_endpoint():
    data = _request_data()
    sconto_finale = data.get('sconto_finale')
    sconti_fissi = data.get('sconti_fissi', [])
    risultato = calcola_sconto_complementare(sconto_finale, sconti_fissi)
    return jsonify({'sconto_complementare': risultato})

