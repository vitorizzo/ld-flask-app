import logging
import requests
from flask_mail import Message
from models import TrelloAction

logger = logging.getLogger(__name__)


def process_trello_event(connection, payload):
    """
    Dispatcher per gli eventi Trello:
    - Estrae trigger_type e card_id dal payload
    - Recupera tutte le TrelloAction associate alla connection e al trigger
    - Esegue per ognuna l'azione specificata in action_type
    """
    # Estrai tipo di trigger
    action = payload.get('action', {})
    trigger_type = action.get('type')
    data = action.get('data', {})

    # Recupera le azioni configurate in DB
    actions = TrelloAction.query.filter_by(
        connection_id=connection.id,
        trigger_type=trigger_type
    ).all()

    if not actions:
        logger.debug(f"Nessuna azione configurata per trigger {trigger_type}")
        return

    # Dati di contesto comuni
    context = {}
    # Esempio: estrai card_id se presente
    if 'card' in data:
        card = data['card']
        context['card_id'] = card.get('id')
        context['card_name'] = card.get('name')

    # Per ogni azione, esegui la logica
    for act in actions:
        logger.info(f"Esecuzione azione {act.action_type} per trigger {trigger_type}")
        cfg = act.config_json or {}
        try:
            if act.action_type == 'sendEmail':
                # Config_json expected: { to, subject, body }
                _send_email(cfg)
            elif act.action_type == 'internalCall':
                # Config_json expected: { url, method, headers?, payload? }
                _internal_call(cfg, context)
            else:
                logger.warning(f"Action type non riconosciuto: {act.action_type}")
        except Exception as e:
            logger.exception(f"Errore eseguendo azione {act.id}: {e}")


def _send_email(cfg):
    from app import mail
    """
    Invia un'email usando un servizio esterno o SMTP.
    cfg: dict con chiavi 'to', 'subject', 'body'
    """
    # Placeholder: integra con il tuo mailer
    to = cfg.get('to')
    subject = cfg.get('subject')
    body = cfg.get('body')
    msg = Message(subject,
                  recipients=[to],
                  body=body)
    mail.send(msg)
    logger.debug(f"Invio email a {to}: {subject}\n{body}")
    # Esempio con un'API di mail service
    # requests.post(
    #     'https://api.mailservice.local/send',
    #     json={'to': to, 'subject': subject, 'body': body}
    # )


def _internal_call(cfg, context):
    """
    Esegue una chiamata HTTP interna.
    cfg: dict con chiavi 'url', 'method', 'headers', 'payload_template'
    context: dict di contesto (es. card_id)
    """
    url = cfg.get('url')
    method = cfg.get('method', 'POST').upper()
    headers = cfg.get('headers', {})
    # Sostituisci template nel payload se necessario
    payload = cfg.get('payload', {})
    # Esempio di templating semplice
    if isinstance(payload, str):
        payload = payload.format(**context)

    logger.debug(f"Internal call {method} {url} payload={payload}")
    resp = requests.request(method, url, json=payload, headers=headers)
    resp.raise_for_status()
    return resp.json()
