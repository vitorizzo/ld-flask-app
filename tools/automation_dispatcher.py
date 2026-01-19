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

                try:
                    ex.execute(act.action_type, act.action_config or {}, payload)
                    executed += 1
                except Exception:
                    logger.exception("[V2][ACTION_FAIL] automation_id=%s action_id=%s", a.id, act.id)

        return executed
