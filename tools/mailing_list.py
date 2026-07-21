from datetime import datetime, timezone

from flask import url_for
from flask_mail import Message

from extensions import db
from models import MailingCampaign, MailingDelivery, MailingSubscriber
from tools.mail_accounts import send_account_mail


def send_campaign(campaign_id):
    campaign = db.session.get(MailingCampaign, campaign_id)
    if not campaign or campaign.status == "sent":
        return {"campaign_id": campaign_id, "skipped": True}
    campaign.status, campaign.started_at = "sending", datetime.now(timezone.utc)
    subscribers = MailingSubscriber.query.filter_by(status="subscribed").order_by(MailingSubscriber.id).all()
    campaign.recipient_count = len(subscribers)
    db.session.commit()
    for subscriber in subscribers:
        delivery = MailingDelivery.query.filter_by(campaign_id=campaign.id, subscriber_id=subscriber.id).first()
        if delivery and delivery.status == "sent":
            continue
        if not delivery:
            delivery = MailingDelivery(campaign_id=campaign.id, subscriber_id=subscriber.id)
            db.session.add(delivery)
        unsubscribe_url = url_for("mailing_list.unsubscribe", token=subscriber.unsubscribe_token, _external=True)
        footer = f'<hr><p style="font-size:12px;color:#666">Ricevi questa email perche\' sei iscritto alla mailing list LD Enoteca. <a href="{unsubscribe_url}">Disiscriviti</a>.</p>'
        message = Message(subject=campaign.subject, recipients=[subscriber.email], html=campaign.html_body + footer)
        try:
            send_account_mail(campaign.account_code, message)
            delivery.status, delivery.sent_at, delivery.error_message = "sent", datetime.now(timezone.utc), None
        except Exception as exc:
            delivery.status, delivery.error_message = "failed", str(exc)[:1000]
        db.session.commit()
    campaign.sent_count = MailingDelivery.query.filter_by(campaign_id=campaign.id, status="sent").count()
    campaign.failed_count = MailingDelivery.query.filter_by(campaign_id=campaign.id, status="failed").count()
    campaign.status = "sent" if campaign.failed_count == 0 else "failed"
    campaign.completed_at = datetime.now(timezone.utc)
    db.session.commit()
    return {"campaign_id": campaign.id, "sent": campaign.sent_count, "failed": campaign.failed_count}
