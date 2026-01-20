# tools/executors/trello_executor.py
from __future__ import annotations

from typing import Any, Dict

from tools.executors.base import BaseExecutor


class TrelloExecutor(BaseExecutor):
    app_name = "trello"

    def execute(self, action_type: str, config: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
        """
        Executor Trello simmetrico a SlackExecutor.
        Riusa ESATTAMENTE la logica legacy già esistente:
        - get_trello() per l'API
        - mapping action_type → comportamento già implementato
        """
        from tools.processor import get_trello, comment_from_to
        t = get_trello()
        if not t:
            return None

        match action_type:
            case "addComment":
                # riuso diretto della funzione legacy
                return comment_from_to(config or {}, ctx or {})
            case _:
                # fallback: nessuna azione riconosciuta
                return None
