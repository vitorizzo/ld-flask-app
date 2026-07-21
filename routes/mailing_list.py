from datetime import datetime, timezone

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from extensions import db
from models import EmailAccount, MailingCampaign, MailingSubscriber
from tools.role_required import role_required

mailing_list_bp = Blueprint("mailing_list", __name__)


@mailing_list_bp.route("/")
@login_required
@role_required(100)
def index():
    subscribers = MailingSubscriber.query.order_by(MailingSubscriber.created_at.desc()).limit(500).all()
    campaigns = MailingCampaign.query.order_by(MailingCampaign.created_at.desc()).limit(50).all()
    accounts = EmailAccount.query.filter_by(is_enabled=True).order_by(EmailAccount.name).all()
    return render_template("mailing_list/index.html", subscribers=subscribers, campaigns=campaigns, accounts=accounts)


@mailing_list_bp.post("/subscribers")
@login_required
@role_required(100)
def add_subscriber():
    email = (request.form.get("email") or "").strip()
    normalized = email.casefold()
    if not email or "@" not in email:
        flash("Inserisci un indirizzo email valido.", "warning")
        return redirect(url_for("mailing_list.index"))
    subscriber = MailingSubscriber.query.filter(func.lower(MailingSubscriber.email) == normalized).first()
    now = datetime.now(timezone.utc)
    if subscriber:
        subscriber.email, subscriber.name, subscriber.status = email, (request.form.get("name") or "").strip() or None, "subscribed"
        subscriber.consent_at, subscriber.unsubscribed_at = now, None
    else:
        subscriber = MailingSubscriber(email=email, email_normalized=normalized, name=(request.form.get("name") or "").strip() or None, consent_at=now)
        db.session.add(subscriber)
    db.session.commit()
    flash("Iscritto salvato.", "success")
    return redirect(url_for("mailing_list.index"))


@mailing_list_bp.post("/subscribers/<int:subscriber_id>/toggle")
@login_required
@role_required(100)
def toggle_subscriber(subscriber_id):
    subscriber = MailingSubscriber.query.get_or_404(subscriber_id)
    now = datetime.now(timezone.utc)
    if subscriber.status == "subscribed":
        subscriber.status, subscriber.unsubscribed_at = "unsubscribed", now
    else:
        subscriber.status, subscriber.consent_at, subscriber.unsubscribed_at = "subscribed", now, None
    db.session.commit()
    return redirect(url_for("mailing_list.index"))


@mailing_list_bp.post("/campaigns")
@login_required
@role_required(100)
def create_campaign():
    subject = (request.form.get("subject") or "").strip()
    body = (request.form.get("html_body") or "").strip()
    if not subject or not body:
        flash("Oggetto e contenuto sono obbligatori.", "warning")
        return redirect(url_for("mailing_list.index"))
    campaign = MailingCampaign(subject=subject, html_body=body, account_code=(request.form.get("account_code") or "general").strip(), created_by_user_id=current_user.id)
    db.session.add(campaign)
    db.session.commit()
    flash("Campagna salvata come bozza.", "success")
    return redirect(url_for("mailing_list.index"))


@mailing_list_bp.post("/campaigns/<int:campaign_id>/send")
@login_required
@role_required(100)
def send_campaign(campaign_id):
    campaign = MailingCampaign.query.get_or_404(campaign_id)
    if campaign.status not in {"draft", "failed"}:
        flash("Questa campagna e' gia' in lavorazione o completata.", "warning")
    else:
        from config.tasks import send_mailing_campaign_task
        campaign.status = "queued"
        db.session.commit()
        try:
            send_mailing_campaign_task.delay(campaign.id)
            flash("Campagna accodata per l'invio.", "success")
        except Exception:
            campaign.status = "draft"
            db.session.commit()
            flash("Impossibile accodare la campagna: servizio task non disponibile.", "warning")
    return redirect(url_for("mailing_list.index"))


@mailing_list_bp.route("/unsubscribe/<token>", methods=["GET", "POST"])
def unsubscribe(token):
    subscriber = MailingSubscriber.query.filter_by(unsubscribe_token=token).first_or_404()
    if request.method == "POST" and subscriber.status != "unsubscribed":
        subscriber.status = "unsubscribed"
        subscriber.unsubscribed_at = datetime.now(timezone.utc)
        db.session.commit()
    return render_template("mailing_list/unsubscribe.html", subscriber=subscriber)
