# tools/slack_processor.py
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from flask import current_app

from models import SlackConnection
from tools.log_utils import get_logger
from tools.slack_api import SlackAPI, SlackAPIConfig

logger = get_logger("slack_processor", level=logging.INFO)


class SlackProcessor:
    """
    Orchestratore Slack (coerente con la struttura Trello):
    - legge config da current_app.config
    - crea SlackAPI (slack_sdk) in modo lazy
    - espone metodi di alto livello usabili da routes e, in futuro, da Celery
    """

    def __init__(self, connection=None) -> None:
        """
        connection: opzionale (in futuro SlackConnection)
        """
        self._api: Optional[SlackAPI] = None
        self.connection = connection

    def _get_api(self) -> SlackAPI:
        if self._api is not None:
            return self._api

        bot_token = current_app.config.get("SLACK_BOT_TOKEN", "") or ""
        if not bot_token:
            raise RuntimeError("SLACK_BOT_TOKEN mancante in current_app.config")

        cfg = SlackAPIConfig(bot_token=bot_token)
        self._api = SlackAPI(cfg)
        return self._api

    def auth_test(self) -> Dict[str, Any]:
        """
        Verifica che il bot token sia valido e l'app sia installata nel workspace.
        """
        logger.info("SlackProcessor.auth_test()")
        api = self._get_api()
        return api.auth_test()

    def handle_message_channels(self, channel: str, ts: str, *, reaction: str = "eyes") -> bool:
        """
        Handler minimale per message.channels:
        - aggiunge una reaction al messaggio (default :eyes:)
        - ritorna True se ok, False se fallisce (logga l’errore)
        """
        try:
            api = self._get_api()
            api.add_reaction(channel=channel, timestamp=ts, name=reaction)
            logger.info("Reaction aggiunta: channel=%s ts=%s reaction=%s", channel, ts, reaction)
            return True
        except Exception:
            logger.exception("Errore in handle_message_channels")
            return False

    # ============================================================
    # B.1 — Dispatcher centrale eventi Slack
    # ============================================================
    def dispatch_event(self, event_type: str, payload: dict):
        """
        Entry point unico per TUTTI gli eventi Slack.
        - Normalizza
        - Logga
        - (in futuro) risolve actions
        """
        if not event_type:
            logger.warning("dispatch_event chiamato senza event_type")
            return

        normalizer = {
            "message": self._normalize_message,
            "reaction_added": self._normalize_reaction_added,
        }

        handler = normalizer.get(event_type)

        if not handler:
            logger.info(
                "[SLACK][IGNORED] event_type=%s payload_keys=%s",
                event_type,
                list(payload.keys())
            )
            return

        normalized = handler(payload)

        if not normalized:
            logger.warning(
                "[SLACK][NORMALIZE_FAIL] event_type=%s",
                event_type
            )
            return

        logger.info(
            "[SLACK][EVENT] trigger=%s data=%s",
            normalized["trigger"],
            normalized["data"]
        )

        # filter/search actions
        conn_id = None
        try:
            conn_id = (self.connection.id
                       if self.connection and getattr(self.connection, "id", None)
                       else payload.get("team_id") and
                       SlackConnection.query.filter_by(team_id=payload.get("team_id")).first().id
                       )
        except Exception:
            conn_id = None

        if conn_id:
            actions = self.find_actions_for_trigger(conn_id, normalized["trigger"])

            # B.2: esegui action reali (per ora solo addReaction su message.channels)
            for a in actions:
                try:
                    if a.get("action_type") == "addReaction" and normalized["trigger"] == "message.channels":
                        name = (a.get("config_json") or {}).get("name") or "thumbsup"

                        channel = (normalized["data"] or {}).get("channel") or ""
                        ts = (normalized["data"] or {}).get("ts") or ""

                        if channel and ts:
                            api = self._get_api()
                            api.add_reaction(channel=channel, timestamp=ts, name=name)
                            logger.info("[SLACK][ACTION][OK] addReaction name=%s channel=%s ts=%s", name, channel, ts)
                        else:
                            logger.warning("[SLACK][ACTION][SKIP] addReaction missing channel/ts data=%s",
                                           normalized["data"])
                except Exception:
                    logger.exception("[SLACK][ACTION][ERR] action=%s", a)

        else:
            logger.warning("[SLACK][NO_CONN] cannot find connection for event")
        # STOP QUI — niente azioni reali (B.1 finisce qui)
        return normalized

    def find_actions_for_trigger(self, connection_id: int, trigger: str) -> list[dict]:
        """
        Carica tutte le SlackAction per questa connection_id
        che hanno lo stesso trigger_type.
        Ritorna lista di dict con action_type + config_json.
        """
        from models import SlackAction

        actions = (
            SlackAction.query
            .filter_by(connection_id=connection_id, trigger_type=trigger)
            .order_by(SlackAction.ordine.asc().nullslast())
            .all()
        )

        result = []
        for a in actions:
            result.append({
                "id": a.id,
                "action_type": a.action_type,
                "config_json": a.config_json,
                "ordine": a.ordine,
            })
        logger.info(
            "[SLACK][ACTIONS] found %d actions for trigger=%s conn_id=%s",
            len(result), trigger, connection_id
        )
        return result

    # ============================================================
    # Normalizzatori
    # ============================================================
    def _normalize_message(self, event: dict) -> dict | None:
        """
        Slack message.channels
        """
        if event.get("channel_type") != "channel":
            return None

        if event.get("subtype"):
            return None

        return {
            "trigger": "message.channels",
            "data": {
                "channel": event.get("channel"),
                "user": event.get("user"),
                "ts": event.get("ts"),
                "text": event.get("text"),
            }
        }

    def _normalize_reaction_added(self, event: dict) -> dict | None:
        """
        Slack reaction_added
        """
        item = event.get("item") or {}

        return {
            "trigger": "reaction_added",
            "data": {
                "reaction": event.get("reaction"),
                "user": event.get("user"),
                "item_channel": item.get("channel"),
                "item_ts": item.get("ts"),
            }
        }
