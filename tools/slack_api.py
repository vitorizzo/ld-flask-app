# tools/slack_api.py

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from tools.log_utils import get_logger

logger = get_logger("slack_api", level=logging.INFO)


@dataclass(frozen=True)
class SlackAPIConfig:
    """
    Config minimale per usare Slack Web API.
    - bot_token: token del bot (xoxb-...)
    """
    bot_token: str


class SlackAPI:
    """
    Wrapper minimale sopra slack_sdk.WebClient.
    Niente Flask qui: passa solo config/params.
    """

    def __init__(self, config: SlackAPIConfig):
        if not config.bot_token:
            raise ValueError("SlackAPIConfig.bot_token mancante (BOT token xoxb-...)")
        self.config = config
        self.client = WebClient(token=config.bot_token)

    @staticmethod
    def _norm_reaction_name(name: str) -> str:
        n = (name or "").strip()
        if n.startswith(":") and n.endswith(":") and len(n) >= 3:
            n = n[1:-1].strip()
        return n

    def auth_test(self) -> Dict[str, Any]:
        """
        Test base: verifica che token e workspace siano validi.
        Ritorna il JSON di Slack (ok, team, user_id, bot_id, url, ecc.).
        """
        try:
            resp = self.client.auth_test()
            data = resp.data  # dict
            logger.info("Slack auth_test ok: team=%s user_id=%s", data.get("team"), data.get("user_id"))
            return data
        except SlackApiError as e:
            err = e.response.get("error") if e.response else str(e)
            logger.error("Slack auth_test failed: %s", err)
            raise
        except Exception:
            logger.exception("Errore inatteso in SlackAPI.auth_test")
            raise

    def post_message(
        self,
        channel: str,
        text: str,
        *,
        thread_ts: Optional[str] = None,
        blocks: Optional[list] = None,
        unfurl_links: bool = False,
        unfurl_media: bool = False,
        client_msg_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Invia un messaggio in un canale."""
        try:
            resp = self.client.chat_postMessage(
                channel=channel,
                text=text,
                thread_ts=thread_ts,
                blocks=blocks,
                unfurl_links=unfurl_links,
                unfurl_media=unfurl_media,
                client_msg_id=client_msg_id,
            )
            return resp.data if hasattr(resp, "data") else dict(resp)
        except SlackApiError as e:
            err = e.response.get("error") if e.response else str(e)
            logger.error("Slack chat_postMessage failed: %s", err)
            raise
        except Exception:
            logger.exception("Errore inatteso in SlackAPI.post_message")
            raise

    def send_message(self, channel: str, text: str) -> Dict[str, Any]:
        """
        Alias semplice di post_message (per retro-compatibilità).
        """
        try:
            resp = self.client.chat_postMessage(channel=channel, text=text)
            return resp.data if hasattr(resp, "data") else dict(resp)
        except SlackApiError as e:
            err = e.response.get("error") if e.response else str(e)
            logger.error("Slack chat_postMessage failed: %s", err)
            raise
        except Exception:
            logger.exception("Errore inatteso in SlackAPI.send_message")
            raise

    def upload_file(
        self,
        channel: str,
        file_path: str,
        *,
        title: str | None = None,
        filename: str | None = None,
        thread_ts: str | None = None,
        initial_comment: str | None = None,
    ) -> Dict[str, Any]:
        """Carica un file in Slack, opzionalmente nel thread di un messaggio."""
        try:
            kwargs = {
                "channel": channel,
                "file": file_path,
                "title": title,
                "filename": filename,
                "initial_comment": initial_comment,
            }
            if thread_ts:
                kwargs["thread_ts"] = thread_ts
            resp = self.client.files_upload_v2(**{k: v for k, v in kwargs.items() if v})
            return resp.data if hasattr(resp, "data") else dict(resp)
        except SlackApiError as e:
            err = e.response.get("error") if e.response else str(e)
            logger.error("Slack files_upload_v2 failed: %s", err)
            raise
        except Exception:
            logger.exception("Errore inatteso in SlackAPI.upload_file")
            raise

    def add_reaction(self, channel: str, timestamp: str, name: str) -> Dict[str, Any]:
        """
        Aggiunge una reaction ad un messaggio.
        Idempotente: se già presente, non fallisce (skipped=True).
        """
        reaction = self._norm_reaction_name(name)
        try:
            resp = self.client.reactions_add(channel=channel, timestamp=timestamp, name=reaction)
            return resp.data
        except SlackApiError as e:
            err = e.response.get("error") if e.response else str(e)

            # Caso NON fatale: reaction già presente
            if err == "already_reacted":
                logger.info(
                    "Slack reactions_add skipped: already_reacted (channel=%s ts=%s name=%s)",
                    channel, timestamp, reaction
                )
                return {"ok": True, "skipped": True, "error": "already_reacted"}

            logger.error("Slack reactions_add failed: %s", err)
            raise
        except Exception:
            logger.exception("Errore inatteso in SlackAPI.add_reaction")
            raise

    def remove_reaction(self, channel: str, timestamp: str, name: str) -> Dict[str, Any]:
        """
        Rimuove una reaction da un messaggio.
        Idempotente: se non presente, non fallisce (skipped=True).
        """
        reaction = self._norm_reaction_name(name)
        try:
            resp = self.client.reactions_remove(channel=channel, timestamp=timestamp, name=reaction)
            return resp.data
        except SlackApiError as e:
            err = e.response.get("error") if e.response else str(e)

            # Caso NON fatale: reaction non presente
            if err == "no_reaction":
                logger.info(
                    "Slack reactions_remove skipped: no_reaction (channel=%s ts=%s name=%s)",
                    channel, timestamp, reaction
                )
                return {"ok": True, "skipped": True, "error": "no_reaction"}

            logger.error("Slack reactions_remove failed: %s", err)
            raise
        except Exception:
            logger.exception("Errore inatteso in SlackAPI.remove_reaction")
            raise

    def delete_message(self, channel: str, timestamp: str) -> Dict[str, Any]:
        """Cancella un messaggio Slack scritto dal bot."""
        try:
            resp = self.client.chat_delete(channel=channel, ts=timestamp)
            return resp.data if hasattr(resp, "data") else dict(resp)
        except SlackApiError as e:
            err = e.response.get("error") if e.response else str(e)
            logger.error("Slack chat_delete failed: %s", err)
            raise
        except Exception:
            logger.exception("Errore inatteso in SlackAPI.delete_message")
            raise

    def get_thread_replies(self, channel: str, timestamp: str) -> list[Dict[str, Any]]:
        """Legge tutti i messaggi del thread, inclusa la radice."""
        messages: list[Dict[str, Any]] = []
        cursor = None
        while True:
            kwargs = {"channel": channel, "ts": timestamp, "limit": 200}
            if cursor:
                kwargs["cursor"] = cursor
            resp = self.client.conversations_replies(**kwargs)
            data = resp.data if hasattr(resp, "data") else dict(resp)
            messages.extend(data.get("messages") or [])
            cursor = ((data.get("response_metadata") or {}).get("next_cursor") or "").strip()
            if not cursor:
                return messages

    def delete_thread(self, channel: str, timestamp: str) -> Dict[str, Any]:
        """Cancella prima le risposte dell'app e infine il messaggio radice."""
        identity = self.auth_test()
        bot_user_id = identity.get("user_id")
        bot_id = identity.get("bot_id")
        replies = self.get_thread_replies(channel, timestamp)
        foreign_replies = []
        owned_replies = []
        for message in replies:
            message_ts = message.get("ts")
            if not message_ts or message_ts == timestamp:
                continue
            is_owned = (
                (bot_user_id and message.get("user") == bot_user_id)
                or (bot_id and message.get("bot_id") == bot_id)
            )
            (owned_replies if is_owned else foreign_replies).append(message_ts)

        if foreign_replies:
            raise RuntimeError("il thread contiene risposte pubblicate da altri utenti")

        for reply_ts in reversed(owned_replies):
            self.delete_message(channel, reply_ts)
        response = self.delete_message(channel, timestamp)
        return {
            "ok": True,
            "action": "deleted",
            "deleted_replies": len(owned_replies),
            "delete_response": response,
        }

    def delete_or_mark_message(self, channel: str, timestamp: str, deleted_by: str) -> Dict[str, Any]:
        """Cancella tutto il thread dell'app; se non e' possibile, lo marca come eliminato."""
        try:
            return self.delete_thread(channel, timestamp)
        except Exception as delete_error:
            logger.info(
                "Slack thread not fully deletable, applying marker fallback channel=%s ts=%s error=%s",
                channel,
                timestamp,
                delete_error,
            )

        comment_error = None
        reaction_error = None
        try:
            self.post_message(
                channel,
                f"Ordine eliminato dalla bacheca da {deleted_by or 'operatore LDApp'}.",
                thread_ts=timestamp,
            )
        except Exception as exc:
            comment_error = exc
            logger.exception("Slack delete fallback comment failed channel=%s ts=%s", channel, timestamp)

        try:
            self.add_reaction(channel, timestamp, "wastebasket")
        except Exception as exc:
            reaction_error = exc
            logger.exception("Slack delete fallback reaction failed channel=%s ts=%s", channel, timestamp)

        if comment_error and reaction_error:
            raise RuntimeError(
                f"messaggio non cancellabile; commento e reaction non applicati: {comment_error}; {reaction_error}"
            )
        return {
            "ok": True,
            "action": "marked_deleted",
            "comment_added": comment_error is None,
            "reaction_added": reaction_error is None,
            "warning": str(comment_error or reaction_error) if (comment_error or reaction_error) else None,
        }

    def get_permalink(self, channel: str, message_ts: str) -> Optional[str]:
        """
        Ritorna il permalink di un messaggio (utile per mapping Trello <-> Slack).
        """
        try:
            resp = self.client.chat_getPermalink(channel=channel, message_ts=message_ts)
            data = dict(resp)
            return data.get("permalink")
        except SlackApiError as e:
            err = e.response.get("error") if e.response else str(e)
            logger.error("Slack chat_getPermalink failed: %s", err)
            return None
        except Exception:
            logger.exception("Errore inatteso in SlackAPI.get_permalink")
            return None
