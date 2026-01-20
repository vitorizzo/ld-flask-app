import datetime
import logging
import requests
from flask_mail import Message
from jinja2 import Template

from models import TrelloAction
from tools.log_utils import get_logger
from tools.trello_api import TrelloAPI

logger = get_logger("processor", level=logging.DEBUG)
logger.debug("🧪 Logger 'processor' inizializzato correttamente - test DEBUG")

# trello = TrelloAPI()  # legge TRELLO_KEY e TRELLO_TOKEN dall'env
trello = None  # lazy init

customized_boards = ['Ordini', 'Scarichi-Ufficio']

template_comments = [
    {
        'board_name': 'Scarichi - Ufficio',
        'fixed_comments': {
            'Nuovi Prodotti': "###✨ Nuovi prodotti:\n---\n - testo nuovi prodotti qui",
            'Anomalie': "###🚧 Anomalie:\n---\n - testo anomalie qui",
            'Nuove Annate': "###📅 Nuove annate:\n----\n - testo annate qui",
            'Variazioni di Prezzo': "###📈 Variazioni di prezzo:\n---\n - testo variazioni qui",
            'Controllare i Prezzi': "###🚨 Controllare i prezzi:\n---\n - testo prezzi qui",
            'Omaggi': "###🎁 Gestione Omaggi:\n---\n - testo omaggi qui",
            'Contributo Catalogo': "###📓 Contributo Catalogo:\n---\n - testo contributo qui",
            'Fine Anno': "###🧾 Fine Anno:\n---\n - testo fine anno qui",
            'Interventi da Ricevere': "###💰 Interventi da Ricevere:\n---\n - testo interventi qui",
            'Consegna Parziale': "###🚚 Consegna Parziale:\n---\n - testo consegna qui",
            'Informazioni Aggiuntive': "###📣 Informazioni Aggiuntive:\n---\n - testo informazioni qui"
        }
    }
]

custom_cards = [
    {
        'board_name': 'Ordini',
        'name': 'addDate',
        'checklists': {
            'checklist_name': 'Magazzino',
            'items': {
                'item1': 'Scaricato',
                'item2': 'Accettato con Riserva',
                'item3': 'Controllato',
                'item4': 'Riposto in Magazzino'
            }
        },
        'cover': {
            'color': 'blue',
            'size': 'normal',
            'brightness': 'light'
        }
    },
    {
        'board_name': 'Scarichi - Ufficio',
        'name': 'addDate',
        'checklists': {
            'checklist_name': 'Documenti acquisiti',
            'items': {
                'item1': 'Documento di Trasporto',
                'item2': 'Fattura'
            }
        },
        'cover': {
            'color': 'red',
            'size': 'normal',
            'brightness': 'light'
        }
    }
]

AUTO_MIRROR_LABEL = "LDAPP:AUTO_MIRROR"
AUTO_MIRROR_COLOR = "lime"
AUTO_MIRROR_COMMENT = AUTO_MIRROR_LABEL


def get_trello():
    global trello
    if trello is not None:
        return trello
    try:
        trello = TrelloAPI()  # legge TRELLO_KEY e TRELLO_TOKEN dall'env
        return trello
    except Exception as e:
        logger.warning(f"Trello non configurato o non disponibile: {e}. Funzioni Trello disabilitate.")
        return None


def ensure_label_id(t, board_id: str, label_name: str = AUTO_MIRROR_LABEL, color: str = AUTO_MIRROR_COLOR):
    """
    Ritorna l'id della label 'label_name' sulla board.
    Se non esiste, la crea (color).
    """
    labels = t.get_labels(board_id)  # lista di label della board
    for lb in labels or []:
        if (lb.get("name") or "").strip() == label_name:
            return lb.get("id")

    # Non trovata -> crea
    created = t.create_label(board_id=board_id, name=label_name, color=color)
    return created.get("id")


def card_has_label(card: dict, label_name: str) -> bool:
    for lb in card.get("labels") or []:
        if (lb.get("name") or "").strip() == label_name:
            return True
    return False


def card_has_auto_mirror_comment(t, card_id: str) -> bool:
    """
    Fallback: controlla se tra i commenti esiste il commento tecnico AUTO_MIRROR_COMMENT.
    """
    actions = t.get_card_actions(card_id, action_filter="commentCard") or []
    for a in actions:
        txt = (((a.get("data") or {}).get("text")) or "").strip()
        if txt == AUTO_MIRROR_COMMENT:
            return True
    return False


def process_trello_event(connection, payload):
    """
    Dispatcher per gli eventi Trello:
    - Estrae trigger_type e card_id dal payload
    - Recupera tutte le TrelloAction associate alla connection e al trigger
    - Esegue per ognuna l'azione specificata in action_type
    """

    logger.info(f"Chiamata process_trello_event con \nconnection: \n {connection} \ne payload: \n {payload}")
    # Estrai tipo di trigger
    action = payload.get('action', {})
    trigger_type = action.get('type')
    data = action.get('data', {})

    trigger_type = elabora_trigger(trigger_type, payload)

    logger.info(f"trigger rilevato: {trigger_type}")

    # Normalizzazione
    # Assicuriamoci che trigger_type sia una lista
    if not isinstance(trigger_type, list):
        trigger_type = [trigger_type]

    # Query su tutti i tipi di trigger in lista
    actions = TrelloAction.query.filter(
        TrelloAction.connection_id == connection.id,
        TrelloAction.trigger_type.in_(trigger_type)
    ).order_by(TrelloAction.ordine).all()

    logger.info(f"Trovate {len(actions)} azioni per i trigger: {trigger_type}")
    # fallback nel caso trigger_type fosse una lista vuota o errore
    if 'actions' not in locals():
        actions = []

    if not actions:
        return

    # Dati di contesto comuni
    context = {}
    # Esempio: estrai card_id se presente
    if 'card' in data:
        card = data['card']
        context['card_id'] = card.get('id')
        context['card_name'] = card.get('name')
        logger.info(f"card passata {card.get('name')}")

    # ==========================================================
    # V2 — Cross-app automations (parallelo al legacy)
    # ==========================================================
    try:
        from tools.automation_dispatcher import AutomationDispatcher
        dispatcher = AutomationDispatcher()
        dispatcher.dispatch({
            "app": "trello",
            "trigger": trigger_type,  # già lista normalizzata
            "connection_id": connection.id,
            "payload": payload,  # per Trello usiamo payload completo
        })
    except Exception:
        logger.exception("[V2][TRELLO] dispatcher failed")

    # Per ogni azione, esegui la logica
    for act in actions:
        logger.info(f"Esecuzione azione {act.action_type} per trigger {trigger_type}")
        cfg = act.config_json or {}
        try:
            logger.info(f"action richiesta: {act.action_type}")
            logger.info(f"contenuto cfg: {cfg}")
            match act.action_type:
                case 'sendEmail':
                    # Config_json expected: { to, subject, body }
                    _send_email(cfg, payload)
                case 'internalCall':
                    # Config_json expected: { url, method, headers?, payload? }
                    _internal_call(cfg, context)
                case 'addComment':
                    comment_from_to(cfg, payload)
                case 'serviceComments':
                    service_comment(cfg, payload)
                case 'mirrorCard':
                    crea_mirror_card(cfg, payload)
                case 'customizeCard':
                    personalizza_card(cfg, payload)
                case 'sendSlackMessage':
                    _send_slack_message(payload)
                case _:
                    logger.warning(f"Action type non riconosciuto: {act.action_type}")
        except Exception as e:
            logger.exception(f"Errore eseguendo azione {act.id}: {e}")


def service_comment(cfg, payload):
    logger.info("Commento di servizio...")
    try:
        card_id = payload['action']['data']['card']['id']
        context = {
            'card': payload['action']['data'].get('card', {}),
            'list': payload['action']['data'].get('list', {}),
            'board': payload['action']['data'].get('board', {}),
            'label': payload['action']['data'].get('label', {}).get('name', '')
        }
        t = get_trello()
        if not t:
            logger.warning("Salto add_service_comment: Trello non configurato.")
            return
        for template_comment in template_comments:
            if template_comment['board_name'] == context['board']['name']:
                associations = template_comment['fixed_comments']
                for label_name, comment in associations.items():
                    if context['label'] == label_name:
                        tpl = Template(comment)
                        message = tpl.render()
                        t.add_comment_to_card(card_id, message)
                        logger.info(f"[COMMENTO SERVIZIO] Aggiunta commento alla card {card_id}: {message}")

    except Exception as e:
        logger.exception(f"Errore durante l'aggiunta del commento di servizio: {e}")


def elabora_trigger(tipo, payload):
    trigger_type = []

    match tipo:
        case 'updateCard':
            if is_moved(payload):
                trigger_type.append('moveCard')
            else:
                trigger_type.append(tipo)
        case _:
            trigger_type.append(tipo)
    return trigger_type


def is_moved(payload):
    try:
        b = payload['action']['data']['listBefore']['id']
        a = payload['action']['data']['listAfter']['id']
    except KeyError:
        return False
    return b != a


def comment_from_to(cfg, payload):
    try:
        card_id = payload['action']['data']['card']['id']
        context = {
            'user': payload['action']['memberCreator']['fullName'],
            'card': payload['action']['data'].get('card', {}),
            'listbefore': payload['action']['data'].get('listBefore', {}),
            'listafter': payload['action']['data'].get('listAfter', {}),
            'list': payload['action']['data'].get('list', {}),
            'board': payload['action']['data'].get('board', {}),
            'comment': payload['action']['data'].get('text', {})  # per commentCard
        }

        comment_template = cfg.get('comment') if cfg else "{{user}} ha spostato la card '{{card.name}}'."
        tpl = Template(comment_template)
        message = tpl.render(**context)

        logger.info(f"[COMMENTO] Aggiunta commento alla card {card_id}: {message}")
        # trello.add_comment_to_card(card_id, message)
        t = get_trello()
        if not t:
            logger.warning("Salto add_comment_to_card: Trello non configurato.")
            return
        t.add_comment_to_card(card_id, message)
    except Exception as e:
        logger.exception(f"Errore durante l'aggiunta del commento: {e}")


def trova_id_label(board_id, nome_label):
    t = get_trello()
    if not t:
        logger.warning("Salto trova_id_label: Trello non configurato.")
        return None
    labels = t.get_labels(board_id)
    for label in labels:
        if label['name'].lower() == nome_label.lower():
            return label['id']
    return None


def personalizza_card(cfg, payload):
    logger.info("Personalizzazione card...")
    logger.debug(f"parametri \n cfg: \n{cfg}\npayload: \n{payload}")

    try:
        card_id = payload['action']['data']['card']['id']
        board_name = payload['model']['name']

        t = get_trello()
        if not t:
            logger.warning("Salto personalizza_card: Trello non configurato.")
            return

        for custom_card in custom_cards:
            if custom_card['board_name'] == board_name:
                checklist_name = custom_card['checklists']['checklist_name']
                items = custom_card['checklists']['items']
                new_card = True
                if card_has_label(t.get_card(card_id), AUTO_MIRROR_LABEL):
                    new_card = False
                if card_has_auto_mirror_comment(t, card_id):
                    new_card = False

                match custom_card['name']:
                    case 'addDate':
                        if new_card:
                            t.update_card(card_id, name=payload['action']['data']['card']['name']
                                          + f" - {datetime.datetime.now().strftime('%d-%m-%Y')}")
                if custom_card.get('cover'):
                    cover = custom_card['cover']
                    scc_response = t.set_card_cover_color(
                        card_id,
                        cover.get('color', 'pink'),
                        cover.get('brightness', 'light'),
                        cover.get('size', 'normal')
                    )
                    logger.debug(f"Set cover color response: {scc_response}")
                # Creazione checklist
                cc_response = t.create_checklist_on_card(card_id, checklist_name)
                logger.debug(f"Create checklist response: {cc_response}")
                checklist_id = cc_response.get('id')
                logger.debug(f"Checklist ID: {checklist_id}")
                # Aggiunta items
                for item_key, item_name in items.items():
                    logger.debug(f"Aggiunta item '{item_name}' alla checklist '{checklist_name}'")
                    ac_response = t.add_item_to_checklist(checklist_id, item_name)
                    logger.debug(f"Add item to checklist response: {ac_response}")

    except Exception as e:
        logger.exception(f"Errore durante la personalizzazione della scheda: {e}")


def crea_mirror_card(cfg, payload):

    # assicurarsi che nella bacheca source esista la label 'scheda mirror creata' e
    # nella bacheca dest 'Creata da altra Bacheca'

    logger.info("Creazione mirror card...")
    logger.debug(f"parametri \n cfg: \n{cfg}\npayload: \n{payload}")

    try:
        card_id = payload['action']['data']['card']['id']
        context = {
            'user': payload['action']['memberCreator']['fullName'],
            'card': payload['action']['data']['card']['id'],
            'card_name': payload['action']['data']['card']['name'],
            'date': datetime.datetime.now().strftime("%d-%m-%Y"),
            'source_board': payload['model']['id'],
            'dest_board': cfg.get('target_board_id', ''),
            'dest_board_name': cfg.get('target_board_name', ''),
            'dest_list': cfg.get('target_list_id', '')
        }

        t = get_trello()
        if not t:
            logger.warning("Salto mirror_card: Trello non configurato.")
            return

        # --- ANTI-LOOP GUARD (primario: label, fallback: commento tecnico) ---
        card = t.get_card(card_id)

        # Se la card è stata auto-generata, non creare mirror
        if card_has_label(card, AUTO_MIRROR_LABEL):
            logger.info("Salto mirror_card: card marcata come AUTO_MIRROR (label).")
            return

        if card_has_auto_mirror_comment(t, card_id):
            logger.info("Salto mirror_card: card marcata come AUTO_MIRROR (commento).")
            return

        cc_response = t.create_card(context.get('dest_list'), context.get('card_name'))
        logger.debug(f"Create card response: {cc_response}")
        dest_card_id = cc_response.get('id')

        # --- assicura label AUTO_MIRROR su board dest ed applicala alla card ---
        dest_board_id = context.get('dest_board')
        auto_label_id_dest = ensure_label_id(t, dest_board_id)

        if auto_label_id_dest:
            t.add_label_to_card(dest_card_id, auto_label_id_dest)

        # --- commento tecnico (fallback) ---
        t.add_comment_to_card(dest_card_id, AUTO_MIRROR_COMMENT)

        dest_message = f"scheda madre {t.get_card(card_id)['shortUrl']} della bacheca {context.get('dest_board_name')}"
        dest_card_url = cc_response.get('shortUrl')
        source_message = f"scheda mirror {dest_card_url} nella bacheca {context.get('dest_board_name')}"

        scc_response = t.set_card_cover_color(dest_card_id, 'green', 'light')
        logger.debug(f"Set cover color response: {scc_response}")
        actc_response = t.add_comment_to_card(dest_card_id, dest_message)
        logger.debug(f"Add comment to card response: {actc_response}")
        uc_response = t.update_card(dest_card_id, desc=f"Card originale {t.get_card(card_id)['shortUrl']}")
        logger.debug(f"Update card response: {uc_response}")

        actc_response = t.add_comment_to_card(card_id, source_message)
        logger.debug(f"Add comment to source card response: {actc_response}")
        uc_response = t.update_card(card_id, desc=t.get_card(card_id).get('desc')
                                    + f"\n Card mirror {t.get_card(dest_card_id)['url']}")
        logger.debug(f"Update source card response: {uc_response}")

    except Exception as e:
        logger.exception(f"Errore durante la creazione della scheda mirror: {e}")


def aggiorna_card(card_id, payload):

    # payload contiene i dati da aggiornare in formato json:

    # payload = {
    #   "name": "Nuovo nome scheda",
    #   "desc": "Nuova descrizione scheda",
    #   "due": "2024-12-31T12:00:00.000Z",
    #   "labels": ["label_id1", "label_id2"],
    #   "checklists": {
    #       checklist_id1: ["item1", "item2"],
    #       checklist_id2: ["itemA", "itemB"]
    #   },
    #   "cover": {
    #       color: colore cotertina black|blue|green|lime|orange|pink|purple|red|sky|yellow,
    #       size: dimensione copertina normal|full,
    #       idAttachment: id allegato per copertina immagine,
    #       brightness: light|dark,
    #       url: url immagine per copertina
    #   },
    #   "closed": false
    # }

    logger.info("Aggiornamento card...")
    logger.debug(f"parametri \n card_id: \n{card_id}\npayload: \n{payload}")

    t = get_trello()
    if not t:
        logger.warning("Salto aggiorna_card: Trello non configurato.")
        return

    params = ""
    has_cover = False
    has_labels = False
    has_checklists = False
    color = None
    size = None
    brightness = None
    idattachment = None
    url = None
    labels = []

    if 'name' in payload:
        params += f"&name={payload['name']}"
    if 'desc' in payload:
        params += f"&desc={payload['desc']}"
    if 'due' in payload:
        params += f"&due={payload['due']}"
    if 'closed' in payload:
        params += f"&closed={str(payload['closed']).lower()}"
    if 'cover' in payload:
        has_cover = True
        cover = payload['cover']
        if 'color' in cover:
            color = cover['color']
        if 'size' in cover:
            size = cover['size']
        if 'idAttachment' in cover:
            idattachment = cover['idAttachment']
        if 'brightness' in cover:
            brightness = cover['brightness']
        if 'url' in cover:
            url = cover['url']
    if 'labels' in payload:
        has_labels = True
        for label in payload['labels']:
            labels.append(trova_id_label(t.get_card(card_id)['idBoard'], label))

    try:
        response = t.update_card(card_id, params=params)
        logger.debug(f"Update card response: {response}")
        if has_cover:
            scc_response = t.set_card_cover_color(card_id, color, brightness, size, idattachment, url)
            logger.debug(f"Set cover color response: {scc_response}")
        if has_labels:
            for label_id in labels:
                pl_response = t.add_label_to_card(card_id, label_id)
                logger.debug(f"Add label to card response: {pl_response}")

    except Exception as e:
        logger.exception(f"Errore durante l'aggiornamento della scheda: {e}")


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


def _send_slack_message(payload):
    pass


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


def new_ordini_card():
    pass
