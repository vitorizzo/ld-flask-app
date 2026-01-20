# tools/automation_dispatcher.py
from __future__ import annotations

import logging
from typing import Any, Dict, List

from tools.log_utils import get_logger
from models import Automation, AutomationAction

from tools.executors.slack_executor import SlackExecutor
from tools.executors.trello_executor import TrelloExecutor

logger = get_logger("automation_dispatcher", level=logging.INFO)


class AutomationDispatcher:
    """
    Dispatcher cross-app v2:
    - riceve evento normalizzato
    - trova automations compatibili
    - esegue actions ordinate delegando agli executor app-specifici
    """

    def __init__(self) -> None:
        self._executors = {
            SlackExecutor.app_name: SlackExecutor(),
            TrelloExecutor.app_name: TrelloExecutor(),
        }

    def dispatch(self, event: Dict[str, Any]) -> int:
        """
        event:
          {
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
                        a = (payload or {}).get("action", {}) or {}
                        data = a.get("data", {}) or {}
                        member = (payload or {}).get("memberCreator", {}) or a.get("memberCreator", {}) or {}
                        display = a.get("display", {}) or {}

                        ctx_for_action = {
                            "user": member.get("fullName") or member.get("username") or "",
                            "card": data.get("card") or {},
                            "board": data.get("board") or {},
                            "listbefore": data.get("listBefore") or {},
                            "listafter": data.get("listAfter") or {},
                            "trigger": a.get("type") or "",
                            "raw": payload,  # fallback se serve
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
