import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import load_only, selectinload
from werkzeug.utils import secure_filename

from extensions import db
from models import (
    BusinessRegistry,
    CustomerAccountingItemState,
    CustomerAccountEntry,
    CustomerAccountStatementImport,
    CustomerPaymentAllocation,
    CustomerPaymentCase,
    CustomerPaymentEvent,
    CustomerPaymentEvidence,
    CustomerPaymentInstructions,
    User,
)
from tools.customer_memberships import active_customer_memberships, customer_registry_for_user
from tools.customer_payments import (
    ACTIVE_ITEM_STATUSES,
    account_entry_snapshot,
    account_entry_source_key,
    format_iban,
    is_valid_iban,
    is_selectable_settlement_item,
)
from tools.log_utils import get_logger
from tools.nexi_xpay import NexiXPayClient, NexiXPayError, NexiXPayUncertainError
from tools.role_required import role_required


customer_account_bp = Blueprint("customer_account", __name__)
ALLOWED_ROLE_NAMES = {"customer_horeca", "dev"}
CASE_STATUS_LABELS = {
    "creating_checkout": "Preparazione pagamento in corso",
    "checkout_ready": "Pagamento da completare",
    "provider_authorized": "Pagamento autorizzato",
    "provider_uncertain": "Pagamento in verifica tecnica",
    "awaiting_accounting": "In attesa di contabilizzazione",
    "under_review": "In fase di verifica",
    "partially_accounted": "Parzialmente contabilizzato",
    "accounted": "Contabilizzato",
    "rejected": "Rigettato",
    "cancelled": "Annullato",
    "failed": "Errore",
    "expired": "Scaduto",
}
TERMINAL_CASE_STATUSES = {"accounted", "rejected", "cancelled", "failed", "expired"}
CUSTOMER_EDITABLE_CASE_STATUSES = {"awaiting_accounting", "under_review"}
OFFICE_CASE_STATUSES = tuple(CASE_STATUS_LABELS)
CASE_TYPE_LABELS = {
    "bank_transfer": "Comunicazione di pagamento",
    "payment_claim": "Contestazione partita aperta",
    "online_payment": "Pagamento online",
}
MAX_EVIDENCE_BYTES = 12 * 1024 * 1024
logger = get_logger("customer_account")


def _base36(value):
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    value = int(value)
    result = "0"
    if value > 0:
        parts = []
        while value:
            value, remainder = divmod(value, 36)
            parts.append(alphabet[remainder])
        result = "".join(reversed(parts))
    return result


def _nexi_is_configured():
    return bool(str(current_app.config.get("NEXI_XPAY_API_KEY") or "").strip())


def _public_url(endpoint, **values):
    path = url_for(endpoint, _external=False, **values)
    base_url = (
        current_app.config.get("PUBLIC_BASE_URL")
        or os.getenv("PUBLIC_BASE_URL")
        or "https://ldapp.ldenoteca.it"
    )
    return f"{str(base_url).rstrip('/')}{path}"


def _active_role_names():
    return {str(getattr(role, "name", "")).strip().lower() for role in current_user.active_roles or []}


def _role_context():
    role_names = _active_role_names()
    if not role_names.intersection(ALLOWED_ROLE_NAMES):
        abort(403)
    return role_names, "dev" in role_names


def _authorized_registry(registry_id, is_developer):
    if not registry_id:
        return None
    if is_developer:
        return BusinessRegistry.query.filter_by(id=registry_id, kind="customer", is_active=True).first()
    return customer_registry_for_user(current_user, registry_id)


def _latest_statement_import():
    return (
        CustomerAccountStatementImport.query
        .order_by(CustomerAccountStatementImport.imported_at.desc(), CustomerAccountStatementImport.id.desc())
        .first()
    )


def _entry_ownership_filter(registry):
    return or_(
        CustomerAccountEntry.registry_id == registry.id,
        and_(
            CustomerAccountEntry.registry_id.is_(None),
            CustomerAccountEntry.source_customer_code == registry.source_code,
        ),
    )


def _payment_instructions(include_inactive=False):
    query = CustomerPaymentInstructions.query.order_by(CustomerPaymentInstructions.id.asc())
    if not include_inactive:
        query = query.filter(CustomerPaymentInstructions.is_active.is_(True))
    return query.first()


def _detect_evidence_type(data):
    if data.startswith(b"%PDF-"):
        return "pdf", "application/pdf"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg", "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp", "image/webp"
    if len(data) >= 12 and data[4:8] == b"ftyp" and data[8:12] in {b"heic", b"heix", b"hevc", b"hevx", b"heif", b"mif1"}:
        return "heic", "image/heic"
    return None, None


def _trimmed_form_value(name, limit):
    return (request.form.get(name) or "").strip()[:limit] or None


@customer_account_bp.get("/")
@login_required
def index():
    _, is_developer = _role_context()
    requested_registry_id = request.args.get("customer", type=int)
    if is_developer:
        registries = (
            BusinessRegistry.query
            .options(load_only(
                BusinessRegistry.id,
                BusinessRegistry.display_name,
                BusinessRegistry.legal_name,
                BusinessRegistry.source_code,
            ))
            .filter_by(kind="customer", is_active=True)
            .order_by(BusinessRegistry.display_name.asc(), BusinessRegistry.id.asc())
            .all()
        )
        registry = next(
            (item for item in registries if requested_registry_id is not None and item.id == requested_registry_id),
            registries[0] if registries else None,
        )
    else:
        memberships = active_customer_memberships(current_user)
        registries = [membership.registry for membership in memberships]
        registry = customer_registry_for_user(current_user, requested_registry_id)
        if not registries and registry is not None:
            registries = [registry]

    current_import = _latest_statement_import()
    entries = None
    totals = None
    recent_cases = []
    payable_entry_ids = set()
    entry_states = {}
    if registry is not None and current_import is not None:
        ownership_filter = _entry_ownership_filter(registry)
        base_query = CustomerAccountEntry.query.filter(
            CustomerAccountEntry.import_id == current_import.id,
            ownership_filter,
        )
        entries = base_query.order_by(
            CustomerAccountEntry.document_date.desc().nullslast(),
            CustomerAccountEntry.row_number.desc(),
        ).paginate(page=max(1, request.args.get("page", type=int) or 1), per_page=50, error_out=False)
        totals = db.session.query(
            func.sum(case((CustomerAccountEntry.accounting_side == "D", CustomerAccountEntry.amount), else_=0)).label("debit"),
            func.sum(case((CustomerAccountEntry.accounting_side == "A", CustomerAccountEntry.amount), else_=0)).label("credit"),
            func.sum(CustomerAccountEntry.signed_amount).label("balance"),
        ).filter(
            CustomerAccountEntry.import_id == current_import.id,
            ownership_filter,
            CustomerAccountEntry.is_balance_relevant.is_(True),
        ).one()
        entry_keys = {
            entry.id: account_entry_source_key(entry)
            for entry in entries.items
            if is_selectable_settlement_item(entry)
        }
        if entry_keys:
            active_states = (
                CustomerAccountingItemState.query
                .filter(
                    CustomerAccountingItemState.registry_id == registry.id,
                    CustomerAccountingItemState.source_item_key.in_(tuple(entry_keys.values())),
                    CustomerAccountingItemState.status.in_(tuple(ACTIVE_ITEM_STATUSES)),
                )
                .all()
            )
            states_by_key = {state.source_item_key: state for state in active_states}
            payable_entry_ids = {
                entry_id for entry_id, source_key in entry_keys.items()
                if source_key not in states_by_key
            }
            entry_states = {
                entry_id: states_by_key[source_key]
                for entry_id, source_key in entry_keys.items()
                if source_key in states_by_key
            }
        recent_cases = (
            CustomerPaymentCase.query
            .options(
                selectinload(CustomerPaymentCase.allocations),
                selectinload(CustomerPaymentCase.evidence),
            )
            .filter(
                CustomerPaymentCase.registry_id == registry.id,
                CustomerPaymentCase.status != "cancelled",
            )
            .order_by(CustomerPaymentCase.created_at.desc())
            .limit(20)
            .all()
        )

    payment_instructions = _payment_instructions(include_inactive=is_developer)

    return render_template(
        "customer_account/index.html",
        registries=registries,
        registry=registry,
        current_import=current_import,
        entries=entries,
        totals=totals,
        recent_cases=recent_cases,
        is_developer=is_developer,
        payable_entry_ids=payable_entry_ids,
        entry_states=entry_states,
        payment_instructions=payment_instructions,
        formatted_iban=format_iban(payment_instructions.iban) if payment_instructions else None,
        case_status_labels=CASE_STATUS_LABELS,
        case_type_labels=CASE_TYPE_LABELS,
        customer_editable_case_statuses=CUSTOMER_EDITABLE_CASE_STATUSES,
        nexi_configured=_nexi_is_configured(),
        nexi_environment=str(current_app.config.get("NEXI_XPAY_ENVIRONMENT") or "sandbox").strip().lower(),
    )


@customer_account_bp.get("/select/<int:registry_id>")
@login_required
def select_registry(registry_id):
    _, is_developer = _role_context()
    registry = _authorized_registry(registry_id, is_developer)
    if registry is None:
        abort(403)
    return redirect(url_for("customer_account.index", customer=registry_id))


@customer_account_bp.post("/bank-details")
@login_required
def save_bank_details():
    _, is_developer = _role_context()
    if not is_developer:
        abort(403)

    compact_iban = "".join((request.form.get("iban") or "").upper().split())
    account_holder = _trimmed_form_value("account_holder", 255)
    if not account_holder:
        flash("L'intestatario del conto e' obbligatorio.", "warning")
        return redirect(url_for("customer_account.index", customer=request.form.get("registry_id")))
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", compact_iban) or not is_valid_iban(compact_iban):
        flash("IBAN non valido: controlla il codice inserito.", "warning")
        return redirect(url_for("customer_account.index", customer=request.form.get("registry_id")))

    instructions = _payment_instructions(include_inactive=True)
    if instructions is None:
        instructions = CustomerPaymentInstructions()
        db.session.add(instructions)
    instructions.label = _trimmed_form_value("label", 120) or "Bonifico bancario"
    instructions.account_holder = account_holder
    instructions.iban = compact_iban
    instructions.bank_name = _trimmed_form_value("bank_name", 160)
    instructions.bic_swift = _trimmed_form_value("bic_swift", 16)
    instructions.beneficiary_address = _trimmed_form_value("beneficiary_address", 255)
    instructions.payment_reason_template = _trimmed_form_value("payment_reason_template", 500)
    instructions.notes = (request.form.get("notes") or "").strip()[:4000] or None
    instructions.is_active = request.form.get("is_active") == "1"
    instructions.updated_by_user_id = current_user.id
    db.session.commit()
    flash("Coordinate per i bonifici aggiornate.", "success")
    return redirect(url_for("customer_account.index", customer=request.form.get("registry_id")))


@customer_account_bp.post("/payments/bank-transfer")
@login_required
def communicate_bank_transfer():
    _, is_developer = _role_context()
    registry_id = request.form.get("registry_id", type=int)
    registry = _authorized_registry(registry_id, is_developer)
    if registry is None:
        abort(403)

    raw_entry_ids = request.form.getlist("entry_ids")
    try:
        entry_ids = list(dict.fromkeys(int(value) for value in raw_entry_ids if str(value).strip()))
    except (TypeError, ValueError):
        entry_ids = []
    if not entry_ids or len(entry_ids) > 50:
        flash("Seleziona da una a 50 fatture.", "warning")
        return redirect(url_for("customer_account.index", customer=registry.id))

    current_import = _latest_statement_import()
    if current_import is None:
        flash("La situazione contabile non e' disponibile.", "warning")
        return redirect(url_for("customer_account.index", customer=registry.id))

    entries = (
        CustomerAccountEntry.query
        .filter(
            CustomerAccountEntry.import_id == current_import.id,
            CustomerAccountEntry.id.in_(entry_ids),
            _entry_ownership_filter(registry),
        )
        .all()
    )
    entries_by_id = {entry.id: entry for entry in entries if is_selectable_settlement_item(entry)}
    if len(entries_by_id) != len(entry_ids):
        abort(400, description="Uno o piu' documenti non sono selezionabili nell'ultimo aggiornamento.")
    entries = [entries_by_id[entry_id] for entry_id in entry_ids]
    source_keys = [account_entry_source_key(entry) for entry in entries]
    if len(set(source_keys)) != len(source_keys):
        abort(409, description="Due righe selezionate hanno la stessa identita' contabile.")

    already_active = (
        CustomerAccountingItemState.query
        .filter(
            CustomerAccountingItemState.registry_id == registry.id,
            CustomerAccountingItemState.source_item_key.in_(tuple(source_keys)),
            CustomerAccountingItemState.status.in_(tuple(ACTIVE_ITEM_STATUSES)),
        )
        .first()
    )
    if already_active:
        flash("Almeno un documento selezionato appartiene gia' a una pratica in corso.", "warning")
        return redirect(url_for("customer_account.index", customer=registry.id))

    declared_amount = sum((Decimal(entry.signed_amount) for entry in entries), Decimal("0.00"))
    if declared_amount <= 0:
        flash("Il totale dei documenti selezionati deve essere maggiore di zero.", "warning")
        return redirect(url_for("customer_account.index", customer=registry.id))

    upload = request.files.get("payment_evidence")
    if upload is None or not upload.filename:
        flash("Allega la contabile del bonifico.", "warning")
        return redirect(url_for("customer_account.index", customer=registry.id))
    evidence_data = upload.read(MAX_EVIDENCE_BYTES + 1)
    if not evidence_data:
        flash("Il file allegato e' vuoto.", "warning")
        return redirect(url_for("customer_account.index", customer=registry.id))
    if len(evidence_data) > MAX_EVIDENCE_BYTES:
        flash("La contabile supera il limite di 12 MB.", "warning")
        return redirect(url_for("customer_account.index", customer=registry.id))
    extension, content_type = _detect_evidence_type(evidence_data)
    if not extension:
        flash("Formato contabile non supportato. Usa PDF, JPG, PNG, WEBP o HEIC.", "warning")
        return redirect(url_for("customer_account.index", customer=registry.id))

    submitted_at = datetime.now(timezone.utc)
    transfer_date = _trimmed_form_value("transfer_date", 10)
    if transfer_date:
        try:
            transfer_date = datetime.strptime(transfer_date, "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError:
            flash("La data del bonifico non e' valida.", "warning")
            return redirect(url_for("customer_account.index", customer=registry.id))
    transfer_reference = _trimmed_form_value("transfer_reference", 255)
    payment_reference = " - ".join(value for value in (transfer_date, transfer_reference) if value) or None
    payment_case = CustomerPaymentCase(
        registry_id=registry.id,
        created_by_user_id=current_user.id,
        case_type="bank_transfer",
        status="awaiting_accounting",
        currency="EUR",
        declared_amount=declared_amount,
        payment_reference=payment_reference,
        note=(request.form.get("note") or "").strip()[:4000] or None,
        submitted_at=submitted_at,
    )
    db.session.add(payment_case)
    target_path = None
    try:
        db.session.flush()
        evidence_root = Path(current_app.instance_path) / "customer_payment_evidence"
        case_folder = evidence_root / payment_case.public_id
        case_folder.mkdir(parents=True, exist_ok=True)
        stored_name = f"{secrets.token_hex(16)}.{extension}"
        target_path = case_folder / stored_name
        target_path.write_bytes(evidence_data)
        relative_storage_path = target_path.relative_to(Path(current_app.instance_path)).as_posix()
        original_filename = secure_filename(Path(upload.filename).name)[:255] or f"contabile.{extension}"

        db.session.add(CustomerPaymentEvidence(
            case_id=payment_case.id,
            uploaded_by_user_id=current_user.id,
            original_filename=original_filename,
            storage_path=relative_storage_path,
            content_type=content_type,
            size_bytes=len(evidence_data),
            sha256=hashlib.sha256(evidence_data).hexdigest(),
        ))
        existing_states = {
            state.source_item_key: state
            for state in CustomerAccountingItemState.query.filter(
                CustomerAccountingItemState.registry_id == registry.id,
                CustomerAccountingItemState.source_item_key.in_(tuple(source_keys)),
            ).all()
        }
        for entry, source_key in zip(entries, source_keys):
            db.session.add(CustomerPaymentAllocation(
                case_id=payment_case.id,
                source_customer_code=entry.source_customer_code,
                source_item_key=source_key,
                current_entry_id=entry.id,
                allocated_amount=entry.signed_amount,
                document_snapshot=account_entry_snapshot(entry),
            ))
            item_state = existing_states.get(source_key)
            if item_state is None:
                item_state = CustomerAccountingItemState(
                    registry_id=registry.id,
                    source_customer_code=entry.source_customer_code,
                    source_item_key=source_key,
                )
                db.session.add(item_state)
            item_state.status = "awaiting_accounting"
            item_state.payment_case_id = payment_case.id
            item_state.last_seen_entry_id = entry.id
            item_state.message = "Contabile bonifico inviata dal cliente"
        db.session.add(CustomerPaymentEvent(
            case_id=payment_case.id,
            actor_user_id=current_user.id,
            event_type="bank_transfer_submitted",
            from_status=None,
            to_status="awaiting_accounting",
            message="Contabile bonifico inviata",
            event_metadata={"document_count": len(entries), "evidence_sha256": hashlib.sha256(evidence_data).hexdigest()},
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()
        if target_path is not None:
            try:
                target_path.unlink(missing_ok=True)
            except OSError:
                pass
        logger.exception("Errore registrazione comunicazione bonifico cliente=%s", registry.id)
        flash("Non e' stato possibile registrare la comunicazione. Riprova.", "danger")
        return redirect(url_for("customer_account.index", customer=registry.id))

    try:
        from config.tasks import notify_customer_payment_case_task

        notify_customer_payment_case_task.delay(payment_case.id)
    except Exception:
        logger.exception("Impossibile accodare la notifica ufficio per la pratica %s", payment_case.id)
        try:
            db.session.add(CustomerPaymentEvent(
                case_id=payment_case.id,
                event_type="office_notification_queue_failed",
                message="Notifica email non accodata; la pratica resta disponibile nella coda ufficio.",
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception("Impossibile registrare il mancato accodamento della pratica %s", payment_case.id)

    flash(
        f"Contabile inviata: {len(entries)} documenti per {declared_amount:.2f} EUR. "
        "La pratica e' in attesa di contabilizzazione ed e' stata inoltrata all'ufficio.",
        "success",
    )
    return redirect(url_for("customer_account.index", customer=registry.id))


@customer_account_bp.post("/payments/claim")
@login_required
def submit_payment_claim():
    _, is_developer = _role_context()
    registry_id = request.form.get("registry_id", type=int)
    registry = _authorized_registry(registry_id, is_developer)
    if registry is None:
        abort(403)

    try:
        entry_ids = list(dict.fromkeys(
            int(value) for value in request.form.getlist("entry_ids") if str(value).strip()
        ))
    except (TypeError, ValueError):
        entry_ids = []
    if not entry_ids or len(entry_ids) > 50:
        flash("Seleziona da uno a 50 documenti da contestare.", "warning")
        return redirect(url_for("customer_account.index", customer=registry.id))

    current_import = _latest_statement_import()
    if current_import is None:
        flash("La situazione contabile non e' disponibile.", "warning")
        return redirect(url_for("customer_account.index", customer=registry.id))
    entries = CustomerAccountEntry.query.filter(
        CustomerAccountEntry.import_id == current_import.id,
        CustomerAccountEntry.id.in_(entry_ids),
        _entry_ownership_filter(registry),
    ).all()
    entries_by_id = {entry.id: entry for entry in entries if is_selectable_settlement_item(entry)}
    if len(entries_by_id) != len(entry_ids):
        abort(400, description="Uno o piu' documenti non sono contestabili nell'ultimo aggiornamento.")
    entries = [entries_by_id[entry_id] for entry_id in entry_ids]
    source_keys = [account_entry_source_key(entry) for entry in entries]
    if len(set(source_keys)) != len(source_keys):
        abort(409, description="Due righe selezionate hanno la stessa identita' contabile.")
    if CustomerAccountingItemState.query.filter(
        CustomerAccountingItemState.registry_id == registry.id,
        CustomerAccountingItemState.source_item_key.in_(tuple(source_keys)),
        CustomerAccountingItemState.status.in_(tuple(ACTIVE_ITEM_STATUSES)),
    ).first():
        flash("Almeno un documento selezionato appartiene gia' a una pratica in corso.", "warning")
        return redirect(url_for("customer_account.index", customer=registry.id))

    reason = (request.form.get("reason") or "").strip()[:4000] or None
    uploads = [item for item in request.files.getlist("claim_evidence") if item and item.filename]
    if len(uploads) > 5:
        flash("Puoi allegare al massimo 5 prove di pagamento.", "warning")
        return redirect(url_for("customer_account.index", customer=registry.id))
    if not reason and not uploads:
        flash("Scrivi una motivazione oppure allega almeno una prova di pagamento.", "warning")
        return redirect(url_for("customer_account.index", customer=registry.id))

    prepared_uploads = []
    total_evidence_bytes = 0
    for upload in uploads:
        data = upload.read(MAX_EVIDENCE_BYTES + 1)
        extension, content_type = _detect_evidence_type(data)
        if not data or len(data) > MAX_EVIDENCE_BYTES or not extension:
            flash("Una delle prove non e' valida. Usa PDF, JPG, PNG, WEBP o HEIC, massimo 12 MB ciascuna.", "warning")
            return redirect(url_for("customer_account.index", customer=registry.id))
        total_evidence_bytes += len(data)
        if total_evidence_bytes > 24 * 1024 * 1024:
            flash("Gli allegati superano complessivamente 24 MB.", "warning")
            return redirect(url_for("customer_account.index", customer=registry.id))
        prepared_uploads.append((upload, data, extension, content_type))

    submitted_at = datetime.now(timezone.utc)
    payment_case = CustomerPaymentCase(
        registry_id=registry.id,
        created_by_user_id=current_user.id,
        case_type="payment_claim",
        status="under_review",
        currency="EUR",
        declared_amount=sum((Decimal(entry.signed_amount) for entry in entries), Decimal("0.00")),
        payment_reference=_trimmed_form_value("claim_reference", 255),
        note=reason,
        submitted_at=submitted_at,
    )
    db.session.add(payment_case)
    written_paths = []
    try:
        db.session.flush()
        case_folder = Path(current_app.instance_path) / "customer_payment_evidence" / payment_case.public_id
        if prepared_uploads:
            case_folder.mkdir(parents=True, exist_ok=True)
        for upload, data, extension, content_type in prepared_uploads:
            target_path = case_folder / f"{secrets.token_hex(16)}.{extension}"
            target_path.write_bytes(data)
            written_paths.append(target_path)
            original_filename = secure_filename(Path(upload.filename).name)[:255] or f"prova.{extension}"
            db.session.add(CustomerPaymentEvidence(
                case_id=payment_case.id,
                uploaded_by_user_id=current_user.id,
                original_filename=original_filename,
                storage_path=target_path.relative_to(Path(current_app.instance_path)).as_posix(),
                content_type=content_type,
                size_bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest(),
            ))
        existing_states = {
            state.source_item_key: state
            for state in CustomerAccountingItemState.query.filter(
                CustomerAccountingItemState.registry_id == registry.id,
                CustomerAccountingItemState.source_item_key.in_(tuple(source_keys)),
            ).all()
        }
        for entry, source_key in zip(entries, source_keys):
            db.session.add(CustomerPaymentAllocation(
                case_id=payment_case.id,
                source_customer_code=entry.source_customer_code,
                source_item_key=source_key,
                current_entry_id=entry.id,
                allocated_amount=entry.signed_amount,
                document_snapshot=account_entry_snapshot(entry),
            ))
            item_state = existing_states.get(source_key)
            if item_state is None:
                item_state = CustomerAccountingItemState(
                    registry_id=registry.id,
                    source_customer_code=entry.source_customer_code,
                    source_item_key=source_key,
                )
                db.session.add(item_state)
            item_state.status = "under_review"
            item_state.payment_case_id = payment_case.id
            item_state.last_seen_entry_id = entry.id
            item_state.message = "Partita contestata dal cliente"
        db.session.add(CustomerPaymentEvent(
            case_id=payment_case.id,
            actor_user_id=current_user.id,
            event_type="payment_claim_submitted",
            from_status=None,
            to_status="under_review",
            message="Contestazione partita aperta inviata",
            event_metadata={"document_count": len(entries), "evidence_count": len(prepared_uploads)},
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()
        for target_path in written_paths:
            try:
                target_path.unlink(missing_ok=True)
            except OSError:
                pass
        logger.exception("Errore registrazione contestazione cliente=%s", registry.id)
        flash("Non e' stato possibile registrare la contestazione. Riprova.", "danger")
        return redirect(url_for("customer_account.index", customer=registry.id))

    _queue_case_notification(payment_case.id, "created")
    flash(
        f"Contestazione inviata per {len(entries)} documenti. La pratica e' in fase di verifica.",
        "success",
    )
    return redirect(url_for("customer_account.index", customer=registry.id))


@customer_account_bp.post("/payments/checkout")
@login_required
def create_online_payment_checkout():
    _, is_developer = _role_context()
    registry_id = request.form.get("registry_id", type=int)
    registry = _authorized_registry(registry_id, is_developer)
    if registry is None:
        abort(403)
    if not _nexi_is_configured():
        flash("Il pagamento Nexi non e' ancora configurato.", "warning")
        return redirect(url_for("customer_account.index", customer=registry.id))

    try:
        entry_ids = list(dict.fromkeys(
            int(value) for value in request.form.getlist("entry_ids") if str(value).strip()
        ))
    except (TypeError, ValueError):
        entry_ids = []
    if not entry_ids or len(entry_ids) > 50:
        flash("Seleziona da uno a 50 documenti da pagare.", "warning")
        return redirect(url_for("customer_account.index", customer=registry.id))

    current_import = _latest_statement_import()
    if current_import is None:
        flash("La situazione contabile non e' disponibile.", "warning")
        return redirect(url_for("customer_account.index", customer=registry.id))
    entries = CustomerAccountEntry.query.filter(
        CustomerAccountEntry.import_id == current_import.id,
        CustomerAccountEntry.id.in_(entry_ids),
        _entry_ownership_filter(registry),
    ).all()
    entries_by_id = {entry.id: entry for entry in entries if is_selectable_settlement_item(entry)}
    if len(entries_by_id) != len(entry_ids):
        abort(400, description="Uno o piu' documenti non sono pagabili nell'ultimo aggiornamento.")
    entries = [entries_by_id[entry_id] for entry_id in entry_ids]
    source_keys = [account_entry_source_key(entry) for entry in entries]
    if len(set(source_keys)) != len(source_keys):
        abort(409, description="Due righe selezionate hanno la stessa identita' contabile.")
    if CustomerAccountingItemState.query.filter(
        CustomerAccountingItemState.registry_id == registry.id,
        CustomerAccountingItemState.source_item_key.in_(tuple(source_keys)),
        CustomerAccountingItemState.status.in_(tuple(ACTIVE_ITEM_STATUSES)),
    ).first():
        flash("Almeno un documento selezionato appartiene gia' a una pratica in corso.", "warning")
        return redirect(url_for("customer_account.index", customer=registry.id))

    declared_amount = sum((Decimal(entry.signed_amount) for entry in entries), Decimal("0.00"))
    if declared_amount <= 0:
        flash("Il totale netto da pagare deve essere maggiore di zero.", "warning")
        return redirect(url_for("customer_account.index", customer=registry.id))

    payment_case = CustomerPaymentCase(
        registry_id=registry.id,
        created_by_user_id=current_user.id,
        case_type="online_payment",
        status="creating_checkout",
        currency="EUR",
        declared_amount=declared_amount,
        provider="nexi_xpay",
    )
    db.session.add(payment_case)
    try:
        db.session.flush()
        payment_case.provider_order_id = f"LD{_base36(payment_case.id)}"
        locked_states = CustomerAccountingItemState.query.filter(
            CustomerAccountingItemState.registry_id == registry.id,
            CustomerAccountingItemState.source_item_key.in_(tuple(source_keys)),
        ).with_for_update().all()
        if any(state.status in ACTIVE_ITEM_STATUSES for state in locked_states):
            db.session.rollback()
            flash("Almeno un documento selezionato appartiene gia' a una pratica in corso.", "warning")
            return redirect(url_for("customer_account.index", customer=registry.id))
        existing_states = {
            state.source_item_key: state
            for state in locked_states
        }
        for entry, source_key in zip(entries, source_keys):
            db.session.add(CustomerPaymentAllocation(
                case_id=payment_case.id,
                source_customer_code=entry.source_customer_code,
                source_item_key=source_key,
                current_entry_id=entry.id,
                allocated_amount=entry.signed_amount,
                document_snapshot=account_entry_snapshot(entry),
            ))
            item_state = existing_states.get(source_key)
            if item_state is None:
                item_state = CustomerAccountingItemState(
                    registry_id=registry.id,
                    source_customer_code=entry.source_customer_code,
                    source_item_key=source_key,
                )
                db.session.add(item_state)
            item_state.status = "creating_checkout"
            item_state.payment_case_id = payment_case.id
            item_state.last_seen_entry_id = entry.id
            item_state.message = "Preparazione pagamento sicuro Nexi"
        db.session.add(CustomerPaymentEvent(
            case_id=payment_case.id,
            actor_user_id=current_user.id,
            event_type="online_payment_requested",
            from_status=None,
            to_status="creating_checkout",
            message="Richiesta checkout XPay Hosted Payment Page",
            event_metadata={"document_count": len(entries), "provider": "nexi_xpay"},
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("Errore preparazione checkout XPay cliente=%s", registry.id)
        flash("Non e' stato possibile preparare il pagamento. Riprova.", "danger")
        return redirect(url_for("customer_account.index", customer=registry.id))

    amount_minor = str(int((declared_amount * 100).quantize(Decimal("1"))))
    customer_info = {}
    if current_user.email:
        customer_info["cardHolderEmail"] = str(current_user.email)[:255]
    payload = {
        "order": {
            "orderId": payment_case.provider_order_id,
            "amount": amount_minor,
            "currency": "EUR",
            "customerId": str(registry.source_code or registry.id)[:27],
            "description": f"Pagamento {len(entries)} documenti LD Enoteca"[:255],
            "customField": payment_case.public_id[:255],
        },
        "paymentSession": {
            "actionType": "PAY",
            "amount": amount_minor,
            "captureType": "IMPLICIT",
            "language": "ita",
            "resultUrl": _public_url(
                "customer_account.xpay_checkout_result",
                public_id=payment_case.public_id,
                order_id=payment_case.provider_order_id,
            ),
            "cancelUrl": _public_url(
                "customer_account.xpay_checkout_cancelled_return",
                public_id=payment_case.public_id,
                order_id=payment_case.provider_order_id,
            ),
            "notificationUrl": _public_url("customer_account.nexi_notification"),
        },
    }
    if customer_info:
        payload["customerInfo"] = customer_info
    try:
        result = NexiXPayClient.from_app().create_hosted_payment(payload)
        payment_case.provider_security_token = result.security_token
        payment_case.payment_url = result.hosted_page
        payment_case.status = "checkout_ready"
        for state in CustomerAccountingItemState.query.filter_by(payment_case_id=payment_case.id).all():
            state.status = "checkout_ready"
            state.message = "Pagamento Nexi da completare"
        db.session.add(CustomerPaymentEvent(
            case_id=payment_case.id,
            actor_user_id=current_user.id,
            event_type="online_checkout_created",
            from_status="creating_checkout",
            to_status="checkout_ready",
            message="Checkout XPay Hosted Payment Page creato",
            event_metadata={"provider": "nexi_xpay"},
        ))
        db.session.commit()
    except NexiXPayUncertainError as exc:
        db.session.rollback()
        payment_case = CustomerPaymentCase.query.get(payment_case.id)
        if payment_case is not None:
            payment_case.status = "provider_uncertain"
            CustomerAccountingItemState.query.filter_by(payment_case_id=payment_case.id).update({
                CustomerAccountingItemState.status: "provider_uncertain",
                CustomerAccountingItemState.message: "Esito tecnico Nexi da verificare; non ripetere il pagamento",
            }, synchronize_session=False)
            db.session.add(CustomerPaymentEvent(
                case_id=payment_case.id,
                actor_user_id=current_user.id,
                event_type="online_checkout_uncertain",
                from_status="creating_checkout",
                to_status="provider_uncertain",
                message=str(exc)[:500],
            ))
            db.session.commit()
        logger.error("Esito checkout XPay incerto pratica=%s: %s", payment_case.id if payment_case else None, exc)
        flash(str(exc) + " La pratica e' stata bloccata per una verifica tecnica.", "danger")
        return redirect(url_for("customer_account.index", customer=registry.id))
    except NexiXPayError as exc:
        db.session.rollback()
        payment_case = CustomerPaymentCase.query.get(payment_case.id)
        if payment_case is not None:
            CustomerAccountingItemState.query.filter_by(payment_case_id=payment_case.id).update({
                CustomerAccountingItemState.status: "failed",
                CustomerAccountingItemState.message: "Preparazione pagamento Nexi non riuscita",
            }, synchronize_session=False)
            payment_case.status = "failed"
            payment_case.resolved_at = datetime.now(timezone.utc)
            db.session.add(CustomerPaymentEvent(
                case_id=payment_case.id,
                actor_user_id=current_user.id,
                event_type="online_checkout_failed",
                from_status="creating_checkout",
                to_status="failed",
                message=str(exc)[:500],
            ))
            db.session.commit()
        logger.warning("Creazione checkout XPay fallita pratica=%s: %s", payment_case.id if payment_case else None, exc)
        flash(str(exc), "danger")
        return redirect(url_for("customer_account.index", customer=registry.id))
    except Exception:
        db.session.rollback()
        logger.exception("Errore salvataggio risposta checkout XPay pratica=%s", payment_case.id)
        flash("Il collegamento con Nexi ha avuto un esito incerto. Non ripetere il pagamento e contatta l'assistenza.", "danger")
        return redirect(url_for("customer_account.index", customer=registry.id))

    return redirect(payment_case.payment_url, code=303)


def _validate_nexi_operation(payment_case, operation, *, expected_channel=True):
    if not isinstance(operation, dict):
        abort(400)
    if str(operation.get("orderId") or "").strip() != payment_case.provider_order_id:
        abort(400)
    try:
        expected_amount = int((Decimal(payment_case.declared_amount) * 100).quantize(Decimal("1")))
        notified_amount = int(str(operation.get("operationAmount")))
    except (TypeError, ValueError, ArithmeticError):
        abort(400)
    if notified_amount != expected_amount or str(operation.get("operationCurrency") or "").upper() != payment_case.currency:
        logger.warning("Operazione Nexi con importo/valuta incoerenti order=%s", payment_case.provider_order_id)
        abort(400)
    channel_detail = str(operation.get("channelDetail") or "").upper()
    if expected_channel and channel_detail not in {"HOSTED_PAYMENT_PAGE", "POST_PAYMENT_OPERATION"}:
        abort(400)


def _apply_nexi_operation(payment_case, operation, *, event_id=None, source="notification"):
    _validate_nexi_operation(payment_case, operation)
    result = str(operation.get("operationResult") or "").upper()
    operation_type = str(operation.get("operationType") or "").upper()
    operation_id = str(operation.get("operationId") or "").strip()[:160] or None
    old_status = payment_case.status
    payment_case.provider_last_event_id = event_id or payment_case.provider_last_event_id
    payment_case.provider_operation_id = operation_id or payment_case.provider_operation_id
    confirmed = result == "EXECUTED" and operation_type == "CAPTURE"
    authorized = result == "AUTHORIZED" and operation_type == "AUTHORIZATION"
    failed = result in {"DECLINED", "DENIED_BY_RISK", "THREEDS_FAILED", "FAILED"}
    cancelled = result == "CANCELED"

    if confirmed and payment_case.status != "accounted":
        payment_case.status = "awaiting_accounting"
        payment_case.provider_confirmed_at = datetime.now(timezone.utc)
        payment_case.submitted_at = payment_case.provider_confirmed_at
        payment_case.resolved_at = None
        state_message = "Pagamento Nexi confermato; in attesa di contabilizzazione"
    elif authorized and payment_case.status not in {"awaiting_accounting", "accounted"}:
        payment_case.status = "provider_authorized"
        state_message = "Pagamento Nexi autorizzato"
    elif (failed or cancelled) and payment_case.status not in {"awaiting_accounting", "accounted"}:
        payment_case.status = "cancelled" if cancelled else "failed"
        payment_case.resolved_at = datetime.now(timezone.utc)
        state_message = "Pagamento Nexi annullato" if cancelled else "Pagamento Nexi non riuscito"
    else:
        state_message = None

    if state_message:
        CustomerAccountingItemState.query.filter_by(payment_case_id=payment_case.id).update({
            CustomerAccountingItemState.status: payment_case.status,
            CustomerAccountingItemState.message: state_message,
        }, synchronize_session=False)
    db.session.add(CustomerPaymentEvent(
        case_id=payment_case.id,
        event_type=f"nexi_{source}",
        from_status=old_status,
        to_status=payment_case.status,
        message=f"Nexi: {operation_type or 'operazione'} {result or 'senza esito'}"[:500],
        event_metadata={
            "event_id": event_id,
            "operation_id": operation_id,
            "operation_type": operation_type,
            "operation_result": result,
            "payment_method": str(operation.get("paymentMethod") or "")[:40],
            "payment_circuit": str(operation.get("paymentCircuit") or "")[:80],
        },
    ))
    return confirmed, old_status


def _latest_relevant_nexi_operation(order_payload):
    order_status = order_payload.get("orderStatus") if isinstance(order_payload, dict) else None
    operations = order_status.get("operations") if isinstance(order_status, dict) else None
    operations = [item for item in (operations or []) if isinstance(item, dict)]
    if not operations:
        return None
    captures = [
        item for item in operations
        if str(item.get("operationType") or "").upper() == "CAPTURE"
        and str(item.get("operationResult") or "").upper() == "EXECUTED"
    ]
    candidates = captures or operations
    return max(candidates, key=lambda item: str(item.get("operationTime") or ""))


def _sync_nexi_order(payment_case, *, source="order_check"):
    payload = NexiXPayClient.from_app().get_order(payment_case.provider_order_id)
    order_status = payload.get("orderStatus") if isinstance(payload, dict) else None
    order = order_status.get("order") if isinstance(order_status, dict) else None
    if isinstance(order, dict):
        if str(order.get("orderId") or "").strip() != payment_case.provider_order_id:
            abort(400)
        expected_amount = int((Decimal(payment_case.declared_amount) * 100).quantize(Decimal("1")))
        try:
            order_amount = int(str(order.get("amount")))
        except (TypeError, ValueError):
            abort(400)
        if order_amount != expected_amount or str(order.get("currency") or "").upper() != payment_case.currency:
            abort(400)
    operation = _latest_relevant_nexi_operation(payload)
    if operation is None:
        return None, False, payment_case.status
    confirmed, old_status = _apply_nexi_operation(payment_case, operation, source=source)
    db.session.commit()
    return operation, confirmed, old_status


@customer_account_bp.get("/payments/xpay/result/<public_id>/<order_id>")
@login_required
def xpay_checkout_result(public_id, order_id):
    payment_case = CustomerPaymentCase.query.filter_by(public_id=public_id, case_type="online_payment").first_or_404()
    if not hmac.compare_digest(str(order_id), str(payment_case.provider_order_id or "")):
        abort(404)
    _, is_developer = _role_context()
    if _authorized_registry(payment_case.registry_id, is_developer) is None:
        abort(403)
    try:
        _sync_nexi_order(payment_case, source="return_check")
    except NexiXPayError as exc:
        logger.warning("Verifica rientro XPay non riuscita order=%s: %s", order_id, exc)
    if payment_case.status == "awaiting_accounting":
        flash("Pagamento confermato da Nexi. Le partite sono in attesa di contabilizzazione.", "success")
    elif payment_case.status in {"failed", "cancelled"}:
        flash("Il pagamento non e' stato completato. I documenti sono nuovamente selezionabili.", "warning")
    else:
        flash("Pagamento in verifica. Lo stato verra' aggiornato automaticamente.", "info")
    return redirect(url_for("customer_account.index", customer=payment_case.registry_id))


@customer_account_bp.get("/payments/xpay/cancelled/<public_id>/<order_id>")
@login_required
def xpay_checkout_cancelled_return(public_id, order_id):
    payment_case = CustomerPaymentCase.query.filter_by(public_id=public_id, case_type="online_payment").first_or_404()
    if not hmac.compare_digest(str(order_id), str(payment_case.provider_order_id or "")):
        abort(404)
    _, is_developer = _role_context()
    if _authorized_registry(payment_case.registry_id, is_developer) is None:
        abort(403)
    try:
        operation, _, _ = _sync_nexi_order(payment_case, source="cancel_return_check")
    except NexiXPayError as exc:
        operation = None
        logger.warning("Verifica annullamento XPay non riuscita order=%s: %s", order_id, exc)
    if payment_case.status == "awaiting_accounting":
        flash("Pagamento confermato da Nexi. Le partite sono in attesa di contabilizzazione.", "success")
    elif payment_case.status in {"failed", "cancelled"}:
        flash("Pagamento non completato. I documenti sono nuovamente selezionabili.", "info")
    elif operation is None:
        flash("Checkout interrotto. Lo stato verra' verificato automaticamente; puoi riprendere il pagamento dalla pratica.", "info")
    else:
        flash("Pagamento ancora in elaborazione. Attendi la conferma prima di riprovare.", "info")
    return redirect(url_for("customer_account.index", customer=payment_case.registry_id))


@customer_account_bp.post("/nexi/notification")
def nexi_notification():
    if request.content_length is not None and request.content_length > 128 * 1024:
        abort(413)
    payload = request.get_json(silent=True)
    operation = payload.get("operation") if isinstance(payload, dict) else None
    if not isinstance(operation, dict):
        abort(400)
    order_id = str(operation.get("orderId") or "").strip()
    payment_case = CustomerPaymentCase.query.filter_by(
        provider="nexi_xpay", provider_order_id=order_id, case_type="online_payment",
    ).first()
    if payment_case is None:
        abort(404)
    supplied_token = str(payload.get("securityToken") or "")
    expected_token = str(payment_case.provider_security_token or "")
    if not expected_token or not hmac.compare_digest(supplied_token, expected_token):
        logger.warning("Notifica Nexi con token non valido order=%s", order_id)
        abort(400)
    event_id = str(payload.get("eventId") or "").strip()[:80]
    if event_id and event_id == payment_case.provider_last_event_id:
        return ("", 200)
    confirmed, old_status = _apply_nexi_operation(payment_case, operation, event_id=event_id)
    db.session.commit()
    if confirmed and old_status != "awaiting_accounting":
        _queue_case_notification(payment_case.id, "created")
    return ("", 200)


@customer_account_bp.get("/payment-evidence/<int:evidence_id>")
@login_required
def download_payment_evidence(evidence_id):
    evidence = CustomerPaymentEvidence.query.get_or_404(evidence_id)
    if current_user.max_role_weight < 40:
        _, is_developer = _role_context()
        if _authorized_registry(evidence.payment_case.registry_id, is_developer) is None:
            abort(403)
    instance_root = Path(current_app.instance_path).resolve()
    target = (instance_root / evidence.storage_path).resolve()
    if instance_root not in target.parents or not target.is_file():
        abort(404)
    return send_file(
        target,
        mimetype=evidence.content_type or "application/octet-stream",
        as_attachment=True,
        download_name=evidence.original_filename,
        conditional=True,
        max_age=0,
    )


def _customer_owned_editable_case(case_id):
    _, is_developer = _role_context()
    payment_case = (
        CustomerPaymentCase.query
        .options(
            selectinload(CustomerPaymentCase.registry),
            selectinload(CustomerPaymentCase.allocations),
            selectinload(CustomerPaymentCase.evidence),
        )
        .filter(CustomerPaymentCase.id == case_id)
        .first_or_404()
    )
    if _authorized_registry(payment_case.registry_id, is_developer) is None:
        abort(403)
    if not is_developer and payment_case.created_by_user_id != current_user.id:
        abort(403)
    if payment_case.status not in CUSTOMER_EDITABLE_CASE_STATUSES:
        abort(409, description="La pratica e' gia' in lavorazione e non puo' piu' essere modificata.")
    return payment_case


def _queue_case_notification(case_id, notification_kind):
    try:
        from config.tasks import notify_customer_payment_case_task

        notify_customer_payment_case_task.delay(case_id, notification_kind)
    except Exception:
        logger.exception("Impossibile accodare la notifica %s per la pratica %s", notification_kind, case_id)


@customer_account_bp.route("/payments/<int:case_id>/edit", methods=["GET", "POST"])
@login_required
def edit_payment_case(case_id):
    payment_case = _customer_owned_editable_case(case_id)
    current_import = _latest_statement_import()
    if current_import is None:
        abort(409, description="La situazione contabile non e' disponibile.")

    all_entries = (
        CustomerAccountEntry.query
        .filter(
            CustomerAccountEntry.import_id == current_import.id,
            _entry_ownership_filter(payment_case.registry),
        )
        .order_by(CustomerAccountEntry.document_date.desc().nullslast(), CustomerAccountEntry.row_number.desc())
        .all()
    )
    selectable_entries = [entry for entry in all_entries if is_selectable_settlement_item(entry)]
    entry_keys = {entry.id: account_entry_source_key(entry) for entry in selectable_entries}
    selected_keys = {allocation.source_item_key for allocation in payment_case.allocations}
    states = CustomerAccountingItemState.query.filter(
        CustomerAccountingItemState.registry_id == payment_case.registry_id,
        CustomerAccountingItemState.source_item_key.in_(tuple(entry_keys.values()) or ("",)),
    ).all()
    states_by_key = {state.source_item_key: state for state in states}
    available_entries = [
        entry for entry in selectable_entries
        if entry_keys[entry.id] in selected_keys
        or entry_keys[entry.id] not in states_by_key
        or states_by_key[entry_keys[entry.id]].payment_case_id == payment_case.id
        or states_by_key[entry_keys[entry.id]].status not in ACTIVE_ITEM_STATUSES
    ]

    if request.method == "POST":
        try:
            entry_ids = list(dict.fromkeys(
                int(value) for value in request.form.getlist("entry_ids") if str(value).strip()
            ))
        except (TypeError, ValueError):
            entry_ids = []
        available_by_id = {entry.id: entry for entry in available_entries}
        if not entry_ids or len(entry_ids) > 50 or any(entry_id not in available_by_id for entry_id in entry_ids):
            flash("Seleziona da uno a 50 documenti disponibili.", "warning")
            return redirect(url_for("customer_account.edit_payment_case", case_id=payment_case.id))
        selected_entries = [available_by_id[entry_id] for entry_id in entry_ids]
        new_keys = [entry_keys[entry.id] for entry in selected_entries]
        if len(set(new_keys)) != len(new_keys):
            abort(409, description="Due righe selezionate hanno la stessa identita' contabile.")
        declared_amount = sum((Decimal(entry.signed_amount) for entry in selected_entries), Decimal("0.00"))
        if payment_case.case_type != "payment_claim" and declared_amount <= 0:
            flash("Il totale netto dei documenti deve essere maggiore di zero.", "warning")
            return redirect(url_for("customer_account.edit_payment_case", case_id=payment_case.id))

        replacement_data = None
        replacement_extension = None
        replacement_content_type = None
        replacement_upload = request.files.get("payment_evidence")
        if replacement_upload is not None and replacement_upload.filename:
            replacement_data = replacement_upload.read(MAX_EVIDENCE_BYTES + 1)
            if not replacement_data or len(replacement_data) > MAX_EVIDENCE_BYTES:
                flash("Il nuovo allegato e' vuoto oppure supera 12 MB.", "warning")
                return redirect(url_for("customer_account.edit_payment_case", case_id=payment_case.id))
            replacement_extension, replacement_content_type = _detect_evidence_type(replacement_data)
            if not replacement_extension:
                flash("Formato allegato non supportato.", "warning")
                return redirect(url_for("customer_account.edit_payment_case", case_id=payment_case.id))

        target_path = None
        old_evidence_paths = []
        old_keys = sorted(selected_keys)
        try:
            active_other_case = CustomerAccountingItemState.query.filter(
                CustomerAccountingItemState.registry_id == payment_case.registry_id,
                CustomerAccountingItemState.source_item_key.in_(tuple(new_keys)),
                CustomerAccountingItemState.status.in_(tuple(ACTIVE_ITEM_STATUSES)),
                CustomerAccountingItemState.payment_case_id != payment_case.id,
            ).first()
            if active_other_case:
                abort(409, description="Uno dei documenti appartiene gia' a un'altra pratica attiva.")

            CustomerPaymentAllocation.query.filter_by(case_id=payment_case.id).delete(synchronize_session=False)
            db.session.flush()
            owned_states = CustomerAccountingItemState.query.filter_by(payment_case_id=payment_case.id).all()
            new_key_set = set(new_keys)
            for state in owned_states:
                if state.source_item_key not in new_key_set:
                    db.session.delete(state)
            current_states = {
                state.source_item_key: state
                for state in CustomerAccountingItemState.query.filter(
                    CustomerAccountingItemState.registry_id == payment_case.registry_id,
                    CustomerAccountingItemState.source_item_key.in_(tuple(new_keys)),
                ).all()
            }
            target_status = "under_review" if payment_case.case_type == "payment_claim" else "awaiting_accounting"
            for entry, source_key in zip(selected_entries, new_keys):
                db.session.add(CustomerPaymentAllocation(
                    case_id=payment_case.id,
                    source_customer_code=entry.source_customer_code,
                    source_item_key=source_key,
                    current_entry_id=entry.id,
                    allocated_amount=entry.signed_amount,
                    document_snapshot=account_entry_snapshot(entry),
                ))
                item_state = current_states.get(source_key)
                if item_state is None:
                    item_state = CustomerAccountingItemState(
                        registry_id=payment_case.registry_id,
                        source_customer_code=entry.source_customer_code,
                        source_item_key=source_key,
                    )
                    db.session.add(item_state)
                item_state.status = target_status
                item_state.payment_case_id = payment_case.id
                item_state.last_seen_entry_id = entry.id
                item_state.message = "Pratica modificata dal cliente"

            payment_case.declared_amount = declared_amount
            payment_case.payment_reference = _trimmed_form_value("payment_reference", 255)
            payment_case.note = (request.form.get("note") or "").strip()[:4000] or None
            if replacement_data is not None:
                evidence_root = Path(current_app.instance_path) / "customer_payment_evidence"
                case_folder = evidence_root / payment_case.public_id
                case_folder.mkdir(parents=True, exist_ok=True)
                stored_name = f"{secrets.token_hex(16)}.{replacement_extension}"
                target_path = case_folder / stored_name
                target_path.write_bytes(replacement_data)
                for evidence in list(payment_case.evidence):
                    old_evidence_paths.append(evidence.storage_path)
                    db.session.delete(evidence)
                original_filename = secure_filename(Path(replacement_upload.filename).name)[:255] or f"allegato.{replacement_extension}"
                db.session.add(CustomerPaymentEvidence(
                    case_id=payment_case.id,
                    uploaded_by_user_id=current_user.id,
                    original_filename=original_filename,
                    storage_path=target_path.relative_to(Path(current_app.instance_path)).as_posix(),
                    content_type=replacement_content_type,
                    size_bytes=len(replacement_data),
                    sha256=hashlib.sha256(replacement_data).hexdigest(),
                ))
            db.session.add(CustomerPaymentEvent(
                case_id=payment_case.id,
                actor_user_id=current_user.id,
                event_type="customer_case_edited",
                from_status=payment_case.status,
                to_status=payment_case.status,
                message="Pratica corretta dal cliente",
                event_metadata={
                    "old_document_count": len(old_keys), "new_document_count": len(new_keys),
                    "evidence_replaced": replacement_data is not None,
                },
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()
            if target_path is not None:
                try:
                    target_path.unlink(missing_ok=True)
                except OSError:
                    pass
            raise

        instance_root = Path(current_app.instance_path).resolve()
        for relative_path in old_evidence_paths:
            old_path = (instance_root / relative_path).resolve()
            if instance_root in old_path.parents:
                try:
                    old_path.unlink(missing_ok=True)
                except OSError:
                    logger.exception("Impossibile eliminare il vecchio allegato %s", old_path)
        _queue_case_notification(payment_case.id, "updated")
        flash("Comunicazione aggiornata e ufficio avvisato.", "success")
        return redirect(url_for("customer_account.index", customer=payment_case.registry_id))

    return render_template(
        "customer_account/edit_case.html",
        payment_case=payment_case,
        entries=available_entries,
        selected_keys=selected_keys,
        entry_keys=entry_keys,
        case_type_labels=CASE_TYPE_LABELS,
    )


@customer_account_bp.post("/payments/<int:case_id>/delete")
@login_required
def delete_payment_case(case_id):
    payment_case = _customer_owned_editable_case(case_id)
    registry_id = payment_case.registry_id
    CustomerAccountingItemState.query.filter_by(payment_case_id=payment_case.id).delete(synchronize_session=False)
    old_status = payment_case.status
    payment_case.status = "cancelled"
    payment_case.resolved_at = datetime.now(timezone.utc)
    db.session.add(CustomerPaymentEvent(
        case_id=payment_case.id,
        actor_user_id=current_user.id,
        event_type="customer_case_cancelled",
        from_status=old_status,
        to_status="cancelled",
        message="Pratica eliminata dal cliente prima della lavorazione",
    ))
    db.session.commit()
    _queue_case_notification(payment_case.id, "cancelled")
    flash("Comunicazione eliminata. I documenti sono nuovamente selezionabili.", "success")
    return redirect(url_for("customer_account.index", customer=registry_id))


def _office_case_query(case_types):
    return (
        CustomerPaymentCase.query
        .options(
            selectinload(CustomerPaymentCase.registry),
            selectinload(CustomerPaymentCase.created_by),
            selectinload(CustomerPaymentCase.allocations),
            selectinload(CustomerPaymentCase.evidence),
        )
        .filter(CustomerPaymentCase.case_type.in_(case_types))
    )


def _render_office_cases(queue_code, case_types, title, description):
    query = _office_case_query(case_types)
    selected_status = (request.args.get("status") or "active").strip()
    if selected_status == "active":
        query = query.filter(CustomerPaymentCase.status.notin_(tuple(TERMINAL_CASE_STATUSES)))
    elif selected_status in OFFICE_CASE_STATUSES:
        query = query.filter(CustomerPaymentCase.status == selected_status)
    elif selected_status != "all":
        selected_status = "active"
        query = query.filter(CustomerPaymentCase.status.notin_(tuple(TERMINAL_CASE_STATUSES)))

    search = (request.args.get("q") or "").strip()[:120]
    if search:
        pattern = f"%{search}%"
        query = query.filter(or_(
            CustomerPaymentCase.public_id.ilike(pattern),
            CustomerPaymentCase.payment_reference.ilike(pattern),
            CustomerPaymentCase.registry.has(or_(
                BusinessRegistry.display_name.ilike(pattern),
                BusinessRegistry.legal_name.ilike(pattern),
                BusinessRegistry.source_code.ilike(pattern),
            )),
            CustomerPaymentCase.created_by.has(or_(
                User.email.ilike(pattern),
                User.name.ilike(pattern),
                User.surname.ilike(pattern),
            )),
        ))

    cases = query.order_by(CustomerPaymentCase.created_at.desc()).paginate(
        page=max(1, request.args.get("page", type=int) or 1), per_page=40, error_out=False,
    )
    return render_template(
        "customer_account/office_cases.html",
        queue_code=queue_code,
        title=title,
        description=description,
        cases=cases,
        search=search,
        selected_status=selected_status,
        status_labels=CASE_STATUS_LABELS,
        terminal_statuses=TERMINAL_CASE_STATUSES,
    )


@customer_account_bp.get("/office/payment-communications")
@login_required
@role_required(40)
def office_payment_communications():
    return _render_office_cases(
        "payments", ("bank_transfer", "online_payment"), "Comunicazioni di pagamento",
        "Bonifici comunicati dai clienti e pagamenti in attesa di riscontro contabile.",
    )


@customer_account_bp.get("/office/payment-disputes")
@login_required
@role_required(40)
def office_payment_disputes():
    return _render_office_cases(
        "disputes", ("payment_claim",), "Contestazioni partite aperte",
        "Documenti che il cliente dichiara gia' pagati e che richiedono una verifica.",
    )


@customer_account_bp.route("/office/cases/<int:case_id>", methods=["GET", "POST"])
@login_required
@role_required(40)
def office_case_detail(case_id):
    payment_case = (
        _office_case_query(("bank_transfer", "online_payment", "payment_claim"))
        .options(selectinload(CustomerPaymentCase.events).selectinload(CustomerPaymentEvent.actor))
        .filter(CustomerPaymentCase.id == case_id)
        .first_or_404()
    )
    if request.method == "POST":
        new_status = (request.form.get("status") or "").strip()
        message = (request.form.get("message") or "").strip()[:4000] or None
        if new_status not in OFFICE_CASE_STATUSES:
            abort(400, description="Stato pratica non valido.")
        if new_status == "rejected" and not message:
            flash("Indica al cliente il motivo del rigetto.", "warning")
            return redirect(url_for("customer_account.office_case_detail", case_id=payment_case.id))

        old_status = payment_case.status
        payment_case.status = new_status
        payment_case.resolved_at = datetime.now(timezone.utc) if new_status in TERMINAL_CASE_STATUSES else None
        payment_case.rejection_message = message if new_status == "rejected" else None
        CustomerAccountingItemState.query.filter_by(payment_case_id=payment_case.id).update({
            CustomerAccountingItemState.status: new_status,
            CustomerAccountingItemState.message: message or CASE_STATUS_LABELS.get(new_status, new_status),
        }, synchronize_session=False)
        db.session.add(CustomerPaymentEvent(
            case_id=payment_case.id,
            actor_user_id=current_user.id,
            event_type="office_status_changed",
            from_status=old_status,
            to_status=new_status,
            message=message,
        ))
        db.session.commit()
        flash("Stato della pratica aggiornato.", "success")
        return redirect(url_for("customer_account.office_case_detail", case_id=payment_case.id))

    queue_endpoint = (
        "customer_account.office_payment_disputes"
        if payment_case.case_type == "payment_claim"
        else "customer_account.office_payment_communications"
    )
    return render_template(
        "customer_account/office_case_detail.html",
        payment_case=payment_case,
        queue_endpoint=queue_endpoint,
        status_labels=CASE_STATUS_LABELS,
        case_type_labels=CASE_TYPE_LABELS,
        office_statuses=OFFICE_CASE_STATUSES,
    )
