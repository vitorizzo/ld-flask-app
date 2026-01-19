# tools/executors/base.py
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseExecutor(ABC):
    """
    Interfaccia comune per tutti gli executor (Slack, Trello, future app).
    Il dispatcher userà SOLO questa API.
    """
    app_name: str  # es: "slack", "trello"

    @abstractmethod
    def execute(self, action_type: str, config: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """
        Esegue una singola action.
        - action_type: string capability (es. "sendMessage", "addComment")
        - config: config_json dell'action (dict)
        - ctx: payload normalizzato dell'evento/trigger (dict)
        """
        raise NotImplementedError
