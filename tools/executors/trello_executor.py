# tools/executors/trello_executor.py
from __future__ import annotations

from typing import Any, Dict
import logging
from jinja2 import Template

from tools.executors.base import BaseExecutor
from tools.log_utils import get_logger

logger = get_logger("trello_executor", level=logging.INFO)


class TrelloExecutor(BaseExecutor):
    app_name = "trello"

    def _render(self, tpl: str, ctx: Dict[str, Any]) -> str:
        return Template(tpl or "").render(**(ctx or {}))

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

        cfg = config or {}
        payload = ctx or {}

        match action_type:
            case "addComment":
                # riuso diretto della funzione legacy
                return comment_from_to(cfg, payload)

            case "createCard":
                # cfg: { list_id, name, desc? }  (board_id ignorato volutamente)
                list_id = (cfg.get("list_id") or "").strip()
                name_tpl = cfg.get("name") or ""
                desc_tpl = cfg.get("desc") or ""

                if not list_id:
                    logger.warning("[V2][TRELLO] createCard skipped: missing list_id cfg=%s", cfg)
                    return None

                name = self._render(name_tpl, payload).strip()
                desc = self._render(desc_tpl, payload).strip()

                if not name:
                    logger.warning("[V2][TRELLO] createCard skipped: empty name after render cfg=%s", cfg)
                    return None

                return t.create_card(list_id=list_id, name=name, desc=desc)

            case _:
                logger.warning("Azione non ancora codificata: %s", action_type)
                return None
