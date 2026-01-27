# tools/slack_processor.py
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from flask import current_app
from jinja2 import Template

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

    def _render(self, tpl: str, ctx: dict) -> str:
        return Template(tpl or "").render(**ctx)

    def execute_actions(self, actions: list[dict], ctx: dict) -> None:
        api = self._get_api()

        for act in actions:
            action_type = act.get("action_type")
            cfg = act.get("config_json") or {}

            match action_type:
                case "addReaction":
                    # cfg: { reaction }
                    reaction = (cfg.get("reaction") or "eyes").strip()

                    # timestamp+channel dipendono dal trigger
                    ch = ctx.get("channel") or ctx.get("item_channel") or ""
                    ts = ctx.get("ts") or ctx.get("item_ts") or ""

                    if ch and ts:
                        api.add_reaction(channel=ch, timestamp=ts, name=reaction)
                        logger.info("[SLACK][ACTION] addReaction ok: %s %s %s", reaction, ch, ts)
                    else:
                        logger.warning("[SLACK][ACTION] addReaction skipped: missing channel/ts ctx=%s", ctx)

                case "sendMessage":
                    # cfg: { channel, message }
                    channel = (cfg.get("channel") or "").strip()
                    message_tpl = cfg.get("message") or ""
                    text = self._render(message_tpl, ctx)

                    if channel and text:
                        api.send_message(channel=channel, text=text)
                        logger.info("[SLACK][ACTION] sendMessage ok: %s", channel)
                    else:
                        logger.warning("[SLACK][ACTION] sendMessage skipped: missing channel/text cfg=%s", cfg)

                case _:
                    logger.warning("[SLACK][ACTION] type non riconosciuto: %s", action_type)

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
    def dispatch_event(self, event_type: str, event: dict, *, team_id: str | None = None):
        """
        Entry point unico per TUTTI gli eventi Slack.
        - Normalizza
        - Logga
        - risolve actions e le esegue
        """
        if not event_type:
            logger.warning("dispatch_event chiamato senza event_type")
            return None

        normalizer = {
            "message": self._normalize_message,
            "reaction_added": self._normalize_reaction_added,
        }

        handler = normalizer.get(event_type)
        if not handler:
            logger.info(
                "[SLACK][IGNORED] event_type=%s payload_keys=%s",
                event_type,
                list(event.keys())
            )
            return None

        normalized = handler(event)
        if not normalized:
            logger.warning("[SLACK][NORMALIZE_FAIL] event_type=%s", event_type)
            return None

        logger.info(
            "[SLACK][EVENT] trigger=%s data=%s",
            normalized["trigger"],
            normalized["data"]
        )

        # filter/search actions
        conn_id = None

        if self.connection and getattr(self.connection, "id", None):
            conn_id = self.connection.id
        elif team_id:
            conn = SlackConnection.query.filter_by(team_id=team_id).first()
            conn_id = conn.id if conn else None

        if not conn_id:
            logger.warning("[SLACK][NO_CONN] cannot find connection for event (team_id=%s)", team_id)
            return normalized

        # ============================================================
        # V2 — Cross-app automations (parallelo al legacy)
        # ============================================================
        try:
            from tools.automation_dispatcher import AutomationDispatcher
            dispatcher = AutomationDispatcher()
            dispatcher.dispatch({
                "app": "slack",
                "trigger": normalized["trigger"],
                "connection_id": conn_id,
                "payload": normalized["data"],
            })
        except Exception:
            logger.exception("[V2][SLACK] dispatcher failed")

        actions = self.find_actions_for_trigger(conn_id, normalized["trigger"])
        self.execute_actions(actions, normalized["data"])

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
        Slack message (pubblici, privati, DM, ecc.)
        Normalizziamo tutto su trigger unico "message".
        """
        # ignora messaggi "speciali" (bot_message, message_changed, ecc.)
        if event.get("subtype"):
            return None

        return {
            "trigger": "message",
            "data": {
                "channel": event.get("channel"),
                "channel_type": event.get("channel_type"),  # channel | group | im | mpim (se presente)
                "user": event.get("user"),
                "ts": event.get("ts"),
                "text": event.get("text") or "",
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
