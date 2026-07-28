from datetime import datetime, timezone

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from extensions import db
from models import (
    BusinessRegistry,
    EmailAccount,
    MailingCampaign,
    MailingDelivery,
    MailingList,
    MailingListMember,
    MailingSubscriber,
    Role,
    User,
)
from tools.role_required import role_required
from tools.log_utils import get_logger

mailing_list_bp = Blueprint("mailing_list", __name__)
logger = get_logger("mailing_list")


def _delivery_error_kind(message):
    normalized = (message or "").casefold()
    if "unable to build urls" in normalized or "server_name" in normalized:
        return "Configurazione link pubblico"
    if "authentication" in normalized or "authenticate" in normalized or "smtp 535" in normalized:
        return "Autenticazione SMTP"
    if "recipient" in normalized or "recipientsrefused" in normalized or "smtp 550" in normalized:
        return "Destinatario rifiutato"
    if "timed out" in normalized or "timeout" in normalized or "connection" in normalized:
        return "Connessione SMTP"
    return "Errore di invio"


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
        (
            str(item.get("category_code") or ""),
            str(item.get("subcategory_description") or item.get("subcategory_code") or ""),
        )
        for item in config.get("clusters", [])
    }
    selection_is_explicit = config.get("filter_mode") == "selected" or bool(config.get("clusters"))
    registries = BusinessRegistry.query.filter_by(kind="customer", is_active=True).all()
    count = 0
    for registry in registries:
        cluster = (registry.category_code or "", registry.subcategory_description or "")
        if selection_is_explicit and cluster not in selected:
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


def _customer_filter_tree():
    rows = (
        db.session.query(
            BusinessRegistry.category_code,
            BusinessRegistry.category_description,
            BusinessRegistry.subcategory_description,
            func.count(BusinessRegistry.id),
        )
        .filter(BusinessRegistry.kind == "customer", BusinessRegistry.is_active.is_(True))
        .group_by(
            BusinessRegistry.category_code,
            BusinessRegistry.category_description,
            BusinessRegistry.subcategory_description,
        )
        .all()
    )
    grouped = {}
    for category_code, category_description, subcategory_description, customer_count in rows:
        category_key = category_code or ""
        subcategory_key = subcategory_description or ""
        category = grouped.setdefault(category_key, {
            "code": category_key,
            "label": category_description or category_key or "Senza categoria",
            "customer_count": 0,
            "subcategories": {},
        })
        category["customer_count"] += int(customer_count or 0)
        subcategory = category["subcategories"].setdefault(subcategory_key, {
            "code": subcategory_key,
            "label": subcategory_key or "Senza sottocategoria",
            "value": f"{category_key}|{subcategory_key}",
            "customer_count": 0,
        })
        subcategory["customer_count"] += int(customer_count or 0)

    tree = list(grouped.values())
    tree.sort(key=lambda item: item["label"].casefold())
    for category in tree:
        category["subcategories"] = list(category["subcategories"].values())
        category["subcategories"].sort(key=lambda item: item["label"].casefold())
    return tree


def _customer_filter_config(values):
    clusters = []
    for value in values:
        category_code, separator, subcategory_description = value.partition("|")
        if separator:
            clusters.append({
                "category_code": category_code,
                "subcategory_description": subcategory_description,
            })
    return {"filter_mode": "selected", "clusters": clusters}


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
    active_campaigns = [
        campaign
        for campaign in campaigns
        if campaign.status in {"draft", "queued", "sending", "failed"}
    ]
    campaign_errors = {}
    campaign_ids = [campaign.id for campaign in campaigns]
    if campaign_ids:
        failed_deliveries = (
            MailingDelivery.query
            .filter(
                MailingDelivery.campaign_id.in_(campaign_ids),
                MailingDelivery.status == "failed",
            )
            .join(MailingSubscriber)
            .order_by(MailingDelivery.campaign_id.desc(), MailingSubscriber.email)
            .all()
        )
        for delivery in failed_deliveries:
            campaign_errors.setdefault(delivery.campaign_id, []).append({
                "delivery": delivery,
                "kind": _delivery_error_kind(delivery.error_message),
            })
    accounts = EmailAccount.query.filter_by(is_enabled=True).order_by(EmailAccount.name).all()
    customer_filter_tree = _customer_filter_tree()
    roles = Role.query.order_by(Role.name).all()
    selected_filter_config = (selected_list.filter_config or {}) if selected_list else {}
    selected_clusters = {
        (
            f"{item.get('category_code') or ''}|"
            f"{item.get('subcategory_description') or item.get('subcategory_code') or ''}"
        )
        for item in (selected_filter_config.get("clusters", []) if selected_list else [])
    }
    if (
        selected_list
        and selected_list.source_type == "customers"
        and selected_filter_config.get("filter_mode") != "selected"
        and not selected_clusters
    ):
        selected_clusters = {
            subcategory["value"]
            for category in customer_filter_tree
            for subcategory in category["subcategories"]
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
        active_campaigns=active_campaigns,
        campaign_errors=campaign_errors,
        accounts=accounts,
        customer_filter_tree=customer_filter_tree,
        roles=roles,
        selected_clusters=selected_clusters,
        selected_role_ids=selected_role_ids,
        requested_modal=request.args.get("modal") if request.args.get("modal") in {"lists", "campaigns"} else None,
    )


@mailing_list_bp.post("/lists")
@login_required
@role_required(100)
def create_list():
    name = (request.form.get("name") or "").strip()
    source_type = (request.form.get("source_type") or "manual").strip()
    if not name or source_type not in {"manual", "customers", "users"}:
        flash("Nome o origine della lista non validi.", "warning")
        return redirect(url_for("mailing_list.index", modal="lists"))
    if MailingList.query.filter(func.lower(MailingList.name) == name.casefold()).first():
        flash("Esiste già una lista con questo nome.", "warning")
        return redirect(url_for("mailing_list.index", modal="lists"))
    mailing_list = MailingList(name=name, source_type=source_type)
    db.session.add(mailing_list)
    db.session.commit()
    logger.info(
        "Mailing list creata list_id=%s name=%s source_type=%s user_id=%s",
        mailing_list.id,
        mailing_list.name,
        mailing_list.source_type,
        current_user.id,
    )
    flash("Mailing list creata.", "success")
    return redirect(url_for("mailing_list.index", list_id=mailing_list.id, modal="lists"))


@mailing_list_bp.post("/lists/<int:list_id>/sync")
@login_required
@role_required(100)
def sync_list(list_id):
    mailing_list = MailingList.query.get_or_404(list_id)
    count = _sync_list(mailing_list)
    db.session.commit()
    logger.info(
        "Mailing list sincronizzata list_id=%s source_type=%s processed=%s user_id=%s",
        mailing_list.id,
        mailing_list.source_type,
        count,
        current_user.id,
    )
    flash(f"Lista sincronizzata: {count} indirizzi elaborati.", "success")
    return redirect(url_for("mailing_list.index", list_id=mailing_list.id, modal="lists"))


@mailing_list_bp.post("/lists/<int:list_id>/filters")
@login_required
@role_required(100)
def update_filters(list_id):
    mailing_list = MailingList.query.get_or_404(list_id)
    if mailing_list.source_type == "customers":
        mailing_list.filter_config = _customer_filter_config(request.form.getlist("clusters"))
    elif mailing_list.source_type == "users":
        mailing_list.filter_config = {"role_ids": request.form.getlist("role_ids", type=int)}
    count = _sync_list(mailing_list)
    db.session.commit()
    logger.info(
        "Filtri mailing applicati list_id=%s source_type=%s processed=%s user_id=%s",
        mailing_list.id,
        mailing_list.source_type,
        count,
        current_user.id,
    )
    flash(f"Filtri applicati: {count} indirizzi elaborati.", "success")
    return redirect(url_for("mailing_list.index", list_id=mailing_list.id, modal="lists"))


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
        return redirect(url_for("mailing_list.index", list_id=mailing_list.id, modal="lists"))
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
    logger.info(
        "Iscritto aggiunto list_id=%s subscriber_id=%s email=%s user_id=%s",
        mailing_list.id,
        subscriber.id,
        subscriber.email,
        current_user.id,
    )
    flash("Iscritto salvato.", "success")
    return redirect(url_for("mailing_list.index", list_id=mailing_list.id, modal="lists"))


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
    logger.info(
        "Stato iscritto modificato subscriber_id=%s email=%s status=%s user_id=%s",
        subscriber.id,
        subscriber.email,
        subscriber.status,
        current_user.id,
    )
    return redirect(url_for(
        "mailing_list.index",
        list_id=request.form.get("mailing_list_id", type=int),
        modal="lists",
    ))


@mailing_list_bp.post("/campaigns")
@login_required
@role_required(100)
def create_campaign():
    from tools.mailing_list import prepare_campaign

    subject = (request.form.get("subject") or "").strip()
    body = (request.form.get("html_body") or "").strip()
    if not subject or not body:
        flash("Oggetto e contenuto sono obbligatori.", "warning")
        return redirect(url_for("mailing_list.index", modal="campaigns"))
    mailing_list = MailingList.query.get_or_404(request.form.get("mailing_list_id", type=int))
    campaign = MailingCampaign(
        subject=subject,
        html_body=body,
        account_code=(request.form.get("account_code") or "general").strip(),
        mailing_list_id=mailing_list.id,
        created_by_user_id=current_user.id,
    )
    db.session.add(campaign)
    db.session.flush()
    prepare_campaign(campaign)
    db.session.commit()
    logger.info(
        "Campagna creata campaign_id=%s list_id=%s account=%s recipients=%s user_id=%s",
        campaign.id,
        campaign.mailing_list_id,
        campaign.account_code,
        campaign.recipient_count,
        current_user.id,
    )
    flash(f"Campagna salvata come bozza con {campaign.recipient_count} destinatari.", "success")
    return redirect(url_for("mailing_list.index", list_id=mailing_list.id, modal="campaigns"))


@mailing_list_bp.post("/campaigns/<int:campaign_id>/send")
@login_required
@role_required(100)
def send_campaign(campaign_id):
    from tools.mailing_list import prepare_campaign

    campaign = MailingCampaign.query.get_or_404(campaign_id)
    if not campaign.mailing_list_id:
        flash("La campagna non è associata a una mailing list.", "warning")
    elif campaign.status not in {"draft", "failed"}:
        flash("Questa campagna e' gia' in lavorazione o completata.", "warning")
    else:
        from config.tasks import send_mailing_campaign_task
        prepare_campaign(campaign)
        if campaign.recipient_count == 0:
            db.session.commit()
            flash("La lista selezionata non contiene destinatari attivi.", "warning")
            return redirect(url_for("mailing_list.index", list_id=campaign.mailing_list_id))
        campaign.status = "queued"
        campaign.completed_at = None
        db.session.commit()
        try:
            send_mailing_campaign_task.delay(campaign.id)
            logger.info(
                "Campagna accodata campaign_id=%s list_id=%s account=%s recipients=%s user_id=%s",
                campaign.id,
                campaign.mailing_list_id,
                campaign.account_code,
                campaign.recipient_count,
                current_user.id,
            )
            flash("Campagna accodata per l'invio.", "success")
        except Exception:
            logger.exception(
                "Accodamento campagna fallito campaign_id=%s user_id=%s",
                campaign.id,
                current_user.id,
            )
            campaign.status = "draft"
            db.session.commit()
            flash("Impossibile accodare la campagna: servizio task non disponibile.", "warning")
    return redirect(url_for("mailing_list.index"))


@mailing_list_bp.post("/campaigns/<int:campaign_id>/reset")
@login_required
@role_required(100)
def reset_campaign(campaign_id):
    from tools.mailing_list import reset_campaign_delivery_state

    campaign = MailingCampaign.query.get_or_404(campaign_id)
    try:
        recipient_count = reset_campaign_delivery_state(campaign)
    except ValueError as exc:
        flash(str(exc), "warning")
        return redirect(url_for("mailing_list.index", list_id=campaign.mailing_list_id))
    logger.info(
        "Reset campagna richiesto campaign_id=%s recipients=%s user_id=%s",
        campaign.id,
        recipient_count,
        current_user.id,
    )
    flash(
        f"Invio azzerato. La campagna e' tornata in bozza con {recipient_count} destinatari.",
        "success",
    )
    return redirect(url_for("mailing_list.index", list_id=campaign.mailing_list_id))


@mailing_list_bp.route("/unsubscribe/<token>", methods=["GET", "POST"])
def unsubscribe(token):
    subscriber = MailingSubscriber.query.filter_by(unsubscribe_token=token).first_or_404()
    if request.method == "POST" and subscriber.status != "unsubscribed":
        subscriber.status = "unsubscribed"
        subscriber.unsubscribed_at = datetime.now(timezone.utc)
        db.session.commit()
        logger.info(
            "Disiscrizione completata subscriber_id=%s email=%s",
            subscriber.id,
            subscriber.email,
        )
    return render_template("mailing_list/unsubscribe.html", subscriber=subscriber)
