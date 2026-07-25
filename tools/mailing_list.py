from datetime import datetime, timezone

from flask import current_app
from flask_mail import Message

from extensions import db
from models import MailingCampaign, MailingDelivery, MailingListMember, MailingSubscriber
from tools.mail_accounts import send_account_mail


def _unsubscribe_url(subscriber):
    base_url = (current_app.config.get("PUBLIC_BASE_URL") or "https://ldapp.ldenoteca.it").rstrip("/")
    return f"{base_url}/mailing-list/unsubscribe/{subscriber.unsubscribe_token}"


def _eligible_subscribers(campaign):
    return (
        MailingSubscriber.query
        .join(MailingListMember)
        .filter(
            MailingListMember.mailing_list_id == campaign.mailing_list_id,
            MailingListMember.is_active.is_(True),
            MailingSubscriber.status == "subscribed",
        )
        .order_by(MailingSubscriber.id)
        .all()
    )


def prepare_campaign(campaign):
    """Congela i destinatari della campagna prima che venga accodata."""
    existing = {
        delivery.subscriber_id: delivery
        for delivery in MailingDelivery.query.filter_by(campaign_id=campaign.id).all()
    }
    if not existing:
        for subscriber in _eligible_subscribers(campaign):
            db.session.add(MailingDelivery(
                campaign_id=campaign.id,
                subscriber_id=subscriber.id,
                status="pending",
            ))
        db.session.flush()

    campaign.recipient_count = MailingDelivery.query.filter_by(campaign_id=campaign.id).count()
    campaign.sent_count = MailingDelivery.query.filter_by(campaign_id=campaign.id, status="sent").count()
    campaign.failed_count = MailingDelivery.query.filter_by(campaign_id=campaign.id, status="failed").count()
    return campaign.recipient_count


def _finalize_campaign(campaign):
    campaign.sent_count = MailingDelivery.query.filter_by(campaign_id=campaign.id, status="sent").count()
    campaign.failed_count = MailingDelivery.query.filter_by(campaign_id=campaign.id, status="failed").count()
    pending_count = MailingDelivery.query.filter_by(campaign_id=campaign.id, status="pending").count()
    campaign.status = "sent" if campaign.failed_count == 0 and pending_count == 0 else "failed"
    campaign.completed_at = datetime.now(timezone.utc)
    db.session.commit()


def fail_campaign(campaign_id, error):
    db.session.rollback()
    campaign = db.session.get(MailingCampaign, campaign_id)
    if not campaign or campaign.status == "sent":
        return
    campaign.status = "failed"
    campaign.completed_at = datetime.now(timezone.utc)
    message = str(error)[:1000]
    for delivery in MailingDelivery.query.filter_by(campaign_id=campaign.id, status="pending").all():
        delivery.status = "failed"
        delivery.error_message = message
    campaign.failed_count = MailingDelivery.query.filter_by(campaign_id=campaign.id, status="failed").count()
    campaign.sent_count = MailingDelivery.query.filter_by(campaign_id=campaign.id, status="sent").count()
    db.session.commit()


def reset_campaign_delivery_state(campaign):
    if campaign.status in {"queued", "sending"}:
        raise ValueError("Non puoi azzerare una campagna mentre l'invio e' in corso.")
    MailingDelivery.query.filter_by(campaign_id=campaign.id).delete(synchronize_session=False)
    campaign.status = "draft"
    campaign.recipient_count = 0
    campaign.sent_count = 0
    campaign.failed_count = 0
    campaign.started_at = None
    campaign.completed_at = None
    db.session.flush()
    prepare_campaign(campaign)
    db.session.commit()
    return campaign.recipient_count


def send_campaign(campaign_id):
    campaign = db.session.get(MailingCampaign, campaign_id)
    if not campaign or campaign.status == "sent":
        return {"campaign_id": campaign_id, "skipped": True}
    prepare_campaign(campaign)
    campaign.status = "sending"
    campaign.started_at = datetime.now(timezone.utc)
    campaign.completed_at = None
    db.session.commit()

    deliveries = (
        MailingDelivery.query
        .filter(
            MailingDelivery.campaign_id == campaign.id,
            MailingDelivery.status.in_(("pending", "failed")),
        )
        .order_by(MailingDelivery.id)
        .all()
    )
    for delivery in deliveries:
        if delivery.status == "sent":
            continue
        subscriber = delivery.subscriber
        delivery.status = "pending"
        delivery.error_message = None
        db.session.commit()
        unsubscribe_url = _unsubscribe_url(subscriber)
        footer = f'<hr><p style="font-size:12px;color:#666">Ricevi questa email perche\' sei iscritto alla mailing list LD Enoteca. <a href="{unsubscribe_url}">Disiscriviti</a>.</p>'
        message = Message(subject=campaign.subject, recipients=[subscriber.email], html=campaign.html_body + footer)
        try:
            send_account_mail(campaign.account_code, message)
            delivery.status, delivery.sent_at, delivery.error_message = "sent", datetime.now(timezone.utc), None
        except Exception as exc:
            delivery.status, delivery.error_message = "failed", str(exc)[:1000]
        db.session.commit()
    _finalize_campaign(campaign)
    return {"campaign_id": campaign.id, "sent": campaign.sent_count, "failed": campaign.failed_count}
