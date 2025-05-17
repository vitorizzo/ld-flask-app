# app/trello_client.py

import requests
from flask import current_app
from sqlalchemy.orm.exc import NoResultFound

from extensions import db
from models import TrelloConnection


BASE_URL = 'https://api.trello.com/1'


class TrelloClientError(Exception):
    pass


def _get_connection_by_board(board_id):
    """Recupera la connessione Trello dal DB via board_id."""
    try:
        return TrelloConnection.query.filter_by(board_id=board_id).one()
    except NoResultFound:
        raise TrelloClientError(f"Nessuna connessione trovata per board_id={board_id}")


def create_webhook(board_id: str, callback_url: str) -> str:
    """
    Crea un webhook Trello sul board specificato.

    :param board_id: l'ID della board Trello
    :param callback_url: URL al quale Trello invierà le notifiche
    :return: webhook_id appena creato
    """
    conn = _get_connection_by_board(board_id)
    url = f"{BASE_URL}/webhooks"
    params = {
        'key': conn.api_key,
        'token': conn.token,
        'callbackURL': callback_url,
        'idModel': board_id,
        'description': f"Webhook for board {conn.board_name}"
    }
    resp = requests.post(url, params=params)
    if not resp.ok:
        current_app.logger.error(f"Trello create_webhook error: {resp.text}")
        raise TrelloClientError(f"Errore creando webhook: {resp.status_code}")
    data = resp.json()
    # Salvo l'ID del webhook sul DB
    conn.webhook_id = data.get('id')
    db.session.commit()
    return data.get('id')


def delete_webhook(webhook_id: str) -> None:
    """
    Elimina un webhook Trello dato il suo ID.

    :param webhook_id: l'ID del webhook da cancellare
    """
    # Cerco in DB la connessione che ha questo webhook_id (opzionale)
    conn = TrelloConnection.query.filter_by(webhook_id=webhook_id).first()
    if conn:
        api_key, token = conn.api_key, conn.token
    else:
        # Se non la trovo in DB, prendo da config (fallback)
        api_key = current_app.config.get('TRELLO_API_KEY')
        token = current_app.config.get('TRELLO_TOKEN')
        if not api_key or not token:
            raise TrelloClientError("Impossibile trovare credenziali per cancellare il webhook")

    url = f"{BASE_URL}/webhooks/{webhook_id}"
    params = {'key': api_key, 'token': token}
    resp = requests.delete(url, params=params)
    if not resp.ok:
        current_app.logger.error(f"Trello delete_webhook error: {resp.text}")
        raise TrelloClientError(f"Errore eliminando webhook: {resp.status_code}")

    # Rimuovo l'ID dal record DB, se presente
    if conn:
        conn.webhook_id = None
        db.session.commit()
