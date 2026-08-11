from flask import request, flash, render_template, Blueprint, jsonify, redirect, current_app, url_for, send_from_directory
from flask_login import current_user, login_required
from flask_mail import Message
from flask_socketio import SocketIO
from sqlalchemy import and_, asc, inspect, or_, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload, load_only
from werkzeug.utils import secure_filename
import os
import re
import secrets
import uuid
from urllib.parse import quote, unquote, urlparse
from dotenv import dotenv_values, set_key, unset_key

from extensions import db
from tools.mail_accounts import (
    SYSTEM_EMAIL_ACCOUNTS,
    assistance_mail_sender,
    get_email_account,
    send_account_mail,
    send_assistance_mail,
)
from tools.support_tickets import (
    mark_ticket_read_by_support,
    outbound_ticket_message_id,
    public_ticket_url,
    support_unread_count,
)
from models import (
    Menu,
    AppPreference,
    EmailAccount,
    Role,
    ImportConflict,
    ImportConflictResolution,
    Articoli,
    User,
    UserRole,
    SpecialPermission,
    UserSpecialPermission,
    PasswordResetToken,
    BusinessRegistry,
    RoleActivationRequest,
    SupportTicket,
    SupportTicketMessage,
    SupportTicketAttachment,
    CustomerOrderDeliveryOption,
    CashBank,
    PosCircuit,
    PosDevice,
    CashDeposit,
    CashIssuedCheck,
    CashSalePayment,
    PosMove,
    CashClosurePos,
    pos_device_circuits,
    CashSalePaymentPosMove,
)
from tools.role_required import role_required
from tools.preferences import (
    build_preferences_sections,
    get_definition_map,
    load_preferences_into_app_config,
    save_preferences_from_form,
)
from tools.matrixws_client import (
    MatrixWSConfig,
    MatrixWSError,
    call_sync as call_matrixws_sync,
    renew_secret as renew_matrixws_secret,
)
from tools.import_transfer_config import (
    available_export_files,
    available_trace_files,
    build_transfer_definitions,
    save_transfer_definitions,
)
from config.tasks import (
    import_anagrafiche_task,
    import_articoli_task,
    import_barcode_task,
    import_estratti_conto_clienti_task,
    import_giacenze_task,
    import_poleepo_products_task,
    import_ps_task,
)
from tools.ps_util import get_product_by_code
from tools.log_utils import log_task, get_logger
import hashlib
from datetime import datetime, date, time, timedelta, timezone

logger = get_logger('settings')

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')
socketio = SocketIO()
ASSISTANCE_EMAIL = "assistenza.ldapp@ldenoteca.it"
SUPPORT_ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".txt", ".doc", ".docx", ".xls", ".xlsx"}


def _form_bool(form, key, default=False):
    if key in form:
        value = str(form.get(key)).strip().lower()
        return value in {"1", "true", "on", "yes"}
    return bool(default)


def _parse_int(value, fallback=None):
    try:
        if value is None or str(value).strip() == "":
            return fallback
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _parse_date(value, fallback=None):
    raw = (value or "").strip()
    if not raw:
        return fallback
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return fallback


def _parse_datetime_date(value, *, end_of_day=False):
    parsed = _parse_date(value)
    if not parsed:
        return None
    return datetime.combine(parsed, time.max if end_of_day else time.min)


def _table_has_column(table_name, column_name):
    try:
        inspector = inspect(db.engine)
        return any(col["name"] == column_name for col in inspector.get_columns(table_name))
    except Exception:
        return False


_POS_SCHEMA_READY = None


def _ensure_pos_validity_schema():
    global _POS_SCHEMA_READY
    if _POS_SCHEMA_READY is not None:
        return _POS_SCHEMA_READY
    try:
        db.session.execute(text("ALTER TABLE pos_circuits ADD COLUMN IF NOT EXISTS valid_from DATE"))
        db.session.execute(text("ALTER TABLE pos_circuits ADD COLUMN IF NOT EXISTS valid_to DATE"))
        db.session.execute(text("ALTER TABLE pos_devices ADD COLUMN IF NOT EXISTS valid_from DATE"))
        db.session.execute(text("ALTER TABLE pos_devices ADD COLUMN IF NOT EXISTS valid_to DATE"))
        db.session.commit()
        _POS_SCHEMA_READY = True
    except Exception as exc:
        db.session.rollback()
        logger.warning("Schema POS validity non disponibile: %s", exc)
        _POS_SCHEMA_READY = False
    return _POS_SCHEMA_READY


def _selected_ids_from_form(form, key):
    raw_values = form.getlist(key) if hasattr(form, "getlist") else []
    ids = []
    for raw in raw_values:
        parsed = _parse_int(raw)
        if parsed is not None:
            ids.append(parsed)
    return ids


def _settings_upload_folder(*parts):
    base = current_app.config.get("UPLOAD_FOLDER")
    if not base:
        base = os.path.join(current_app.root_path, "static", "uploads")
    folder = os.path.join(base, *parts)
    os.makedirs(folder, exist_ok=True)
    return folder


def _save_uploaded_logo(file_storage, prefix="logo", folder_name="pos"):
    if not file_storage or not getattr(file_storage, "filename", ""):
        return None
    filename = secure_filename(file_storage.filename)
    if not filename:
        return None
    ext = os.path.splitext(filename)[1].lower() or ".png"
    target_name = f"{prefix}_{uuid.uuid4().hex}{ext}"
    folder = os.path.join(current_app.static_folder, "images", folder_name)
    os.makedirs(folder, exist_ok=True)
    target_path = os.path.join(folder, target_name)
    file_storage.save(target_path)
    return f"images/{folder_name}/{target_name}"


def _support_ticket_upload_folder(ticket_id):
    folder = os.path.join(current_app.static_folder, "uploads", "support_tickets", str(ticket_id))
    os.makedirs(folder, exist_ok=True)
    return folder


def _save_ticket_attachments(message, files):
    attachments = []
    for file_storage in files:
        if not file_storage or not getattr(file_storage, "filename", ""):
            continue
        original = secure_filename(file_storage.filename)
        if not original:
            continue
        ext = os.path.splitext(original)[1].lower()
        if ext not in SUPPORT_ALLOWED_EXTENSIONS:
            raise ValueError(f"Formato allegato non valido: {original}")
        target_name = f"{uuid.uuid4().hex}_{original}"
        target_path = os.path.join(_support_ticket_upload_folder(message.ticket_id), target_name)
        file_storage.save(target_path)
        rel_path = os.path.relpath(target_path, current_app.static_folder).replace(os.sep, "/")
        attachment = SupportTicketAttachment(
            message=message,
            file_path=rel_path,
            original_filename=original,
            mime_type=file_storage.mimetype or None,
            file_size=os.path.getsize(target_path) if os.path.exists(target_path) else None,
        )
        db.session.add(attachment)
        attachments.append(attachment)
    return attachments


def _can_handle_ticket(ticket):
    if (ticket.ticket_type or "support") == "support":
        return (current_user.max_role_weight or 0) >= 900
    return (current_user.max_role_weight or 0) >= 40


def _ticket_email_body(ticket, body):
    return (
        f"Ticket #{ticket.id} - {ticket.subject}\n\n"
        f"{body}\n\n"
        "Assistenza LDApp"
    )


def _send_mail(message):
    send_account_mail("general", message)


@settings_bp.get("/circuit-logos/<path:logo_path>")
@login_required
@role_required(40)
def pos_circuit_logo(logo_path):
    relative = (logo_path or "").lstrip("/").replace("\\", "/")
    if relative.startswith("static/"):
        relative = relative[len("static/"):]
    directory = current_app.static_folder
    response = send_from_directory(directory, relative, conditional=True, max_age=0)
    response.cache_control.no_cache = True
    response.cache_control.no_store = True
    response.cache_control.must_revalidate = True
    return response


@settings_bp.get("/bank-logos/<path:logo_path>")
@login_required
@role_required(40)
def bank_logo(logo_path):
    relative = (logo_path or "").lstrip("/").replace("\\", "/")
    if relative.startswith("static/"):
        relative = relative[len("static/"):]
    directory = current_app.static_folder
    response = send_from_directory(directory, relative, conditional=True, max_age=0)
    response.cache_control.no_cache = True
    response.cache_control.no_store = True
    response.cache_control.must_revalidate = True
    return response


def _promote_default_bank():
    bank = (
        CashBank.query
        .filter(CashBank.is_active.is_(True))
        .order_by(CashBank.sort_order.asc(), CashBank.name.asc())
        .first()
    )
    if bank:
        bank.is_default = True


def _promote_default_device():
    device = (
        PosDevice.query
        .filter(PosDevice.is_active.is_(True))
        .order_by(PosDevice.name.asc())
        .first()
    )
    if device:
        device.is_default = True


@settings_bp.route("/", methods=["GET"])
@login_required
@role_required(40)
@log_task(logger)
def settings_index():
    all_entries = [
        {
            "title": "Utenti",
            "description": "Anagrafiche, ruoli e stato degli account.",
            "route": url_for("settings.users_index"),
            "icon": "fa-solid fa-users",
            "icon_class": "text-bg-info",
            "min_weight": 40,
        },
        {
            "title": "Banche",
            "description": "Conti e istituti usati nei versamenti e negli incassi.",
            "route": url_for("settings.banks_index"),
            "icon": "fa-solid fa-building-columns",
            "icon_class": "text-bg-danger",
            "min_weight": 40,
        },
        {
            "title": "Circuiti Carte",
            "description": "Circuiti di pagamento associati ai movimenti POS.",
            "route": url_for("settings.pos_circuits_index"),
            "icon": "fa-solid fa-credit-card",
            "icon_class": "text-bg-info",
            "min_weight": 40,
        },
        {
            "title": "Dispositivi POS",
            "description": "Terminali e dispositivi usati per gli incassi elettronici.",
            "route": url_for("settings.pos_devices_index"),
            "icon": "fa-solid fa-cash-register",
            "icon_class": "text-bg-warning",
            "min_weight": 40,
        },
        {
            "title": "Chiavi API",
            "description": "Credenziali e parametri delle integrazioni esterne.",
            "route": url_for("settings.api_keys"),
            "icon": "fa-solid fa-key",
            "icon_class": "text-bg-secondary",
            "min_weight": 900,
        },
        {
            "title": "Database",
            "description": "Connessione applicativa, credenziali e stringa DATABASE_URL.",
            "route": url_for("settings.database_config"),
            "icon": "fa-solid fa-database",
            "icon_class": "text-bg-success",
            "min_weight": 900,
        },
        {
            "title": "Email",
            "description": "Server SMTP, credenziali e mittente predefinito.",
            "route": url_for("settings.email_config"),
            "icon": "fa-solid fa-envelope",
            "icon_class": "text-bg-info",
            "min_weight": 40,
        },
        {
            "title": "Ruoli e Autorizzazioni",
            "description": "Pesi ruolo, descrizioni e soglie permessi.",
            "route": url_for("settings.roles_permissions"),
            "icon": "fa-solid fa-shield-halved",
            "icon_class": "text-bg-info",
            "min_weight": 900,
        },
        {
            "title": "Gestione menù",
            "description": "Struttura della navbar e visibilità delle voci.",
            "route": url_for("settings.manage_menus"),
            "icon": "fa-solid fa-bars",
            "icon_class": "text-bg-dark",
            "min_weight": 900,
        },
        {
            "title": "Conflitti import",
            "description": "Risoluzione guidata dei conflitti tra sorgenti.",
            "route": url_for("settings.import_conflicts_page"),
            "icon": "fa-solid fa-triangle-exclamation",
            "icon_class": "text-bg-warning",
            "min_weight": 40,
        },
        {
            "title": "Tracciati importazione",
            "description": "Associa file export e tracciati alle importazioni gestionali.",
            "route": url_for("settings.import_transfer_definitions"),
            "icon": "fa-solid fa-file-import",
            "icon_class": "text-bg-success",
            "min_weight": 900,
        },
        {
            "title": "Opzioni consegna Horeca",
            "description": "Scelte disponibili per la consegna degli ordini Horeca.",
            "route": url_for("settings.customer_order_options"),
            "icon": "fa-solid fa-truck-fast",
            "icon_class": "text-bg-info",
            "min_weight": 40,
        },
        {
            "title": "Associazione Utente-Cliente",
            "description": "Collega gli account Horeca alle anagrafiche cliente.",
            "route": url_for("settings.customer_order_links"),
            "icon": "fa-solid fa-user-link",
            "icon_class": "text-bg-info",
            "min_weight": 40,
        },
    ]
    max_weight = current_user.max_role_weight or 0
    entries = [entry for entry in all_entries if max_weight >= entry["min_weight"]]
    return render_template("settings/index.html", entries=entries)


@settings_bp.route("/import-transfer-definitions", methods=["GET", "POST"])
@login_required
@role_required(900)
@log_task(logger)
def import_transfer_definitions():
    if request.method == "POST":
        try:
            save_transfer_definitions(request.form)
        except ValueError as exc:
            flash(str(exc), "warning")
        except SQLAlchemyError:
            db.session.rollback()
            logger.exception("Salvataggio configurazione tracciati importazione fallito")
            flash("Impossibile salvare la configurazione dei tracciati.", "danger")
        else:
            flash("Configurazione importazioni aggiornata.", "success")
        return redirect(url_for("settings.import_transfer_definitions"))

    return render_template(
        "settings/import_transfer_definitions.html",
        definitions=build_transfer_definitions(),
        export_files=available_export_files(),
        trace_files=available_trace_files(),
        export_folder=current_app.config.get("EXPORT_FOLDER"),
        trace_folder="static/tracciati/importazione",
    )


@settings_bp.get("/support-tickets")
@login_required
@role_required(900)
def support_tickets():
    status = (request.args.get("status") or "").strip()
    query = SupportTicket.query.options(selectinload(SupportTicket.messages)).filter(SupportTicket.ticket_type == "support")
    if status:
        query = query.filter(SupportTicket.status == status)
    tickets = query.order_by(SupportTicket.updated_at.desc(), SupportTicket.id.desc()).limit(200).all()
    unread_counts = {
        ticket.id: sum(
            1
            for message in ticket.messages
            if message.sender_type == "user" and message.read_by_support_at is None
        )
        for ticket in tickets
    }
    return render_template(
        "settings/support_tickets.html",
        tickets=tickets,
        status=status,
        unread_counts=unread_counts,
    )


@settings_bp.get("/support-tickets/unread-count")
@login_required
@role_required(40)
def support_tickets_unread_count():
    support_count = support_unread_count()
    activation_count = SupportTicket.query.filter(
        SupportTicket.ticket_type == "horeca_activation",
        SupportTicket.status.notin_(["closed", "activated"]),
    ).count()
    return {
        "ok": True,
        "unread_count": support_count,
        "support_count": support_count,
        "activation_count": activation_count,
        "total_count": support_count + activation_count,
    }


@settings_bp.route("/support-tickets/<int:ticket_id>", methods=["GET", "POST"])
@login_required
@role_required(40)
def support_ticket_detail(ticket_id):
    ticket = (
        SupportTicket.query
        .options(
            selectinload(SupportTicket.messages).selectinload(SupportTicketMessage.attachments),
            selectinload(SupportTicket.user),
            selectinload(SupportTicket.role_activation_request).selectinload(RoleActivationRequest.user),
        )
        .get_or_404(ticket_id)
    )
    if not _can_handle_ticket(ticket):
        flash("Accesso negato.", "danger")
        return redirect(url_for("settings.settings_index"))

    if ticket.ticket_type == "support" and mark_ticket_read_by_support(ticket.id):
        db.session.commit()

    if request.method == "POST":
        action = (request.form.get("action") or "reply").strip()
        if action == "status":
            new_status = (request.form.get("status") or "open").strip()
            if new_status not in {"open", "in_progress", "waiting_user", "closed", "activated"}:
                flash("Stato ticket non valido.", "warning")
                return redirect(url_for("settings.support_ticket_detail", ticket_id=ticket.id))
            ticket.status = new_status
            ticket.closed_at = datetime.now(timezone.utc) if new_status in {"closed", "activated"} else None
            db.session.commit()
            flash("Stato ticket aggiornato.", "success")
            return redirect(url_for("settings.support_ticket_detail", ticket_id=ticket.id))

        body = (request.form.get("body") or "").strip()
        if not body:
            flash("Scrivi un messaggio di risposta.", "warning")
            return redirect(url_for("settings.support_ticket_detail", ticket_id=ticket.id))
        outgoing_message_id = outbound_ticket_message_id(ticket.id)
        message = SupportTicketMessage(
            ticket_id=ticket.id,
            sender_type="support",
            sender_user_id=current_user.id,
            source="web",
            body=body,
            email_from=ASSISTANCE_EMAIL,
            email_to=ticket.reply_email,
            external_message_id=outgoing_message_id,
            read_by_support_at=datetime.now(timezone.utc),
        )
        db.session.add(message)
        db.session.flush()
        try:
            attachments = _save_ticket_attachments(message, request.files.getlist("attachments"))
            msg = Message(
                subject=f"Re: {ticket.subject} [Ticket #{ticket.id}]",
                sender=assistance_mail_sender(),
                recipients=[ticket.reply_email],
                reply_to=ASSISTANCE_EMAIL,
                body=(
                    f"{_ticket_email_body(ticket, body)}\n\n"
                    "Puoi rispondere direttamente a questa email oppure aprire il ticket:\n"
                    f"{public_ticket_url(ticket)}"
                ),
                extra_headers={"Message-ID": outgoing_message_id},
            )
            for attachment in attachments:
                abs_path = os.path.join(current_app.static_folder, attachment.file_path)
                with open(abs_path, "rb") as fp:
                    msg.attach(attachment.original_filename, attachment.mime_type or "application/octet-stream", fp.read())
            send_assistance_mail(msg)
            ticket.status = "waiting_user"
            ticket.closed_at = None
            db.session.commit()
            flash("Risposta inviata.", "success")
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "warning")
        except Exception as exc:
            db.session.rollback()
            logger.exception("Errore invio risposta ticket")
            flash(f"Impossibile inviare la risposta: {exc}", "danger")
        return redirect(url_for("settings.support_ticket_detail", ticket_id=ticket.id))

    return render_template("settings/support_ticket_detail.html", ticket=ticket)


@settings_bp.get("/api/customer-registries/search")
@login_required
@role_required(40)
def customer_registries_search():
    query_text = (request.args.get("q") or "").strip()
    query = BusinessRegistry.query.filter(
        BusinessRegistry.kind == "customer",
        BusinessRegistry.is_active.is_(True),
    )
    if query_text:
        pattern = f"%{query_text}%"
        query = query.filter(or_(
            BusinessRegistry.display_name.ilike(pattern),
            BusinessRegistry.legal_name.ilike(pattern),
            BusinessRegistry.source_code.ilike(pattern),
            BusinessRegistry.vat_number.ilike(pattern),
        ))
    registries = query.order_by(BusinessRegistry.display_name.asc(), BusinessRegistry.id.asc()).limit(50).all()
    return jsonify({
        "ok": True,
        "items": [
            {
                "id": registry.id,
                "label": (
                    (registry.display_name or registry.legal_name or f"Cliente #{registry.id}")
                    + (f" - {registry.source_code}" if registry.source_code else "")
                    + (f" [ID {registry.id}]" )
                ),
            }
            for registry in registries
        ],
    })


@settings_bp.get("/horeca-activations")
@login_required
@role_required(40)
def horeca_activations():
    tickets = (
        SupportTicket.query
        .options(selectinload(SupportTicket.user), selectinload(SupportTicket.role_activation_request))
        .filter(SupportTicket.ticket_type == "horeca_activation")
        .order_by(SupportTicket.updated_at.desc(), SupportTicket.id.desc())
        .limit(200)
        .all()
    )
    return render_template("settings/horeca_activations.html", tickets=tickets)


@settings_bp.post("/horeca-activations/<int:ticket_id>/activate")
@login_required
@role_required(40)
def activate_horeca(ticket_id):
    ticket = SupportTicket.query.get_or_404(ticket_id)
    if ticket.ticket_type != "horeca_activation" or not ticket.user:
        flash("Ticket attivazione non valido.", "warning")
        return redirect(url_for("settings.horeca_activations"))
    registry_id = _parse_int(request.form.get("registry_id"))
    registry = BusinessRegistry.query.filter_by(id=registry_id, kind="customer", is_active=True).first() if registry_id else None
    if not registry:
        flash("Seleziona un cliente valido.", "warning")
        return redirect(url_for("settings.support_ticket_detail", ticket_id=ticket.id))
    role = Role.query.filter_by(name="customer_horeca").first()
    if not role:
        flash("Ruolo customer_horeca non configurato.", "danger")
        return redirect(url_for("settings.support_ticket_detail", ticket_id=ticket.id))

    now = datetime.now()
    user = ticket.user
    user.customer_registry_id = registry.id
    for user_role in user.roles or []:
        if user_role.role and user_role.role.name == "customer" and (user_role.valid_until is None or user_role.valid_until >= now):
            user_role.valid_until = now
            if user_role.type == "lifetime":
                user_role.type = "until"
    has_active_horeca = any(
        user_role.role and user_role.role.name == "customer_horeca" and user_role.is_active
        for user_role in user.roles or []
    )
    if not has_active_horeca:
        db.session.add(UserRole(
            user_id=user.id,
            role_id=role.id,
            type="lifetime",
            valid_from=now,
            valid_until=None,
            notes=f"Attivazione Horeca da ticket #{ticket.id}",
        ))

    ticket.status = "activated"
    ticket.closed_at = datetime.now(timezone.utc)
    if ticket.role_activation_request:
        ticket.role_activation_request.status = "approved"
        ticket.role_activation_request.reviewed_at = datetime.now(timezone.utc)
        ticket.role_activation_request.reviewed_by_user_id = current_user.id

    body = (request.form.get("body") or "").strip() or (
        "La tua richiesta di attivazione Horeca e' stata approvata.\n"
        "Da questo momento puoi accedere ai servizi Horeca disponibili in LDApp."
    )
    db.session.add(SupportTicketMessage(
        ticket_id=ticket.id,
        sender_type="support",
        sender_user_id=current_user.id,
        body=body,
        email_from=ASSISTANCE_EMAIL,
        email_to=ticket.reply_email,
    ))
    msg = Message(
        subject="Attivazione servizi Horeca completata",
        sender=assistance_mail_sender(),
        recipients=[ticket.reply_email],
        reply_to=ASSISTANCE_EMAIL,
        body=_ticket_email_body(ticket, body),
    )
    try:
        send_assistance_mail(msg)
        db.session.commit()
        flash("Cliente Horeca attivato e email inviata.", "success")
    except Exception as exc:
        db.session.rollback()
        logger.exception("Errore attivazione cliente horeca")
        flash(f"Impossibile completare l'attivazione: {exc}", "danger")
    return redirect(url_for("settings.support_ticket_detail", ticket_id=ticket.id))


@settings_bp.route("/customer-order-options", methods=["GET", "POST"])
@login_required
@role_required(40)
def customer_order_options():
    if request.method == "POST":
        action = (request.form.get("action") or "").strip()
        if action == "create_option":
            option = CustomerOrderDeliveryOption(
                code=(request.form.get("code") or "").strip(),
                label=(request.form.get("label") or "").strip(),
                requires_value=_form_bool(request.form, "requires_value"),
                value_label=(request.form.get("value_label") or "").strip() or None,
                sort_order=_parse_int(request.form.get("sort_order"), 0) or 0,
                is_active=_form_bool(request.form, "is_active", True),
            )
            if not option.code or not option.label:
                flash("Codice e label sono obbligatori.", "warning")
            else:
                db.session.add(option)
                db.session.commit()
                flash("Opzione consegna inserita.", "success")
        elif action == "update_option":
            option = CustomerOrderDeliveryOption.query.get_or_404(_parse_int(request.form.get("option_id")))
            option.code = (request.form.get("code") or "").strip()
            option.label = (request.form.get("label") or "").strip()
            option.requires_value = _form_bool(request.form, "requires_value")
            option.value_label = (request.form.get("value_label") or "").strip() or None
            option.sort_order = _parse_int(request.form.get("sort_order"), 0) or 0
            option.is_active = _form_bool(request.form, "is_active")
            db.session.commit()
            flash("Opzione consegna aggiornata.", "success")
        return redirect(url_for("settings.customer_order_options"))

    options = CustomerOrderDeliveryOption.query.order_by(CustomerOrderDeliveryOption.sort_order.asc(), CustomerOrderDeliveryOption.id.asc()).all()
    return render_template("settings/customer_order_options.html", options=options)


@settings_bp.route("/customer-order-links", methods=["GET", "POST"])
@login_required
@role_required(40)
def customer_order_links():
    if request.method == "POST":
        user = User.query.get_or_404(_parse_int(request.form.get("user_id")))
        registry_id = _parse_int(request.form.get("registry_id"))
        registry = BusinessRegistry.query.filter_by(id=registry_id, kind="customer", is_active=True).first() if registry_id else None
        user.customer_registry_id = registry.id if registry else None
        db.session.commit()
        flash("Associazione account-anagrafica aggiornata.", "success")
        return redirect(url_for("settings.customer_order_links"))

    users = User.query.order_by(User.surname.asc(), User.name.asc()).all()
    registries = (
        BusinessRegistry.query
        .filter_by(kind="customer", is_active=True)
        .order_by(BusinessRegistry.display_name.asc(), BusinessRegistry.id.asc())
        .limit(2000)
        .all()
    )
    return render_template("settings/customer_order_links.html", users=users, registries=registries)


@settings_bp.route("/users", methods=["GET"])
@login_required
@role_required(40)
@log_task(logger)
def users_index():
    try:
        roles = Role.query.order_by(Role.weight.asc(), Role.name.asc()).all()
        special_permissions = (
            SpecialPermission.query
            .filter(SpecialPermission.is_active.is_(True))
            .order_by(SpecialPermission.name.asc())
            .all()
        )
        users = (
            User.query.options(
                selectinload(User.roles).selectinload(UserRole.role),
                selectinload(User.special_permissions).selectinload(UserSpecialPermission.permission),
            )
            .order_by(User.surname.asc(), User.name.asc(), User.id.asc())
            .all()
        )
    except Exception as exc:
        logger.exception("Errore nel caricamento utenti")
        roles = []
        special_permissions = []
        users = []
        flash(f"Impossibile caricare gli utenti: {exc}", "warning")

    return render_template(
        "settings/users.html",
        users=users,
        roles=roles,
        special_permissions=special_permissions,
    )


@settings_bp.post("/users/<int:user_id>/update")
@login_required
@role_required(40)
@log_task(logger)
def user_update(user_id):
    user = User.query.get_or_404(user_id)
    email = (request.form.get("email") or "").strip().lower()
    name = (request.form.get("name") or "").strip()
    surname = (request.form.get("surname") or "").strip()

    if not email or not name or not surname:
        flash("Nome, cognome ed email sono obbligatori.", "warning")
        return redirect(url_for("settings.users_index"))

    duplicate = User.query.filter(User.email == email, User.id != user.id).first()
    if duplicate:
        flash("Email gia' assegnata a un altro utente.", "warning")
        return redirect(url_for("settings.users_index"))

    user.name = name
    user.surname = surname
    user.email = email
    user.phone = (request.form.get("phone") or "").strip() or None
    user.city = (request.form.get("city") or "").strip() or None
    user.province = (request.form.get("province") or "").strip() or None
    user.notes = (request.form.get("notes") or "").strip() or None
    db.session.commit()
    flash("Utente aggiornato.", "success")
    return redirect(url_for("settings.users_index"))


@settings_bp.post("/users/<int:user_id>/delete")
@login_required
@role_required(40)
@log_task(logger)
def user_delete(user_id):
    user = User.query.get_or_404(user_id)
    if current_user.is_authenticated and user.id == current_user.id:
        flash("Non puoi eliminare l'utente con cui sei autenticato.", "warning")
        return redirect(url_for("settings.users_index"))
    try:
        UserRole.query.filter_by(user_id=user.id).delete(synchronize_session=False)
        UserSpecialPermission.query.filter_by(user_id=user.id).delete(synchronize_session=False)
        PasswordResetToken.query.filter_by(user_id=user.id).delete(synchronize_session=False)
        db.session.delete(user)
        db.session.commit()
        flash("Utente eliminato.", "success")
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception("Impossibile eliminare utente %s", user_id)
        flash("Impossibile eliminare l'utente: esistono riferimenti storici collegati.", "warning")
    return redirect(url_for("settings.users_index"))


@settings_bp.post("/users/<int:user_id>/role")
@login_required
@role_required(40)
@log_task(logger)
def user_change_role(user_id):
    user = User.query.get_or_404(user_id)
    role_id = _parse_int(request.form.get("role_id"))
    role = Role.query.get(role_id) if role_id is not None else None
    if not role:
        flash("Ruolo non valido.", "warning")
        return redirect(url_for("settings.users_index"))

    now = datetime.now()
    for user_role in user.roles or []:
        if user_role.valid_until is None or user_role.valid_until >= now:
            user_role.valid_until = now
            if user_role.type == "lifetime":
                user_role.type = "until"

    db.session.add(UserRole(
        user_id=user.id,
        role_id=role.id,
        type="lifetime",
        valid_from=now,
        valid_until=None,
        notes="Cambio ruolo da impostazioni utenti",
    ))
    db.session.commit()
    flash("Ruolo utente aggiornato.", "success")
    return redirect(url_for("settings.users_index"))


@settings_bp.post("/users/<int:user_id>/special-authorizations")
@login_required
@role_required(40)
@log_task(logger)
def user_add_special_authorization(user_id):
    user = User.query.get_or_404(user_id)
    authorization_type = (request.form.get("authorization_type") or "").strip()
    valid_from = _parse_datetime_date(request.form.get("valid_from")) or datetime.now()
    valid_until = _parse_datetime_date(request.form.get("valid_to"), end_of_day=True)
    notes = (request.form.get("notes") or "").strip() or None

    if valid_until and valid_until < valid_from:
        flash("La data fine validita' non puo' precedere la data inizio.", "warning")
        return redirect(url_for("settings.users_index"))

    if authorization_type == "role":
        role_id = _parse_int(request.form.get("role_id"))
        role = Role.query.get(role_id) if role_id is not None else None
        if not role:
            flash("Ruolo non valido.", "warning")
            return redirect(url_for("settings.users_index"))
        db.session.add(UserRole(
            user_id=user.id,
            role_id=role.id,
            type="period" if valid_until else "until",
            valid_from=valid_from,
            valid_until=valid_until,
            notes=notes or "Autorizzazione temporanea da impostazioni utenti",
        ))
    elif authorization_type == "permission":
        permission_id = _parse_int(request.form.get("permission_id"))
        permission = SpecialPermission.query.get(permission_id) if permission_id is not None else None
        if not permission:
            flash("Autorizzazione speciale non valida.", "warning")
            return redirect(url_for("settings.users_index"))
        db.session.add(UserSpecialPermission(
            user_id=user.id,
            permission_id=permission.id,
            valid_from=valid_from,
            valid_until=valid_until,
            notes=notes,
        ))
    else:
        flash("Tipo autorizzazione non valido.", "warning")
        return redirect(url_for("settings.users_index"))

    db.session.commit()
    flash("Autorizzazione aggiunta.", "success")
    return redirect(url_for("settings.users_index"))


@settings_bp.post("/users/<int:user_id>/reset-password")
@login_required
@role_required(40)
@log_task(logger)
def user_reset_password(user_id):
    user = User.query.get_or_404(user_id)
    now = datetime.now(timezone.utc)
    PasswordResetToken.query.filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used_at.is_(None),
        PasswordResetToken.expires_at > now,
    ).update({"expires_at": now}, synchronize_session=False)

    raw_token = secrets.token_urlsafe(32)
    reset_token = PasswordResetToken(
        user_id=user.id,
        token_hash=PasswordResetToken.hash_token(raw_token),
        expires_at=now + timedelta(hours=24),
        requested_ip=request.remote_addr,
        user_agent=request.headers.get("User-Agent"),
    )
    db.session.add(reset_token)
    db.session.flush()

    reset_link = url_for("auth.reset_password", token=raw_token, _external=True)
    msg = Message(
        subject="Reimposta la tua password",
        recipients=[user.email],
        body=(
            "E' stato richiesto un reset password dall'amministratore LD Enoteca.\n\n"
            f"Apri questo link entro 24 ore per impostare una nuova password:\n{reset_link}\n\n"
            "Scadute le 24 ore il link non sara' piu' valido."
        ),
    )
    try:
        _send_mail(msg)
        db.session.commit()
        flash("Link reset password inviato all'utente.", "success")
    except Exception as exc:
        db.session.rollback()
        logger.exception("Errore invio reset password admin")
        flash(f"Impossibile inviare il reset password: {exc}", "danger")
    return redirect(url_for("settings.users_index"))


@settings_bp.route("/banks", methods=["GET", "POST"])
@login_required
@role_required(40)
@log_task(logger)
def banks_index():
    try:
        if request.method == "POST":
            bank_id = _parse_int(request.form.get("bank_id"))
            name = (request.form.get("name") or "").strip()
            if not name:
                flash("Il nome della banca è obbligatorio.", "warning")
                return redirect(url_for("settings.banks_index"))

            bank = CashBank.query.get(bank_id) if bank_id else None
            if bank is None:
                bank = CashBank()
                db.session.add(bank)

            bank.name = name
            bank.is_active = _form_bool(request.form, "is_active", True)
            bank.is_default = _form_bool(request.form, "is_default", False)
            bank.sort_order = _parse_int(request.form.get("sort_order"), 0) or 0
            uploaded_logo = request.files.get("logo_file")
            if uploaded_logo and uploaded_logo.filename:
                bank.logo_path = _save_uploaded_logo(uploaded_logo, prefix=f"bank_{bank.id or 'new'}", folder_name="banks")

            if bank.is_default:
                CashBank.query.filter(CashBank.id != bank.id).update({"is_default": False})

            db.session.commit()
            flash("Banca salvata con successo.", "success")
            return redirect(url_for("settings.banks_index"))

        banks = (
            CashBank.query
            .order_by(CashBank.is_default.desc(), CashBank.sort_order.asc(), CashBank.name.asc())
            .all()
        )
    except Exception as exc:
        logger.exception("Errore nel caricamento banche")
        banks = []
        flash(f"Impossibile caricare le banche: {exc}", "warning")
    return render_template("settings/banks.html", banks=banks)


@settings_bp.route("/banks/<int:bank_id>/toggle", methods=["POST"])
@login_required
@role_required(40)
@log_task(logger)
def bank_toggle_active(bank_id):
    bank = CashBank.query.get_or_404(bank_id)
    bank.is_active = not bool(bank.is_active)
    if not bank.is_active and bank.is_default:
        bank.is_default = False
        _promote_default_bank()
    db.session.commit()
    flash("Stato banca aggiornato.", "success")
    return redirect(url_for("settings.banks_index"))


@settings_bp.route("/banks/<int:bank_id>/delete", methods=["POST"])
@login_required
@role_required(40)
@log_task(logger)
def bank_delete(bank_id):
    bank = CashBank.query.get_or_404(bank_id)
    usage_count = (
        CashDeposit.query.filter_by(bank_id=bank.id).count()
        + CashIssuedCheck.query.filter_by(bank_id=bank.id).count()
        + CashSalePayment.query.filter_by(bank_id=bank.id).count()
    )
    if usage_count:
        flash("La banca è usata da movimenti storici: disattivala invece di eliminarla.", "warning")
        return redirect(url_for("settings.banks_index"))

    was_default = bool(bank.is_default)
    db.session.delete(bank)
    db.session.commit()
    if was_default:
        _promote_default_bank()
        db.session.commit()
    flash("Banca eliminata.", "success")
    return redirect(url_for("settings.banks_index"))


@settings_bp.route("/pos-circuits", methods=["GET", "POST"])
@login_required
@role_required(40)
@log_task(logger)
def pos_circuits_index():
    try:
        _ensure_pos_validity_schema()
        validity_enabled = _table_has_column("pos_circuits", "valid_from") and _table_has_column("pos_circuits", "valid_to")
        if request.method == "POST":
            circuit_id = _parse_int(request.form.get("circuit_id"))
            name = (request.form.get("name") or "").strip()
            if not name:
                flash("Il nome del circuito è obbligatorio.", "warning")
                return redirect(url_for("settings.pos_circuits_index"))

            circuit = PosCircuit.query.get(circuit_id) if circuit_id else None
            if circuit is None:
                circuit = PosCircuit()
                db.session.add(circuit)

            circuit.name = name
            circuit.icon = (request.form.get("icon") or "").strip() or None
            has_valid_from = _form_bool(request.form, "has_valid_from", False)
            has_valid_to = _form_bool(request.form, "has_valid_to", False)
            circuit.valid_from = _parse_date(request.form.get("valid_from")) if has_valid_from else None
            circuit.valid_to = _parse_date(request.form.get("valid_to")) if has_valid_to else None
            uploaded_logo = request.files.get("logo_file")
            if uploaded_logo and uploaded_logo.filename:
                circuit.logo_path = _save_uploaded_logo(uploaded_logo, prefix=f"circuit_{circuit.id or 'new'}")
            circuit.is_active = _form_bool(request.form, "is_active", True)
            db.session.commit()
            flash("Circuito salvato con successo.", "success")
            return redirect(url_for("settings.pos_circuits_index"))

        circuits_q = PosCircuit.query.options(
            load_only(PosCircuit.id, PosCircuit.name, PosCircuit.icon, PosCircuit.logo_path, PosCircuit.is_active)
        )
        if validity_enabled:
            circuits_q = circuits_q.options(load_only(PosCircuit.valid_from, PosCircuit.valid_to)).order_by(
                PosCircuit.is_active.desc(),
                PosCircuit.valid_from.desc().nullslast(),
                PosCircuit.name.asc(),
            )
        else:
            circuits_q = circuits_q.order_by(PosCircuit.is_active.desc(), PosCircuit.name.asc())
        circuits = circuits_q.all()
    except Exception as exc:
        logger.exception("Errore nel caricamento circuiti POS")
        circuits = []
        flash(f"Impossibile caricare i circuiti carte: {exc}", "warning")
    icon_choices = [
        "fa-solid fa-credit-card",
        "fa-solid fa-cc-visa",
        "fa-solid fa-cc-mastercard",
        "fa-solid fa-cc-amex",
        "fa-brands fa-cc-paypal",
        "fa-brands fa-google-pay",
        "fa-brands fa-apple-pay",
        "fa-brands fa-amazon-pay",
        "fa-brands fa-cc-stripe",
        "fa-brands fa-cc-discover",
        "fa-brands fa-cc-diners-club",
        "fa-brands fa-cc-jcb",
        "fa-solid fa-credit-card-front",
        "fa-solid fa-money-check-dollar",
        "fa-solid fa-money-bill-wave",
        "fa-solid fa-wallet",
        "fa-solid fa-piggy-bank",
        "fa-solid fa-circle-nodes",
        "fa-solid fa-network-wired",
        "fa-solid fa-building-columns",
        "fa-solid fa-landmark",
        "fa-solid fa-hand-holding-dollar",
        "fa-solid fa-receipt",
        "fa-solid fa-store",
        "fa-solid fa-shop",
        "fa-solid fa-cart-shopping",
        "fa-solid fa-basket-shopping",
        "fa-solid fa-bag-shopping",
        "fa-solid fa-magnifying-glass",
        "fa-solid fa-barcode",
        "fa-solid fa-plug",
        "fa-solid fa-terminal",
        "fa-solid fa-sim-card",
        "fa-solid fa-qrcode",
        "fa-solid fa-fingerprint",
        "fa-solid fa-shield-halved",
        "fa-solid fa-square-check",
        "fa-solid fa-circle-check",
        "fa-solid fa-circle-notch",
        "fa-solid fa-bolt",
        "fa-solid fa-battery-full",
        "fa-solid fa-bolt-lightning",
        "fa-solid fa-receipt",
        "fa-solid fa-building",
        "fa-solid fa-shop",
        "fa-solid fa-store",
        "fa-solid fa-cash-register",
    ]
    return render_template(
        "settings/pos_circuits.html",
        circuits=circuits,
        icon_choices=icon_choices,
        today=date.today(),
        pos_validity_enabled=validity_enabled if "validity_enabled" in locals() else False,
    )


@settings_bp.route("/pos-circuits/<int:circuit_id>/toggle", methods=["POST"])
@login_required
@role_required(40)
@log_task(logger)
def pos_circuit_toggle_active(circuit_id):
    circuit = PosCircuit.query.get_or_404(circuit_id)
    circuit.is_active = not bool(circuit.is_active)
    db.session.commit()
    flash("Stato circuito aggiornato.", "success")
    return redirect(url_for("settings.pos_circuits_index"))


@settings_bp.route("/pos-circuits/<int:circuit_id>/delete", methods=["POST"])
@login_required
@role_required(40)
@log_task(logger)
def pos_circuit_delete(circuit_id):
    circuit = PosCircuit.query.get_or_404(circuit_id)
    usage_count = (
        db.session.query(pos_device_circuits).filter(pos_device_circuits.c.pos_circuit_id == circuit.id).count()
        + PosMove.query.filter_by(pos_circuit_id=circuit.id).count()
        + CashClosurePos.query.filter_by(pos_circuit_id=circuit.id).count()
        + CashSalePaymentPosMove.query.join(PosMove).filter(PosMove.pos_circuit_id == circuit.id).count()
    )
    if usage_count:
        flash("Il circuito è usato da dispositivi o movimenti storici: disattivalo invece di eliminarlo.", "warning")
        return redirect(url_for("settings.pos_circuits_index"))

    db.session.delete(circuit)
    db.session.commit()
    flash("Circuito eliminato.", "success")
    return redirect(url_for("settings.pos_circuits_index"))


@settings_bp.route("/pos-devices", methods=["GET", "POST"])
@login_required
@role_required(40)
@log_task(logger)
def pos_devices_index():
    try:
        _ensure_pos_validity_schema()
        validity_enabled = _table_has_column("pos_devices", "valid_from") and _table_has_column("pos_devices", "valid_to")
        if request.method == "POST":
            device_id = _parse_int(request.form.get("device_id"))
            name = (request.form.get("name") or "").strip()
            if not name:
                flash("Il nome del dispositivo POS è obbligatorio.", "warning")
                return redirect(url_for("settings.pos_devices_index"))

            device = PosDevice.query.get(device_id) if device_id else None
            is_new_device = device is None
            if device is None:
                device = PosDevice()
                db.session.add(device)

            device.name = name
            device.type = (request.form.get("type") or "physical").strip() or "physical"
            has_valid_from = _form_bool(request.form, "has_valid_from", False)
            has_valid_to = _form_bool(request.form, "has_valid_to", False)
            device.valid_from = _parse_date(request.form.get("valid_from")) if has_valid_from else None
            device.valid_to = _parse_date(request.form.get("valid_to")) if has_valid_to else None
            device.is_active = _form_bool(request.form, "is_active", True)
            device.is_default = _form_bool(request.form, "is_default", False)

            selected_circuits = _selected_ids_from_form(request.form, "circuit_ids")
            if is_new_device:
                db.session.flush()
            else:
                for circuit in list(device.circuits.all()):
                    device.circuits.remove(circuit)
            if selected_circuits:
                for circuit in PosCircuit.query.filter(PosCircuit.id.in_(selected_circuits)).all():
                    device.circuits.append(circuit)

            if device.is_default:
                PosDevice.query.filter(PosDevice.id != device.id).update({"is_default": False})

            db.session.commit()
            flash("Dispositivo POS salvato con successo.", "success")
            return redirect(url_for("settings.pos_devices_index"))

        circuits_q = PosCircuit.query.options(load_only(PosCircuit.id, PosCircuit.name, PosCircuit.is_active))
        if validity_enabled:
            circuits_q = circuits_q.options(load_only(PosCircuit.valid_from, PosCircuit.valid_to)).order_by(
                PosCircuit.is_active.desc(),
                PosCircuit.valid_from.desc().nullslast(),
                PosCircuit.name.asc(),
            )
        else:
            circuits_q = circuits_q.order_by(PosCircuit.is_active.desc(), PosCircuit.name.asc())
        circuits_all = circuits_q.all()

        devices_q = PosDevice.query.options(
            load_only(PosDevice.id, PosDevice.name, PosDevice.type, PosDevice.is_active, PosDevice.is_default),
        )
        if validity_enabled:
            devices_q = devices_q.options(load_only(PosDevice.valid_from, PosDevice.valid_to)).order_by(
                PosDevice.is_default.desc(),
                PosDevice.is_active.desc(),
                PosDevice.valid_from.desc().nullslast(),
                PosDevice.name.asc(),
            )
        else:
            devices_q = devices_q.order_by(PosDevice.is_default.desc(), PosDevice.is_active.desc(), PosDevice.name.asc())
        devices = devices_q.all()
    except Exception as exc:
        db.session.rollback()
        logger.exception("Errore nel caricamento dispositivi POS")
        circuits_all = []
        devices = []
        flash(f"Impossibile caricare i dispositivi POS: {exc}", "warning")
    return render_template(
        "settings/pos_devices.html",
        devices=devices,
        circuits_all=circuits_all,
        today=date.today(),
        pos_validity_enabled=validity_enabled if "validity_enabled" in locals() else False,
    )


@settings_bp.route("/pos-devices/<int:device_id>/toggle", methods=["POST"])
@login_required
@role_required(40)
@log_task(logger)
def pos_device_toggle_active(device_id):
    device = PosDevice.query.get_or_404(device_id)
    device.is_active = not bool(device.is_active)
    if not device.is_active and device.is_default:
        device.is_default = False
        _promote_default_device()
    db.session.commit()
    flash("Stato dispositivo aggiornato.", "success")
    return redirect(url_for("settings.pos_devices_index"))


@settings_bp.route("/pos-devices/<int:device_id>/delete", methods=["POST"])
@login_required
@role_required(40)
@log_task(logger)
def pos_device_delete(device_id):
    device = PosDevice.query.get_or_404(device_id)
    usage_count = (
        db.session.query(pos_device_circuits).filter(pos_device_circuits.c.pos_device_id == device.id).count()
        + PosMove.query.filter_by(pos_device_id=device.id).count()
        + CashClosurePos.query.filter_by(pos_device_id=device.id).count()
        + CashSalePaymentPosMove.query.join(PosMove).filter(PosMove.pos_device_id == device.id).count()
    )
    if usage_count:
        flash("Il dispositivo POS è usato da movimenti storici o associazioni: disattivalo invece di eliminarlo.", "warning")
        return redirect(url_for("settings.pos_devices_index"))

    was_default = bool(device.is_default)
    db.session.delete(device)
    db.session.commit()
    if was_default:
        _promote_default_device()
        db.session.commit()
    flash("Dispositivo POS eliminato.", "success")
    return redirect(url_for("settings.pos_devices_index"))


def _save_role_preferences_from_form(form):
    changed = 0
    for role in Role.query.order_by(Role.weight.asc(), Role.name.asc()).all():
        weight_raw = (form.get(f"role_weight_{role.id}") or "").strip()
        description_raw = (form.get(f"role_description_{role.id}") or "").strip()

        if weight_raw == "":
            continue

        new_weight = int(weight_raw)
        if role.weight != new_weight:
            role.weight = new_weight
            changed += 1

        new_description = description_raw or None
        if role.description != new_description:
            role.description = new_description
            changed += 1

    db.session.commit()
    return changed


API_KEY_PREFERENCE_CATEGORIES = {"TeamSystem MATRIXWS", "Prestashop", "Poleepo", "Trello", "Slack", "Facebook", "Instagram", "Notifiche push"}
ROLE_PERMISSION_PREFERENCE_CATEGORIES = {"Permessi e ruoli"}
API_KEY_CATEGORY_LABELS = {
    "TeamSystem MATRIXWS": "TeamSystem MATRIXWS",
    "Prestashop": "Prestashop",
    "Poleepo": "Poleepo",
    "Trello": "Trello",
    "Slack": "Slack",
    "Facebook": "Facebook",
    "Instagram": "Instagram",
    "Notifiche push": "VAPID",
}


def _normalize_permission_code(value):
    code = re.sub(r"[^a-z0-9_.-]+", "_", (value or "").strip().lower())
    return code.strip("_.-")


def _sync_postgres_pk_sequence(model, column_name="id"):
    bind = db.session.get_bind()
    if not bind or bind.dialect.name != "postgresql":
        return
    table_name = model.__tablename__
    max_id = db.session.query(db.func.max(getattr(model, column_name))).scalar() or 0
    db.session.execute(
        text("SELECT setval(pg_get_serial_sequence(:table_name, :column_name), :next_id, false)"),
        {
            "table_name": table_name,
            "column_name": column_name,
            "next_id": int(max_id) + 1,
        },
    )


def _filter_preference_sections(sections, include_categories=None, exclude_categories=None):
    include_categories = set(include_categories or [])
    exclude_categories = set(exclude_categories or [])
    filtered = []
    for section in sections or []:
        category = section.get("category")
        if include_categories and category not in include_categories:
            continue
        if exclude_categories and category in exclude_categories:
            continue
        filtered.append(section)
    return filtered


def _env_local_path():
    project_root = os.path.dirname(current_app.static_folder or os.getcwd())
    return os.path.join(project_root, ".env.local")


DATABASE_TYPE_OPTIONS = [
    {"value": "postgresql", "label": "PostgreSQL", "default_port": 5432},
    {"value": "mysql", "label": "MySQL", "default_port": 3306},
    {"value": "mariadb", "label": "MariaDB", "default_port": 3306},
    {"value": "sqlite", "label": "SQLite", "default_port": None},
    {"value": "mssql", "label": "Microsoft SQL Server", "default_port": 1433},
    {"value": "oracle", "label": "Oracle", "default_port": 1521},
]


def _read_env_file_value(key):
    path = _env_local_path()
    if not os.path.exists(path):
        return None
    try:
        return dotenv_values(path).get(key)
    except Exception:
        logger.exception("Impossibile leggere %s da .env.local", key)
        return None


def _ensure_env_local_file():
    path = _env_local_path()
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("")
    return path


def _mask_secret(value, visible=3):
    raw = str(value or "")
    if not raw:
        return ""
    if len(raw) <= visible:
        return "*" * len(raw)
    return f"{raw[:visible]}{'*' * max(len(raw) - visible, 6)}"


def _mask_database_uri(uri):
    parsed = urlparse(uri or "")
    if not parsed.password:
        return uri or ""
    masked_netloc = parsed.netloc.replace(f":{parsed.password}@", ":********@")
    return parsed._replace(netloc=masked_netloc).geturl()


def _parse_database_uri(uri):
    parsed = urlparse(uri or "")
    scheme = parsed.scheme or "postgresql"
    if scheme.startswith("postgres"):
        db_type = "postgresql"
    else:
        db_type = scheme

    if db_type == "sqlite":
        database_name = unquote((parsed.path or "").lstrip("/"))
        if parsed.netloc:
            database_name = f"{parsed.netloc}/{database_name}".strip("/")
        return {
            "type": db_type,
            "host": "",
            "port": "",
            "database": database_name,
            "username": "",
            "password": "",
        }

    try:
        parsed_port = parsed.port
    except ValueError:
        parsed_port = None

    return {
        "type": db_type,
        "host": parsed.hostname or "",
        "port": str(parsed_port or ""),
        "database": unquote((parsed.path or "").lstrip("/")),
        "username": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
    }


def _build_database_uri(db_type, host, port, database, username, password):
    db_type = (db_type or "postgresql").strip().lower()
    host = (host or "").strip()
    port = (port or "").strip()
    database = (database or "").strip()
    username = (username or "").strip()
    password = password or ""

    if db_type == "sqlite":
        if not database:
            raise ValueError("Per SQLite serve il percorso del database.")
        return f"sqlite:///{database}"

    if not host:
        raise ValueError("Indirizzo database obbligatorio.")
    if not database:
        raise ValueError("Nome database obbligatorio.")

    auth = ""
    if username:
        auth = quote(username, safe="")
        if password:
            auth = f"{auth}:{quote(password, safe='')}@"
        else:
            auth = f"{auth}@"
    netloc = host
    if port:
        netloc = f"{netloc}:{port}"
    return f"{db_type}://{auth}{netloc}/{quote(database, safe='')}"


def _build_database_config():
    env_uri = _read_env_file_value("DATABASE_URL")
    runtime_uri = current_app.config.get("SQLALCHEMY_DATABASE_URI") or os.getenv("DATABASE_URL") or ""
    uri = env_uri or runtime_uri or ""
    parsed = _parse_database_uri(uri)
    return {
        "exists": bool(uri),
        "source": ".env.local" if env_uri is not None else ("runtime" if runtime_uri else "mancante"),
        "uri": uri,
        "masked_uri": _mask_database_uri(uri),
        "masked_password": _mask_secret(parsed.get("password")),
        **parsed,
    }


@settings_bp.route("/database", methods=["GET", "POST"])
@login_required
@role_required(900)
@log_task(logger)
def database_config():
    if request.method == "POST":
        form_type = (request.form.get("form_type") or "update_database").strip().lower()
        try:
            if form_type == "delete_database":
                unset_key(_ensure_env_local_file(), "DATABASE_URL")
                os.environ.pop("DATABASE_URL", None)
                current_app.config["SQLALCHEMY_DATABASE_URI"] = None
                flash("Configurazione database eliminata da .env.local. Riavvia l'app prima di continuare a usare una nuova connessione.", "warning")
                return redirect(url_for("settings.database_config"))

            db_uri = _build_database_uri(
                request.form.get("db_type"),
                request.form.get("host"),
                request.form.get("port"),
                request.form.get("database"),
                request.form.get("username"),
                request.form.get("password"),
            )
            set_key(_ensure_env_local_file(), "DATABASE_URL", db_uri)
            os.environ["DATABASE_URL"] = db_uri
            current_app.config["SQLALCHEMY_DATABASE_URI"] = db_uri
            flash("Configurazione database salvata. Riavvia l'app per applicare la connessione al motore SQLAlchemy.", "success")
            return redirect(url_for("settings.database_config"))
        except Exception as exc:
            logger.exception("Errore aggiornando configurazione database")
            flash(f"Impossibile aggiornare la configurazione database: {exc}", "danger")

    config = _build_database_config()
    return render_template(
        "settings/database.html",
        db_config=config,
        db_type_options=DATABASE_TYPE_OPTIONS,
    )


EMAIL_ACCOUNT_CODE_RE = re.compile(r"^[a-z0-9_]+$")


def _email_accounts_table_ready():
    return inspect(db.engine).has_table("email_accounts")


def _build_email_account_rows():
    rows = []
    present_codes = set()
    if _email_accounts_table_ready():
        for account in EmailAccount.query.order_by(EmailAccount.is_system.desc(), EmailAccount.name.asc()).all():
            row = account.to_dict()
            row["source"] = "database"
            rows.append(row)
            present_codes.add(account.code)

    for code in SYSTEM_EMAIL_ACCOUNTS:
        if code in present_codes:
            continue
        legacy = get_email_account(code)
        if legacy:
            legacy.pop("password", None)
            legacy.pop("imap_password", None)
            legacy["has_password"] = bool(get_email_account(code).get("password"))
            rows.append(legacy)
    return rows


def _save_email_account_from_form():
    if not _email_accounts_table_ready():
        raise RuntimeError("Tabella email_accounts non disponibile: applicare prima la migrazione database")

    account_id = request.form.get("account_id", type=int)
    account = db.session.get(EmailAccount, account_id) if account_id else None
    code = str(request.form.get("code") or "").strip().lower()
    if not code or not EMAIL_ACCOUNT_CODE_RE.fullmatch(code):
        raise ValueError("Il codice account puo' contenere solo lettere minuscole, numeri e underscore")
    if account and code != account.code:
        raise ValueError("Il codice di un account esistente non puo' essere modificato")
    duplicate = EmailAccount.query.filter(EmailAccount.code == code)
    if account:
        duplicate = duplicate.filter(EmailAccount.id != account.id)
    if duplicate.first():
        raise ValueError(f"Esiste gia' un account con codice '{code}'")

    name = str(request.form.get("name") or "").strip()
    smtp_server = str(request.form.get("smtp_server") or "").strip()
    username = str(request.form.get("username") or "").strip()
    default_sender = str(request.form.get("default_sender") or "").strip()
    smtp_port = request.form.get("smtp_port", type=int)
    use_tls = request.form.get("use_tls") == "1"
    use_ssl = request.form.get("use_ssl") == "1"
    if not all([name, smtp_server, username, default_sender, smtp_port]):
        raise ValueError("Compilare tutti i campi obbligatori dell'account email")
    if not 1 <= smtp_port <= 65535:
        raise ValueError("La porta SMTP deve essere compresa tra 1 e 65535")
    if use_tls and use_ssl:
        raise ValueError("TLS e SSL non possono essere attivati contemporaneamente")

    imap_enabled = request.form.get("imap_enabled") == "1"
    imap_server = str(request.form.get("imap_server") or "").strip()
    imap_port = request.form.get("imap_port", type=int) or 993
    imap_use_tls = request.form.get("imap_use_tls") == "1"
    imap_use_ssl = request.form.get("imap_use_ssl") == "1"
    imap_username = str(request.form.get("imap_username") or "").strip()
    imap_folder = str(request.form.get("imap_folder") or "INBOX").strip() or "INBOX"
    if not 1 <= imap_port <= 65535:
        raise ValueError("La porta IMAP deve essere compresa tra 1 e 65535")
    if imap_use_tls and imap_use_ssl:
        raise ValueError("IMAP TLS e SSL non possono essere attivati contemporaneamente")
    if imap_enabled and not all([imap_server, imap_username, imap_folder]):
        raise ValueError("Per abilitare la posta in entrata compilare server, utente e cartella IMAP")

    legacy = get_email_account(code) if not account else None
    password = str(request.form.get("password") or "")
    if not password:
        password = account.password_encrypted if account else (legacy or {}).get("password")
    if not password:
        raise ValueError("La password e' obbligatoria per un nuovo account")
    imap_password = str(request.form.get("imap_password") or "")
    if not imap_password:
        imap_password = account.imap_password_encrypted if account else (legacy or {}).get("imap_password")
    if imap_enabled and not imap_password:
        raise ValueError("La password IMAP e' obbligatoria quando la posta in entrata e' abilitata")

    if not account:
        account = EmailAccount(code=code)
        db.session.add(account)
    account.code = code
    account.name = name
    account.smtp_server = smtp_server
    account.smtp_port = smtp_port
    account.use_tls = use_tls
    account.use_ssl = use_ssl
    account.username = username
    account.password_encrypted = password
    account.default_sender = default_sender
    account.imap_server = imap_server or None
    account.imap_port = imap_port
    account.imap_use_tls = imap_use_tls
    account.imap_use_ssl = imap_use_ssl
    account.imap_username = imap_username or None
    account.imap_password_encrypted = imap_password or None
    account.imap_folder = imap_folder
    account.imap_enabled = imap_enabled
    account.is_enabled = request.form.get("is_enabled") == "1"
    account.is_system = code in SYSTEM_EMAIL_ACCOUNTS
    db.session.commit()
    return account


@settings_bp.route("/email", methods=["GET", "POST"])
@login_required
@role_required(40)
@log_task(logger)
def email_config():
    if request.method == "POST":
        form_type = (request.form.get("form_type") or "save_account").strip().lower()
        try:
            if form_type == "delete_account":
                account = db.session.get(EmailAccount, request.form.get("account_id", type=int))
                if not account:
                    raise ValueError("Account email non trovato")
                if account.is_system or account.code in SYSTEM_EMAIL_ACCOUNTS:
                    raise ValueError("Gli account di sistema non possono essere eliminati; possono essere disattivati")
                db.session.delete(account)
                db.session.commit()
                flash("Account email eliminato.", "warning")
                return redirect(url_for("settings.email_config"))
            account = _save_email_account_from_form()
            flash(f"Account email '{account.name}' salvato.", "success")
            return redirect(url_for("settings.email_config"))
        except Exception as exc:
            db.session.rollback()
            logger.exception("Errore aggiornando configurazione email")
            flash(f"Impossibile aggiornare la configurazione email: {exc}", "danger")

    rows = _build_email_account_rows()
    return render_template(
        "settings/email.html",
        email_accounts=rows,
        email_accounts_table_ready=_email_accounts_table_ready(),
    )


@settings_bp.post("/email/sync-support-mailbox")
@login_required
@role_required(40)
@log_task(logger)
def sync_support_mailbox_now():
    try:
        from tools.support_mailbox import sync_support_mailbox

        result = sync_support_mailbox(limit=100)
        if not result.get("enabled"):
            flash("La lettura IMAP dell'account assistance non e' abilitata.", "warning")
        else:
            flash(
                "Sincronizzazione completata: "
                f"{result.get('imported', 0)} risposte importate, "
                f"{result.get('duplicates', 0)} duplicate, "
                f"{result.get('ignored', 0)} ignorate.",
                "success",
            )
    except Exception as exc:
        logger.exception("Errore sincronizzazione mailbox assistenza")
        flash(f"Sincronizzazione mailbox non riuscita: {exc}", "danger")
    return redirect(url_for("settings.email_config"))


def _parse_env_local_custom_keys():
    path = _env_local_path()
    known_config_keys = {
        item.get("config_key")
        for section in build_preferences_sections(current_app._get_current_object())
        for item in section.get("items", [])
        if item.get("config_key")
    }
    custom_rows = []
    if not os.path.exists(path):
        return custom_rows

    descriptions = {}
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            lines = handle.readlines()

        for line in lines:
            raw = line.strip()
            if raw.startswith("# LDAPP_DESC "):
                _, _, rest = raw.partition("# LDAPP_DESC ")
                key, _, desc = rest.partition(":")
                descriptions[key.strip()] = desc.strip()

        for line in lines:
            raw = line.strip()
            if not raw or raw.startswith("#") or "=" not in raw:
                continue
            key, value = raw.split("=", 1)
            key = key.strip()
            if not key or key in known_config_keys or key not in descriptions:
                continue
            custom_rows.append({
                "name": key,
                "value": value.strip().strip('"').strip("'"),
                "description": descriptions.get(key, ""),
            })
    except OSError:
        logger.exception("Impossibile leggere .env.local per chiavi custom")
    return custom_rows


def _write_env_description(key, description):
    path = _env_local_path()
    try:
        lines = []
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as handle:
                lines = handle.readlines()
        marker_prefix = f"# LDAPP_DESC {key}:"
        marker = f"{marker_prefix} {description.strip()}\n"
        for idx, line in enumerate(lines):
            if line.startswith(marker_prefix):
                lines[idx] = marker
                break
        else:
            lines.append(marker)
        with open(path, "w", encoding="utf-8") as handle:
            handle.writelines(lines)
    except OSError:
        logger.exception("Impossibile scrivere descrizione .env.local per %s", key)


def _remove_env_description(key):
    path = _env_local_path()
    if not os.path.exists(path):
        return
    marker_prefix = f"# LDAPP_DESC {key}:"
    try:
        with open(path, "r", encoding="utf-8") as handle:
            lines = [line for line in handle.readlines() if not line.startswith(marker_prefix)]
        with open(path, "w", encoding="utf-8") as handle:
            handle.writelines(lines)
    except OSError:
        logger.exception("Impossibile eliminare descrizione .env.local per %s", key)


def _coerce_preference_form_value(definition, raw_value):
    if definition.value_type == "bool":
        return "1" if str(raw_value or "").strip().lower() in {"1", "true", "yes", "on"} else "0"
    if definition.value_type == "int":
        return str(int(raw_value or 0))
    if definition.value_type == "float":
        return str(float(raw_value or 0))
    return str(raw_value or "")


def _upsert_api_preference(definition, raw_value, *, keep_empty_secret=True):
    row = AppPreference.query.filter_by(key=definition.key).first()
    if row is None:
        row = AppPreference(
            key=definition.key,
            category=definition.category,
            label=definition.label,
            description=definition.description,
            value_type=definition.value_type,
            sort_order=definition.sort_order,
        )
        db.session.add(row)
    else:
        row.category = definition.category
        row.label = definition.label
        row.description = definition.description
        row.value_type = definition.value_type
        row.sort_order = definition.sort_order

    if definition.is_secret:
        if raw_value in (None, "") and keep_empty_secret:
            return False
        row.secret_value = str(raw_value or "")
        row.value_text = None
        row.value_json = None
        return True

    row.value_text = _coerce_preference_form_value(definition, raw_value)
    row.value_json = None
    row.secret_value = None
    return True


def _build_api_key_rows(sections):
    rows = []
    for section in sections:
        items = section.get("items", [])
        stored_count = sum(1 for item in items if item.get("stored"))
        secret_count = sum(1 for item in items if item.get("is_secret"))
        configured_count = sum(
            1
            for item in items
            if item.get("stored") or str(item.get("current_value") or "").strip()
        )
        disabled = bool(items) and configured_count == 0
        rows.append({
            "category": section.get("category"),
            "label": API_KEY_CATEGORY_LABELS.get(section.get("category"), section.get("category")),
            "items": items,
            "stored_count": stored_count,
            "secret_count": secret_count,
            "configured_count": configured_count,
            "disabled": disabled,
        })
    return rows


@settings_bp.route("/api-keys", methods=["GET", "POST"])
@login_required
@role_required(900)
@log_task(logger)
def api_keys():
    if request.method == "POST":
        form_type = (request.form.get("form_type") or "update_api_group").strip().lower()
        definition_map = get_definition_map()
        try:
            if form_type == "update_api_group":
                category = (request.form.get("category") or "").strip()
                changed = 0
                for definition in definition_map.values():
                    if definition.category != category:
                        continue
                    if definition.key not in request.form:
                        continue
                    if _upsert_api_preference(definition, request.form.get(definition.key), keep_empty_secret=True):
                        changed += 1
                db.session.commit()
                load_preferences_into_app_config(current_app._get_current_object())
                flash(f"{API_KEY_CATEGORY_LABELS.get(category, category)} aggiornata ({changed} valori).", "success")

            elif form_type == "deactivate_api_group":
                category = (request.form.get("category") or "").strip()
                changed = 0
                for definition in definition_map.values():
                    if definition.category != category:
                        continue
                    if _upsert_api_preference(definition, "", keep_empty_secret=False):
                        changed += 1
                db.session.commit()
                load_preferences_into_app_config(current_app._get_current_object())
                flash(f"{API_KEY_CATEGORY_LABELS.get(category, category)} disattivata ({changed} valori svuotati).", "success")

            elif form_type == "delete_api_group":
                category = (request.form.get("category") or "").strip()
                deleted = 0
                for definition in definition_map.values():
                    if definition.category != category:
                        continue
                    row = AppPreference.query.filter_by(key=definition.key).first()
                    if row:
                        db.session.delete(row)
                        deleted += 1
                db.session.commit()
                load_preferences_into_app_config(current_app._get_current_object())
                flash(f"Override {API_KEY_CATEGORY_LABELS.get(category, category)} eliminati ({deleted} valori).", "success")

            elif form_type == "create_env_key":
                field_name = (request.form.get("field_name") or "").strip().upper()
                field_value = request.form.get("field_value") or ""
                description = (request.form.get("field_description") or "").strip()
                if not re.match(r"^[A-Z][A-Z0-9_]*$", field_name):
                    flash("Nome campo non valido. Usa lettere maiuscole, numeri e underscore, iniziando con una lettera.", "warning")
                    return redirect(url_for("settings.api_keys"))
                set_key(_env_local_path(), field_name, field_value)
                _write_env_description(field_name, description)
                os.environ[field_name] = field_value
                current_app.config[field_name] = field_value
                flash(f"Chiave {field_name} creata in .env.local.", "success")

            elif form_type == "delete_env_key":
                field_name = (request.form.get("field_name") or "").strip().upper()
                if field_name:
                    unset_key(_env_local_path(), field_name)
                    _remove_env_description(field_name)
                    os.environ.pop(field_name, None)
                    current_app.config.pop(field_name, None)
                    flash(f"Chiave {field_name} eliminata da .env.local.", "success")
                else:
                    flash("Chiave custom non valida.", "warning")

            else:
                changed_keys = save_preferences_from_form(request.form)
                load_preferences_into_app_config(current_app._get_current_object())
                flash(f"Chiavi API aggiornate ({len(changed_keys)} valori).", "success")
        except Exception as exc:
            db.session.rollback()
            logger.exception("Errore aggiornando Chiavi API")
            flash(f"Impossibile aggiornare Chiavi API: {exc}", "danger")
        return redirect(url_for("settings.api_keys"))

    sections = _filter_preference_sections(
        build_preferences_sections(current_app._get_current_object()),
        include_categories=API_KEY_PREFERENCE_CATEGORIES,
    )
    return render_template(
        "settings/api_keys.html",
        sections=sections,
        api_rows=_build_api_key_rows(sections),
        custom_env_keys=_parse_env_local_custom_keys(),
    )


@settings_bp.route("/api-keys/matrixws/test", methods=["POST"])
@login_required
@role_required(900)
@log_task(logger)
def matrixws_test():
    payload = {
        "CodiceWS": "500003",
        "Schema": "1",
        "Versione": "20260100",
        "Operazione": "read",
        "Ditta": "1",
        "TabellaCampi": [
            {
                "WKSCADWS-STATO-EFF": "Aperto",
                "operatore": "=",
            }
        ],
    }

    try:
        config = MatrixWSConfig.from_app_config(current_app.config)
        result = call_matrixws_sync(config, payload, method="POST", timeout=(5, 120))
        secret_renewed = False
        if result["status_code"] == 401:
            renewed_secret = renew_matrixws_secret(config)
            secret_definition = get_definition_map()["matrixws.secret"]
            _upsert_api_preference(
                secret_definition,
                renewed_secret,
                keep_empty_secret=False,
            )
            db.session.commit()
            load_preferences_into_app_config(current_app._get_current_object())
            config = MatrixWSConfig.from_app_config(current_app.config)
            result = call_matrixws_sync(config, payload, method="POST", timeout=(5, 120))
            secret_renewed = True
    except MatrixWSError as exc:
        db.session.rollback()
        return jsonify({
            "ok": False,
            "kind": exc.kind,
            "message": str(exc),
            "details": exc.details,
        }), 400
    except Exception:
        db.session.rollback()
        logger.exception("Errore salvando il rinnovo secret MATRIXWS")
        return jsonify({
            "ok": False,
            "kind": "renewal_storage",
            "message": "Il secret e' stato rinnovato ma non e' stato possibile salvarlo in modo sicuro.",
        }), 500

    status_code = result["status_code"]
    if status_code in {401, 403}:
        message = "Secret MATRIXWS non accettato o non autorizzato per il servizio richiesto."
    elif status_code == 404:
        message = "Endpoint MATRIXWS non trovato: verifica ambiente, start e applicativo."
    elif not result["ok"]:
        message = f"MATRIXWS ha risposto con stato HTTP {status_code}."
    else:
        message = "Connessione e autenticazione MATRIXWS riuscite."
        if secret_renewed:
            message += " Il secret scaduto e' stato rinnovato e salvato automaticamente."

    response_body = result["json"] if result["json"] is not None else result["text"]
    response_truncated = result["truncated"]
    if isinstance(response_body, dict) and isinstance(response_body.get("dati"), list):
        record_count = len(response_body["dati"])
        if record_count > 25:
            response_body = {
                **response_body,
                "dati": response_body["dati"][:25],
                "diagnostica_app": {
                    "record_totali": record_count,
                    "record_mostrati": 25,
                    "nota": "Anteprima limitata per non rallentare la pagina impostazioni.",
                },
            }
            response_truncated = True

    return jsonify({
        "ok": result["ok"],
        "secret_renewed": secret_renewed,
        "message": message,
        "request": {
            "url": result["url"],
            "method": result["method"],
            "service_code": payload["CodiceWS"],
            "service_description": "Estrazione scadenze aperte personalizzata",
            "operation": payload["Operazione"],
        },
        "response": {
            "status_code": status_code,
            "content_type": result["content_type"],
            "body": response_body,
            "truncated": response_truncated,
        },
    }), (200 if result["ok"] else 502)


@settings_bp.route("/roles-permissions", methods=["GET", "POST"])
@login_required
@role_required(900)
@log_task(logger)
def roles_permissions():
    if request.method == "POST":
        form_type = (request.form.get("form_type") or "roles").strip().lower()
        try:
            if form_type == "create_role":
                name = (request.form.get("role_name") or "").strip()
                weight = _parse_int(request.form.get("role_weight"), 0)
                description = (request.form.get("role_description") or "").strip() or None
                if not name:
                    flash("Il nome ruolo e' obbligatorio.", "warning")
                    return redirect(url_for("settings.roles_permissions"))
                if Role.query.filter(Role.name == name).first():
                    flash("Esiste gia' un ruolo con questo nome.", "warning")
                    return redirect(url_for("settings.roles_permissions"))
                _sync_postgres_pk_sequence(Role)
                db.session.add(Role(name=name, weight=weight, description=description))
                db.session.commit()
                flash("Ruolo creato.", "success")

            elif form_type == "delete_role":
                role_id = _parse_int(request.form.get("role_id"))
                replacement_role_id = _parse_int(request.form.get("replacement_role_id"))
                role = Role.query.get_or_404(role_id)
                usage_count = UserRole.query.filter_by(role_id=role.id).count()
                if usage_count:
                    replacement = Role.query.get(replacement_role_id) if replacement_role_id is not None else None
                    if not replacement or replacement.id == role.id:
                        flash("Se il ruolo e' usato da utenti devi indicare un ruolo di destinazione valido.", "warning")
                        return redirect(url_for("settings.roles_permissions"))
                    UserRole.query.filter_by(role_id=role.id).update(
                        {"role_id": replacement.id},
                        synchronize_session=False,
                    )
                db.session.delete(role)
                db.session.commit()
                flash("Ruolo eliminato e utenti ricanalizzati.", "success")

            elif form_type == "create_permission":
                code = _normalize_permission_code(request.form.get("permission_code"))
                name = (request.form.get("permission_name") or "").strip()
                description = (request.form.get("permission_description") or "").strip() or None
                if not code or not name:
                    flash("Identificatore e nome autorizzazione sono obbligatori.", "warning")
                    return redirect(url_for("settings.roles_permissions"))
                if SpecialPermission.query.filter(SpecialPermission.code == code).first():
                    flash("Esiste gia' un'autorizzazione con questo identificatore.", "warning")
                    return redirect(url_for("settings.roles_permissions"))
                _sync_postgres_pk_sequence(SpecialPermission)
                db.session.add(SpecialPermission(code=code, name=name, description=description, is_active=True))
                db.session.commit()
                flash("Autorizzazione creata.", "success")

            elif form_type == "update_permission":
                permission_id = _parse_int(request.form.get("permission_id"))
                permission = SpecialPermission.query.get_or_404(permission_id)
                code = _normalize_permission_code(request.form.get("permission_code"))
                name = (request.form.get("permission_name") or "").strip()
                if not code or not name:
                    flash("Identificatore e nome autorizzazione sono obbligatori.", "warning")
                    return redirect(url_for("settings.roles_permissions"))
                duplicate = SpecialPermission.query.filter(
                    SpecialPermission.code == code,
                    SpecialPermission.id != permission.id,
                ).first()
                if duplicate:
                    flash("Identificatore autorizzazione gia' in uso.", "warning")
                    return redirect(url_for("settings.roles_permissions"))
                permission.code = code
                permission.name = name
                permission.description = (request.form.get("permission_description") or "").strip() or None
                permission.is_active = _form_bool(request.form, "permission_is_active", default=permission.is_active)
                db.session.commit()
                flash("Autorizzazione aggiornata.", "success")

            elif form_type == "delete_permission":
                permission_id = _parse_int(request.form.get("permission_id"))
                replacement_permission_id = _parse_int(request.form.get("replacement_permission_id"))
                permission = SpecialPermission.query.get_or_404(permission_id)
                usage_count = UserSpecialPermission.query.filter_by(permission_id=permission.id).count()
                if usage_count:
                    replacement = SpecialPermission.query.get(replacement_permission_id) if replacement_permission_id else None
                    if not replacement or replacement.id == permission.id:
                        flash("Se l'autorizzazione e' assegnata a utenti devi indicare una destinazione valida.", "warning")
                        return redirect(url_for("settings.roles_permissions"))
                    UserSpecialPermission.query.filter_by(permission_id=permission.id).update(
                        {"permission_id": replacement.id},
                        synchronize_session=False,
                    )
                db.session.delete(permission)
                db.session.commit()
                flash("Autorizzazione eliminata e assegnazioni ricanalizzate.", "success")

            elif form_type == "role_permissions":
                changed_keys = save_preferences_from_form(request.form)
                load_preferences_into_app_config(current_app._get_current_object())
                flash(f"Soglie legacy aggiornate ({len(changed_keys)} valori).", "success")

            else:
                changed = _save_role_preferences_from_form(request.form)
                flash(f"Ruoli aggiornati ({changed} modifiche).", "success")
        except SQLAlchemyError as exc:
            db.session.rollback()
            logger.exception("Errore aggiornando ruoli/autorizzazioni")
            flash(f"Impossibile completare l'operazione: {exc}", "danger")
        return redirect(url_for("settings.roles_permissions"))

    sections = _filter_preference_sections(
        build_preferences_sections(current_app._get_current_object()),
        include_categories=ROLE_PERMISSION_PREFERENCE_CATEGORIES,
    )
    try:
        roles = Role.query.order_by(Role.weight.desc(), Role.name.asc()).all()
        special_permissions = SpecialPermission.query.order_by(SpecialPermission.name.asc()).all()
        role_usage = {
            role.id: UserRole.query.filter_by(role_id=role.id).count()
            for role in roles
        }
        role_function_usage = {
            role.id: Menu.query.filter(Menu.weight == (role.weight or 0)).count()
            for role in roles
        }
        permission_usage = {
            permission.id: UserSpecialPermission.query.filter_by(permission_id=permission.id).count()
            for permission in special_permissions
        }
        permission_function_usage = {permission.id: 0 for permission in special_permissions}
    except SQLAlchemyError as exc:
        logger.warning("Ruoli non disponibili durante il caricamento ruoli/autorizzazioni: %s", exc)
        roles = []
        special_permissions = []
        role_usage = {}
        role_function_usage = {}
        permission_usage = {}
        permission_function_usage = {}
    return render_template(
        "settings/roles_permissions.html",
        sections=sections,
        roles=roles,
        special_permissions=special_permissions,
        role_usage=role_usage,
        role_function_usage=role_function_usage,
        permission_usage=permission_usage,
        permission_function_usage=permission_function_usage,
    )


@settings_bp.route("/preferences", methods=["GET", "POST"])
@login_required
@role_required(900)
@log_task(logger)
def preferences():
    flash("Configurazione e' stata sostituita dai widget dedicati.", "info")
    return redirect(url_for("settings.settings_index"))


@settings_bp.route('/update_menu', methods=['POST'])
@login_required
@role_required(500)
@log_task(logger)
def update_menu():
    try:
        menu_id = request.form.get('menu_id')
        if not menu_id:
            logger.warning("Menu ID mancante.")
            return jsonify({'success': False, 'error': 'Menu ID is missing'}), 400

        menu = Menu.query.get(menu_id)
        if not menu:
            logger.warning(f"Nessun menu trovato con ID {menu_id}")
            return jsonify({'success': False, 'error': f'No menu found with ID {menu_id}'}), 404

        menu.name = request.form.get('name')
        menu.route = request.form.get('route')
        menu.is_active = request.form.get('is_active') == 'true'
        menu.weight = request.form.get('weight')
        menu.parent_id = request.form.get('parent_id')
        menu.sort_order = int(request.form.get("sort_order") or 0)
        db.session.commit()

        logger.info(f"Menu ID {menu_id} aggiornato con successo.")
        return jsonify({'success': True, 'message': 'Menu updated successfully'})
    except Exception as e:
        db.session.rollback()
        logger.exception("Errore nell'aggiornamento menu")
        return jsonify({'success': False, 'error': str(e)}), 500


@settings_bp.route('/menu/<int:menu_id>')
@log_task(logger)
def get_menu_data(menu_id):
    logger.info(f"Richiesta dati menu ID: {menu_id}")
    menu = Menu.query.get_or_404(menu_id)
    return jsonify(menu.to_dict())


@settings_bp.route('/menus', methods=['GET', 'POST'])
@login_required
@role_required(900)
@log_task(logger)
def manage_menus():
    if request.method == 'POST':
        name = request.form['name']
        route = request.form['route']
        parent_id = request.form.get('parent_id', None)
        weight = request.form.get('weight', 0)
        parent_id = request.form.get('parent_id') or None
        parent_id_int = int(parent_id) if parent_id is not None else None
        weight = int(request.form.get('weight') or 0)

        max_sort = (db.session.query(db.func.max(Menu.sort_order))
                    .filter(Menu.parent_id == parent_id_int)
                    .scalar())
        next_sort = (max_sort or 0) + 1

        new_menu = Menu(
            name=name,
            route=route or None,
            parent_id=parent_id_int,
            weight=weight,
            sort_order=next_sort,
            is_active=True
        )
        db.session.add(new_menu)
        db.session.commit()
        flash('Menu salvato con successo!', 'success')
        logger.info(f"Nuovo menu aggiunto: {name}")
    menus = Menu.query.all()
    roles = Role.query.order_by(Role.weight.desc()).all()
    menu_fields = [column.name for column in Menu.__table__.columns if column.name != 'id']
    return render_template('settings/menus.html', menus=menus, roles=roles, menu_fields=menu_fields)


@settings_bp.route('/import_articoli', methods=['GET', 'POST'])
@login_required
@role_required(100)
@log_task(logger)
def lancia_import_articoli():
    logger.info("Importazione articoli richiesta.")
    task = import_articoli_task.delay()
    from tools.redis_utils import update_task, status_string
    update_task(task.id, "Importazione articoli", 0, status_string['attached'])
    return '', 204


@settings_bp.route('/import_ps_data', methods=['GET', 'POST'])
@login_required
@role_required(500)
@log_task(logger)
def lancia_import_prestashop():
    logger.info("Importazione Prestashop richiesta.")
    task = import_ps_task.delay()
    from tools.redis_utils import update_task, status_string
    update_task(task.id, "Importazione dati da Prestashop", 0, status_string['attached'])
    return '', 204


@settings_bp.route('/import_poleepo_products', methods=['GET', 'POST'])
@login_required
@role_required(500)
@log_task(logger)
def lancia_import_prodotti_poleepo():
    logger.info("Importazione prodotti Poleepo richiesta.")
    task = import_poleepo_products_task.delay({})
    from tools.redis_utils import update_task, status_string
    update_task(task.id, "Importazione prodotti da Poleepo", 0, status_string['attached'])
    return '', 204


@settings_bp.route("/reorder_menus", methods=["POST"])
@login_required
@role_required(900)
@log_task(logger)
def reorder_menus():
    data = request.get_json(silent=True) or {}
    items = data.get("items") or []

    if not isinstance(items, list) or not items:
        return jsonify({"ok": False, "error": "Payload non valido: items[] richiesto"}), 400

    try:
        parent_by_id = {
            int(it["id"]): (int(it["parent_id"]) if it.get("parent_id") is not None else None)
            for it in items
            if it.get("id") is not None
        }

        def would_create_cycle(menu_id, parent_id):
            seen = {menu_id}
            current = parent_id
            while current is not None:
                if current in seen:
                    return True
                seen.add(current)
                if current in parent_by_id:
                    current = parent_by_id[current]
                else:
                    parent = Menu.query.get(current)
                    current = parent.parent_id if parent else None
            return False

        # Validazione + update
        for it in items:
            mid = it.get("id")
            if mid is None:
                continue

            mid = int(mid)
            menu = Menu.query.get(mid)
            if not menu:
                continue

            parent_id = it.get("parent_id", None)
            parent_id = int(parent_id) if parent_id is not None else None
            sort_order = it.get("sort_order", 0)

            if parent_id == mid or would_create_cycle(mid, parent_id):
                return jsonify({"ok": False, "error": "Gerarchia menu non valida"}), 400

            menu.parent_id = parent_id
            menu.sort_order = int(sort_order)

        db.session.commit()
        return jsonify({"ok": True, "updated": len(items)})
    except Exception as e:
        db.session.rollback()
        logger.exception("Errore reorder_menus")
        return jsonify({"ok": False, "error": str(e)}), 500


@settings_bp.route('/import_art_descr', methods=['GET', 'POST'])
@login_required
@role_required(500)
@log_task(logger)
def lancia_import_descr_prestashop():
    logger.info("Importazione descrizione articolo da Prestashop richiesta (hardcoded).")
    get_product_by_code('VB075133-21')
    return jsonify({'success': True, 'message': 'Interrogazione conclusa.'})


@settings_bp.route('/import_giacenze', methods=['GET', 'POST'])
@login_required
@role_required(100)
@log_task(logger)
def lancia_import_giacenze():
    logger.info("Importazione giacenze richiesta.")
    task = import_giacenze_task.delay()
    from tools.redis_utils import update_task, status_string
    update_task(task.id, "Importazione giacenze da gestionale", 0, status_string['attached'])
    return '', 204


@settings_bp.route('/import_barcode', methods=['GET', 'POST'])
@login_required
@role_required(100)
@log_task(logger)
def lancia_import_barcode():
    logger.info("Importazione codici a barre richiesta.")
    task = import_barcode_task.delay()
    from tools.redis_utils import update_task, status_string
    update_task(task.id, "Importazione codici a barre articoli da gestionale", 0, status_string['attached'])
    return '', 204


@settings_bp.route('/import_anagrafiche', methods=['GET', 'POST'])
@login_required
@role_required(100)
@log_task(logger)
def lancia_import_anagrafiche():
    logger.info("Importazione anagrafiche richiesta.")
    task = import_anagrafiche_task.delay()
    from tools.redis_utils import update_task, status_string
    update_task(task.id, "Importazione anagrafiche TeamSystem", 0, status_string['attached'])
    if request.accept_mimetypes.best == "application/json" or request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"ok": True, "task_id": task.id}), 202
    flash("Importazione anagrafiche avviata.", "success")
    return redirect(request.referrer or "/importazioni/storico")


@settings_bp.route('/import_estratti_conto_clienti', methods=['GET', 'POST'])
@login_required
@role_required(100)
@log_task(logger)
def lancia_import_estratti_conto_clienti():
    logger.info("Importazione estratti conto clienti richiesta.")
    task = import_estratti_conto_clienti_task.delay()
    from tools.redis_utils import update_task, status_string
    update_task(task.id, "Importazione estratti conto clienti TeamSystem", 0, status_string['attached'])
    if request.accept_mimetypes.best == "application/json" or request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"ok": True, "task_id": task.id}), 202
    flash("Importazione delle situazioni contabili avviata.", "success")
    return redirect(request.referrer or "/importazioni/storico")


@settings_bp.route("/import_conflicts", methods=["GET"])
@login_required
@role_required(40)
def import_conflicts_page():
    return render_template("settings/import_conflicts.html")


@settings_bp.route("/next_conflict", methods=["GET"])
@login_required
@role_required(40)
def api_import_conflicts_next():
    ctype = request.args.get("type")

    q = ImportConflict.query.filter(ImportConflict.status == "pending")
    if ctype:
        q = q.filter(ImportConflict.type == ctype)

    pending_count = q.count()
    conflict = q.order_by(ImportConflict.created_at.asc(), ImportConflict.id.asc()).first()

    if not conflict:
        return jsonify({"ok": True, "conflict": None, "pending_count": pending_count})

    duplicate_count = (
        ImportConflict.query
        .filter(
            ImportConflict.status == "pending",
            ImportConflict.type == conflict.type,
            ImportConflict.payload == conflict.payload,
        )
        .count()
    )
    current_position = (
        q.filter(
            or_(
                ImportConflict.created_at < conflict.created_at,
                and_(
                    ImportConflict.created_at == conflict.created_at,
                    ImportConflict.id <= conflict.id,
                ),
            )
        )
        .count()
    )

    return jsonify({
        "ok": True,
        "pending_count": pending_count,
        "current_position": current_position,
        "duplicate_count": duplicate_count,
        "conflict": {
            "id": conflict.id,
            "type": conflict.type,
            "payload": conflict.payload,
            "created_at": conflict.created_at.isoformat() if conflict.created_at else None,
        }
    })


import hashlib
import json
from flask import request, jsonify
from flask_login import login_required

from extensions import db
from models import ImportConflict, ImportConflictResolution  # adegua i nomi se diversi


def _sha256_text(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if s == "":
        return None
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


@settings_bp.route("/resolve_conflict", methods=["POST"])
@login_required
@role_required(40)
def resolve_conflict():
    data = request.get_json(silent=True) or {}
    conflict_id = data.get("id")
    action = (data.get("action") or "").strip().upper()
    mode = (data.get("mode") or "CONDITIONAL").strip().upper()
    resolve_identical = bool(data.get("resolve_identical", True))

    if not conflict_id or action not in {"KEEP_CSV", "KEEP_DB", "SKIP"}:
        return jsonify(ok=False, error="Payload non valido: servono id e action (KEEP_CSV|KEEP_DB|SKIP)."), 400

    c = ImportConflict.query.get(conflict_id)
    if not c:
        return jsonify(ok=False, error="Conflitto non trovato."), 404

    duplicate_q = ImportConflict.query.filter(
        ImportConflict.status == "pending",
        ImportConflict.type == c.type,
        ImportConflict.payload == c.payload,
    )
    duplicate_conflicts = duplicate_q.all() if resolve_identical else [c]

    if action == "SKIP":
        for conflict in duplicate_conflicts:
            conflict.status = "skipped"
            conflict.resolved_at = datetime.utcnow()
            conflict.resolved_by = current_user.id if current_user.is_authenticated else None
        db.session.commit()
        return jsonify(ok=True, skipped=True, id=c.id, duplicates_resolved=len(duplicate_conflicts))

    payload = c.payload or {}
    cod_art = payload.get("cod_art") or payload.get("entity_key")
    csv_obj = payload.get("csv") or {}
    db_obj = payload.get("db") or {}

    if not cod_art:
        return jsonify(ok=False, error="Payload conflitto senza cod_art/entity_key."), 400

    all_fields = sorted(set(list(csv_obj.keys()) + list(db_obj.keys())))
    if not all_fields:
        return jsonify(ok=False, error="Payload conflitto senza campi csv/db."), 400

    rule_mode = mode if mode in {"CONDITIONAL", "ALWAYS"} else "CONDITIONAL"
    created = 0
    for conflict in duplicate_conflicts:
        duplicate_payload = conflict.payload or {}
        duplicate_cod_art = duplicate_payload.get("cod_art") or duplicate_payload.get("entity_key") or cod_art
        duplicate_csv = duplicate_payload.get("csv") or csv_obj
        duplicate_db = duplicate_payload.get("db") or db_obj
        duplicate_fields = sorted(set(list(duplicate_csv.keys()) + list(duplicate_db.keys())))

        for field in duplicate_fields:
            csv_val = duplicate_csv.get(field)
            db_val = duplicate_db.get(field)
            db.session.add(ImportConflictResolution(
                type=conflict.type,
                entity_key=str(duplicate_cod_art),
                field=str(field),
                db_value=None if db_val is None else str(db_val),
                csv_value=None if csv_val is None else str(csv_val),
                db_value_hash=_sha256_text(db_val),
                csv_value_hash=_sha256_text(csv_val),
                action=action,
                mode=rule_mode,
            ))
            created += 1

    if action == "KEEP_CSV":
        art = Articoli.query.filter_by(cod_art=cod_art).first()
        if not art:
            return jsonify(ok=False, error=f"Articolo not found for cod_art={cod_art}"), 404
        if "descrizione" in csv_obj:
            art.descrizione = csv_obj.get("descrizione")
        if "descrizione_aggiuntiva" in csv_obj:
            art.descrizione_aggiuntiva = csv_obj.get("descrizione_aggiuntiva")
        if "prezzo" in csv_obj:
            art.prezzo = csv_obj.get("prezzo")

    for conflict in duplicate_conflicts:
        db.session.delete(conflict)
    db.session.commit()

    return jsonify(
        ok=True,
        resolved=True,
        action=action,
        mode=rule_mode,
        rules_created=created,
        duplicates_resolved=len(duplicate_conflicts),
    )


@settings_bp.route("/get_menu_structure", methods=["GET"])
@login_required
@role_required(900)
@log_task(logger)
def get_menu_structure():
    menus = (
        Menu.query
        .order_by(asc(Menu.parent_id), asc(Menu.sort_order), asc(Menu.id))
        .all()
    )
    return jsonify([m.to_dict() for m in menus])


@settings_bp.route("/create_menu", methods=["POST"])
@login_required
@role_required(900)
@log_task(logger)
def create_menu():
    data = request.get_json(silent=True) or {}

    name = (data.get("name") or "").strip()
    item_type = (data.get("item_type") or "link").strip()
    if item_type not in ("link", "separator"):
        return jsonify(ok=False, error="Tipo menu non valido"), 400
    if item_type == "separator" and not name:
        name = "Separatore"
    if not name:
        return jsonify(ok=False, error="Nome obbligatorio"), 400

    parent_id = data.get("parent_id")
    parent_id = int(parent_id) if parent_id is not None else None
    if parent_id is not None and not Menu.query.get(parent_id):
        return jsonify(ok=False, error="Menu padre non trovato"), 404

    weight = int(data.get("weight") or 0)
    route = data.get("route") or None
    is_active = bool(data.get("is_active", True))
    is_visible = bool(data.get("is_visible", True))
    if is_active:
        is_visible = True

    # sort_order = ultimo tra i fratelli + 1
    max_sort = (db.session.query(db.func.max(Menu.sort_order))
                .filter(Menu.parent_id == parent_id)
                .scalar())
    sort_order = (max_sort or 0) + 1

    m = Menu(
        name=name,
        route=route,
        parent_id=parent_id,
        weight=weight,
        sort_order=sort_order,
        is_active=is_active,
        is_visible=is_visible,
        item_type=item_type
    )
    db.session.add(m)
    db.session.commit()

    return jsonify(ok=True, id=m.id)


@settings_bp.route("/update_menu_json", methods=["POST"])
@login_required
@role_required(900)
@log_task(logger)
def update_menu_json():
    data = request.get_json(silent=True) or {}
    mid = data.get("id")
    if not mid:
        return jsonify(ok=False, error="ID mancante"), 400

    m = Menu.query.get_or_404(int(mid))

    m.name = (data.get("name") or "").strip()
    item_type = (data.get("item_type") or m.item_type or "link").strip()
    if item_type not in ("link", "separator"):
        return jsonify(ok=False, error="Tipo menu non valido"), 400
    if item_type == "separator" and not m.name:
        m.name = "Separatore"
    if not m.name:
        return jsonify(ok=False, error="Nome obbligatorio"), 400

    m.route = data.get("route") or None
    m.weight = int(data.get("weight") or 0)
    m.is_active = bool(data.get("is_active", True))
    m.is_visible = bool(data.get("is_visible", True))
    if m.is_active:
        m.is_visible = True
    m.item_type = item_type

    if "parent_id" in data:
        parent_id = data.get("parent_id")
        parent_id = int(parent_id) if parent_id is not None else None

        if parent_id == m.id:
            return jsonify(ok=False, error="Un menu non può essere padre di sé stesso"), 400

        current = parent_id
        while current is not None:
            if current == m.id:
                return jsonify(ok=False, error="Gerarchia menu non valida"), 400

            parent = Menu.query.get(current)
            if not parent:
                return jsonify(ok=False, error="Menu padre non trovato"), 404

            current = parent.parent_id

        m.parent_id = parent_id

    db.session.commit()
    return jsonify(ok=True)


@settings_bp.route("/delete_menu/<int:menu_id>", methods=["POST"])
@login_required
@role_required(900)
@log_task(logger)
def delete_menu(menu_id):
    data = request.get_json(silent=True) or {}
    cascade = bool(data.get("cascade", False))

    menu = Menu.query.get_or_404(menu_id)

    children = Menu.query.filter(Menu.parent_id == menu.id).all()
    has_children = len(children) > 0

    if has_children and not cascade:
        return jsonify({
            "ok": False,
            "code": "HAS_CHILDREN",
            "error": "Il menu contiene sotto-menu. Conferma eliminazione con cascata."
        }), 409

    try:
        if cascade:
            # elimina figli (e nipoti) in profondità
            def delete_rec(m):
                for c in Menu.query.filter(Menu.parent_id == m.id).all():
                    delete_rec(c)
                db.session.delete(m)

            delete_rec(menu)
        else:
            db.session.delete(menu)

        db.session.commit()
        return jsonify({"ok": True, "cascade": cascade})

    except Exception as e:
        db.session.rollback()
        logger.exception("Errore delete_menu")
        return jsonify({"ok": False, "error": str(e)}), 500


@settings_bp.route("/toggle_menu_active/<int:menu_id>", methods=["POST"])
@login_required
@role_required(900)
@log_task(logger)
def toggle_menu_active(menu_id):
    m = Menu.query.get_or_404(menu_id)
    m.is_active = not bool(m.is_active)
    if m.is_active:
        m.is_visible = True
    db.session.commit()
    return jsonify(ok=True, id=m.id, is_active=bool(m.is_active))


@settings_bp.route("/toggle_menu_visible/<int:menu_id>", methods=["POST"])
@login_required
@role_required(900)
@log_task(logger)
def toggle_menu_visible(menu_id):
    m = Menu.query.get_or_404(menu_id)
    if m.is_active:
        return jsonify(ok=False, error="Un menu attivo è sempre visibile"), 400
    m.is_visible = not bool(m.is_visible)
    db.session.commit()
    return jsonify(ok=True, id=m.id, is_visible=bool(m.is_visible))
