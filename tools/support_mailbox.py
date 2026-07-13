import html
import hashlib
import imaplib
import os
import re
import uuid
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr

from flask import current_app
from werkzeug.utils import secure_filename

from extensions import db
from models import SupportTicket, SupportTicketAttachment, SupportTicketMessage
from tools.log_utils import get_logger
from tools.mail_accounts import get_email_account


logger = get_logger("support_mailbox")
TICKET_PATTERN = re.compile(r"\[?Ticket\s*#(\d+)\]?", re.IGNORECASE)
MESSAGE_ID_PATTERN = re.compile(r"<[^>]+>")
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".txt", ".doc", ".docx", ".xls", ".xlsx"}


def _message_ids(value):
    return MESSAGE_ID_PATTERN.findall(value or "")


def _plain_body(message):
    plain_parts = []
    html_parts = []
    parts = message.walk() if message.is_multipart() else [message]
    for part in parts:
        if part.get_content_disposition() == "attachment":
            continue
        content_type = part.get_content_type()
        if content_type not in {"text/plain", "text/html"}:
            continue
        try:
            content = part.get_content()
        except Exception:
            payload = part.get_payload(decode=True) or b""
            content = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        if content_type == "text/plain":
            plain_parts.append(str(content))
        else:
            html_parts.append(str(content))
    if plain_parts:
        return "\n".join(plain_parts).strip()
    raw_html = "\n".join(html_parts)
    text = re.sub(r"<\s*br\s*/?>", "\n", raw_html, flags=re.IGNORECASE)
    text = re.sub(r"</\s*p\s*>", "\n", text, flags=re.IGNORECASE)
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


def _ticket_from_message(message, body):
    correlation_ids = []
    correlation_ids.extend(_message_ids(message.get("In-Reply-To")))
    correlation_ids.extend(_message_ids(message.get("References")))
    if correlation_ids:
        linked = (
            SupportTicketMessage.query
            .filter(SupportTicketMessage.external_message_id.in_(correlation_ids))
            .order_by(SupportTicketMessage.id.desc())
            .first()
        )
        if linked:
            return linked.ticket

    match = TICKET_PATTERN.search(message.get("Subject") or "") or TICKET_PATTERN.search(body or "")
    if not match:
        return None
    return SupportTicket.query.filter_by(id=int(match.group(1)), ticket_type="support").first()


def _save_attachments(ticket_message, email_message):
    saved = 0
    folder = os.path.join(current_app.static_folder, "uploads", "support_tickets", str(ticket_message.ticket_id))
    os.makedirs(folder, exist_ok=True)
    for part in email_message.walk():
        filename = part.get_filename()
        if not filename:
            continue
        original = secure_filename(filename)
        extension = os.path.splitext(original)[1].lower()
        if not original or extension not in ALLOWED_EXTENSIONS:
            logger.warning("Allegato email ticket ignorato: %s", filename)
            continue
        payload = part.get_payload(decode=True) or b""
        target_name = f"{uuid.uuid4().hex}_{original}"
        target_path = os.path.join(folder, target_name)
        with open(target_path, "wb") as handle:
            handle.write(payload)
        relative_path = os.path.relpath(target_path, current_app.static_folder).replace(os.sep, "/")
        db.session.add(SupportTicketAttachment(
            message=ticket_message,
            file_path=relative_path,
            original_filename=original,
            mime_type=part.get_content_type(),
            file_size=len(payload),
        ))
        saved += 1
    return saved


def _connect(account):
    server = account.get("imap_server")
    port = int(account.get("imap_port") or 993)
    if account.get("imap_use_ssl"):
        client = imaplib.IMAP4_SSL(server, port)
    else:
        client = imaplib.IMAP4(server, port)
        if account.get("imap_use_tls"):
            client.starttls()
    client.login(account.get("imap_username"), account.get("imap_password"))
    return client


def sync_support_mailbox(limit=100):
    account = get_email_account("assistance")
    if not account or not account.get("imap_enabled"):
        return {"enabled": False, "processed": 0, "imported": 0, "ignored": 0, "duplicates": 0}
    required = [account.get("imap_server"), account.get("imap_username"), account.get("imap_password")]
    if not all(required):
        raise RuntimeError("Account assistance: configurazione IMAP incompleta")

    stats = {"enabled": True, "processed": 0, "imported": 0, "ignored": 0, "duplicates": 0, "attachments": 0}
    client = _connect(account)
    try:
        status, _ = client.select(account.get("imap_folder") or "INBOX")
        if status != "OK":
            raise RuntimeError("Impossibile aprire la cartella IMAP configurata")
        status, data = client.search(None, "UNSEEN")
        if status != "OK":
            raise RuntimeError("Ricerca messaggi IMAP non riuscita")
        message_numbers = (data[0] or b"").split()[:max(1, int(limit or 100))]
        for number in message_numbers:
            status, fetched = client.fetch(number, "(RFC822)")
            if status != "OK" or not fetched or not isinstance(fetched[0], tuple):
                continue
            stats["processed"] += 1
            raw_message = fetched[0][1]
            message = BytesParser(policy=policy.default).parsebytes(raw_message)
            external_id = (message.get("Message-ID") or "").strip()
            if not external_id:
                external_id = f"<imap-{hashlib.sha256(raw_message).hexdigest()}@ldapp.local>"
            if external_id and SupportTicketMessage.query.filter_by(external_message_id=external_id).first():
                stats["duplicates"] += 1
                client.store(number, "+FLAGS", "\\Seen")
                continue
            body = _plain_body(message)
            ticket = _ticket_from_message(message, body)
            sender = parseaddr(message.get("From") or "")[1].strip().casefold()
            allowed_senders = {str(ticket.reply_email or "").strip().casefold()} if ticket else set()
            if ticket and ticket.user and ticket.user.email:
                allowed_senders.add(ticket.user.email.strip().casefold())
            if not ticket or not sender or sender not in allowed_senders:
                stats["ignored"] += 1
                logger.warning("Email assistenza ignorata: ticket=%s mittente=%s", ticket.id if ticket else None, sender)
                client.store(number, "+FLAGS", "\\Seen")
                continue
            if not body:
                body = "Messaggio email senza corpo testuale."
            ticket_message = SupportTicketMessage(
                ticket=ticket,
                sender_type="user",
                source="email",
                body=body,
                email_from=sender,
                email_to=parseaddr(message.get("To") or "")[1] or None,
                external_message_id=external_id,
                in_reply_to=(message.get("In-Reply-To") or "").strip() or None,
                read_by_user_at=datetime.now(timezone.utc),
            )
            db.session.add(ticket_message)
            db.session.flush()
            stats["attachments"] += _save_attachments(ticket_message, message)
            ticket.status = "open"
            ticket.closed_at = None
            db.session.commit()
            stats["imported"] += 1
            client.store(number, "+FLAGS", "\\Seen")
    except Exception:
        db.session.rollback()
        raise
    finally:
        try:
            client.logout()
        except Exception:
            pass
    return stats
