import base64
import hashlib
import hmac
import logging
import json

import requests
from flask import Blueprint, request, abort, current_app, jsonify, render_template, url_for
from sqlalchemy.exc import NoResultFound

# from sqlalchemy.orm.exc import NoResultFound

from extensions import db
from models import TrelloConnection, TrelloAction
from tools.log_utils import get_logger
from tools.trello_api import TrelloAPI
from tools.trello_client import create_webhook, delete_webhook, TrelloClientError
from tools.processor import process_trello_event  # da implementare al punto 6
from config.capabilities import get_capabilities

logger = get_logger("trello", level=logging.DEBUG)
logger.debug("🧪 Logger 'trello' inizializzato correttamente - test DEBUG")

trello_bp = Blueprint('trello', __name__, url_prefix='/trello')


@trello_bp.route("/capabilities", methods=["GET"])
def trello_capabilities():
    """
    Restituisce le capabilities Trello (triggers, actions, placeholders, field defs).
    """
    return jsonify(get_capabilities("trello")), 200


@trello_bp.route('/boards/<string:board_id>/lists', methods=['GET'])
def list_board_lists(board_id):
    """
    Restituisce le liste di una board Trello.
    Output: [{id, name}, ...]
    """
    logger.info(f"route: /trello/boards/{board_id}/lists")

    api_key = current_app.config.get('TRELLO_KEY')
    token = current_app.config.get('TRELLO_TOKEN')
    if not api_key or not token:
        return jsonify({'error': 'Trello non configurato: manca TRELLO_KEY o TRELLO_TOKEN'}), 500

    try:
        t = TrelloAPI(api_key=api_key, token=token)
        lists_ = t.get_lists(board_id) or []
    except requests.exceptions.RequestException:
        logger.exception("Errore HTTP/connessione Trello (board_id=%s)", board_id)
        return jsonify({'error': 'Errore Trello durante il recupero liste'}), 502

    out = [
        {'id': lista.get('id'),
         'name': lista.get('name')
         } for lista in lists_ if lista.get('id') and lista.get('name')
    ]
    out.sort(key=lambda x: x['name'].lower())
    return jsonify(out), 200


@trello_bp.route('/boards', methods=['GET'])
def list_boards():
    """
    Restituisce l'elenco delle board visibili al token Trello globale.
    Output: [{id, name}, ...]
    """
    logger.info("route: /trello/boards <GET>")

    api_key = current_app.config.get('TRELLO_KEY')
    token = current_app.config.get('TRELLO_TOKEN')
    if not api_key or not token:
        return jsonify({'error': 'Trello non configurato: manca TRELLO_API_KEY o TRELLO_TOKEN'}), 500

    t = TrelloAPI(api_key=api_key, token=token)
    boards = t.get_boards(member_id="me") or []

    # Normalizza l'output (id + name) e ordina per nome
    out = [{'id': b.get('id'), 'name': b.get('name')} for b in boards if b.get('id') and b.get('name')]
    out.sort(key=lambda x: x['name'].lower())
    return jsonify(out), 200


@trello_bp.route('/webhook/<int:conn_id>', methods=['HEAD', 'POST'])
def handle_webhook(conn_id):
    logger.info(f'route: /trello/webhook/{conn_id} <HEAD, POST>')
    if request.method == 'HEAD':
        logger.info("↔️  Trello HEAD check, OK")
        return '', 200

    conn = TrelloConnection.query.get_or_404(conn_id)
    raw_body = request.get_data()               # bytes
    signature = request.headers.get('X-Trello-Webhook', '')

    # Carica il tuo secret dal .env
    secret = current_app.config['TRELLO_SECRET'].encode('utf-8')

    # Usa raw_body + callbackURL
    cb_url = conn.callback_url.encode('utf-8')
    mac = hmac.new(secret, raw_body + cb_url, hashlib.sha1).digest()
    expected = base64.b64encode(mac).decode('utf-8')

    if not hmac.compare_digest(signature, expected):
        logger.warning(
            f"❌ HMAC mismatch (got {signature!r}, expected {expected!r})"
        )
        abort(401)

    payload = request.get_json(force=True)
    logger.info(f"🎯 Ricevuto evento Trello per conn_id={conn_id}")
    process_trello_event(connection=conn, payload=payload)
    return '', 200


#
# Connections CRUD
#
@trello_bp.route('/connection', methods=['GET'])
def list_connections():
    logger.info(f'route: /trello/connection <GET>')
    conns = TrelloConnection.query.all()
    return jsonify([
        {
            'id': c.id,
            'board_id': c.board_id,
            'board_name': c.board_name,
            'webhook_id': c.webhook_id,
            'created_at': c.created_at.isoformat(),
            'updated_at': c.updated_at.isoformat() if c.updated_at else 'N/A',
        }
        for c in conns
    ]), 200


@trello_bp.route('/connection/reset_webhooks', methods=['POST', 'GET'])
def reset_all_webhooks():
    """
    Per ogni TrelloConnection in DB:
    - cancella il vecchio webhook (se presente)
    - ricrea un nuovo webhook puntando allo stesso callback_url
    - aggiorna webhook_id in tabella
    Restituisce un report JSON con id di connessione, webhook vecchio/nuovo e eventuali errori.
    """
    logger.info(f'route: /trello/connection/reser_webhooks <POST, GET>')
    results = []
    conns = TrelloConnection.query.all()
    for conn in conns:
        old_wh = conn.webhook_id
        # 1) cancello il vecchio
        if old_wh:
            try:
                delete_webhook(old_wh)
            except TrelloClientError as e:
                logger.warning(f"Non ho potuto cancellare webhook {old_wh}: {e}")

        # 2) (ri)costruisco il callback (in genere non cambia)
        cb = url_for('trello.handle_webhook', conn_id=conn.id, _external=True)
        conn.callback_url = cb

        # 3) provo a creare il nuovo webhook
        try:
            new_wh = create_webhook(conn.board_id, cb)
            conn.webhook_id = new_wh
            db.session.commit()
            results.append({
                'connection_id': conn.id,
                'old_webhook': old_wh,
                'new_webhook': new_wh,
                'status': 'ok'
            })
        except TrelloClientError as e:
            db.session.rollback()
            results.append({
                'connection_id': conn.id,
                'old_webhook':   old_wh,
                'error':         str(e),
                'status':        'error'
            })

    return jsonify(results), 200


@trello_bp.route('/connection/<int:myid>', methods=['GET'])
def get_connection(myid):
    logger.info(f'route: /trello/connection/{myid} <GET>')
    conn = TrelloConnection.query.get_or_404(myid)
    return jsonify({
        'id':           conn.id,
        'board_id':     conn.board_id,
        'board_name':   conn.board_name,
        'api_key':      conn.api_key,
        'token':        conn.token,
        'callback_url': conn.callback_url,  # o come lo chiami
        'schema':       conn.schema_json or {'nodes': [], 'connections': []}
    }), 200


@trello_bp.route('/connection', methods=['POST'])
def create_connection():
    from flask import current_app

    logger.info(f'route: /trello/connection <POST>')
    data = request.get_json()
    apikey = current_app.config.get('TRELLO_KEY')
    token = current_app.config.get('TRELLO_TOKEN')

    # 1) Validazione minima
    for f in ('board_id', 'board_name'):
        if not data.get(f):
            return jsonify({'error': f"Campo mancante: {f}"}), 400

    # 1b) Credenziali Trello globali obbligatorie (modello A)
    if not apikey or not token:
        return jsonify({'error': "Trello non configurato: manca TRELLO_API_KEY o TRELLO_TOKEN"}), 500

    # 2) Creo il record in DB (senza callback_url né webhook_id per ora)
    conn = TrelloConnection(
        board_id=data['board_id'],
        board_name=data['board_name'],
        api_key=apikey,
        token=token
    )
    db.session.add(conn)
    db.session.commit()   # <-- qui conn.id viene assegnato dal DB

    # 3) Genero automaticamente il callback_url basato su conn.id
    cb = url_for('trello.handle_webhook', conn_id=conn.id, _external=True)
    conn.callback_url = cb
    db.session.commit()   # <-- salvo il campo callback_url

    # 4) Chiamo l’API di Trello per creare il webhook
    try:
        webhook_id = create_webhook(conn.board_id, cb)
    except TrelloClientError as e:
        # se fallisce, rollback: rimuovo il record DB
        db.session.delete(conn)
        db.session.commit()
        return jsonify({'error': str(e)}), 400

    # 5) Se va a buon fine, salvo anche l’ID del webhook
    conn.webhook_id = webhook_id
    db.session.commit()

    # 6) Rispondo con il nuovo ID di connessione e di webhook
    return jsonify({'id': conn.id, 'webhook_id': webhook_id}), 201


@trello_bp.route('/connection/<int:myid>', methods=['PUT'])
def update_connection(myid):
    logger.info(f'route: /trello/connection/{myid} <PUT>')
    data = request.get_json()
    conn = TrelloConnection.query.get_or_404(myid)

    # 1) aggiorno solo se è cambiato (evito di ricreare webhook a ogni PUT)
    for attr in ('board_name', 'api_key', 'token'):
        if attr in data:
            setattr(conn, attr, data[attr])

    # 2) se callback_url è stata modificata davvero, allora ricreo il webhook
    if 'callback_url' in data and data['callback_url'] != conn.callback_url:
        # cancelliamo l’eventuale vecchio
        if conn.webhook_id:
            try:
                delete_webhook(conn.webhook_id)
            except TrelloClientError:
                logger.warning(f"Non ho potuto cancellare il vecchio webhook {conn.webhook_id}")
        # creiamo il nuovo, **dentro un try** per NON far esplodere tutto
        try:
            new_wh = create_webhook(conn.board_id, data['callback_url'])
        except TrelloClientError as e:
            # restituisco un 400 con l’errore di Trello, così vedi causa e non 500
            return jsonify({'error': str(e)}), 400

        conn.webhook_id = new_wh
        conn.callback_url = data['callback_url']

    db.session.commit()
    return jsonify({'message': 'Connessione aggiornata'}), 200


@trello_bp.route('/connection/<int:myid>', methods=['DELETE'])
def delete_connection(myid):
    logger.info(f'route: /trello/connection/{myid} <DELETE>')
    conn = None
    try:
        conn = TrelloConnection.query.filter_by(id=myid).one()
    except NoResultFound:
        abort(404)

    if conn.webhook_id:
        try:
            delete_webhook(conn.webhook_id)
        except TrelloClientError:
            logger.warning(f"Non ho potuto cancellare webhook {conn.webhook_id}")

    db.session.delete(conn)
    db.session.commit()
    return '', 204


@trello_bp.route('/connection/editor/<int:conn_id>', methods=['GET'])
def edit_connection(conn_id):
    logger.info(f'route: /trello/connection/editor/{conn_id} <GET>')
    conn = TrelloConnection.query.get_or_404(conn_id)
    # se c’è già uno schema salvato, serializzalo qui in existing_schema
    existing_schema = conn.schema_json or {'nodes': [], 'connections': []}
    return render_template(
        'trello_connections.html',
        board_id=conn.board_id,
        board_name=conn.board_name,
        api_key=conn.api_key,
        token=conn.token,
        callback_url=conn.callback_url,
        existingSchema=json.dumps(existing_schema)
    )


#
# Actions CRUD
#
@trello_bp.route('/actions', methods=['GET'])
def list_actions():
    """
    GET /trello/actions?connection_id=<id>
    Restituisce tutte le azioni associate a una connection.
    """
    logger.info(f'route: /trello/actions <GET>')
    conn_id = request.args.get('connection_id', type=int)
    if conn_id is None:
        return jsonify({'error': 'connection_id è obbligatorio'}), 400

    actions = TrelloAction.query.filter_by(connection_id=conn_id).all()
    result = [{
        'id': a.id,
        'trigger_type': a.trigger_type,
        'action_type': a.action_type,
        'config_json': a.config_json,
        'created_at': a.created_at.isoformat()
    } for a in actions]
    return jsonify(result), 200


@trello_bp.route('/actions', methods=['POST'])
def create_action():
    """
    POST /trello/actions
    BODY JSON: { connection_id, trigger_type, action_type, config_json }
    """
    logger.info(f'route: /trello/actions <POST>')
    data = request.get_json()
    for f in ('connection_id', 'trigger_type', 'action_type', 'config_json'):
        if f not in data:
            return jsonify({'error': f"Campo mancante: {f}"}), 400

    # verifica che la connection esista
    if not TrelloConnection.query.get(data['connection_id']):
        return jsonify({'error': 'connection_id non valido'}), 404

    action = TrelloAction(
        connection_id=data['connection_id'],
        trigger_type=data['trigger_type'],
        action_type=data['action_type'],
        config_json=data['config_json']
    )
    db.session.add(action)
    db.session.commit()

    return jsonify({'id': action.id}), 201


@trello_bp.route('/actions/<int:action_id>')
def get_action(action_id):
    logger.info(f'route: /trello/actions/{action_id}')
    action = TrelloAction.query.get_or_404(action_id)
    return jsonify({
        'id': action.id,
        'ordine': action.ordine,
        'connection_id': action.connection_id,
        'trigger_type': action.trigger_type,
        'action_type': action.action_type,
        'config_json': action.config_json
    })


@trello_bp.route('/actions/<int:myid>', methods=['PUT'])
def update_action(myid):
    """
    PUT /trello/actions/<id>
    BODY JSON: { trigger_type?, action_type?, config_json? }
    """
    logger.info(f'route: /trello/actions/{myid} <PUT>')
    action = TrelloAction.query.get_or_404(myid)
    data = request.get_json()

    for attr in ('trigger_type', 'action_type', 'config_json', 'ordine'):
        if attr in data:
            setattr(action, attr, data[attr])

    db.session.commit()
    return jsonify({'message': 'Aggiornamento avvenuto'}), 200


@trello_bp.route('/actions/<int:myid>', methods=['DELETE'])
def delete_action(myid):
    """
    DELETE /trello/actions/<id>
    """
    logger.info(f'route: /trello/actions/{myid} <DELETE>')
    action = TrelloAction.query.get_or_404(myid)
    db.session.delete(action)
    db.session.commit()
    return '', 204


@trello_bp.route('/connection/<int:myid>/actions', methods=['GET'])
def edit_actions(myid):
    logger.info(f'route: /trello/connection/{myid}/actions <GET>')
    conn = TrelloConnection.query.get_or_404(myid)
    return render_template('trello_actions.html', connection=conn)


@trello_bp.route('/connections', methods=['GET'])
def connections_list_ui():
    """Mostra la pagina con la tabella di tutte le connessioni."""
    logger.info(f'route: /trello/connections <GET>')
    return render_template('trello_connections_list.html')


@trello_bp.route('/connection/editor/new', methods=['GET'])
def new_connection_editor():
    """Editor di una nuova connessione (riusa lo stesso template di edit)."""
    # Passiamo valori vuoti e schema vuoto
    logger.info(f'route: /trello/connection/editor/new <GET>')
    empty_schema = json.dumps({'nodes': [], 'connections': []})
    return render_template(
        'trello_connections.html',
        board_id='',
        board_name='',
        api_key='',
        token='',
        callback_url='',
        existingSchema=empty_schema
    )
