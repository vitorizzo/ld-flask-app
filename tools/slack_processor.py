# tools/slack_processor.py
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from flask import current_app

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

    def __init__(self) -> None:
        self._api: Optional[SlackAPI] = None

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
