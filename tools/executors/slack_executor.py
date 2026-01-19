# tools/executors/slack_executor.py
from __future__ import annotations

from typing import Any, Dict

from tools.executors.base import BaseExecutor
from tools.slack_processor import SlackProcessor


class SlackExecutor(BaseExecutor):
    app_name = "slack"

    def __init__(self, *, processor: SlackProcessor | None = None) -> None:
        # Permette injection nei test; in runtime usa quello standard.
        self._processor = processor or SlackProcessor()

    def execute(self, action_type: str, config: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """
        Adapter simmetrico: converte una singola action nel formato atteso da SlackProcessor.execute_actions().
        """
        actions = [{
            "action_type": action_type,
            "config_json": config or {},
        }]
        return self._processor.execute_actions(actions, ctx or {})
