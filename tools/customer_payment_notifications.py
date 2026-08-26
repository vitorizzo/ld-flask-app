import os

from flask import current_app, url_for
from flask_mail import Message
from sqlalchemy.orm import selectinload

from extensions import db
from models import CustomerPaymentCase, CustomerPaymentEvent
from tools.log_utils import get_logger
from tools.mail_accounts import assistance_mail_sender, send_account_mail


logger = get_logger("customer_payment_notifications")


def _recipient_for(case_type):
    if case_type == "payment_claim":
        return (
            current_app.config.get("DISPUTES_APP_EMAIL")
            or os.getenv("DISPUTES_APP_EMAIL")
            or "contestazioni_ldapp@ldenoteca.it"
        )
    return (
        current_app.config.get("PAYMENTS_APP_EMAIL")
        or os.getenv("PAYMENTS_APP_EMAIL")
        or "pagamenti_ldapp@ldenoteca.it"
    )


def _absolute_office_url(case_id):
    path = url_for("customer_account.office_case_detail", case_id=case_id, _external=False)
    base_url = (
        current_app.config.get("PUBLIC_BASE_URL")
        or os.getenv("PUBLIC_BASE_URL")
        or "https://ldapp.ldenoteca.it"
    )
    return f"{str(base_url).rstrip('/')}{path}"


def notify_customer_payment_case(case_id, notification_kind="created"):
    payment_case = (
        CustomerPaymentCase.query
        .options(
            selectinload(CustomerPaymentCase.registry),
            selectinload(CustomerPaymentCase.created_by),
            selectinload(CustomerPaymentCase.allocations),
            selectinload(CustomerPaymentCase.evidence),
        )
        .filter(CustomerPaymentCase.id == case_id)
        .first()
    )
    if payment_case is None:
        return {"success": False, "case_id": case_id, "reason": "case_not_found"}

    already_sent = None
    if notification_kind == "created":
        already_sent = CustomerPaymentEvent.query.filter_by(
            case_id=payment_case.id, event_type="office_email_sent",
        ).first()
    if already_sent is not None:
        return {"success": True, "case_id": payment_case.id, "skipped": True, "reason": "already_sent"}

    registry = payment_case.registry
    user = payment_case.created_by
    recipient = _recipient_for(payment_case.case_type)
    subject_prefix = "Contestazione partita" if payment_case.case_type == "payment_claim" else "Comunicazione pagamento"
    notification_labels = {
        "created": ("Nuova", "ricevuta", "office_email_sent"),
        "updated": ("Aggiornamento", "modificata dal cliente", "office_email_update_sent"),
        "cancelled": ("Annullamento", "eliminata dal cliente", "office_email_cancelled_sent"),
    }
    subject_action, body_action, success_event_type = notification_labels.get(
        notification_kind, notification_labels["created"]
    )
    customer_name = registry.display_name or registry.legal_name or registry.source_code
    document_lines = []
    for allocation in payment_case.allocations:
        snapshot = allocation.document_snapshot or {}
        number = snapshot.get("document_number") or snapshot.get("number") or "senza numero"
        document_lines.append(f"- {number}: {allocation.allocated_amount} {payment_case.currency}")
    body = "\n".join([
        f"{subject_prefix} {body_action} su LDApp.",
        "",
        f"Pratica: {payment_case.public_id}",
        f"Cliente: {customer_name} (codice {registry.source_code})",
        f"Utente: {user.name} {user.surname} <{user.email}>",
        f"Totale dichiarato: {payment_case.declared_amount} {payment_case.currency}",
        f"Riferimento: {payment_case.payment_reference or '-'}",
        f"Nota: {payment_case.note or '-'}",
        f"Contabili/prove allegate: {len(payment_case.evidence)}",
        "",
        "Documenti selezionati:",
        *(document_lines or ["- nessun documento associato"]),
        "",
        "Apri la pratica nell'area privata LDApp:",
        _absolute_office_url(payment_case.id),
        "",
        "Gli allegati non sono inclusi nell'email e restano protetti nell'app.",
    ])
    message = Message(
        subject=f"[LDApp] {subject_action}: {subject_prefix} - {customer_name} - {payment_case.public_id[-8:]}",
        recipients=[recipient],
        body=body,
        sender=assistance_mail_sender(),
    )
    try:
        result = send_account_mail("assistance", message)
    except Exception as exc:
        logger.exception("Notifica email pratica %s non inviata a %s", payment_case.id, recipient)
        db.session.add(CustomerPaymentEvent(
            case_id=payment_case.id,
            event_type="office_email_failed",
            message="Invio email ufficio non riuscito; pratica disponibile nella coda LDApp.",
            event_metadata={"recipient": recipient, "error": str(exc)[:500]},
        ))
        db.session.commit()
        return {"success": False, "case_id": payment_case.id, "recipient": recipient, "error": str(exc)}

    db.session.add(CustomerPaymentEvent(
        case_id=payment_case.id,
        event_type=success_event_type,
        message=f"Notifica inviata a {recipient}",
        event_metadata={"recipient": recipient},
    ))
    db.session.commit()
    return {"success": True, "case_id": payment_case.id, "recipient": recipient, "mail": result}
