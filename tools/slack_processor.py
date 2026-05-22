# tools/slack_processor.py
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, time
from sqlalchemy import func
from typing import Any, Dict, Optional

from flask import current_app
from jinja2 import Template

from models import SlackConnection, SlackOrder, SlackOrderEvent, DeliveryRoute, DeliveryScheduleRule, OrderStatus, RouteOrderBoardEntry
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
        "manca",
        "mancano",
        "non c",
        "non c'",
        "finito",
        "anomalia",
        "sostitu",
        "rotto",
        "errore",
        "vuoto",
        "rimasto",
        "non trovato",
    ]

    _NOTE_KEYWORDS = [
        "subito",
        "domani",
        "domattina",
        "dopodomani",
        "pomeriggio",
        "stamattina",
        "stasera",
        "passa",
        "porto",
        "portare",
        "consegna",
        "consegnare",
        "consegnato",
        "consegnarlo",
        "ritiro",
        "ritirare",
        "per lun",
        "per mar",
        "per mer",
        "per gio",
        "per ven",
        "per sab",
        "per dom",
        "scontrino",
        "fattura",
        "preso",
    ]

    _WEEKDAY_ALIASES = {
        "lun": 0,
        "lunedì": 0,
        "lunedi": 0,
        "mar": 1,
        "martedì": 1,
        "martedi": 1,
        "mer": 2,
        "mercoledì": 2,
        "mercoledi": 2,
        "gio": 3,
        "giovedì": 3,
        "giovedi": 3,
        "ven": 4,
        "venerdì": 4,
        "venerdi": 4,
        "sab": 5,
        "sabato": 5,
        "dom": 6,
        "domenica": 6,
    }

    _DELIVERY_TIME_ALIASES = [
        (r"\b(?:all[' ]?apertura|apertura|appena apre|appena aprite)\b", time(9, 0), "apertura"),
        (r"\b(?:domattina|stamattina|mattina|in mattinata)\b", time(10, 0), "mattina"),
        (r"\b(?:mezzogiorno|pranzo|ora di pranzo)\b", time(12, 0), "pranzo"),
        (r"\b(?:pomeriggio|nel pomeriggio|primo pomeriggio)\b", time(16, 0), "pomeriggio"),
        (r"\b(?:sera|stasera|serata)\b", time(18, 0), "sera"),
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

        first = re.sub(r"[*_~`]+", "", lines[0].strip()).strip()

        # Caso "Aggiunta "
        m = re.match(r"(?i)^\s*aggiunta\s+(.+?)\s*$", first)
        if m:
            return m.group(1).strip()

        # Caso " aggiunta" / " aggiunta 2" / " aggiunta bis"
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

    def _delivery_time_for_route(self, route: DeliveryRoute | None, base_dt: datetime) -> time:
        if route and route.default_time:
            return route.default_time
        return time(hour=base_dt.hour, minute=base_dt.minute)

    def _extract_delivery_time_from_text(
        self,
        normalized: str,
        route: DeliveryRoute | None,
        base_dt: datetime,
    ) -> tuple[time, str]:
        explicit = re.search(
            r"\b(?:dopo\s+le|dopo\s+le\s+ore|dalle|alle|ore|h)\s*(\d{1,2})(?:[:.,](\d{2}))?\b|\b(\d{1,2})[:.](\d{2})\b",
            normalized,
        )
        if explicit:
            hour = int(explicit.group(1) or explicit.group(3))
            minute = int(explicit.group(2) or explicit.group(4) or 0)
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return time(hour, minute), explicit.group(0)

        for pattern, target_time, label in self._DELIVERY_TIME_ALIASES:
            if re.search(pattern, normalized):
                return target_time, label

        return self._delivery_time_for_route(route, base_dt), ""

    def _build_delivery_dt(
        self,
        base_dt: datetime,
        route: DeliveryRoute | None,
        target_date,
        target_time: time | None = None,
    ) -> datetime:
        return datetime.combine(target_date, target_time or self._delivery_time_for_route(route, base_dt))

    def _next_weekday_dt(self, base_dt: datetime, target_weekday: int, target_time: time) -> datetime:
        delivery_weekday = int(target_weekday)
        python_weekday = delivery_weekday - 1 if 1 <= delivery_weekday <= 7 else delivery_weekday
        days_ahead = (python_weekday - base_dt.weekday()) % 7
        candidate_date = (base_dt + timedelta(days=days_ahead)).date()
        candidate_dt = datetime.combine(candidate_date, target_time)
        if candidate_dt <= base_dt:
            candidate_dt = candidate_dt + timedelta(days=7)
        return candidate_dt

    def _compute_route_delivery_without_rules(self, base_dt: datetime, route: DeliveryRoute) -> datetime:
        target_weekday = int(route.default_weekday)
        target_time = route.default_time
        if target_weekday == 0:
            candidate_dt = datetime.combine(base_dt.date(), target_time)
            if candidate_dt <= base_dt:
                candidate_dt = candidate_dt + timedelta(days=1)
            return candidate_dt
        return self._next_weekday_dt(base_dt, target_weekday, target_time)

    def _week_index(self, value_date) -> int:
        iso = value_date.isocalendar()
        return int(iso.year) * 53 + int(iso.week)

    def _next_biweekly_dt(
        self,
        base_dt: datetime,
        target_weekday: int,
        target_time: time,
        anchor_date,
        end_date=None,
    ) -> datetime | None:
        anchor = anchor_date or base_dt.date()
        candidate = self._next_weekday_dt(base_dt, target_weekday, target_time)
        for _ in range(54):
            if (self._week_index(candidate.date()) - self._week_index(anchor)) % 2 == 0:
                if end_date and candidate.date() > end_date:
                    return None
                return candidate
            candidate = candidate + timedelta(days=7)
        return None

    def _schedule_candidate(
        self,
        base_dt: datetime,
        *,
        frequency: str,
        target_weekday: int,
        target_time: time,
        second_weekday: int | None = None,
        second_time: time | None = None,
        anchor_date=None,
        end_date=None,
    ) -> datetime | None:
        frequency = frequency or "weekly"

        if frequency == "biweekly":
            return self._next_biweekly_dt(base_dt, target_weekday, target_time, anchor_date, end_date=end_date)

        candidates = [self._next_weekday_dt(base_dt, target_weekday, target_time)]
        if frequency == "twice_weekly" and second_weekday and second_time:
            candidates.append(self._next_weekday_dt(base_dt, second_weekday, second_time))

        if end_date:
            candidates = [c for c in candidates if c.date() <= end_date]
        return min(candidates) if candidates else None

    def _apply_once_schedule_rule(self, route: DeliveryRoute, candidate_dt: datetime) -> datetime:
        rule = (
            DeliveryScheduleRule.query
            .filter_by(route_id=route.id, scope="once", is_active=True, source_date=candidate_dt.date())
            .order_by(DeliveryScheduleRule.id.desc())
            .first()
        )
        if not rule or not rule.target_date:
            return candidate_dt
        return datetime.combine(rule.target_date, rule.target_time or candidate_dt.time())

    def _period_schedule_candidate(self, base_dt: datetime, route: DeliveryRoute) -> datetime | None:
        today = base_dt.date()
        rules = (
            DeliveryScheduleRule.query
            .filter(
                DeliveryScheduleRule.route_id == route.id,
                DeliveryScheduleRule.scope == "period",
                DeliveryScheduleRule.is_active.is_(True),
                DeliveryScheduleRule.start_date.isnot(None),
                DeliveryScheduleRule.end_date.isnot(None),
                DeliveryScheduleRule.target_weekday.isnot(None),
                DeliveryScheduleRule.end_date >= today,
            )
            .order_by(DeliveryScheduleRule.start_date.desc(), DeliveryScheduleRule.id.desc())
            .all()
        )

        for rule in rules:
            anchor = base_dt
            if rule.start_date and rule.start_date > today:
                anchor = datetime.combine(rule.start_date, time.min)

            candidate = self._schedule_candidate(
                anchor,
                frequency=rule.frequency or "weekly",
                target_weekday=int(rule.target_weekday),
                target_time=rule.target_time,
                second_weekday=rule.second_weekday,
                second_time=rule.second_time,
                anchor_date=rule.start_date,
                end_date=rule.end_date,
            )
            if not candidate:
                continue
            while rule.start_date and candidate.date() < rule.start_date:
                candidate += timedelta(days=7)

            if rule.end_date and candidate.date() > rule.end_date:
                continue

            return candidate

        return None

    def _extract_delivery_dt_from_text(
        self,
        text: str,
        base_dt: datetime,
        route: DeliveryRoute | None,
    ) -> tuple[datetime | None, str]:
        """
        Estrae indicazioni semplici di consegna dal messaggio:
        - domani / dopodomani
        - per/consegna/consegnare + giorno settimana
        - per/consegna/consegnare + data dd/mm o dd-mm
        """
        raw = text or ""
        normalized = raw.lower()
        normalized = normalized.replace("’", "'")
        normalized = re.sub(r"[*_~`]+", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        target_time, time_hint = self._extract_delivery_time_from_text(normalized, route, base_dt)

        def _hint(*parts: str) -> str:
            return " ".join([p for p in parts if p]).strip()

        if re.search(r"\bdopodomani\b", normalized):
            target_date = (base_dt + timedelta(days=2)).date()
            return self._build_delivery_dt(base_dt, route, target_date, target_time), _hint("dopodomani", time_hint)

        if re.search(r"\b(?:domani|domattina)\b", normalized):
            target_date = (base_dt + timedelta(days=1)).date()
            return self._build_delivery_dt(base_dt, route, target_date, target_time), _hint("domani", time_hint)

        if re.search(r"\boggi\b|\bstamattina\b|\bstasera\b", normalized):
            target_dt = self._build_delivery_dt(base_dt, route, base_dt.date(), target_time)
            if target_dt <= base_dt and time_hint:
                target_dt = target_dt + timedelta(days=1)
            return target_dt, _hint("oggi", time_hint)

        date_match = re.search(
            r"\b(?:consegna(?:re)?|consegnare|per|entro|il)\s+(?:il\s+)?(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b",
            normalized,
        )
        if date_match:
            day = int(date_match.group(1))
            month = int(date_match.group(2))
            year_raw = date_match.group(3)
            year = int(year_raw) if year_raw else base_dt.year
            if year < 100:
                year += 2000
            try:
                target_dt = self._build_delivery_dt(base_dt, route, datetime(year, month, day).date(), target_time)
                if not year_raw and target_dt.date() < base_dt.date():
                    target_dt = self._build_delivery_dt(
                        base_dt,
                        route,
                        datetime(year + 1, month, day).date(),
                        target_time,
                    )
                return target_dt, _hint(date_match.group(0), time_hint)
            except ValueError:
                pass

        weekday_re = r"\b(?:consegna(?:re)?|consegnare|per|entro)\s+(?:il\s+)?(lun(?:edì|edi)?|mar(?:tedì|tedi)?|mer(?:coledì|coledi)?|gio(?:vedì|vedi)?|ven(?:erdì|erdi)?|sab(?:ato)?|dom(?:enica)?)\b"
        weekday_match = re.search(weekday_re, normalized)
        if weekday_match:
            token = weekday_match.group(1)
            target_weekday = self._WEEKDAY_ALIASES.get(token)
            if target_weekday is not None:
                days_ahead = (target_weekday - base_dt.weekday()) % 7
                target_date = (base_dt + timedelta(days=days_ahead)).date()
                target_dt = self._build_delivery_dt(base_dt, route, target_date, target_time)
                if target_dt <= base_dt:
                    target_dt = target_dt + timedelta(days=7)
                return target_dt, _hint(weekday_match.group(0), time_hint)

        weekday_day_re = r"\b(lun(?:edì|edi)?|mar(?:tedì|tedi)?|mer(?:coledì|coledi)?|gio(?:vedì|vedi)?|ven(?:erdì|erdi)?|sab(?:ato)?|dom(?:enica)?)\s+(\d{1,2})\b"
        weekday_day_matches = list(re.finditer(weekday_day_re, normalized))
        if weekday_day_matches:
            match = weekday_day_matches[-1]
            day = int(match.group(2))
            year = base_dt.year
            month = base_dt.month
            try:
                target_date = datetime(year, month, day).date()
                if target_date < base_dt.date():
                    if month == 12:
                        target_date = datetime(year + 1, 1, day).date()
                    else:
                        target_date = datetime(year, month + 1, day).date()
                target_dt = self._build_delivery_dt(base_dt, route, target_date, target_time)
                return target_dt, _hint(match.group(0), time_hint)
            except ValueError:
                pass

        if time_hint:
            if route:
                try:
                    default_dt = self._compute_next_delivery_dt(base_dt, route)
                except RuntimeError:
                    default_dt = self._compute_route_delivery_without_rules(base_dt, route)
                return datetime.combine(default_dt.date(), target_time), time_hint

            target_dt = datetime.combine(base_dt.date(), target_time)
            if target_dt <= base_dt:
                target_dt = target_dt + timedelta(days=1)
            return target_dt, time_hint

        return None, ""

    def _is_reply(self, ts: str | None, thread_ts: str | None) -> bool:
        return bool(thread_ts) and bool(ts) and thread_ts != ts

    def _detect_issue(self, text: str) -> bool:
        t = (text or "").lower()
        return any(k in t for k in self._ISSUE_KEYWORDS)

    def _extract_message_text(self, event: dict) -> str:
        """
        Slack mette la didascalia dei file_share in campi diversi a seconda
        del payload. Per gli ordini usiamo solo testo/caption reali.
        """
        candidates = [
            event.get("text"),
            (event.get("message") or {}).get("text"),
            (event.get("original_message") or {}).get("text"),
        ]
        for value in candidates:
            text = (value or "").strip()
            if text:
                return text
        return ""

    def _extract_file_attachments(self, event: dict) -> list[dict]:
        files = event.get("files")
        if not isinstance(files, list):
            files = (event.get("message") or {}).get("files")
        if not isinstance(files, list):
            return []

        attachments = []
        for f in files:
            if not isinstance(f, dict):
                continue

            file_id = (f.get("id") or "").strip()
            if not file_id:
                continue

            mimetype = (f.get("mimetype") or "").strip()
            filetype = (f.get("filetype") or "").strip()
            is_image = bool(
                mimetype.startswith("image/")
                or filetype in {"jpg", "jpeg", "png", "gif", "webp", "heic", "heif"}
                or any(f.get(k) for k in ("thumb_360", "thumb_480", "thumb_720", "thumb_1024"))
            )

            attachments.append(
                {
                    "id": file_id,
                    "name": f.get("name") or "",
                    "title": f.get("title") or f.get("name") or "",
                    "mimetype": mimetype,
                    "filetype": filetype,
                    "size": f.get("size"),
                    "is_image": is_image,
                    "url_private": f.get("url_private") or "",
                    "url_private_download": f.get("url_private_download") or "",
                    "thumb_360": f.get("thumb_360") or "",
                    "thumb_480": f.get("thumb_480") or "",
                    "thumb_720": f.get("thumb_720") or "",
                    "thumb_1024": f.get("thumb_1024") or "",
                    "permalink": f.get("permalink") or "",
                }
            )

        return attachments

    def _compute_next_delivery_dt(self, base_dt: datetime, route: DeliveryRoute) -> datetime:
        """
        base_dt: datetime del messaggio (timezone naive; coerente col resto dell'app)
        route.default_weekday: 0=consegna immediata 1=lun ... 7=dom
        route.default_time: time
        """
        period_candidate = self._period_schedule_candidate(base_dt, route)
        if period_candidate:
            return self._apply_once_schedule_rule(route, period_candidate)

        target_weekday = int(route.default_weekday)
        target_time = route.default_time

        if target_weekday == 0:
            candidate_dt = base_dt
        else:
            candidate_dt = self._schedule_candidate(
                base_dt,
                frequency=getattr(route, "frequency", None) or "weekly",
                target_weekday=target_weekday,
                target_time=target_time,
                second_weekday=getattr(route, "second_weekday", None),
                second_time=getattr(route, "second_time", None),
                anchor_date=getattr(route, "frequency_anchor_date", None),
            )

        return self._apply_once_schedule_rule(route, candidate_dt)

    def _get_route_for_channel(self, channel_id: str) -> DeliveryRoute | None:
        return DeliveryRoute.query.filter_by(slack_channel_id=channel_id, is_active=True).first()

    def _find_open_order(self, channel_id: str, customer_key: str, order_date) -> SlackOrder | None:
        return (
            SlackOrder.query
            .filter(
                SlackOrder.slack_channel_id == channel_id,
                SlackOrder.customer_key == customer_key,
                SlackOrder.order_date == order_date,
                SlackOrder.status.notin_(["evaso", "annullato", "annullata", "cancellato", "cancelled"]),
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

    # ============================================================
    # NEW — Sync reactions su cambio stato (upgrade/downgrade/jump)
    # ============================================================
    @staticmethod
    def _norm_reaction_name(x: str | None) -> str:
        if not x:
            return ""
        x = x.strip()
        if x.startswith(":") and x.endswith(":") and len(x) >= 3:
            x = x[1:-1].strip()
        return x

    def _status_meta(self) -> list[dict]:
        """
        Ritorna lista ordinata di status visibili con reaction.
        Ogni item: {code, order_index, is_terminal, slack_reaction_norm}
        """
        statuses = (
            OrderStatus.query
            .filter(OrderStatus.is_visible.is_(True))
            .order_by(OrderStatus.order_index.asc())
            .all()
        )

        out: list[dict] = []
        for s in statuses:
            rx = self._norm_reaction_name(getattr(s, "slack_reaction", None))
            out.append(
                {
                    "code": s.code,
                    "order_index": int(s.order_index or 0),
                    "is_terminal": bool(getattr(s, "is_terminal", False)),
                    "reaction": rx,
                }
            )
        return out

    def sync_order_status_reactions(
        self,
        order: SlackOrder,
        old_status_code: str | None,
        new_status_code: str | None,
    ) -> None:
        """
        Sincronizza le reaction Slack in base al cambio stato.
        Regole (concordate):
          - promote Δ=+1: add reaction target
          - demote Δ=-1: remove reaction current + remove tutte > target + ensure target
          - jump forward Δ>1: add solo target
          - jump backward Δ<-1: remove tutte > target + ensure target

        Nota: lavora sul messaggio root dell’ordine:
          - preferisce slack_thread_ts (root thread)
          - fallback su slack_message_ts
        """
        if not order:
            return

        channel_id = getattr(order, "slack_channel_id", None) or ""
        ts = getattr(order, "slack_thread_ts", None) or getattr(order, "slack_message_ts", None) or ""
        if not channel_id or not ts:
            logger.info(
                "[SLACK][SYNC] skipped (missing channel/ts) order_id=%s channel=%s ts=%s",
                getattr(order, "id", None),
                channel_id,
                ts,
            )
            return

        if not new_status_code:
            logger.info("[SLACK][SYNC] skipped (missing new_status) order_id=%s", getattr(order, "id", None))
            return

        meta = self._status_meta()
        by_code = {m["code"]: m for m in meta}

        new_meta = by_code.get(new_status_code)
        old_meta = by_code.get(old_status_code) if old_status_code else None

        # Rank: se non esiste in DB, consideralo 0 (ma comunque gestiamo add target se ha reaction)
        new_rank = int(new_meta["order_index"]) if new_meta else 0
        old_rank = int(old_meta["order_index"]) if old_meta else 0

        new_rx = (new_meta["reaction"] if new_meta else "") or ""
        old_rx = (old_meta["reaction"] if old_meta else "") or ""

        if not new_rx:
            logger.info(
                "[SLACK][SYNC] skipped (new status has no reaction) order_id=%s new_status=%s",
                getattr(order, "id", None),
                new_status_code,
            )
            return

        api = self._get_api()

        delta = new_rank - old_rank
        logger.info(
            "[SLACK][SYNC] order_id=%s %s(%s)->%s(%s) delta=%s",
            getattr(order, "id", None),
            old_status_code,
            old_rank,
            new_status_code,
            new_rank,
            delta,
        )

        # Helper: remove tutte le reaction dei livelli > target
        def remove_higher_than(target_rank: int):
            for m in meta:
                rx = m["reaction"]
                rk = int(m["order_index"])
                if not rx:
                    continue
                if rk > target_rank:
                    api.remove_reaction(channel=channel_id, timestamp=ts, name=rx)

        # promote (Δ=+1): add solo target
        if delta == 1:
            api.add_reaction(channel=channel_id, timestamp=ts, name=new_rx)
            return

        # demote (Δ=-1): remove current + remove tutte > target + ensure target
        if delta == -1:
            if old_rx:
                api.remove_reaction(channel=channel_id, timestamp=ts, name=old_rx)
            remove_higher_than(new_rank)
            api.add_reaction(channel=channel_id, timestamp=ts, name=new_rx)
            return

        # jump forward (Δ>1): add solo target (non assumere intermedi)
        if delta > 1:
            api.add_reaction(channel=channel_id, timestamp=ts, name=new_rx)
            return

        # jump backward (Δ<-1): remove tutte > target + ensure target
        if delta < -1:
            remove_higher_than(new_rank)
            api.add_reaction(channel=channel_id, timestamp=ts, name=new_rx)
            return

        # delta == 0 (stesso rank) o caso non mappabile: best effort -> ensure target
        api.add_reaction(channel=channel_id, timestamp=ts, name=new_rx)

    # ============================================================
    # Side effects Orders + normalizzatori + dispatcher
    # ============================================================
    def _mark_order_deleted(self, channel_id: str, message_ts: str, *, via: str, payload: dict | None = None) -> None:
        order = (
            SlackOrder.query
            .filter(
                SlackOrder.slack_channel_id == channel_id,
                (SlackOrder.slack_message_ts == message_ts) | (SlackOrder.slack_thread_ts == message_ts),
            )
            .order_by(SlackOrder.id.desc())
            .first()
        )
        if not order:
            return

        old_status = order.status
        order.status = "cancellato"
        order.closed_at = datetime.utcnow()
        db.session.add(SlackOrderEvent(
            order_id=order.id,
            type="status_change",
            payload={
                "from": old_status,
                "to": "cancellato",
                "via": via,
                "deleted_ts": message_ts,
                **(payload or {}),
            },
        ))
        entries = (
            RouteOrderBoardEntry.query
            .filter_by(slack_channel_id=channel_id, slack_message_ts=message_ts)
            .all()
        )
        for entry in entries:
            db.session.delete(entry)
        db.session.commit()

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

            def _norm_reaction(x: str | None) -> str:
                if not x:
                    return ""
                x = x.strip()
                if x.startswith(":") and x.endswith(":") and len(x) >= 3:
                    x = x[1:-1].strip()
                return x

            reaction_norm = _norm_reaction(reaction)

            # 0) Trova ordine (di solito reaction sul root_ts = thread_ts)
            order = (
                SlackOrder.query
                .filter(
                    SlackOrder.slack_channel_id == channel_id,
                    SlackOrder.slack_thread_ts == item_ts,
                )
                .order_by(SlackOrder.id.desc())
                .first()
            )

            # fallback: a volte è sul message_ts
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

            # 1) Stato target da DB (slack_reaction può essere ':truck:' oppure 'truck')
            target_status = None
            statuses = (
                OrderStatus.query
                .filter(OrderStatus.is_visible.is_(True))
                .all()
            )
            for s in statuses:
                if _norm_reaction(getattr(s, "slack_reaction", None)) == reaction_norm:
                    target_status = s
                    break

            if not target_status:
                return  # reaction non gestita per ordini

            new_status = target_status.code
            new_rank = int(target_status.order_index or 0)

            # 2) Rank corrente da DB (fallback 0)
            current_status = OrderStatus.query.filter_by(code=order.status).first()
            current_rank = int(current_status.order_index) if (
                current_status and current_status.order_index is not None
            ) else 0

            # registra sempre la reaction come evento
            db.session.add(
                SlackOrderEvent(
                    order_id=order.id,
                    type="reaction",
                    payload={
                        "reaction": reaction,
                        "reaction_norm": reaction_norm,
                        "user": user,
                        "item_ts": item_ts,
                        "channel": channel_id,
                        "resolved_to": new_status,
                    },
                )
            )

            # 3) Solo upgrade (come prima) ma basato su order_index
            is_cancelled = new_status in {"annullato", "annullata", "cancellato", "cancelled"}
            if new_rank > current_rank or is_cancelled:
                old_status = order.status
                order.status = new_status

                if is_cancelled:
                    order.closed_at = datetime.utcnow()
                    entry = (
                        RouteOrderBoardEntry.query
                        .filter_by(slack_channel_id=channel_id, slack_message_ts=item_ts)
                        .order_by(RouteOrderBoardEntry.id.desc())
                        .first()
                    )
                    if entry:
                        entry.order_note = None
                        entry.list_done = False
                        entry.status = "da_chiamare"
                elif bool(getattr(target_status, "is_terminal", False)) and not order.closed_at:
                    order.closed_at = datetime.utcnow()

                db.session.add(
                    SlackOrderEvent(
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
                    )
                )
                db.session.commit()
            return

        if trigger == "message_deleted":
            channel_id = data.get("channel")
            deleted_ts = data.get("deleted_ts") or data.get("ts")
            if not channel_id or not deleted_ts:
                return
            self._mark_order_deleted(channel_id, deleted_ts, via="slack_message_deleted")
            return

        if trigger == "message_changed":
            channel_id = data.get("channel")
            ts = data.get("ts")
            text = (data.get("text") or "").strip()
            attachments = data.get("attachments") if isinstance(data.get("attachments"), list) else []
            if not channel_id or not ts:
                return
            if text.lower() in {"this message was deleted.", "this message was deleted"}:
                self._mark_order_deleted(
                    channel_id,
                    ts,
                    via="slack_message_changed_deleted",
                    payload={"to_text": text},
                )
                return
            order = (
                SlackOrder.query
                .filter_by(slack_channel_id=channel_id, slack_message_ts=ts)
                .order_by(SlackOrder.id.desc())
                .first()
            )
            if not order:
                return
            old_text = order.raw_text or ""
            if text:
                order.raw_text = text
            db.session.add(SlackOrderEvent(
                order_id=order.id,
                type="message_changed",
                payload={
                    "from_text": old_text,
                    "to_text": text,
                    "attachments": attachments,
                    "via": "slack_message_changed",
                    "ts": ts,
                },
            ))
            entry = (
                RouteOrderBoardEntry.query
                .filter_by(slack_channel_id=channel_id, slack_message_ts=ts)
                .order_by(RouteOrderBoardEntry.id.desc())
                .first()
            )
            if entry and text:
                lines = [line for line in text.splitlines() if line.strip()]
                if lines and lines[0].strip().startswith("*") and lines[0].strip().endswith("*"):
                    lines = lines[1:]
                entry.order_note = "\n".join(lines).strip() or entry.order_note
            db.session.commit()
            return

        if trigger != "message":
            return

        channel_id = data.get("channel")
        ts = data.get("ts")
        thread_ts = data.get("thread_ts")
        text = (data.get("text") or "").strip()
        attachments = data.get("attachments") if isinstance(data.get("attachments"), list) else []

        if not channel_id or not ts:
            return

        existing_by_ts = (
            SlackOrder.query
            .filter(
                SlackOrder.slack_channel_id == channel_id,
                (SlackOrder.slack_message_ts == ts) | (SlackOrder.slack_thread_ts == ts),
            )
            .order_by(SlackOrder.id.desc())
            .first()
        )
        if existing_by_ts:
            if attachments:
                db.session.add(SlackOrderEvent(
                    order_id=existing_by_ts.id,
                    type="note",
                    payload={
                        "text": "Allegati rilevati dal messaggio Slack gia' registrato",
                        "attachments": attachments,
                        "via": "slack_existing_message",
                        "ts": ts,
                    },
                ))
                db.session.commit()
            return

        # I messaggi generati dal bot LDApp sono gia' stati creati nel DB dal flusso applicativo.
        # Se arrivano qui senza match sul timestamp, li ignoriamo per evitare doppie card.
        if data.get("bot_id") or data.get("app_id"):
            return

        # Reply -> NOTE su ordine esistente (thread root = thread_ts)
        if self._is_reply(ts, thread_ts):
            root_ts = thread_ts
            order = SlackOrder.query.filter_by(slack_channel_id=channel_id, slack_thread_ts=root_ts).first()
            if not order:
                return

            try:
                reply_dt = datetime.fromtimestamp(float(ts))
            except Exception:
                reply_dt = datetime.utcnow()

            parsed_delivery_dt, delivery_hint = self._extract_delivery_dt_from_text(
                text,
                reply_dt,
                self._get_route_for_channel(channel_id),
            )
            if parsed_delivery_dt:
                order.planned_delivery_at = parsed_delivery_dt

            ev = SlackOrderEvent(
                order_id=order.id,
                type="note",
                payload={
                    "user": data.get("user"),
                    "ts": ts,
                    "text": text,
                    "attachments": attachments,
                    "delivery_hint": delivery_hint,
                    "planned_delivery_at": parsed_delivery_dt.isoformat() if parsed_delivery_dt else None,
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
        parsed_delivery_dt, delivery_hint = self._extract_delivery_dt_from_text(text, created_dt, route)
        planned_delivery_at = (
            parsed_delivery_dt
            or (self._compute_next_delivery_dt(created_dt, route) if route else None)
        )

        existing_order = self._find_open_order(channel_id, customer_key, order_date)
        if existing_order:
            existing_order.raw_text = "\n\n".join([p for p in [existing_order.raw_text, text] if p])
            if parsed_delivery_dt:
                existing_order.planned_delivery_at = parsed_delivery_dt
            if self._detect_issue(text):
                existing_order.has_issues = True

            db.session.add(
                SlackOrderEvent(
                    order_id=existing_order.id,
                    type="append_text",
                    payload={
                        "ts": ts,
                        "user": data.get("user"),
                        "text": text,
                        "attachments": attachments,
                        "slack_message_ts": ts,
                        "delivery_hint": delivery_hint,
                        "planned_delivery_at": parsed_delivery_dt.isoformat() if parsed_delivery_dt else None,
                    },
                )
            )
            db.session.commit()
            try:
                from tools.push_notifications import send_push_to_staff
                send_push_to_staff("Ordine aggiornato", existing_order.customer_display, f"/kiosk?order_id={existing_order.id}")
            except Exception:
                logger.exception("Push ordine aggiornato fallita")
            return

        order = SlackOrder(
            route_id=route.id if route else None,
            slack_channel_id=channel_id,
            customer_display=customer_display,
            customer_key=customer_key,
            order_date=order_date,
            planned_delivery_at=planned_delivery_at,
            status="acquisito",
            raw_text=text,
            slack_message_ts=ts,
            slack_thread_ts=ts,
            has_issues=False,
        )
        db.session.add(order)
        db.session.flush()  # per ottenere order.id

        db.session.add(
            SlackOrderEvent(
                order_id=order.id,
                type="created",
                payload={
                    "ts": ts,
                    "user": data.get("user"),
                    "text": text,
                    "attachments": attachments,
                    "delivery_hint": delivery_hint,
                    "planned_delivery_at": parsed_delivery_dt.isoformat() if parsed_delivery_dt else None,
                },
            )
        )
        db.session.commit()
        try:
            from tools.push_notifications import send_push_to_staff
            send_push_to_staff("Nuovo ordine", customer_display, f"/kiosk?order_id={order.id}")
        except Exception:
            logger.exception("Push nuovo ordine Slack fallita")
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
                list(event.keys()),
            )
            return None

        normalized = handler(event)
        if not normalized:
            logger.warning("[SLACK][NORMALIZE_FAIL] event_type=%s", event_type)
            return None

        logger.info("[SLACK][EVENT] trigger=%s data=%s", normalized["trigger"], normalized["data"])

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
            logger.exception("orders side-effect failed")

        # ============================================================
        # V2 — Cross-app automations (parallelo al legacy)
        # ============================================================
        try:
            from tools.automation_dispatcher import AutomationDispatcher

            dispatcher = AutomationDispatcher()
            dispatcher.dispatch(
                {
                    "app": "slack",
                    "trigger": normalized["trigger"],
                    "connection_id": conn_id,
                    "payload": normalized["data"],
                }
            )
        except Exception:
            logger.exception("[V2][SLACK] dispatcher failed")

        actions = self.find_actions_for_trigger(conn_id, normalized["trigger"])
        self.execute_actions(actions, normalized["data"])
        return normalized

    def find_actions_for_trigger(self, connection_id: int, trigger: str) -> list[dict]:
        """
        Carica tutte le SlackAction per questa connection_id che hanno lo stesso trigger_type.
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
            result.append(
                {
                    "id": a.id,
                    "action_type": a.action_type,
                    "config_json": a.config_json,
                    "ordine": a.ordine,
                }
            )

        logger.info(
            "[SLACK][ACTIONS] found %d actions for trigger=%s conn_id=%s",
            len(result),
            trigger,
            connection_id,
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
        subtype = event.get("subtype")

        if subtype == "message_deleted":
            previous = event.get("previous_message") or {}
            return {
                "trigger": "message_deleted",
                "data": {
                    "channel": event.get("channel") or previous.get("channel"),
                    "deleted_ts": event.get("deleted_ts") or previous.get("ts"),
                    "ts": event.get("ts") or event.get("deleted_ts") or previous.get("ts"),
                    "previous_text": previous.get("text") or "",
                },
            }

        if subtype == "message_changed":
            message = event.get("message") or {}
            return {
                "trigger": "message_changed",
                "data": {
                    "channel": event.get("channel") or message.get("channel"),
                    "ts": message.get("ts") or event.get("message_ts"),
                    "text": self._extract_message_text(message),
                    "attachments": self._extract_file_attachments(message),
                    "previous_text": (event.get("previous_message") or {}).get("text") or "",
                },
            }

        # I file_share sono messaggi validi: la didascalia diventa testo ordine
        # e i file allegati vengono salvati sulla card.
        if subtype and subtype != "file_share":
            return None

        text = self._extract_message_text(event)
        attachments = self._extract_file_attachments(event)

        return {
            "trigger": "message",
            "data": {
                "channel": event.get("channel"),
                "channel_type": event.get("channel_type"),  # channel | group | im | mpim (se presente)
                "user": event.get("user"),
                "ts": event.get("ts"),
                "thread_ts": event.get("thread_ts"),
                "text": text,
                "attachments": attachments,
                "subtype": subtype or "",
                "bot_id": event.get("bot_id"),
                "app_id": event.get("app_id"),
            },
        }

    def _normalize_reaction_added(self, event: dict) -> dict | None:
        """Slack reaction_added"""
        item = event.get("item") or {}
        return {
            "trigger": "reaction_added",
            "data": {
                "reaction": event.get("reaction"),
                "user": event.get("user"),
                "item_channel": item.get("channel"),
                "item_ts": item.get("ts"),
            },
        }
