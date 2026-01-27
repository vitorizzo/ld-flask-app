# tools/automation_dispatcher.py
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from models import Automation, AutomationAction
from tools.executors.slack_executor import SlackExecutor
from tools.executors.trello_executor import TrelloExecutor
from tools.log_utils import get_logger

logger = get_logger("automation_dispatcher", level=logging.INFO)


class AutomationDispatcher:
    """
    Dispatcher cross-app v2:
    - riceve evento normalizzato
    - trova automations compatibili
    - applica filtri trigger_config (quando previsti)
    - esegue actions ordinate delegando agli executor app-specifici
    """

    def __init__(self) -> None:
        self._executors = {
            SlackExecutor.app_name: SlackExecutor(),
            TrelloExecutor.app_name: TrelloExecutor(),
        }

    # ----------------------------
    # Helpers: trigger config match
    # ----------------------------
    @staticmethod
    def _as_list(val: Any) -> List[str]:
        """
        Supporta:
        - "" / None -> []
        - "a,b,c" -> ["a","b","c"]
        - ["a","b"] -> ["a","b"]
        - "singolo" -> ["singolo"]
        """
        if val is None:
            return []
        if isinstance(val, list):
            out = []
            for x in val:
                s = str(x).strip()
                if s:
                    out.append(s)
            return out
        s = str(val).strip()
        if not s:
            return []
        if "," in s:
            return [p.strip() for p in s.split(",") if p.strip()]
        return [s]

    @staticmethod
    def _extract_slack_channel(payload: Dict[str, Any]) -> str:
        # prova chiavi comuni in payload normalizzato o grezzo
        for key in ("channel_name", "channel", "channel_id"):
            v = payload.get(key)
            if v:
                return str(v).strip()
        ev = payload.get("event") or {}
        if isinstance(ev, dict):
            v = ev.get("channel")
            if v:
                return str(v).strip()
        return ""

    @staticmethod
    def _extract_slack_text(payload: Dict[str, Any]) -> str:
        for key in ("text", "message", "body"):
            v = payload.get(key)
            if v:
                return str(v)
        ev = payload.get("event") or {}
        if isinstance(ev, dict):
            v = ev.get("text")
            if v:
                return str(v)
        return ""

    @staticmethod
    def _as_str_list(val: Any) -> List[str]:
        """
        Supporta:
        - None / "" -> []
        - "a,b,c" -> ["a","b","c"]
        - ["a","b"] -> ["a","b"]
        """
        if val is None:
            return []
        if isinstance(val, list):
            out = []
            for x in val:
                s = str(x).strip()
                if s:
                    out.append(s)
            return out

        s = str(val).strip()
        if not s:
            return []
        if "," in s:
            return [p.strip() for p in s.split(",") if p.strip()]
        return [s]

    @classmethod
    def _extract_channel_ids(cls, channels_cfg: Any) -> List[str]:
        """
        channels_cfg supportato:
        - [{"id":"C123","label":"test-ldapp"}, ...]
        - ["C123","C456"]
        - "C123,C456"
        """
        ids: List[str] = []
        if channels_cfg is None:
            return ids

        if isinstance(channels_cfg, list):
            for item in channels_cfg:
                if isinstance(item, dict):
                    cid = str(item.get("id") or "").strip()
                    if cid:
                        ids.append(cid)
                else:
                    s = str(item).strip()
                    if s:
                        ids.append(s)
            return ids

        # string/altro
        return cls._as_str_list(channels_cfg)

    @classmethod
    def _match_slack_message_channels(cls, trigger_config: Optional[Dict[str, Any]], payload: Dict[str, Any]) -> bool:
        """
        trigger_config (nuovo):
        - channels: [] | [{"id":"C0..","label":"test-ldapp"}, ...] | ["C0..","C1.."]
        - keywords: [] | ["ordine","urgent"]  (case-insensitive, contains)
        Regole:
        - se channels mancante o vuoto -> match su tutti i canali
        - se keywords mancante o vuoto -> match senza keyword
        """
        cfg = trigger_config or {}

        channel_ids = [c.strip() for c in cls._extract_channel_ids(cfg.get("channels")) if str(c).strip()]
        keywords = [k.lower() for k in cls._as_str_list(cfg.get("keywords"))]

        channel = cls._extract_slack_channel(payload).strip()
        text = cls._extract_slack_text(payload)
        text_l = text.lower()

        # filtro canale
        if channel_ids:
            if not channel:
                return False
            if channel not in channel_ids:
                return False

        # filtro keywords (OR)
        if keywords:
            if not text:
                return False
            if not any(k in text_l for k in keywords):
                return False

        return True

    def dispatch(self, event: Dict[str, Any]) -> int:
        """
        event: {
          "app": "slack"|"trello",
          "trigger": str|list[str],
          "connection_id": int,
          "payload": dict
        }
        return: numero actions eseguite (best effort)
        """
        app = (event.get("app") or "").strip()
        trigger = event.get("trigger")
        conn_id = event.get("connection_id")
        payload = event.get("payload") or {}

        if not app or not conn_id or not trigger:
            logger.warning("[V2][SKIP] missing app/connection_id/trigger event=%s", event)
            return 0

        triggers: List[str] = trigger if isinstance(trigger, list) else [trigger]

        automations = (
            Automation.query
            .filter(
                Automation.enabled.is_(True),
                Automation.trigger_app == app,
                Automation.trigger_connection == conn_id,
                Automation.trigger_type.in_(triggers),
            )
            .all()
        )

        if not automations:
            logger.info("[V2][NO_MATCH] app=%s conn=%s triggers=%s", app, conn_id, triggers)
            return 0

        executed = 0

        for a in automations:
            # Applica filtri specifici per trigger (oggi: Slack message.channels)
            if app == "slack" and a.trigger_type == "message.channels":
                if not self._match_slack_message_channels(a.trigger_config, payload):
                    logger.info(
                        "[V2][FILTER_SKIP] automation_id=%s trigger=message.channels cfg=%s",
                        a.id, a.trigger_config
                    )
                    continue

            actions = (
                AutomationAction.query
                .filter(
                    AutomationAction.automation_id == a.id,
                    AutomationAction.enabled.is_(True),
                )
                .order_by(AutomationAction.order_index.asc())
                .all()
            )

            logger.info("[V2][MATCH] automation_id=%s actions=%s", a.id, len(actions))

            for act in actions:
                ex = self._executors.get((act.action_app or "").strip())
                if not ex:
                    logger.warning("[V2][NO_EXECUTOR] action_app=%s action_id=%s", act.action_app, act.id)
                    continue

                ctx_for_action = payload

                # Se l'azione è Slack e il payload arriva da Trello, crea un ctx compatibile per i template
                if ex.app_name == "slack" and app == "trello":
                    try:
                        a0 = (payload or {}).get("action", {}) or {}
                        data = a0.get("data", {}) or {}
                        member = (payload or {}).get("memberCreator", {}) or a0.get("memberCreator", {}) or {}
                        display = a0.get("display", {}) or {}
                        ctx_for_action = {
                            "user": member.get("fullName") or member.get("username") or "",
                            "card": data.get("card") or {},
                            "board": data.get("board") or {},
                            "listbefore": data.get("listBefore") or {},
                            "listafter": data.get("listAfter") or {},
                            "trigger": a0.get("type") or "",
                            "raw": payload,
                            "display": display,
                        }
                    except Exception:
                        logger.exception("[V2][CTX] trello->slack ctx build failed")
                        ctx_for_action = payload

                try:
                    ex.execute(act.action_type, act.action_config or {}, ctx_for_action)
                    executed += 1
                except Exception:
                    logger.exception("[V2][ACTION_FAIL] automation_id=%s action_id=%s", a.id, act.id)

        return executed
