import logging
from flask import Blueprint, request, abort, current_app
import json

from tools.log_utils import get_logger

logger = get_logger("trello", level=logging.DEBUG)
logger.debug("🧪 Logger 'trello' inizializzato correttamente - test DEBUG")
logger.info("🧪 Logger 'trello' inizializzato correttamente - test INFO")

trello_bp = Blueprint('trello', __name__)


@trello_bp.route('/webhook', methods=['HEAD', 'POST'])
def handle_trello():
    # 1) Risposta alla HEAD di verifica
    if request.method == 'HEAD':
        logger.info("Trello webhook verification received")
        return '', 200

    # 2) Ricevi il payload JSON
    try:
        payload = request.get_json(force=True)
    except Exception as e:
        logger.error(f"Invalid JSON: {e}")
        abort(400)

    # 3) Log di debug (poi potrai rimuovere)
    logger.debug("Trello payload: %s", json.dumps(payload))

    # 4) Estrarre dati utili
    action = payload.get('action', {})
    action_type = action.get('type')
    data = action.get('data', {})

    # 5) Gestisci i vari tipi di evento
    if action_type == 'createCard':
        card_id = data.get('card', {}).get('id')
        card_name = data.get('card', {}).get('name')
        logger.info(f"Nuova card creata: [{card_id}] {card_name}")
        # → Qui inserisci la logica per il tuo inventario...
    elif action_type == 'updateCard':
        # esempio: titolo cambiato, spostamento lista, checklist…
        logger.info("Card aggiornata")
    else:
        logger.info(f"Azione Trello non gestita: {action_type}")

    return '', 200
