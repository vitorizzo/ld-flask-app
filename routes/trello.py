import hashlib
import hmac
import logging
from flask import Blueprint, request, abort, current_app, flash, redirect, url_for, render_template
import json

from extensions import db
from models import TrelloConfig
from tools.log_utils import get_logger

logger = get_logger("trello", level=logging.DEBUG)
logger.debug("🧪 Logger 'trello' inizializzato correttamente - test DEBUG")
logger.info("🧪 Logger 'trello' inizializzato correttamente - test INFO")

trello_bp = Blueprint('trello', __name__)


@trello_bp.route('/webhook', methods=['HEAD', 'POST'])
def handle_trello():
    # 1) Risposta alla HEAD di verifica (Trello fa questo per confermare il webhook)
    if request.method == 'HEAD':
        current_app.logger.info("Trello webhook verification received")
        return '', 200

    # 2) Controllo firma HMAC (opzionale ma consigliato)
    cfg = TrelloConfig.query.first()
    if not cfg:
        current_app.logger.error("TrelloConfig non trovato in DB")
        abort(500)

    # uso il body raw per calcolare la signature
    raw_body = request.get_data()
    secret = f"{cfg.api_key}{cfg.token}"
    signature_header = request.headers.get('X-Trello-Webhook', '')

    computed_sig = hmac.new(
        secret.encode('utf-8'),
        raw_body,
        hashlib.sha1
    ).hexdigest()

    if not hmac.compare_digest(computed_sig, signature_header):
        current_app.logger.warning("Firma Trello NON valida")
        abort(401)

    # 3) Parsing JSON
    try:
        payload = request.get_json(force=True)
    except Exception as e:
        current_app.logger.error(f"Invalid JSON: {e}")
        abort(400)

    current_app.logger.debug("Trello payload: %s", json.dumps(payload))

    # 4) Estrazione dati e dispatch
    action = payload.get('action', {})
    action_type = action.get('type')
    data = action.get('data', {})

    if action_type == 'createCard':
        card = data.get('card', {})
        card_id = card.get('id')
        card_name = card.get('name')
        current_app.logger.info(f"Nuova card creata: [{card_id}] {card_name}")
        # → inserisci qui la logica di business per le nuove card

    elif action_type == 'updateCard':
        current_app.logger.info("Card aggiornata")
        # → qui la logica di business per gli aggiornamenti

    else:
        current_app.logger.info(f"Azione Trello non gestita: {action_type}")

    return '', 200

@trello_bp.route('/config', methods=['GET', 'POST'])
def configure():
    # carica l’unica configurazione (o ne crea una nuova)
    config = TrelloConfig.query.first()
    if not config:
        config = TrelloConfig()

    if request.method == 'POST':
        # prendi i valori dalla form
        config.api_key = request.form['api_key']
        config.token = request.form['token']
        config.id_model = request.form['id_model']
        config.callback_url = request.form['callback_url']

        # salva in DB
        db.session.add(config)
        db.session.commit()

        flash('Configurazione Trello salvata con successo', 'success')
        return redirect(url_for('trello.configure'))

    return render_template('trello_config.html', config=config)
