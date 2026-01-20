# tools/executors/slack_executor.py
from __future__ import annotations

from typing import Any, Dict

from tools.executors.base import BaseExecutor


class SlackExecutor(BaseExecutor):
    app_name = "slack"

    def __init__(self, *, processor=None) -> None:
        if processor is None:
            from tools.slack_processor import SlackProcessor  # lazy import
            processor = SlackProcessor()
        self._processor = processor

    def execute(self, action_type: str, config: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """
        Adapter simmetrico: converte una singola action nel formato atteso da SlackProcessor.execute_actions().
        """
        actions = [{
            "action_type": action_type,
            "config_json": config or {},
        }]
        return self._processor.execute_actions(actions, ctx or {})
