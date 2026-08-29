from datetime import datetime, timezone
from decimal import Decimal
from html import escape

from flask_mail import Message

from extensions import db
from models import AdministrationPaymentLinkDelivery
from tools.log_utils import get_logger
from tools.mail_accounts import assistance_mail_sender, send_account_mail


logger = get_logger("administration_payment_links")


def _money(value):
    amount = Decimal(value or 0).quantize(Decimal("0.01"))
    return f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def send_administration_payment_link(delivery_id):
    delivery = AdministrationPaymentLinkDelivery.query.get(delivery_id)
    if delivery is None:
        return {"success": False, "delivery_id": delivery_id, "reason": "delivery_not_found"}
    if delivery.status == "sent":
        return {"success": True, "delivery_id": delivery.id, "skipped": True, "reason": "already_sent"}

    payment_link = delivery.payment_link
    if (
        payment_link is None
        or payment_link.status != "active"
        or not payment_link.payment_url
        or (
            payment_link.status == "active"
            and payment_link.expires_at is not None
            and payment_link.expires_at <= datetime.now(timezone.utc)
        )
    ):
        if payment_link is not None and payment_link.status == "active" and payment_link.expires_at:
            payment_link.status = "expired"
        delivery.status = "failed"
        delivery.error_message = "Il link di pagamento non e' disponibile o non e' piu' attivo."
        db.session.commit()
        return {"success": False, "delivery_id": delivery.id, "reason": "link_not_active"}

    greeting = f"Gentile {delivery.recipient_name}," if delivery.recipient_name else "Buongiorno,"
    subject = f"Link di pagamento LD Enoteca - {_money(payment_link.amount)} {payment_link.currency}"
    text_body = "\n".join([
        greeting,
        "",
        "LD Enoteca ti ha inviato un link sicuro per effettuare il pagamento:",
        f"Importo: {_money(payment_link.amount)} {payment_link.currency}",
        f"Descrizione: {payment_link.description}",
        "",
        payment_link.payment_url,
        "",
        "Il pagamento avviene interamente sul sito protetto Nexi. LDApp non acquisisce i dati della carta.",
        "Se non riconosci questa richiesta, non procedere e contatta LD Enoteca.",
    ])
    html_body = f"""
      <div style="font-family:Arial,sans-serif;max-width:620px;margin:auto;color:#243447">
        <p>{escape(greeting)}</p>
        <p>LD Enoteca ti ha inviato un link sicuro per effettuare il pagamento.</p>
        <div style="background:#f4f6f8;border-radius:12px;padding:18px;margin:20px 0">
          <div style="font-size:13px;color:#607080">Importo</div>
          <div style="font-size:26px;font-weight:700">{escape(_money(payment_link.amount))} {escape(payment_link.currency)}</div>
          <div style="margin-top:12px;font-size:13px;color:#607080">Descrizione</div>
          <div>{escape(payment_link.description)}</div>
        </div>
        <p><a href="{escape(payment_link.payment_url, quote=True)}" style="display:inline-block;background:#173f5f;color:#fff;text-decoration:none;padding:13px 22px;border-radius:8px;font-weight:700">Paga ora</a></p>
        <p style="font-size:13px;color:#607080">Il pagamento avviene interamente sul sito protetto Nexi. LDApp non acquisisce i dati della carta.</p>
        <p style="font-size:13px;color:#607080">Se non riconosci questa richiesta, non procedere e contatta LD Enoteca.</p>
      </div>
    """
    message = Message(
        subject=subject,
        recipients=[delivery.recipient_email],
        body=text_body,
        html=html_body,
        sender=assistance_mail_sender(),
    )
    try:
        result = send_account_mail("assistance", message)
    except Exception as exc:
        logger.exception("Invio PayByLink fallito delivery=%s", delivery.id)
        delivery.status = "failed"
        delivery.error_message = str(exc)[:1000]
        db.session.commit()
        return {"success": False, "delivery_id": delivery.id, "error": str(exc)}

    delivery.status = "sent"
    delivery.sent_at = datetime.now(timezone.utc)
    delivery.error_message = None
    db.session.commit()
    return {
        "success": True,
        "delivery_id": delivery.id,
        "recipient": delivery.recipient_email,
        "mail": result,
    }
