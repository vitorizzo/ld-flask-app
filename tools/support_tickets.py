import uuid

from flask import url_for


def outbound_ticket_message_id(ticket_id):
    return f"<ldapp-ticket-{int(ticket_id)}-{uuid.uuid4().hex}@ldenoteca.it>"


def public_ticket_url(ticket):
    return url_for("auth.help_desk_ticket", token=ticket.public_token, _external=True)
