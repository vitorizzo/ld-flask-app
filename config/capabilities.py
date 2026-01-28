# config/capabilities.py
"""
Capability registry (server-side) per configurare Trigger / Action / Placeholders / Field defs
senza hardcodare valori nel JS.

Uso previsto:
- routes/trello.py espone /trello/capabilities -> CAPABILITIES["trello"]
- routes/slack.py (in futuro) espone /slack/capabilities -> CAPABILITIES["slack"]
- il frontend usa questi dati per popolare tendine e costruire i campi dinamici.
"""

from __future__ import annotations

from typing import Any, Dict, List

# Nota: i campi sono pensati per essere serializzabili in JSON senza trasformazioni.
# - triggers/actions: list di {value,label}
# - placeholders: list di stringhe
# - trigger_fields/action_fields: dict[str, list[field_def]]
#   field_def: {name,label,type,required,placeholder?,help?,options?}
#
# type supportati lato frontend (renderFields): "text", "email", "textarea", "number", "hidden", "select"
# (Se vuoi "select" basta che il frontend gestisca field.type === "select" e usi field.options.)

CAPABILITIES: Dict[str, Dict[str, Any]] = {
    # ============================================================
    # TRELLO
    # ============================================================
    "trello": {
        "triggers": [
            {"value": "copyCard", "label": "Copia card"},
            {"value": "createCard", "label": "Creazione card"},
            {"value": "updateCard", "label": "Modifica card"},
            {"value": "moveCard", "label": "Spostamento card"},
            {"value": "commentCard", "label": "Commento card"},
            {"value": "moveToList", "label": "Spostamento in lista specifica"},
            {"value": "addLabelToCard", "label": "Etichetta aggiunta alla card"},
        ],
        "actions": [
            {"value": "sendEmail", "label": "Invia email"},
            {"value": "addComment", "label": "Aggiungi commento"},
            {"value": "mirrorCard", "label": "Copia/Mirror card"},
            {"value": "customizeCard", "label": "Personalizza card"},
            {"value": "sendSlackMessage", "label": "Invia messaggio Slack"},
            {"value": "serviceComments", "label": "Commenti di servizio"},
            {"value": "createCard", "label": "Crea card"},
        ],
        "placeholders": [
            "{{user}}",
            "{{card.name}}",
            "{{card.id}}",
            "{{card.url}}",
            "{{listbefore.name}}",
            "{{listafter.name}}",
            "{{list.name}}",
            "{{list.id}}",
            "{{board.name}}",
            "{{board.id}}",
            "{{comment.text}}",
        ],

        # Campi richiesti/mostrati in base al trigger scelto
        "trigger_fields": {
            # Nota: se vuoi usare tendine board+list anche qui, lo gestisci nel JS
            # sostituendo l'input list_id con i selettori e salvando sempre "list_id".
            "moveToList": [
                {
                    "name": "list_id",
                    "label": "ID Lista di Destinazione",
                    "type": "text",
                    "required": True,
                    "placeholder": "641037fdad7b4d617668df55",
                }
            ],
        },

        # Campi richiesti/mostrati in base all'action scelta
        "action_fields": {
            "sendEmail": [
                {"name": "to", "label": "To", "type": "email", "required": True},
                {"name": "subject", "label": "Subject", "type": "text", "required": True},
                {"name": "body", "label": "Body", "type": "textarea", "required": True},
            ],
            "addComment": [
                {
                    "name": "comment",
                    "label": "Commento",
                    "type": "textarea",
                    "required": True,
                    "placeholder": "Esempio: La card {{card.name}} è stata spostata da {{user}}",
                }
            ],
            "mirrorCard": [
                # NB: questi due nel JS verranno “enhanced” a select board/list,
                # ma salvano comunque in config_json target_board_id/target_list_id.
                {"name": "target_board_id", "label": "Board ID destinazione", "type": "text", "required": True},
                {"name": "target_list_id", "label": "Lista destinazione", "type": "text", "required": True},
            ],
            "sendSlackMessage": [
                {"name": "channel", "label": "Canale Slack", "type": "text", "required": True, "placeholder": "#nome-canale"},
                {
                    "name": "message",
                    "label": "Messaggio",
                    "type": "textarea",
                    "required": True,
                    "placeholder": "Esempio: La card {{card.name}} è stata spostata da {{user}}",
                },
            ],
            # Le altre action restano “capabilities-only” finché non definisci i campi
            # o non implementi la loro UI/processor.
            "customizeCard": [],
            "serviceComments": [],
        },
    },

    # ============================================================
    # SLACK (minimo, già pronto per espansione)
    # ============================================================
    "slack": {
        "triggers": [
            {"value": "message", "label": "Messaggio in canale"},
            {"value": "reaction_added", "label": "Reaction aggiunta"},
        ],
        "actions": [
            {"value": "addReaction", "label": "Aggiungi reaction"},
            {"value": "sendMessage", "label": "Invia messaggio"},
        ],
        "placeholders": [
            "{{user}}",
            "{{channel}}",
            "{{item_ts}}",
            "{{text}}",
            "{{reaction}}",
        ],
        "trigger_fields": {
            "message": [],
            "reaction_added": [],
        },
        "action_fields": {
            "addReaction": [
                {
                    "label": "Reazione",
                    "name": "reaction",
                    "type": "text",
                    "placeholder": "eyes",
                    "required": True,
                }
            ],
            "sendMessage": [
                {
                    "label": "Canale",
                    "name": "channel",
                    "type": "text",
                    "placeholder": "#general",
                    "required": True,
                },
                {
                    "label": "Messaggio",
                    "name": "message",
                    "type": "textarea",
                    "placeholder": "Testo del messaggio",
                    "required": True,
                }
            ]
        },
    },
}


def get_capabilities(context: str) -> Dict[str, Any]:
    """
    Helper opzionale per validare il contesto.
    """
    if context not in CAPABILITIES:
        raise KeyError(f"Context non supportato: {context}")
    return CAPABILITIES[context]
