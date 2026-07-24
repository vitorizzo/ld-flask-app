from datetime import datetime, timezone

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from extensions import db
from models import (
    BusinessRegistry,
    EmailAccount,
    MailingCampaign,
    MailingList,
    MailingListMember,
    MailingSubscriber,
    Role,
    User,
)
from tools.role_required import role_required

mailing_list_bp = Blueprint("mailing_list", __name__)


def _ensure_system_lists():
    definitions = (("Clienti", "customers"), ("Utenti APP", "users"))
    changed = False
    for name, source_type in definitions:
        if not MailingList.query.filter_by(name=name).first():
            db.session.add(MailingList(name=name, source_type=source_type, is_system=True))
            changed = True
    if changed:
        db.session.commit()


def _subscriber_for(email, name, source):
    normalized = (email or "").strip().casefold()
    if not normalized or "@" not in normalized:
        return None
    subscriber = MailingSubscriber.query.filter_by(email_normalized=normalized).first()
    if not subscriber:
        subscriber = MailingSubscriber(
            email=email.strip(),
            email_normalized=normalized,
            name=(name or "").strip() or None,
            source=source,
        )
        db.session.add(subscriber)
        db.session.flush()
    else:
        subscriber.email = email.strip()
        if name:
            subscriber.name = name.strip()
    return subscriber


def _activate_member(mailing_list, subscriber, source_type, source_entity_id=None):
    member = MailingListMember.query.filter_by(
        mailing_list_id=mailing_list.id,
        subscriber_id=subscriber.id,
    ).first()
    if not member:
        member = MailingListMember(
            mailing_list_id=mailing_list.id,
            subscriber_id=subscriber.id,
            source_type=source_type,
            source_entity_id=source_entity_id,
        )
        db.session.add(member)
    member.source_type = source_type
    member.source_entity_id = source_entity_id
    member.is_active = True


def _sync_customers(mailing_list):
    config = mailing_list.filter_config or {}
    selected = {
        (str(item.get("category_code") or ""), str(item.get("subcategory_code") or ""))
        for item in config.get("clusters", [])
    }
    registries = BusinessRegistry.query.filter_by(kind="customer", is_active=True).all()
    count = 0
    for registry in registries:
        cluster = (registry.category_code or "", registry.subcategory_code or "")
        if selected and cluster not in selected:
            continue
        for contact in registry.contacts:
            if contact.contact_type not in {"email", "pec"}:
                continue
            subscriber = _subscriber_for(contact.value, registry.display_name, "customers")
            if subscriber:
                _activate_member(mailing_list, subscriber, "customer", registry.id)
                count += 1
    return count


def _sync_users(mailing_list):
    selected_role_ids = {int(value) for value in (mailing_list.filter_config or {}).get("role_ids", [])}
    count = 0
    for user in User.query.all():
        active_role_ids = {role.id for role in user.active_roles}
        if selected_role_ids and not active_role_ids.intersection(selected_role_ids):
            continue
        subscriber = _subscriber_for(user.email, f"{user.name} {user.surname}", "users")
        if subscriber:
            _activate_member(mailing_list, subscriber, "user", user.id)
            count += 1
    return count


def _sync_list(mailing_list):
    MailingListMember.query.filter_by(mailing_list_id=mailing_list.id).update(
        {"is_active": False},
        synchronize_session=False,
    )
    if mailing_list.source_type == "customers":
        return _sync_customers(mailing_list)
    if mailing_list.source_type == "users":
        return _sync_users(mailing_list)
    return 0


@mailing_list_bp.route("/")
@login_required
@role_required(100)
def index():
    _ensure_system_lists()
    mailing_lists = MailingList.query.filter_by(is_active=True).order_by(MailingList.name).all()
    selected_id = request.args.get("list_id", type=int)
    selected_list = next((item for item in mailing_lists if item.id == selected_id), None)
    selected_list = selected_list or (mailing_lists[0] if mailing_lists else None)
    members = []
    if selected_list:
        members = (
            MailingListMember.query
            .filter_by(mailing_list_id=selected_list.id, is_active=True)
            .join(MailingSubscriber)
            .order_by(MailingSubscriber.email)
            .limit(1000)
            .all()
        )
    campaigns = MailingCampaign.query.order_by(MailingCampaign.created_at.desc()).limit(50).all()
    accounts = EmailAccount.query.filter_by(is_enabled=True).order_by(EmailAccount.name).all()
    clusters = (
        db.session.query(
            BusinessRegistry.category_code,
            BusinessRegistry.category_description,
            BusinessRegistry.subcategory_code,
            BusinessRegistry.subcategory_description,
        )
        .filter(BusinessRegistry.kind == "customer", BusinessRegistry.is_active.is_(True))
        .distinct()
        .order_by(BusinessRegistry.category_description, BusinessRegistry.subcategory_description)
        .all()
    )
    roles = Role.query.order_by(Role.name).all()
    selected_clusters = {
        f"{item.get('category_code') or ''}|{item.get('subcategory_code') or ''}"
        for item in ((selected_list.filter_config or {}).get("clusters", []) if selected_list else [])
    }
    selected_role_ids = {
        int(value)
        for value in ((selected_list.filter_config or {}).get("role_ids", []) if selected_list else [])
    }
    return render_template(
        "mailing_list/index.html",
        mailing_lists=mailing_lists,
        selected_list=selected_list,
        members=members,
        campaigns=campaigns,
        accounts=accounts,
        clusters=clusters,
        roles=roles,
        selected_clusters=selected_clusters,
        selected_role_ids=selected_role_ids,
    )


@mailing_list_bp.post("/lists")
@login_required
@role_required(100)
def create_list():
    name = (request.form.get("name") or "").strip()
    source_type = (request.form.get("source_type") or "manual").strip()
    if not name or source_type not in {"manual", "customers", "users"}:
        flash("Nome o origine della lista non validi.", "warning")
        return redirect(url_for("mailing_list.index"))
    if MailingList.query.filter(func.lower(MailingList.name) == name.casefold()).first():
        flash("Esiste già una lista con questo nome.", "warning")
        return redirect(url_for("mailing_list.index"))
    mailing_list = MailingList(name=name, source_type=source_type)
    db.session.add(mailing_list)
    db.session.commit()
    flash("Mailing list creata.", "success")
    return redirect(url_for("mailing_list.index", list_id=mailing_list.id))


@mailing_list_bp.post("/lists/<int:list_id>/sync")
@login_required
@role_required(100)
def sync_list(list_id):
    mailing_list = MailingList.query.get_or_404(list_id)
    count = _sync_list(mailing_list)
    db.session.commit()
    flash(f"Lista sincronizzata: {count} indirizzi elaborati.", "success")
    return redirect(url_for("mailing_list.index", list_id=mailing_list.id))


@mailing_list_bp.post("/lists/<int:list_id>/filters")
@login_required
@role_required(100)
def update_filters(list_id):
    mailing_list = MailingList.query.get_or_404(list_id)
    if mailing_list.source_type == "customers":
        clusters = []
        for value in request.form.getlist("clusters"):
            category_code, _, subcategory_code = value.partition("|")
            clusters.append({"category_code": category_code, "subcategory_code": subcategory_code})
        mailing_list.filter_config = {"clusters": clusters}
    elif mailing_list.source_type == "users":
        mailing_list.filter_config = {"role_ids": request.form.getlist("role_ids", type=int)}
    count = _sync_list(mailing_list)
    db.session.commit()
    flash(f"Filtri applicati: {count} indirizzi elaborati.", "success")
    return redirect(url_for("mailing_list.index", list_id=mailing_list.id))


@mailing_list_bp.post("/subscribers")
@login_required
@role_required(100)
def add_subscriber():
    list_id = request.form.get("mailing_list_id", type=int)
    mailing_list = MailingList.query.get_or_404(list_id)
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
        db.session.flush()
    _activate_member(mailing_list, subscriber, "manual")
    db.session.commit()
    flash("Iscritto salvato.", "success")
    return redirect(url_for("mailing_list.index", list_id=mailing_list.id))


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
    return redirect(url_for("mailing_list.index", list_id=request.form.get("mailing_list_id", type=int)))


@mailing_list_bp.post("/campaigns")
@login_required
@role_required(100)
def create_campaign():
    subject = (request.form.get("subject") or "").strip()
    body = (request.form.get("html_body") or "").strip()
    if not subject or not body:
        flash("Oggetto e contenuto sono obbligatori.", "warning")
        return redirect(url_for("mailing_list.index"))
    mailing_list = MailingList.query.get_or_404(request.form.get("mailing_list_id", type=int))
    campaign = MailingCampaign(
        subject=subject,
        html_body=body,
        account_code=(request.form.get("account_code") or "general").strip(),
        mailing_list_id=mailing_list.id,
        created_by_user_id=current_user.id,
    )
    db.session.add(campaign)
    db.session.commit()
    flash("Campagna salvata come bozza.", "success")
    return redirect(url_for("mailing_list.index", list_id=mailing_list.id))


@mailing_list_bp.post("/campaigns/<int:campaign_id>/send")
@login_required
@role_required(100)
def send_campaign(campaign_id):
    campaign = MailingCampaign.query.get_or_404(campaign_id)
    if not campaign.mailing_list_id:
        flash("La campagna non è associata a una mailing list.", "warning")
    elif campaign.status not in {"draft", "failed"}:
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
