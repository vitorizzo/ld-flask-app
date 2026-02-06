# tools/slack_processor.py
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, time
from sqlalchemy import func
from typing import Any, Dict, Optional

from flask import current_app
from jinja2 import Template

from models import SlackConnection, SlackOrder, SlackOrderEvent, DeliveryRoute
from tools.log_utils import get_logger
from tools.slack_api import SlackAPI, SlackAPIConfig
from extensions import db

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

    _STATUS_RANK = {"acquisito": 10, "listato": 20, "controllato": 30, "evaso": 40}
    _REACTION_TO_STATUS = {
        "white_check_mark": "listato",
        "cactus": "controllato",
        "100": "evaso",
    }

    _ISSUE_KEYWORDS = [
        "manca", "mancano", "non c", "non c'", "finito", "anomalia", "sostitu",
        "rotto", "errore", "vuoto", "rimasto", "non trovato",
    ]

    _NOTE_KEYWORDS = [
        "subito", "domani", "pomeriggio", "stamattina", "stasera",
        "passa", "porto", "portare", "scontrino", "fattura", "preso",
    ]

    def _normalize_customer_key(self, s: str) -> str:
        s = (s or "").strip().lower()
        s = re.sub(r"[^\w\s]", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        # rimuovi suffissi finali: numeri / bis / tris / ter / ordinale
        s = re.sub(r"\s+(bis|tris|ter|ordinale)\s*$", "", s).strip()
        s = re.sub(r"\s+\d+\s*$", "", s).strip()
        return s

    def _extract_customer_display(self, text: str) -> str:
        lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
        if not lines:
            return ""

        first = lines[0].strip()

        # Caso "Aggiunta <cliente>"
        m = re.match(r"(?i)^\s*aggiunta\s+(.+?)\s*$", first)
        if m:
            return m.group(1).strip()

        # Caso "<cliente> aggiunta" / "<cliente> aggiunta 2" / "<cliente> aggiunta bis"
        m = re.match(r"(?i)^\s*(.+?)\s+aggiunta(?:\s+(\d+|bis|tris|ter))?\s*$", first)
        if m:
            return m.group(1).strip()

        lower = first.lower()

        # Se prima riga contiene cliente + note, taglia alla prima keyword nota
        cut_pos = None
        for kw in self._NOTE_KEYWORDS:
            idx = lower.find(f" {kw}")
            if idx != -1:
                cut_pos = idx if cut_pos is None else min(cut_pos, idx)

        if cut_pos is not None:
            candidate = first[:cut_pos].strip()
            return candidate if candidate else first

        return first

    def _is_reply(self, ts: str | None, thread_ts: str | None) -> bool:
        return bool(thread_ts) and bool(ts) and thread_ts != ts

    def _detect_issue(self, text: str) -> bool:
        t = (text or "").lower()
        return any(k in t for k in self._ISSUE_KEYWORDS)

    def _compute_next_delivery_dt(self, base_dt: datetime, route: DeliveryRoute) -> datetime:
        """
        base_dt: datetime del messaggio (timezone naive; coerente col resto dell'app)
        route.default_weekday: 0=consegna immediata 1=lun ... 7=dom
        route.default_time: time
        """
        target_weekday = int(route.default_weekday)
        target_time = route.default_time

        if target_weekday == 0:
            candidate_dt = base_dt
        else:
            # data candidata: stesso giorno della settimana nella stessa settimana di base_dt
            days_ahead = (target_weekday - 1 - base_dt.weekday()) % 7
            candidate_date = (base_dt + timedelta(days=days_ahead)).date()
            candidate_dt = datetime.combine(candidate_date, target_time)

            # se cade oggi ma è già passato -> settimana prossima
            if candidate_dt <= base_dt:
                candidate_dt = candidate_dt + timedelta(days=7)

        return candidate_dt

    def _get_route_for_channel(self, channel_id: str) -> DeliveryRoute | None:
        return DeliveryRoute.query.filter_by(slack_channel_id=channel_id, is_active=True).first()

    def _find_open_order(self, channel_id: str, customer_key: str, order_date) -> SlackOrder | None:
        return (
            SlackOrder.query
            .filter(
                SlackOrder.slack_channel_id == channel_id,
                SlackOrder.customer_key == customer_key,
                SlackOrder.order_date == order_date,
                SlackOrder.status != "evaso",
            )
            .order_by(SlackOrder.id.desc())
            .first()
        )

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

    def _orders_side_effect(self, normalized: dict) -> None:
        trigger = normalized.get("trigger")
        data = normalized.get("data") or {}

        if trigger == "reaction_added":
            reaction = data.get("reaction")
            channel_id = data.get("item_channel")
            item_ts = data.get("item_ts")
            user = data.get("user")

            if not reaction or not channel_id or not item_ts:
                return

            new_status = self._REACTION_TO_STATUS.get(reaction)
            if not new_status:
                return  # reaction non gestita per ordini

            # Trova ordine: reaction di solito è sul messaggio root (ts=root_ts)
            order = (
                SlackOrder.query
                .filter(
                    SlackOrder.slack_channel_id == channel_id,
                    SlackOrder.slack_thread_ts == item_ts,
                )
                .order_by(SlackOrder.id.desc())
                .first()
            )

            # fallback: nel caso raro in cui thread_ts non coincida, prova su slack_message_ts
            if not order:
                order = (
                    SlackOrder.query
                    .filter(
                        SlackOrder.slack_channel_id == channel_id,
                        SlackOrder.slack_message_ts == item_ts,
                    )
                    .order_by(SlackOrder.id.desc())
                    .first()
                )

            if not order:
                return

            # registra sempre la reaction come evento
            db.session.add(SlackOrderEvent(
                order_id=order.id,
                type="reaction",
                payload={
                    "reaction": reaction,
                    "user": user,
                    "item_ts": item_ts,
                    "channel": channel_id,
                },
            ))

            current_rank = self._STATUS_RANK.get(order.status, 0)
            new_rank = self._STATUS_RANK.get(new_status, 0)

            # Solo upgrade
            if new_rank > current_rank:
                old_status = order.status
                order.status = new_status

                if new_status == "evaso":
                    order.closed_at = datetime.utcnow()

                db.session.add(SlackOrderEvent(
                    order_id=order.id,
                    type="status_change",
                    payload={
                        "from": old_status,
                        "to": new_status,
                        "via": "reaction",
                        "reaction": reaction,
                        "user": user,
                        "item_ts": item_ts,
                    },
                ))

            db.session.commit()
            return

        if trigger != "message":
            return

        channel_id = data.get("channel")
        ts = data.get("ts")
        thread_ts = data.get("thread_ts")
        text = (data.get("text") or "").strip()

        if not channel_id or not ts:
            return

        # Reply -> NOTE su ordine esistente (thread root = thread_ts)
        if self._is_reply(ts, thread_ts):
            root_ts = thread_ts
            order = SlackOrder.query.filter_by(slack_channel_id=channel_id, slack_thread_ts=root_ts).first()
            if not order:
                return

            ev = SlackOrderEvent(
                order_id=order.id,
                type="note",
                payload={
                    "user": data.get("user"),
                    "ts": ts,
                    "text": text,
                },
            )
            db.session.add(ev)

            if self._detect_issue(text):
                order.has_issues = True

            db.session.commit()
            return

        # Root message -> crea SEMPRE un nuovo ordine
        customer_display = self._extract_customer_display(text)
        if not customer_display:
            return

        customer_key = self._normalize_customer_key(customer_display)
        if not customer_key:
            return

        # data ordine: "oggi" basato su timestamp Slack
        try:
            ts_seconds = float(ts)
            created_dt = datetime.fromtimestamp(ts_seconds)
        except Exception:
            created_dt = datetime.utcnow()

        order_date = created_dt.date()

        route = self._get_route_for_channel(channel_id)

        # Crea sempre un nuovo SlackOrder (anche se stesso cliente/stesso giorno)
        order = SlackOrder(
            route_id=route.id if route else None,
            slack_channel_id=channel_id,
            customer_display=customer_display,
            customer_key=customer_key,
            order_date=order_date,
            planned_delivery_at=self._compute_next_delivery_dt(created_dt, route) if route else None,
            status="acquisito",
            raw_text=text,
            slack_message_ts=ts,
            slack_thread_ts=ts,
            has_issues=False,
        )

        db.session.add(order)
        db.session.flush()  # per ottenere order.id

        db.session.add(SlackOrderEvent(
            order_id=order.id,
            type="created",
            payload={"ts": ts, "user": data.get("user"), "text": text},
        ))

        db.session.commit()
        return

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

        try:
            self._orders_side_effect(normalized)
        except Exception:
            # non deve mai rompere Automations V2
            self.logger.exception("orders side-effect failed")

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
                "thread_ts": event.get("thread_ts"),  # <-- AGGIUNGI QUESTO
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
