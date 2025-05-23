import base64
import hashlib
import hmac
import logging
import json

from flask import Blueprint, request, abort, current_app, jsonify, render_template, url_for
from sqlalchemy.orm.exc import NoResultFound

from extensions import db
from models import TrelloConnection, TrelloAction
from tools.log_utils import get_logger
from tools.trello_client import create_webhook, delete_webhook, TrelloClientError
from tools.processor import process_trello_event  # da implementare al punto 6

logger = get_logger("trello", level=logging.DEBUG)
trello_bp = Blueprint('trello', __name__, url_prefix='/trello')


@trello_bp.route('/webhook/<int:conn_id>', methods=['HEAD', 'POST'])
def handle_webhook(conn_id):
    # HEAD is Trello’s ping-check
    if request.method == 'HEAD':
        return '', 200

    # load the exact connection
    conn = TrelloConnection.query.get_or_404(conn_id)

    # now validate HMAC
    raw_body = request.get_data()
    signature = request.headers.get('X-Trello-Webhook') or ''
    secret = f"{conn.api_key}{conn.token}".encode('utf-8')
    expected = base64.b64encode(hmac.new(secret, raw_body, hashlib.sha1).digest()).decode('utf-8')

    if not hmac.compare_digest(signature, expected):
        abort(401)

    payload = request.get_json(force=True)
    logger.info(f"Payload ricevuto: \n {payload}")
    process_trello_event(connection=conn, payload=payload)
    return '', 200


#
# Connections CRUD
#
@trello_bp.route('/connection', methods=['GET'])
def list_connections():
    conns = TrelloConnection.query.all()
    return jsonify([
        {
            'id': c.id,
            'board_id': c.board_id,
            'board_name': c.board_name,
            'webhook_id': c.webhook_id,
            'created_at': c.created_at.isoformat(),
            'updated_at': c.updated_at.isoformat(),
        }
        for c in conns
    ]), 200


@trello_bp.route('/connection/<int:id>', methods=['GET'])
def get_connection(id):
    conn = TrelloConnection.query.get_or_404(id)
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
    data = request.get_json()
    # … your validation …
    conn = TrelloConnection(
      board_id=data['board_id'],
      board_name=data['board_name'],
      api_key=data['api_key'],
      token=data['token'],
    )
    for f in ('board_id', 'board_name', 'api_key', 'token'):
        if not data.get(f):
            return jsonify({'error': f"Campo mancante: {f}"}), 400
    db.session.add(conn)
    db.session.commit()

    # build and store the per-connection callback URL
    cb = url_for('trello.handle_webhook', conn_id=conn.id, _external=True)
    conn.callback_url = cb

    try:
        webhook_id = create_webhook(conn.board_id, cb)
    except TrelloClientError as e:
        db.session.delete(conn)
        db.session.commit()
        return jsonify({'error': str(e)}), 400

    conn.webhook_id = webhook_id
    db.session.commit()

    return jsonify({'id': conn.id, 'webhook_id': webhook_id}), 201


@trello_bp.route('/connection/<int:id>', methods=['PUT'])
def update_connection(id):
    data = request.get_json()
    conn  = TrelloConnection.query.get_or_404(id)

    # 1) aggiorno solo se è cambiato (evito di ricreare webhook a ogni PUT)
    for attr in ('board_name','api_key','token'):
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

        conn.webhook_id    = new_wh
        conn.callback_url = data['callback_url']

    db.session.commit()
    return jsonify({'message': 'Connessione aggiornata'}), 200


@trello_bp.route('/connection/<int:id>', methods=['DELETE'])
def delete_connection(id):
    try:
        conn = TrelloConnection.query.filter_by(id=id).one()
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
    data = request.get_json()
    for f in ('connection_id','trigger_type','action_type','config_json'):
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


@trello_bp.route('/actions/<int:id>', methods=['PUT'])
def update_action(id):
    """
    PUT /trello/actions/<id>
    BODY JSON: { trigger_type?, action_type?, config_json? }
    """
    action = TrelloAction.query.get_or_404(id)
    data = request.get_json()

    for attr in ('trigger_type','action_type','config_json'):
        if attr in data:
            setattr(action, attr, data[attr])

    db.session.commit()
    return jsonify({'message': 'Aggiornamento avvenuto'}), 200


@trello_bp.route('/actions/<int:id>', methods=['DELETE'])
def delete_action(id):
    """
    DELETE /trello/actions/<id>
    """
    action = TrelloAction.query.get_or_404(id)
    db.session.delete(action)
    db.session.commit()
    return '', 204


@trello_bp.route('/connection/<int:id>/actions', methods=['GET'])
def edit_actions(id):
    conn = TrelloConnection.query.get_or_404(id)
    return render_template('trello_actions.html', connection=conn)


@trello_bp.route('/connections', methods=['GET'])
def connections_list_ui():
    """Mostra la pagina con la tabella di tutte le connessioni."""
    return render_template('trello_connections_list.html')


@trello_bp.route('/connection/editor/new', methods=['GET'])
def new_connection_editor():
    """Editor di una nuova connessione (riusa lo stesso template di edit)."""
    # Passiamo valori vuoti e schema vuoto
    empty_schema = json.dumps({ 'nodes': [], 'connections': [] })
    return render_template(
        'trello_connections.html',
        board_id='',
        board_name='',
        api_key='',
        token='',
        callback_url='',
        existingSchema=empty_schema
    )
