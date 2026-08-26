import hashlib
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


customer_account_bp = Blueprint("customer_account", __name__)
ALLOWED_ROLE_NAMES = {"customer_horeca", "dev"}
CASE_STATUS_LABELS = {
    "awaiting_accounting": "In attesa di contabilizzazione",
    "under_review": "In fase di verifica",
    "partially_accounted": "Parzialmente contabilizzato",
    "accounted": "Contabilizzato",
    "rejected": "Rigettato",
    "cancelled": "Annullato",
    "failed": "Errore",
}
MAX_EVIDENCE_BYTES = 12 * 1024 * 1024
logger = get_logger("customer_account")


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
    open_cases = []
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
        open_cases = (
            CustomerPaymentCase.query
            .options(
                selectinload(CustomerPaymentCase.allocations),
                selectinload(CustomerPaymentCase.evidence),
            )
            .filter(
                CustomerPaymentCase.registry_id == registry.id,
                CustomerPaymentCase.status.notin_(("accounted", "rejected", "expired", "cancelled", "failed")),
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
        open_cases=open_cases,
        is_developer=is_developer,
        payable_entry_ids=payable_entry_ids,
        entry_states=entry_states,
        payment_instructions=payment_instructions,
        formatted_iban=format_iban(payment_instructions.iban) if payment_instructions else None,
        case_status_labels=CASE_STATUS_LABELS,
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

    flash(
        f"Contabile inviata: {len(entries)} documenti per {declared_amount:.2f} EUR. "
        "La pratica e' in attesa di contabilizzazione.",
        "success",
    )
    return redirect(url_for("customer_account.index", customer=registry.id))


@customer_account_bp.get("/payment-evidence/<int:evidence_id>")
@login_required
def download_payment_evidence(evidence_id):
    _, is_developer = _role_context()
    evidence = CustomerPaymentEvidence.query.get_or_404(evidence_id)
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
