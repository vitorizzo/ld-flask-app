from datetime import datetime, timezone

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from flask_mail import Message
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from extensions import db
from models import (
    CustomerCollaboratorActivationRequest,
    CustomerRegistryMembership,
    RoleActivationRequest,
    SupportTicket,
    SupportTicketMessage,
    User,
)
from tools.customer_memberships import (
    ACCESS_ADMINISTRATION,
    ACCESS_BOTH,
    ACCESS_MANAGEMENT,
    active_customer_memberships,
    normalize_access_scope,
)
from tools.log_utils import get_logger
from tools.mail_accounts import assistance_mail_sender, send_assistance_mail


customer_collaborators_bp = Blueprint("customer_collaborators", __name__)
logger = get_logger("customer_collaborators")
ASSISTANCE_EMAIL = "assistenza.ldapp@ldenoteca.it"
ACCESS_OPTIONS = (
    (ACCESS_BOTH, "Amministrazione e gestione ordini"),
    (ACCESS_ADMINISTRATION, "Solo amministrazione"),
    (ACCESS_MANAGEMENT, "Solo gestione ordini"),
)


def _authorized_memberships():
    if not current_user.has_active_role("customer_horeca"):
        return []
    return active_customer_memberships(current_user, capability=ACCESS_ADMINISTRATION)


def _registry_label(registry):
    return registry.display_name or registry.legal_name or registry.source_code or f"Cliente #{registry.id}"


@customer_collaborators_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    memberships = _authorized_memberships()
    if not memberships:
        flash("Per richiedere collaboratori serve il permesso di amministrazione su almeno un cliente.", "warning")
        return redirect(url_for("home"))

    allowed_registries = {membership.registry_id: membership.registry for membership in memberships}
    if request.method == "POST":
        action = (request.form.get("action") or "create").strip().lower()
        if action == "cancel":
            activation = CustomerCollaboratorActivationRequest.query.filter_by(
                id=request.form.get("request_id", type=int),
                requester_user_id=current_user.id,
                status="pending",
            ).first()
            if activation:
                activation.status = "cancelled"
                activation.reviewed_at = datetime.now(timezone.utc)
                if activation.support_ticket:
                    activation.support_ticket.status = "closed"
                    activation.support_ticket.closed_at = datetime.now(timezone.utc)
                    if activation.support_ticket.role_activation_request:
                        activation.support_ticket.role_activation_request.status = "cancelled"
                db.session.commit()
                flash("Richiesta collaboratore annullata.", "success")
            else:
                flash("La richiesta non è più annullabile.", "warning")
            return redirect(url_for("customer_collaborators.index"))

        registry_id = request.form.get("registry_id", type=int)
        registry = allowed_registries.get(registry_id)
        collaborator_email = (request.form.get("collaborator_email") or "").strip().lower()
        raw_scope = (request.form.get("access_scope") or "").strip().lower()
        notes = (request.form.get("notes") or "").strip()[:2000] or None
        if not registry:
            flash("Seleziona un'attività che puoi amministrare.", "warning")
            return redirect(url_for("customer_collaborators.index"))
        if raw_scope not in {ACCESS_ADMINISTRATION, ACCESS_MANAGEMENT, ACCESS_BOTH}:
            flash("Seleziona permessi validi.", "warning")
            return redirect(url_for("customer_collaborators.index"))
        collaborator = User.query.filter(func.lower(User.email) == collaborator_email).first()
        if collaborator is None:
            flash("L'email indicata non appartiene ancora a un utente LDApp registrato.", "warning")
            return redirect(url_for("customer_collaborators.index"))
        if collaborator.id == current_user.id:
            flash("Sei già collegato a questa attività.", "warning")
            return redirect(url_for("customer_collaborators.index"))

        existing_membership = CustomerRegistryMembership.query.filter_by(
            user_id=collaborator.id,
            registry_id=registry.id,
            status="active",
        ).first()
        if existing_membership:
            flash("Questo utente è già associato all'attività. I permessi possono essere modificati dallo staff.", "info")
            return redirect(url_for("customer_collaborators.index"))
        duplicate = CustomerCollaboratorActivationRequest.query.filter_by(
            collaborator_user_id=collaborator.id,
            registry_id=registry.id,
            status="pending",
        ).first()
        if duplicate:
            flash("Esiste già una richiesta in attesa per questo collaboratore e questa attività.", "info")
            return redirect(url_for("customer_collaborators.index"))

        scope = normalize_access_scope(raw_scope)
        role_request = RoleActivationRequest(
            user=collaborator,
            requested_role="customer_horeca",
            notes=f"Richiesta collaboratore inviata da {current_user.email} per cliente #{registry.id}.",
        )
        db.session.add(role_request)
        db.session.flush()
        ticket = SupportTicket(
            ticket_type="horeca_collaborator_activation",
            status="open",
            subject=f"Attivazione collaboratore Horeca - {_registry_label(registry)}",
            reply_email=collaborator.email,
            user=collaborator,
            role_activation_request=role_request,
        )
        db.session.add(ticket)
        db.session.flush()
        activation = CustomerCollaboratorActivationRequest(
            requester=current_user,
            collaborator=collaborator,
            registry=registry,
            support_ticket=ticket,
            access_scope=scope,
            notes=notes,
        )
        db.session.add(activation)
        db.session.add(SupportTicketMessage(
            ticket_id=ticket.id,
            sender_type="user",
            sender_user_id=current_user.id,
            email_from=current_user.email,
            email_to=ASSISTANCE_EMAIL,
            body=(
                "Richiesta di attivazione collaboratore Horeca.\n\n"
                f"Attività: {_registry_label(registry)}\n"
                f"Codice cliente: {registry.source_code or '-'}\n"
                f"Richiedente: {current_user.name} {current_user.surname} <{current_user.email}>\n"
                f"Collaboratore: {collaborator.name} {collaborator.surname} <{collaborator.email}>\n"
                f"Permessi richiesti: {dict(ACCESS_OPTIONS)[scope]}\n"
                f"Note: {notes or '-'}"
            ),
        ))
        message = Message(
            subject=ticket.subject,
            sender=assistance_mail_sender(),
            recipients=[ASSISTANCE_EMAIL],
            reply_to=current_user.email,
            body=(
                "Nuova richiesta di attivazione collaboratore Horeca.\n\n"
                f"Ticket: #{ticket.id}\n"
                f"Attività: {_registry_label(registry)}\n"
                f"Codice cliente: {registry.source_code or '-'}\n"
                f"Richiedente: {current_user.name} {current_user.surname} <{current_user.email}>\n"
                f"Collaboratore già registrato: {collaborator.name} {collaborator.surname} <{collaborator.email}>\n"
                f"Permessi richiesti: {dict(ACCESS_OPTIONS)[scope]}\n"
                f"Note: {notes or '-'}"
            ),
        )
        try:
            send_assistance_mail(message)
            db.session.commit()
            flash("Richiesta inviata. Il collegamento sarà attivo solo dopo la verifica dello staff.", "success")
        except Exception as exc:
            db.session.rollback()
            logger.exception("Errore invio richiesta collaboratore Horeca")
            flash(f"Impossibile inviare la richiesta: {exc}", "danger")
        return redirect(url_for("customer_collaborators.index"))

    requests = (
        CustomerCollaboratorActivationRequest.query
        .options(
            joinedload(CustomerCollaboratorActivationRequest.collaborator),
            joinedload(CustomerCollaboratorActivationRequest.registry),
            joinedload(CustomerCollaboratorActivationRequest.support_ticket),
        )
        .filter(CustomerCollaboratorActivationRequest.requester_user_id == current_user.id)
        .order_by(CustomerCollaboratorActivationRequest.created_at.desc())
        .limit(100)
        .all()
    )
    active_links = (
        CustomerRegistryMembership.query
        .options(
            joinedload(CustomerRegistryMembership.user),
            joinedload(CustomerRegistryMembership.registry),
        )
        .filter(
            CustomerRegistryMembership.registry_id.in_(allowed_registries),
            CustomerRegistryMembership.status == "active",
            CustomerRegistryMembership.user_id != current_user.id,
        )
        .order_by(CustomerRegistryMembership.registry_id, CustomerRegistryMembership.created_at)
        .all()
    )
    return render_template(
        "customer_collaborators/index.html",
        memberships=memberships,
        requests=requests,
        active_links=active_links,
        access_options=ACCESS_OPTIONS,
        access_labels=dict(ACCESS_OPTIONS),
    )
