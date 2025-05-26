import logging
import requests
from flask_mail import Message
from jinja2 import Template

from models import TrelloAction
from tools.trello_api import TrelloAPI

logger = logging.getLogger(__name__)

trello = TrelloAPI()  # legge TRELLO_KEY e TRELLO_TOKEN dall'env


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

    trigger_type = elabora_trigger(trigger_type, payload)
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
            match act.action_type:
                case 'sendEmail':
                    # Config_json expected: { to, subject, body }
                    _send_email(cfg, payload)
                case 'internalCall':
                    # Config_json expected: { url, method, headers?, payload? }
                    _internal_call(cfg, context)
                case 'addComment':
                    comment_from_to(payload)
                case _:
                    logger.warning(f"Action type non riconosciuto: {act.action_type}")
        except Exception as e:
            logger.exception(f"Errore eseguendo azione {act.id}: {e}")


def elabora_trigger(type, payload):
    match type:
        case 'updateCard':
            if is_moved(payload):
                return 'moveCard'
            else:
                return type
        case _:
            return type


def is_moved(payload):
    da_list = payload.action.data.listBefore.id
    a_list = payload.action.data.listAfter.id
    return da_list == a_list


def comment_from_to(payload):
    provenienza = payload.action.data.listBefore.name
    destinazione = payload.action.data.listAfter.name
    membro = payload.action.memberCreator.username
    message = f"{membro} ha spostato la card da {provenienza} a {destinazione}."
    trello.add_comment_to_card(payload.action.data.card.id, message)


def _send_email(cfg, payload):
    from app import mail
    """
    Invia un'email usando un servizio esterno o SMTP.
    cfg: dict con chiavi 'to', 'subject', 'body'
    """

    # ─────────── RENDER TEMPLATE ───────────
    rendered_cfg = {}
    for key, val in cfg.items():
        # val è tipo "Nuova scheda: {{payload.action.data.card.name}}"
        tpl = Template(val)
        rendered_cfg[key] = tpl.render(payload=payload)
    # ────────────────────────────────────────

    # Placeholder: integra con il tuo mailer
    to = rendered_cfg.get('to')
    subject = rendered_cfg.get('subject')
    body = rendered_cfg.get('body')
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
