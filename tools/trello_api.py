# tools/trello_api.py

import os

import logging
import requests
from typing import Any, Dict, Optional, List

from tools.log_utils import get_logger

logger = get_logger("processor", level=logging.DEBUG)
logger.debug("🧪 Logger 'processor' inizializzato correttamente - test DEBUG")


class TrelloAPI:
    """
    Wrapper per le Trello REST API (v1).
    Chiama gli endpoint di Trello in modo uniforme, gestendo key e token.
    """
    logger.info("🧪 TrelloAPI inizializzato")

    BASE_URL = "https://api.trello.com/1"

    def __init__(self,
                 api_key: Optional[str] = None,
                 token:   Optional[str] = None):
        """
        Inizializza la classe prendendo api_key e token da parametri o da variabili d'ambiente.
        """
        self.api_key = api_key or os.getenv("TRELLO_KEY")
        self.token = token or os.getenv("TRELLO_TOKEN")
        if not (self.api_key and self.token):
            raise ValueError("Servono API_KEY e TOKEN per usare TrelloAPI")

    def _request(self,
                 method: str,
                 path:   str,
                 params: Optional[Dict[str, Any]] = None,
                 json:   Optional[Dict[str, Any]] = None) -> Any:
        """
        Effettua una richiesta HTTP verso BASE_URL + path.
        Aggiunge automaticamente key e token ai query params.
        Lancia exception se lo status non è 2xx.
        """
        url = f"{self.BASE_URL}{path}"
        p = dict(params or {})
        p.update({'key': self.api_key, 'token': self.token})
        resp = requests.request(method, url, params=p, json=json)
        resp.raise_for_status()
        return resp.json()

    # —————————————————————————————————————
    # ———————— BOARDS ————————————————
    # —————————————————————————————————————

    def get_boards(self, member_id: str = "me", **filters) -> List[Dict]:
        """
        GET /members/{member_id}/boards
        Restituisce le board di un membro (default “me”).
        filters possibili: fields, filter, organization, etc.
        """
        logger.info("🧪 Chiamata a get_boards di TrelloAPI")
        return self._request('GET',
                             f"/members/{member_id}/boards",
                             params=filters)

    def get_board(self, board_id: str, **filters) -> Dict:
        """
        GET /boards/{board_id}
        Restituisce i dettagli di una board.
        """
        logger.info("🧪 Chiamata a get_board di TrelloAPI")
        return self._request('GET',
                             f"/boards/{board_id}",
                             params=filters)

    def create_board(self, name: str, **opts) -> Dict:
        """
        POST /boards
        Crea una nuova board. Occorre almeno il parametro ‘name’.
        Altri opts: defaultLists, desc, idOrganization, prefs, etc.
        """
        logger.info("🧪 Chiamata a create_board di TrelloAPI")
        payload = {'name': name, **opts}
        return self._request('POST', '/boards', params=payload)

    def update_board(self, board_id: str, **fields) -> Dict:
        """
        PUT /boards/{board_id}
        Aggiorna i campi di una board (name, desc, closed, etc.).
        """
        logger.info("🧪 Chiamata a update_board di TrelloAPI")
        return self._request('PUT',
                             f"/boards/{board_id}",
                             params=fields)

    def delete_board(self, board_id: str) -> None:
        """
        DELETE /boards/{board_id}
        Archivia la board.
        """
        logger.info("🧪 Chiamata a delete_board di TrelloAPI")
        self._request('DELETE', f"/boards/{board_id}")

    # —————————————————————————————————————
    # ———————— LISTS ————————————————
    # —————————————————————————————————————

    def get_lists(self, board_id: str, **filters) -> List[Dict]:
        """
        GET /boards/{board_id}/lists
        Restituisce le liste di una board.
        filters possibili: filter, fields, etc.
        """
        logger.info("🧪 Chiamata a get_lists di TrelloAPI")
        return self._request('GET',
                             f"/boards/{board_id}/lists",
                             params=filters)

    def create_list(self, board_id: str, name: str, **opts) -> Dict:
        """
        POST /lists
        Crea una nuova lista su board (idBoard richiesto).
        """
        logger.info("🧪 Chiamata a create_list di TrelloAPI")
        payload = {'idBoard': board_id, 'name': name, **opts}
        return self._request('POST', '/lists', params=payload)

    def update_list(self, list_id: str, **fields) -> Dict:
        """
        PUT /lists/{list_id}
        Aggiorna campi di una lista (name, closed, pos, etc.).
        """
        logger.info("🧪 Chiamata a update_list di TrelloAPI")
        return self._request('PUT',
                             f"/lists/{list_id}",
                             params=fields)

    def archive_list(self, list_id: str) -> None:
        """
        PUT /lists/{list_id}/closed
        Archivia o riapre una lista: closed=true|false.
        """
        logger.info("🧪 Chiamata a archive_list di TrelloAPI")
        self._request('PUT',
                      f"/lists/{list_id}/closed",
                      params={'value': True})

    # —————————————————————————————————————
    # ———————— CARDS ————————————————
    # —————————————————————————————————————

    def get_cards_on_board(self, board_id: str, **filters) -> List[Dict]:
        """
        GET /boards/{board_id}/cards
        Restituisce tutte le card su una board.
        """
        logger.info("🧪 Chiamata a get_cards_on_board di TrelloAPI")
        return self._request('GET',
                             f"/boards/{board_id}/cards",
                             params=filters)

    def get_card(self, card_id: str, **filters) -> Dict:
        """
        GET /cards/{card_id}
        Dettagli di una card.
        """
        logger.info("🧪 Chiamata a get_card di TrelloAPI")
        return self._request('GET',
                             f"/cards/{card_id}",
                             params=filters)

    def create_card(self,
                    list_id: str,
                    name:    str,
                    **opts) -> Dict:
        """
        POST /cards
        Crea una nuova card: serve idList e name. Altri opts possibili:
        desc, due, idMembers, idLabels, pos, etc.
        """
        logger.info("🧪 Chiamata a create_card di TrelloAPI")
        payload = {'idList': list_id, 'name': name, **opts}
        return self._request('POST', '/cards', params=payload)

    def update_card(self, card_id: str, **fields) -> Dict:
        """
        PUT /cards/{card_id}
        Aggiorna campi di una card: name, desc, due, idList (per spostare),
        pos, closed, etc.
        """
        logger.info("🧪 Chiamata a update_card di TrelloAPI")
        return self._request('PUT',
                             f"/cards/{card_id}",
                             params=fields)

    def delete_card(self, card_id: str) -> None:
        """
        DELETE /cards/{card_id}
        Elimina definitivamente una card.
        """
        logger.info("🧪 Chiamata a delete_card di TrelloAPI")
        self._request('DELETE', f"/cards/{card_id}")

    def add_comment_to_card(self,
                            card_id: str,
                            text:    str) -> Dict:
        """
        POST /cards/{card_id}/actions/comments
        Aggiunge un commento alla card.
        """
        logger.info("🧪 Chiamata a add_comment_to_card di TrelloAPI")
        return self._request('POST',
                             f"/cards/{card_id}/actions/comments",
                             json={'text': text})

    def move_card(self,
                  card_id:     str,
                  target_list: str) -> Dict:
        """
        Semplice wrapper di update_card per spostare una card in un’altra lista.
        """
        logger.info("🧪 Chiamata a move_card di TrelloAPI")
        return self.update_card(card_id, idList=target_list)

    def rename_card(self,
                    card_id:  str,
                    new_name: str) -> Dict:
        """
        Semplice wrapper di update_card per rinominare la card.
        """
        logger.info("🧪 Chiamata a rename_card di TrelloAPI")
        return self.update_card(card_id, name=new_name)

    def add_label_to_card(self,
                          card_id:  str,
                          label_id: str) -> Dict:
        """
        POST /cards/{card_id}/idLabels
        Aggiunge un’etichetta (label) a una card.
        """
        logger.info("🧪 Chiamata a add_label_to_card di TrelloAPI")
        return self._request('POST',
                             f"/cards/{card_id}/idLabels",
                             json={'value': label_id})

    # —————————————————————————————————————
    # ————— LABELS SU BOARD —————————————
    # —————————————————————————————————————

    def get_labels(self, board_id: str) -> List[Dict]:
        """
        GET /boards/{board_id}/labels
        Restituisce tutte le etichette di una board.
        """
        logger.info("🧪 Chiamata a get_labels di TrelloAPI")
        return self._request('GET',
                             f"/boards/{board_id}/labels")

    def create_label(self,
                     board_id: str,
                     name:     str,
                     color:    str) -> Dict:
        """
        POST /labels
        Crea una label su board: serve idBoard, name, color.
        """
        logger.info("🧪 Chiamata a create_label di TrelloAPI")
        return self._request('POST',
                             '/labels',
                             params={'idBoard': board_id, 'name': name, 'color': color})

    def update_label(self,
                     label_id: str,
                     **fields) -> Dict:
        """
        PUT /labels/{label_id}
        Modifica name o color di una etichetta.
        """
        logger.info("🧪 Chiamata a update_label di TrelloAPI")
        return self._request('PUT',
                             f"/labels/{label_id}",
                             params=fields)

    def delete_label(self, label_id: str) -> None:
        """
        DELETE /labels/{label_id}
        Elimina una label.
        """
        logger.info("🧪 Chiamata a delete_label di TrelloAPI")
        self._request('DELETE', f"/labels/{label_id}")

    # —————————————————————————————————————
    # ————— WEBHOOKS ————————————————
    # —————————————————————————————————————

    def create_webhook(self,
                       id_model:     str,
                       callback_url: str,
                       description:  str = "") -> Dict:
        """
        POST /webhooks
        Crea un webhook sul model (board, card, etc.).
        """
        logger.info("🧪 Chiamata a create_webhook di TrelloAPI")
        payload = {
            'idModel':     id_model,
            'callbackURL': callback_url,
            'description': description
        }
        return self._request('POST', '/webhooks', params=payload)

    def get_webhooks(self, member_id: str = "me") -> List[Dict]:
        """
        GET /members/{member_id}/webhooks
        Lista dei webhooks di un membro.
        """
        logger.info("🧪 Chiamata a get_webhooks di TrelloAPI")
        return self._request('GET',
                             f"/members/{member_id}/webhooks")

    def delete_webhook(self, webhook_id: str) -> None:
        """
        DELETE /webhooks/{webhook_id}
        Rimuove un webhook.
        """
        logger.info("🧪 Chiamata a delete_webhook di TrelloAPI")
        self._request('DELETE', f"/webhooks/{webhook_id}")

    # —————————————————————————————————————
    # ————— ACTIONS (LOG EVENTI) —————————
    # —————————————————————————————————————

    def get_board_actions(self,
                          board_id: str,
                          **filters) -> List[Dict]:
        """
        GET /boards/{board_id}/actions
        Ritorna la history degli eventi (createCard, updateCard, …)
        Filters possibili: filter, limit, since, before, member, etc.
        """
        logger.info("🧪 Chiamata a get_board_actions di TrelloAPI")
        return self._request('GET',
                             f"/boards/{board_id}/actions",
                             params=filters)

    def get_card_actions(self,
                         card_id: str,
                         **filters) -> List[Dict]:
        """
        GET /cards/{card_id}/actions
        History degli eventi per una singola card.
        """
        logger.info("🧪 Chiamata a get_card_actions di TrelloAPI")
        return self._request('GET',
                             f"/cards/{card_id}/actions",
                             params=filters)

    # def set_card_cover_color(self, board_id, list_id, card_id, color='blue'):
    #     url = f"{self.BASE_URL}/cards/{card_id}"
    #     params = {
    #         'key': self.api_key,
    #         'token': self.token
    #     }
    #     body = body = {
    #         "cover": {
    #             "color": "blue",
    #             "brightness": "dark",
    #             "size": "normal"
    #         },
    #         "idBoard": board_id,
    #         "idList": list_id
    #     }
    #     r = requests.put(url, params=params, json=body)
    #     r.raise_for_status()
    #     return r.json()

    def set_card_cover_color(self, card_id, color=None, brightness='dark', size='normal', url=None, idattachment=None):
        """
        PUT /cards/{card_id}
        Imposta il colore di copertina di una card.

        :param card_id:
        :param color:
        :param brightness:
        :param size:
        :param url:
        :param idattachment:
        :return:
        """
        logger.info("🧪 Chiamata a set_card_cover_color di TrelloAPI")
        api_url = f"{self.BASE_URL}/cards/{card_id}"
        params = {
            'key': self.api_key,
            'token': self.token
        }
        body = {
            "cover": {
                "color": color,
                "brightness": brightness,
                "size": size,
                "url": url,
                "idAttachment": idattachment
            }
        }
        r = requests.put(api_url, params=params, json=body)
        r.raise_for_status()
        return r.json()

    def create_checklist_on_card(self, card_id, name, pos=0, idchecklistsource=None):
        """
        POST /cards/{card_id}/checklists
        Crea una checklist su una card.
        """
        logger.info("🧪 Chiamata a create_checklist_on_card di TrelloAPI")
        api_url = f"{self.BASE_URL}/checklists"

        query = {
            'idCard': card_id,
            'name': name,
            'pos': pos,
            'idChecklistSource': idchecklistsource,
            'key': self.api_key,
            'token': self.token
        }

        response = requests.request(
            "POST",
            api_url,
            params=query
        )

        return response.json()

    def get_checklists_on_card(self, chk_id):
        """
        GET /cards/{card_id}/checklists
        Restituisce le checklist di una card.
        """
        logger.info("🧪 Chiamata a get_checklists_on_card di TrelloAPI")
        api_url = f"{self.BASE_URL}/checklists/{chk_id}"

        query = {
            'key': self.api_key,
            'token': self.token
        }

        response = requests.request(
            "GET",
            api_url,
            params=query
        )

        return response.json()

    def add_item_to_checklist(self, checklist_id, name, pos='bottom', checked=False, due=None,
                              duereminder=None, idmember=None):
        """
        POST /checklists/{checklist_id}/checkItems
        Aggiunge un item a una checklist.
        """
        logger.info("🧪 Chiamata a add_item_to_checklist di TrelloAPI")
        logger.debug(f"🧪 add_item_to_checklist params: checklist_id={checklist_id}, name={name}, pos={pos}, "
                     f"checked={checked}, due={due}, duereminder={duereminder}, idmember={idmember}")
        api_url = f"{self.BASE_URL}/checklists/{checklist_id}/checkItems"

        query = {
            'name': name,
            'pos': pos,
            'checked': checked,
            'due': due,
            'dueReminder': duereminder,
            'idMember': idmember,
            'key': self.api_key,
            'token': self.token
        }

        response = requests.request(
            "POST",
            api_url,
            params=query
        )

        return response.json()
