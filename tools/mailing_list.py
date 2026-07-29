import calendar
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import current_app
from flask_mail import Message

from extensions import db
from models import (
    MailingCampaign,
    MailingCampaignRun,
    MailingCampaignSchedule,
    MailingDelivery,
    MailingListMember,
    MailingSubscriber,
)
from tools.mail_accounts import send_account_mail
from tools.log_utils import get_logger


logger = get_logger("mailing_list")


def _attach_campaign_files(message, campaign):
    root = (Path(current_app.instance_path) / "mailing_attachments").resolve()
    for attachment in campaign.attachments:
        path = (root / attachment.storage_path).resolve()
        if root not in path.parents or not path.is_file():
            raise FileNotFoundError(f"Allegato non disponibile: {attachment.original_filename}")
        message.attach(
            attachment.original_filename,
            attachment.mime_type or "application/octet-stream",
            path.read_bytes(),
        )


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


def prepare_campaign(campaign, run=None):
    """Congela i destinatari della campagna prima che venga accodata."""
    delivery_query = MailingDelivery.query.filter_by(campaign_id=campaign.id)
    if run is not None:
        delivery_query = delivery_query.filter_by(run_id=run.id)
    else:
        delivery_query = delivery_query.filter(MailingDelivery.run_id.is_(None))
    existing = {
        delivery.subscriber_id: delivery
        for delivery in delivery_query.all()
    }
    if not existing:
        for subscriber in _eligible_subscribers(campaign):
            db.session.add(MailingDelivery(
                campaign_id=campaign.id,
                run_id=run.id if run else None,
                subscriber_id=subscriber.id,
                status="pending",
            ))
        db.session.flush()

    campaign.recipient_count = delivery_query.count()
    campaign.sent_count = delivery_query.filter_by(status="sent").count()
    campaign.failed_count = delivery_query.filter_by(status="failed").count()
    if run is not None:
        run.recipient_count = campaign.recipient_count
        run.sent_count = campaign.sent_count
        run.failed_count = campaign.failed_count
    logger.info(
        "Campagna preparata campaign_id=%s list_id=%s recipients=%s sent=%s failed=%s",
        campaign.id,
        campaign.mailing_list_id,
        campaign.recipient_count,
        campaign.sent_count,
        campaign.failed_count,
    )
    return campaign.recipient_count


def _finalize_campaign(campaign, run=None):
    delivery_query = MailingDelivery.query.filter_by(campaign_id=campaign.id)
    if run is not None:
        delivery_query = delivery_query.filter_by(run_id=run.id)
    campaign.sent_count = delivery_query.filter_by(status="sent").count()
    campaign.failed_count = delivery_query.filter_by(status="failed").count()
    pending_count = delivery_query.filter_by(status="pending").count()
    result_status = "sent" if campaign.failed_count == 0 and pending_count == 0 else "failed"
    campaign.status = (
        "draft"
        if run is not None and campaign.schedule and campaign.schedule.status == "active" and result_status == "sent"
        else result_status
    )
    campaign.completed_at = datetime.now(timezone.utc)
    if run is not None:
        run.status = result_status
        run.sent_count = campaign.sent_count
        run.failed_count = campaign.failed_count
        run.completed_at = campaign.completed_at
    db.session.commit()
    log_method = logger.warning if campaign.failed_count else logger.info
    log_method(
        "Campagna completata campaign_id=%s status=%s recipients=%s sent=%s failed=%s pending=%s",
        campaign.id,
        campaign.status,
        campaign.recipient_count,
        campaign.sent_count,
        campaign.failed_count,
        pending_count,
    )


def fail_campaign(campaign_id, error, run_id=None):
    db.session.rollback()
    campaign = db.session.get(MailingCampaign, campaign_id)
    if not campaign or campaign.status == "sent":
        return
    campaign.status = "failed"
    campaign.completed_at = datetime.now(timezone.utc)
    message = str(error)[:1000]
    delivery_query = MailingDelivery.query.filter_by(campaign_id=campaign.id, status="pending")
    if run_id is not None:
        delivery_query = delivery_query.filter_by(run_id=run_id)
    for delivery in delivery_query.all():
        delivery.status = "failed"
        delivery.error_message = message
    result_query = MailingDelivery.query.filter_by(campaign_id=campaign.id)
    if run_id is not None:
        result_query = result_query.filter_by(run_id=run_id)
    campaign.failed_count = result_query.filter_by(status="failed").count()
    campaign.sent_count = result_query.filter_by(status="sent").count()
    if run_id is not None:
        run = db.session.get(MailingCampaignRun, run_id)
        if run:
            run.status = "failed"
            run.failed_count = campaign.failed_count
            run.sent_count = campaign.sent_count
            run.completed_at = campaign.completed_at
            run.error_message = message
    db.session.commit()
    logger.error(
        "Campagna interrotta campaign_id=%s sent=%s failed=%s error=%s",
        campaign.id,
        campaign.sent_count,
        campaign.failed_count,
        message,
    )


def reset_campaign_delivery_state(campaign):
    if campaign.status in {"queued", "sending"}:
        raise ValueError("Non puoi azzerare una campagna mentre l'invio e' in corso.")
    MailingDelivery.query.filter_by(campaign_id=campaign.id, run_id=None).delete(synchronize_session=False)
    campaign.status = "draft"
    campaign.recipient_count = 0
    campaign.sent_count = 0
    campaign.failed_count = 0
    campaign.started_at = None
    campaign.completed_at = None
    db.session.flush()
    prepare_campaign(campaign)
    db.session.commit()
    logger.info(
        "Invio campagna azzerato campaign_id=%s list_id=%s recipients=%s",
        campaign.id,
        campaign.mailing_list_id,
        campaign.recipient_count,
    )
    return campaign.recipient_count


def send_campaign(campaign_id, run_id=None):
    campaign = db.session.get(MailingCampaign, campaign_id)
    run = db.session.get(MailingCampaignRun, run_id) if run_id is not None else None
    if not campaign or (run_id is not None and not run) or (run_id is None and campaign.status == "sent"):
        logger.info(
            "Campagna ignorata campaign_id=%s reason=%s",
            campaign_id,
            "not_found" if not campaign else "already_sent",
        )
        return {"campaign_id": campaign_id, "skipped": True}
    prepare_campaign(campaign, run=run)
    campaign.status = "sending"
    campaign.started_at = datetime.now(timezone.utc)
    campaign.completed_at = None
    if run is not None:
        run.status = "sending"
        run.started_at = campaign.started_at
    db.session.commit()
    logger.info(
        "Avvio campagna campaign_id=%s list_id=%s account=%s recipients=%s",
        campaign.id,
        campaign.mailing_list_id,
        campaign.account_code,
        campaign.recipient_count,
    )

    delivery_query = MailingDelivery.query.filter(
        MailingDelivery.campaign_id == campaign.id,
        MailingDelivery.status.in_(("pending", "failed")),
    )
    if run is not None:
        delivery_query = delivery_query.filter(MailingDelivery.run_id == run.id)
    deliveries = delivery_query.order_by(MailingDelivery.id).all()
    for delivery in deliveries:
        if delivery.status == "sent":
            continue
        subscriber = delivery.subscriber
        delivery.status = "pending"
        delivery.error_message = None
        db.session.commit()
        logger.info(
            "Tentativo consegna campaign_id=%s delivery_id=%s recipient=%s account=%s",
            campaign.id,
            delivery.id,
            subscriber.email,
            campaign.account_code,
        )
        unsubscribe_url = _unsubscribe_url(subscriber)
        footer = f'<hr><p style="font-size:12px;color:#666">Ricevi questa email perche\' sei iscritto alla mailing list LD Enoteca. <a href="{unsubscribe_url}">Disiscriviti</a>.</p>'
        message = Message(subject=campaign.subject, recipients=[subscriber.email], html=campaign.html_body + footer)
        try:
            _attach_campaign_files(message, campaign)
            smtp_result = send_account_mail(campaign.account_code, message)
            delivery.status, delivery.sent_at, delivery.error_message = "sent", datetime.now(timezone.utc), None
            logger.info(
                "Consegna accettata da SMTP campaign_id=%s delivery_id=%s recipient=%s accepted=%s refused=%s",
                campaign.id,
                delivery.id,
                subscriber.email,
                smtp_result.get("accepted", []) if smtp_result else [subscriber.email],
                smtp_result.get("refused", {}) if smtp_result else {},
            )
        except Exception as exc:
            delivery.status, delivery.error_message = "failed", str(exc)[:1000]
            logger.exception(
                "Consegna fallita campaign_id=%s delivery_id=%s recipient=%s account=%s",
                campaign.id,
                delivery.id,
                subscriber.email,
                campaign.account_code,
            )
        db.session.commit()
    _finalize_campaign(campaign, run=run)
    return {
        "campaign_id": campaign.id,
        "run_id": run.id if run else None,
        "sent": campaign.sent_count,
        "failed": campaign.failed_count,
    }


def _advance_datetime(value, interval_value, interval_unit):
    if interval_unit == "day":
        return value + timedelta(days=interval_value)
    if interval_unit == "week":
        return value + timedelta(weeks=interval_value)
    if interval_unit == "month":
        month_index = value.month - 1 + interval_value
        year = value.year + month_index // 12
        month = month_index % 12 + 1
        day = min(value.day, calendar.monthrange(year, month)[1])
        return value.replace(year=year, month=month, day=day)
    raise ValueError("Unità di ciclicità non valida.")


def _next_schedule_date(schedule, current_date):
    if schedule.mode == "single":
        return None
    candidate = _advance_datetime(current_date, schedule.interval_value, schedule.interval_unit)
    completed_after_run = schedule.completed_runs + 1
    if schedule.mode == "multiple" and completed_after_run >= schedule.max_runs:
        return None
    if schedule.mode == "until" and candidate > schedule.ends_at:
        return None
    return candidate


def dispatch_due_mailing_schedules():
    now = datetime.now(timezone.utc)
    schedules = (
        MailingCampaignSchedule.query
        .filter(
            MailingCampaignSchedule.status == "active",
            MailingCampaignSchedule.next_run_at.isnot(None),
            MailingCampaignSchedule.next_run_at <= now,
        )
        .with_for_update(skip_locked=True)
        .all()
    )
    queued = []
    for schedule in schedules:
        campaign = schedule.campaign
        if campaign.status in {"queued", "sending"}:
            continue
        if schedule.mode == "until" and schedule.ends_at and now > schedule.ends_at:
            schedule.status = "completed"
            schedule.next_run_at = None
            logger.info(
                "Pianificazione mailing terminata senza invio fuori finestra campaign_id=%s schedule_id=%s",
                campaign.id,
                schedule.id,
            )
            continue
        scheduled_for = schedule.next_run_at
        run_number = (
            db.session.query(db.func.coalesce(db.func.max(MailingCampaignRun.run_number), 0))
            .filter(MailingCampaignRun.campaign_id == campaign.id)
            .scalar()
            + 1
        )
        run = MailingCampaignRun(
            campaign_id=campaign.id,
            run_number=run_number,
            trigger_type="scheduled",
            scheduled_for=scheduled_for,
            status="pending",
        )
        db.session.add(run)
        db.session.flush()
        prepare_campaign(campaign, run=run)
        run.status = "queued"
        campaign.status = "queued"
        schedule.last_run_at = now
        schedule.next_run_at = _next_schedule_date(schedule, max(scheduled_for, now))
        schedule.completed_runs += 1
        if schedule.next_run_at is None:
            schedule.status = "completed"
        queued.append((campaign.id, run.id))
    db.session.commit()

    from config.tasks import send_mailing_campaign_task
    for campaign_id, run_id in queued:
        try:
            send_mailing_campaign_task.delay(campaign_id, run_id)
            logger.info("Esecuzione mailing programmata accodata campaign_id=%s run_id=%s", campaign_id, run_id)
        except Exception as exc:
            logger.exception(
                "Accodamento esecuzione programmata fallito campaign_id=%s run_id=%s",
                campaign_id,
                run_id,
            )
            fail_campaign(campaign_id, exc, run_id=run_id)
    return {"queued": len(queued), "runs": [run_id for _, run_id in queued]}
