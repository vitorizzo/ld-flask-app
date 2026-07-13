import uuid
from datetime import datetime, timezone

from flask import url_for

from extensions import db
from models import SupportTicket, SupportTicketMessage


def outbound_ticket_message_id(ticket_id):
    return f"<ldapp-ticket-{int(ticket_id)}-{uuid.uuid4().hex}@ldenoteca.it>"


def public_ticket_url(ticket):
    return url_for("auth.help_desk_ticket", token=ticket.public_token, _external=True)


def user_unread_count(user_id):
    if not user_id:
        return 0
    return (
        db.session.query(SupportTicketMessage.id)
        .join(SupportTicket, SupportTicketMessage.ticket_id == SupportTicket.id)
        .filter(
            SupportTicket.ticket_type == "support",
            SupportTicket.user_id == user_id,
            SupportTicketMessage.sender_type == "support",
            SupportTicketMessage.read_by_user_at.is_(None),
        )
        .count()
    )


def support_unread_count():
    return (
        db.session.query(SupportTicketMessage.id)
        .join(SupportTicket, SupportTicketMessage.ticket_id == SupportTicket.id)
        .filter(
            SupportTicket.ticket_type == "support",
            SupportTicketMessage.sender_type == "user",
            SupportTicketMessage.read_by_support_at.is_(None),
        )
        .count()
    )


def ticket_user_unread_count(ticket_id):
    return SupportTicketMessage.query.filter(
        SupportTicketMessage.ticket_id == ticket_id,
        SupportTicketMessage.sender_type == "support",
        SupportTicketMessage.read_by_user_at.is_(None),
    ).count()


def mark_ticket_read_by_user(ticket_id):
    return SupportTicketMessage.query.filter(
        SupportTicketMessage.ticket_id == ticket_id,
        SupportTicketMessage.sender_type == "support",
        SupportTicketMessage.read_by_user_at.is_(None),
    ).update({SupportTicketMessage.read_by_user_at: datetime.now(timezone.utc)}, synchronize_session=False)


def mark_ticket_read_by_support(ticket_id):
    return SupportTicketMessage.query.filter(
        SupportTicketMessage.ticket_id == ticket_id,
        SupportTicketMessage.sender_type == "user",
        SupportTicketMessage.read_by_support_at.is_(None),
    ).update({SupportTicketMessage.read_by_support_at: datetime.now(timezone.utc)}, synchronize_session=False)
