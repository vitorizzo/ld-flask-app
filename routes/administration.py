from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from email.utils import parseaddr
from html import escape
import hmac
import os

from flask import Blueprint, abort, current_app, jsonify, render_template, request, url_for
from flask_mail import Message
from flask_login import current_user, login_required
from sqlalchemy import case, func

from extensions import db
from models import (
    AdministrationPaymentLink,
    AdministrationPaymentLinkDelivery,
    BusinessRegistry,
    BusinessRegistryContact,
    CustomerAccountEntry,
    CustomerAccountStatementImport,
    User,
)
from tools.log_utils import get_logger, log_task
from tools.mail_accounts import account_sender, get_email_account, send_account_mail
from tools.nexi_xpay import NexiXPayClient, NexiXPayError, NexiXPayUncertainError
from tools.role_required import role_required


administration_bp = Blueprint("administration", __name__)
logger = get_logger("administration")

UNKNOWN_AREA = "Provincia non definita"
UNKNOWN_ZONE = "Comune non definito"
MONTH_LABELS = (
    "Gen", "Feb", "Mar", "Apr", "Mag", "Giu",
    "Lug", "Ago", "Set", "Ott", "Nov", "Dic",
)


def _base36(value):
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    value = int(value)
    result = "0"
    if value > 0:
        chars = []
        while value:
            value, remainder = divmod(value, 36)
            chars.append(alphabet[remainder])
        result = "".join(reversed(chars))
    return result


def _public_url(endpoint=None, **values):
    if endpoint:
        path = url_for(endpoint, _external=False, **values)
    else:
        path = "/"
    base_url = current_app.config.get("PUBLIC_BASE_URL") or os.getenv("PUBLIC_BASE_URL") or "https://ldapp.ldenoteca.it"
    return f"{str(base_url).rstrip('/')}{path}"


def _parse_positive_amount(raw_value):
    normalized = str(raw_value or "").strip().replace(" ", "")
    if "," in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")
    try:
        amount = Decimal(normalized).quantize(Decimal("0.01"))
    except (ArithmeticError, ValueError):
        return None
    return amount if Decimal("0.01") <= amount <= Decimal("999999999999.99") else None


def _valid_email(value):
    value = str(value or "").strip()
    parsed = parseaddr(value)[1]
    return parsed if parsed and parsed == value and "@" in parsed and len(parsed) <= 255 else None


def _latest_statement_import():
    return CustomerAccountStatementImport.query.order_by(
        CustomerAccountStatementImport.imported_at.desc(),
        CustomerAccountStatementImport.id.desc(),
    ).first()


def _customer_credit_rows(import_id):
    balance = func.sum(CustomerAccountEntry.signed_amount)
    return (
        db.session.query(
            CustomerAccountEntry.source_customer_code.label("source_customer_code"),
            func.max(CustomerAccountEntry.customer_name).label("customer_name"),
            func.max(CustomerAccountEntry.registry_id).label("registry_id"),
            func.max(BusinessRegistry.province).label("province"),
            func.max(BusinessRegistry.city).label("city"),
            func.count(CustomerAccountEntry.id).label("movement_count"),
            balance.label("balance"),
        )
        .outerjoin(BusinessRegistry, BusinessRegistry.id == CustomerAccountEntry.registry_id)
        .filter(
            CustomerAccountEntry.import_id == import_id,
            CustomerAccountEntry.is_balance_relevant.is_(True),
        )
        .group_by(CustomerAccountEntry.source_customer_code)
        .having(balance > 0)
        .all()
    )


def _history_area_options(import_id):
    rows = (
        db.session.query(BusinessRegistry.province)
        .join(CustomerAccountEntry, CustomerAccountEntry.registry_id == BusinessRegistry.id)
        .filter(
            CustomerAccountEntry.import_id == import_id,
            CustomerAccountEntry.is_balance_relevant.is_(True),
        )
        .distinct()
        .all()
    )
    return sorted(
        {province or UNKNOWN_AREA for (province,) in rows},
        key=str.casefold,
    )


def _monthly_credit_history(selected_area=None, month_limit=24):
    imports = CustomerAccountStatementImport.query.order_by(
        CustomerAccountStatementImport.imported_at.asc(),
        CustomerAccountStatementImport.id.asc(),
    ).all()
    latest_by_month = {}
    for statement_import in imports:
        key = (statement_import.imported_at.year, statement_import.imported_at.month)
        latest_by_month[key] = statement_import
    selected_imports = list(latest_by_month.values())[-month_limit:]
    if not selected_imports:
        return []

    import_ids = [item.id for item in selected_imports]
    customer_balance = func.sum(CustomerAccountEntry.signed_amount)
    customer_rows = (
        db.session.query(
            CustomerAccountEntry.import_id.label("import_id"),
            CustomerAccountEntry.source_customer_code.label("source_customer_code"),
            func.max(BusinessRegistry.province).label("province"),
            func.max(BusinessRegistry.city).label("city"),
            customer_balance.label("balance"),
        )
        .outerjoin(BusinessRegistry, BusinessRegistry.id == CustomerAccountEntry.registry_id)
        .filter(CustomerAccountEntry.import_id.in_(import_ids))
        .filter(CustomerAccountEntry.is_balance_relevant.is_(True))
        .group_by(CustomerAccountEntry.import_id, CustomerAccountEntry.source_customer_code)
        .having(customer_balance > 0)
        .all()
    )

    totals = defaultdict(lambda: Decimal("0"))
    for row in customer_rows:
        if selected_area:
            area_label = row.province or UNKNOWN_AREA
            if area_label != selected_area:
                continue
        totals[row.import_id] += row.balance

    return [
        {
            "label": f"{MONTH_LABELS[item.imported_at.month - 1]} {item.imported_at.year}",
            "value": totals[item.id],
            "imported_at": item.imported_at,
        }
        for item in selected_imports
    ]


def _monthly_customer_credit_history(source_customer_code, month_limit=24):
    imports = CustomerAccountStatementImport.query.order_by(
        CustomerAccountStatementImport.imported_at.asc(),
        CustomerAccountStatementImport.id.asc(),
    ).all()
    latest_by_month = {}
    for statement_import in imports:
        latest_by_month[(statement_import.imported_at.year, statement_import.imported_at.month)] = statement_import
    selected_imports = list(latest_by_month.values())[-month_limit:]
    if not selected_imports:
        return []

    totals = dict(
        db.session.query(
            CustomerAccountEntry.import_id,
            func.sum(CustomerAccountEntry.signed_amount),
        )
        .filter(
            CustomerAccountEntry.import_id.in_([item.id for item in selected_imports]),
            CustomerAccountEntry.source_customer_code == source_customer_code,
            CustomerAccountEntry.is_balance_relevant.is_(True),
        )
        .group_by(CustomerAccountEntry.import_id)
        .all()
    )
    return [
        {
            "label": f"{MONTH_LABELS[item.imported_at.month - 1]} {item.imported_at.year}",
            "value": max(totals.get(item.id, Decimal("0")), Decimal("0")),
        }
        for item in selected_imports
    ]


def _customer_aging(entries, today=None):
    today = today or date.today()
    buckets = [
        {"label": "0–30 gg", "value": Decimal("0")},
        {"label": "31–60 gg", "value": Decimal("0")},
        {"label": "61–90 gg", "value": Decimal("0")},
        {"label": "91–120 gg", "value": Decimal("0")},
        {"label": "Oltre 120 gg", "value": Decimal("0")},
    ]
    weighted_days = Decimal("0")
    net_total = Decimal("0")
    for entry in entries:
        if not entry.is_balance_relevant:
            continue
        reference_date = entry.document_date or entry.registration_date or entry.due_date or today
        age_days = max(0, (today - reference_date).days)
        bucket_index = 0 if age_days <= 30 else 1 if age_days <= 60 else 2 if age_days <= 90 else 3 if age_days <= 120 else 4
        signed_amount = entry.amount if entry.accounting_side == "D" else -entry.amount
        buckets[bucket_index]["value"] += signed_amount
        net_total += signed_amount
        weighted_days += signed_amount * age_days

    average_days = max(0, int((weighted_days / net_total).quantize(Decimal("1")))) if net_total > 0 else 0
    return {
        "average_days": average_days,
        "outstanding_total": net_total,
        "buckets": buckets,
    }


def _credit_communication_contacts(customer):
    registry = customer.registry
    if not registry:
        return {"email": [], "pec": []}
    contacts = {"email": [], "pec": []}
    for contact in sorted(registry.contacts, key=lambda item: (not item.is_primary, item.id)):
        if contact.contact_type in contacts:
            contacts[contact.contact_type].append({
                "id": contact.id,
                "value": contact.value,
                "label": contact.label or ("Principale" if contact.is_primary else "Altro recapito"),
                "is_primary": bool(contact.is_primary),
            })
    return contacts


def _credit_account_available(code):
    account = get_email_account(code, include_password=False, legacy_fallback=False)
    return bool(account and account.get("is_enabled"))


def _credit_money(value):
    return f"{Decimal(value or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _credit_message_html(kind, customer, entries, totals):
    balance = Decimal(totals.balance or 0)
    rows = []
    for entry in entries:
        reference_date = entry.document_date or entry.registration_date or entry.due_date
        rows.append(
            "<tr>"
            f"<td>{escape(reference_date.strftime('%d/%m/%Y') if reference_date else '—')}</td>"
            f"<td>{escape(entry.document_number or '—')}</td>"
            f"<td>{escape(entry.description or '—')}</td>"
            f"<td style='text-align:right'>{escape(_credit_money(entry.signed_amount))} €</td>"
            "</tr>"
        )
    table = (
        "<table style='width:100%;border-collapse:collapse' border='1' cellpadding='7'>"
        "<thead><tr><th>Data</th><th>Documento</th><th>Descrizione</th><th>Importo</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )
    heading = "Estratto conto aggiornato" if kind == "statement" else "Sollecito di pagamento"
    intro = (
        "trasmettiamo di seguito la situazione contabile aggiornata risultante dai nostri archivi."
        if kind == "statement"
        else "dai nostri archivi risulta un saldo ancora dovuto. Vi chiediamo cortesemente di provvedere al saldo delle partite aperte o di segnalarci eventuali difformità."
    )
    return (
        f"<h2>{heading}</h2>"
        f"<p>Spett.le {escape(customer.customer_name)},</p>"
        f"<p>{intro}</p>"
        f"<p><strong>Saldo attuale: {_credit_money(balance)} €</strong></p>"
        f"{table}"
        "<p>Per chiarimenti potete rispondere direttamente a questa comunicazione.</p>"
        "<p>Cordiali saluti<br>LD Enoteca</p>"
    )


@administration_bp.route("/customer-credit", methods=["GET"])
@login_required
@role_required(40, roles=["office"])
@log_task(logger)
def customer_credit():
    current_import = _latest_statement_import()
    if current_import is None:
        return render_template(
            "administration/customer_credit.html",
            current_import=None,
            chart_items=[],
            level="areas",
            area=None,
            zone=None,
            total_exposure=Decimal("0"),
            customer_count=0,
            back_url=None,
            breadcrumbs=[{"label": "Credito", "url": None}],
        )

    area = (request.args.get("area") or "").strip() or None
    zone = (request.args.get("zone") or "").strip() or None
    if zone and not area:
        abort(404)

    rows = _customer_credit_rows(current_import.id)
    history_area_options = _history_area_options(current_import.id)
    selected_history_area_value = (request.args.get("history_area") or "").strip()
    selected_history_area = (
        selected_history_area_value
        if selected_history_area_value in history_area_options
        else None
    )
    history_points = _monthly_credit_history(selected_history_area)
    history_payload = [
        {"label": item["label"], "value": float(item["value"])}
        for item in history_points
    ]
    total_exposure = sum((row.balance for row in rows), Decimal("0"))
    chart_items = []
    breadcrumbs = [{"label": "Credito", "url": url_for("administration.customer_credit")}]
    back_url = None

    if area is None:
        level = "areas"
        grouped = defaultdict(lambda: {"value": Decimal("0"), "customers": set()})
        for row in rows:
            label = row.province or UNKNOWN_AREA
            grouped[label]["value"] += row.balance
            grouped[label]["customers"].add(row.source_customer_code)
        for label, values in grouped.items():
            chart_items.append({
                "label": label,
                "value": values["value"],
                "customer_count": len(values["customers"]),
                "url": url_for("administration.customer_credit", area=label),
            })
        breadcrumbs.append({"label": "Aree", "url": None})
    elif zone is None:
        level = "zones"
        selected_rows = [row for row in rows if (row.province or UNKNOWN_AREA) == area]
        if not selected_rows:
            abort(404)
        grouped = defaultdict(lambda: {"value": Decimal("0"), "customers": set()})
        for row in selected_rows:
            label = row.city or UNKNOWN_ZONE
            grouped[label]["value"] += row.balance
            grouped[label]["customers"].add(row.source_customer_code)
        for label, values in grouped.items():
            chart_items.append({
                "label": label,
                "value": values["value"],
                "customer_count": len(values["customers"]),
                "url": url_for("administration.customer_credit", area=area, zone=label),
            })
        total_exposure = sum((row.balance for row in selected_rows), Decimal("0"))
        back_url = url_for("administration.customer_credit")
        breadcrumbs.extend([
            {"label": "Aree", "url": back_url},
            {"label": area, "url": None},
        ])
    else:
        level = "customers"
        selected_rows = [
            row for row in rows
            if (row.province or UNKNOWN_AREA) == area and (row.city or UNKNOWN_ZONE) == zone
        ]
        if not selected_rows:
            abort(404)
        for row in selected_rows:
            chart_items.append({
                "label": row.customer_name,
                "subtitle": f"Cod. {row.source_customer_code}",
                "value": row.balance,
                "customer_count": 1,
                "movement_count": row.movement_count,
                "url": url_for(
                    "administration.customer_credit_detail",
                    source_customer_code=row.source_customer_code,
                    area=area,
                    zone=zone,
                ),
            })
        total_exposure = sum((row.balance for row in selected_rows), Decimal("0"))
        back_url = url_for("administration.customer_credit", area=area)
        breadcrumbs.extend([
            {"label": "Aree", "url": url_for("administration.customer_credit")},
            {"label": area, "url": back_url},
            {"label": zone, "url": None},
            {"label": "Clienti", "url": None},
        ])

    chart_items.sort(key=lambda item: item["value"], reverse=True)
    chart_payload = [
        {
            "label": item["label"],
            "value": float(item["value"]),
            "url": item["url"],
        }
        for item in chart_items
    ]
    logger.info(
        "Dashboard credito visualizzata: import_id=%s livello=%s area=%s zona=%s voci=%s",
        current_import.id, level, area, zone, len(chart_items),
    )
    return render_template(
        "administration/customer_credit.html",
        current_import=current_import,
        chart_items=chart_items,
        chart_payload=chart_payload,
        history_points=history_points,
        history_payload=history_payload,
        history_area_options=history_area_options,
        selected_history_area_value=selected_history_area or "",
        selected_history_area=selected_history_area,
        level=level,
        area=area,
        zone=zone,
        total_exposure=total_exposure,
        customer_count=sum(item["customer_count"] for item in chart_items),
        back_url=back_url,
        breadcrumbs=breadcrumbs,
    )


@administration_bp.route("/customer-credit/customers", methods=["GET"])
@login_required
@role_required(40, roles=["office"])
@log_task(logger)
def customer_credit_customers():
    current_import = _latest_statement_import()
    if current_import is None:
        return render_template(
            "administration/customer_credit_customers.html",
            current_import=None,
            customers=[],
            search="",
            total_exposure=Decimal("0"),
        )

    search = (request.args.get("q") or "").strip()
    customers = _customer_credit_rows(current_import.id)
    if search:
        folded = search.casefold()
        customers = [
            item for item in customers
            if folded in (item.customer_name or "").casefold()
            or folded in (item.source_customer_code or "").casefold()
        ]
    customers.sort(key=lambda item: item.balance, reverse=True)
    total_exposure = sum((item.balance for item in customers), Decimal("0"))
    logger.info(
        "Dashboard situazione clienti visualizzata: import_id=%s clienti=%s ricerca=%s",
        current_import.id, len(customers), bool(search),
    )
    return render_template(
        "administration/customer_credit_customers.html",
        current_import=current_import,
        customers=customers,
        search=search,
        total_exposure=total_exposure,
    )


@administration_bp.route("/customer-credit/<source_customer_code>", methods=["GET"])
@login_required
@role_required(40, roles=["office"])
@log_task(logger)
def customer_credit_detail(source_customer_code):
    current_import = _latest_statement_import()
    if current_import is None:
        abort(404)
    base_query = CustomerAccountEntry.query.filter_by(
        import_id=current_import.id,
        source_customer_code=source_customer_code,
    )
    customer = base_query.order_by(CustomerAccountEntry.row_number.asc()).first_or_404()
    all_entries = base_query.all()
    entries = base_query.order_by(
        CustomerAccountEntry.document_date.desc().nullslast(),
        CustomerAccountEntry.row_number.desc(),
    ).paginate(page=max(1, request.args.get("page", type=int) or 1), per_page=100, error_out=False)
    totals = db.session.query(
        func.sum(case((CustomerAccountEntry.accounting_side == "D", CustomerAccountEntry.amount), else_=0)).label("debit"),
        func.sum(case((CustomerAccountEntry.accounting_side == "A", CustomerAccountEntry.amount), else_=0)).label("credit"),
        func.sum(CustomerAccountEntry.signed_amount).label("balance"),
    ).filter(
        CustomerAccountEntry.import_id == current_import.id,
        CustomerAccountEntry.source_customer_code == source_customer_code,
        CustomerAccountEntry.is_balance_relevant.is_(True),
    ).one()
    area = (request.args.get("area") or "").strip()
    zone = (request.args.get("zone") or "").strip()
    origin = (request.args.get("origin") or "").strip()
    back_url = (
        url_for("administration.customer_credit", area=area, zone=zone)
        if area and zone
        else url_for("administration.customer_credit_customers")
        if origin == "customers"
        else url_for("administration.customer_credit")
    )
    customer_history = _monthly_customer_credit_history(source_customer_code)
    aging = _customer_aging(all_entries)
    communication_contacts = _credit_communication_contacts(customer)
    return render_template(
        "settings/customer_account_statement_detail.html",
        current_import=current_import,
        customer=customer,
        entries=entries,
        totals=totals,
        back_url=back_url,
        area=area,
        zone=zone,
        origin=origin,
        customer_history=customer_history,
        customer_history_payload=[
            {"label": item["label"], "value": float(item["value"])}
            for item in customer_history
        ],
        aging=aging,
        aging_payload=[
            {"label": item["label"], "value": float(item["value"])}
            for item in aging["buckets"]
        ],
        communication_contacts=communication_contacts,
        credit_mail_available=_credit_account_available("creditmanagement"),
        pec_mail_available=_credit_account_available("pec"),
    )


@administration_bp.post("/customer-credit/<source_customer_code>/communications")
@login_required
@role_required(40, roles=["office"])
@log_task(logger)
def send_customer_credit_communication(source_customer_code):
    payload = request.get_json(silent=True) or {}
    action = str(payload.get("action") or "preview").strip().lower()
    kind = str(payload.get("kind") or "").strip().lower()
    channel = str(payload.get("channel") or "").strip().lower()
    contact_id = payload.get("contact_id")
    test_mode = bool(payload.get("test_mode"))
    test_email = str(payload.get("test_email") or "").strip()
    manual_recipient = bool(payload.get("manual_recipient"))
    manual_email = str(payload.get("manual_email") or "").strip()

    if action not in {"preview", "send"}:
        return jsonify({"ok": False, "error": "Azione non valida."}), 400

    allowed = {
        "statement": {"email": ("email", "creditmanagement")},
        "reminder": {
            "email": ("email", "creditmanagement"),
            "pec": ("pec", "pec"),
        },
    }
    if kind not in allowed or channel not in allowed[kind]:
        return jsonify({"ok": False, "error": "Tipo di comunicazione o canale non valido."}), 400

    current_import = _latest_statement_import()
    if current_import is None:
        return jsonify({"ok": False, "error": "Nessuna situazione contabile disponibile."}), 404

    base_query = CustomerAccountEntry.query.filter_by(
        import_id=current_import.id,
        source_customer_code=source_customer_code,
    )
    customer = base_query.order_by(CustomerAccountEntry.row_number.asc()).first()
    if customer is None:
        return jsonify({"ok": False, "error": "Cliente non trovato nella situazione contabile."}), 404

    contact_type, account_code = allowed[kind][channel]
    contact = None
    if test_mode:
        parsed_email = parseaddr(test_email)[1]
        if not parsed_email or parsed_email != test_email or "@" not in parsed_email:
            return jsonify({"ok": False, "error": "Inserisci un indirizzo email di test valido."}), 400
        recipient = parsed_email
    elif manual_recipient:
        parsed_email = parseaddr(manual_email)[1]
        if not parsed_email or parsed_email != manual_email or "@" not in parsed_email:
            return jsonify({"ok": False, "error": "Inserisci un indirizzo destinatario valido."}), 400
        recipient = parsed_email
    else:
        if customer.registry_id is None:
            return jsonify({"ok": False, "error": "Cliente non collegato a un'anagrafica: inserisci il recapito manualmente."}), 404
        try:
            contact_id = int(contact_id)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "Seleziona un destinatario valido."}), 400
        contact = BusinessRegistryContact.query.filter_by(
            id=contact_id,
            registry_id=customer.registry_id,
            contact_type=contact_type,
        ).first()
        if contact is None:
            return jsonify({"ok": False, "error": "Il recapito selezionato non appartiene al cliente."}), 400
        recipient = contact.value

    account = get_email_account(account_code, include_password=False, legacy_fallback=False)
    if not account or not account.get("is_enabled"):
        label = "PEC" if account_code == "pec" else "CreditManagement"
        return jsonify({"ok": False, "error": f"Account {label} non ancora configurato o disattivato."}), 409

    entries = base_query.filter(CustomerAccountEntry.is_balance_relevant.is_(True)).order_by(
        CustomerAccountEntry.document_date.asc().nullsfirst(),
        CustomerAccountEntry.row_number.asc(),
    ).all()
    totals = db.session.query(
        func.sum(case((CustomerAccountEntry.accounting_side == "D", CustomerAccountEntry.amount), else_=0)).label("debit"),
        func.sum(case((CustomerAccountEntry.accounting_side == "A", CustomerAccountEntry.amount), else_=0)).label("credit"),
        func.sum(CustomerAccountEntry.signed_amount).label("balance"),
    ).filter(
        CustomerAccountEntry.import_id == current_import.id,
        CustomerAccountEntry.source_customer_code == source_customer_code,
        CustomerAccountEntry.is_balance_relevant.is_(True),
    ).one()
    if kind == "reminder" and Decimal(totals.balance or 0) <= 0:
        return jsonify({"ok": False, "error": "Il cliente non presenta un saldo positivo da sollecitare."}), 409

    default_subject = (
        f"Estratto conto aggiornato - {customer.customer_name}"
        if kind == "statement"
        else f"Sollecito di pagamento - {customer.customer_name}"
    )
    default_html = _credit_message_html(kind, customer, entries, totals)
    sender = account.get("default_sender") or account.get("username") or account_sender(account_code)

    if action == "preview":
        return jsonify({
            "ok": True,
            "preview": {
                "sender": sender,
                "recipient": recipient,
                "subject": f"[TEST] {default_subject}" if test_mode else default_subject,
                "html": default_html,
                "test_mode": test_mode,
                "account": "PEC" if account_code == "pec" else "CreditManagement",
            },
        })

    subject = str(payload.get("subject") or default_subject).strip()[:255]
    html_body = str(payload.get("html") or default_html).strip()
    if not subject:
        return jsonify({"ok": False, "error": "L'oggetto non può essere vuoto."}), 400
    if not html_body or len(html_body.encode("utf-8")) > 500_000:
        return jsonify({"ok": False, "error": "Il contenuto del messaggio non è valido o è troppo grande."}), 400
    if test_mode and not subject.startswith("[TEST]"):
        subject = f"[TEST] {subject}"

    message = Message(
        subject=subject,
        recipients=[recipient],
        sender=sender,
        html=html_body,
    )
    try:
        result = send_account_mail(account_code, message)
    except Exception:
        logger.exception(
            "Invio comunicazione credito fallito customer=%s kind=%s channel=%s contact_id=%s",
            source_customer_code, kind, channel, contact.id if contact else None,
        )
        return jsonify({"ok": False, "error": "Invio non riuscito. Controlla la configurazione dell'account e riprova."}), 502

    logger.info(
        "Comunicazione credito inviata customer=%s import_id=%s kind=%s channel=%s contact_id=%s test_mode=%s manual_recipient=%s recipient=%s suppressed=%s",
        source_customer_code, current_import.id, kind, channel, contact.id if contact else None,
        test_mode, manual_recipient, recipient, bool(result.get("suppressed")),
    )
    return jsonify({
        "ok": True,
        "message": f"Comunicazione {'di test ' if test_mode else ''}inviata a {recipient}.",
        "suppressed": bool(result.get("suppressed")),
    })


def _payment_link_recipient(payload):
    recipient_type = str(payload.get("recipient_type") or "none").strip().lower()
    if recipient_type in {"", "none", "copy"}:
        return None
    if recipient_type == "email":
        email = _valid_email(payload.get("recipient_email"))
        if not email:
            raise ValueError("Inserisci un indirizzo email valido.")
        return {"type": "email", "email": email, "name": str(payload.get("recipient_name") or "").strip()[:255] or None}
    try:
        recipient_id = int(payload.get("recipient_id"))
    except (TypeError, ValueError):
        raise ValueError("Seleziona un destinatario valido.")
    if recipient_type == "user":
        user = User.query.get(recipient_id)
        if user is None or not _valid_email(user.email):
            raise ValueError("L'utente selezionato non dispone di un indirizzo email valido.")
        return {
            "type": "user", "email": user.email, "name": f"{user.name} {user.surname}".strip(),
            "user_id": user.id,
        }
    if recipient_type == "customer":
        registry = BusinessRegistry.query.filter_by(id=recipient_id, kind="customer", is_active=True).first()
        if registry is None:
            raise ValueError("Cliente non trovato.")
        requested_contact_id = payload.get("recipient_contact_id")
        query = BusinessRegistryContact.query.filter(
            BusinessRegistryContact.registry_id == registry.id,
            BusinessRegistryContact.contact_type == "email",
        )
        if requested_contact_id:
            try:
                query = query.filter(BusinessRegistryContact.id == int(requested_contact_id))
            except (TypeError, ValueError):
                raise ValueError("Recapito cliente non valido.")
        contact = query.order_by(BusinessRegistryContact.is_primary.desc(), BusinessRegistryContact.id.asc()).first()
        if contact is None or not _valid_email(contact.value):
            raise ValueError("Il cliente selezionato non dispone di un indirizzo email valido.")
        return {
            "type": "customer", "email": contact.value,
            "name": registry.display_name or registry.legal_name or registry.source_code,
            "registry_id": registry.id, "contact_id": contact.id,
        }
    raise ValueError("Tipo di destinatario non valido.")


def _queue_payment_link_delivery(payment_link, recipient):
    if not recipient:
        return None
    delivery = AdministrationPaymentLinkDelivery(
        payment_link_id=payment_link.id,
        requested_by_user_id=current_user.id,
        recipient_type=recipient["type"],
        recipient_user_id=recipient.get("user_id"),
        recipient_registry_id=recipient.get("registry_id"),
        recipient_name=recipient.get("name"),
        recipient_email=recipient["email"],
        status="queued",
    )
    db.session.add(delivery)
    db.session.commit()
    try:
        from config.tasks import send_administration_payment_link_task

        send_administration_payment_link_task.delay(delivery.id)
    except Exception as exc:
        logger.exception("Impossibile accodare invio PayByLink delivery=%s", delivery.id)
        delivery.status = "failed"
        delivery.error_message = f"Accodamento non riuscito: {str(exc)[:500]}"
        db.session.commit()
    return delivery


@administration_bp.get("/payment-links")
@login_required
@role_required(40, roles=["office"])
@log_task(logger)
def payment_links():
    expired_count = AdministrationPaymentLink.query.filter(
        AdministrationPaymentLink.status == "active",
        AdministrationPaymentLink.expires_at.isnot(None),
        AdministrationPaymentLink.expires_at <= datetime.now(timezone.utc),
    ).update({AdministrationPaymentLink.status: "expired"}, synchronize_session=False)
    if expired_count:
        db.session.commit()
    page = request.args.get("page", 1, type=int)
    links = AdministrationPaymentLink.query.order_by(
        AdministrationPaymentLink.created_at.desc(), AdministrationPaymentLink.id.desc(),
    ).paginate(page=max(1, page), per_page=30, error_out=False)
    return render_template(
        "administration/payment_links.html",
        links=links,
        xpay_configured=bool(current_app.config.get("NEXI_XPAY_API_KEY")),
        xpay_environment=current_app.config.get("NEXI_XPAY_ENVIRONMENT", "sandbox"),
    )


@administration_bp.get("/payment-links/result")
def payment_link_result():
    return render_template("administration/payment_link_result.html", cancelled=False)


@administration_bp.get("/payment-links/cancelled")
def payment_link_cancelled():
    return render_template("administration/payment_link_result.html", cancelled=True)


@administration_bp.get("/payment-links/recipients")
@login_required
@role_required(40, roles=["office"])
def payment_link_recipients():
    recipient_type = str(request.args.get("type") or "").strip().lower()
    search = str(request.args.get("q") or "").strip()[:100]
    if len(search) < 2:
        return jsonify({"ok": True, "items": []})
    pattern = f"%{search}%"
    if recipient_type == "user":
        users = User.query.filter(
            db.or_(User.name.ilike(pattern), User.surname.ilike(pattern), User.email.ilike(pattern)),
        ).order_by(User.surname.asc(), User.name.asc()).limit(20).all()
        items = [
            {"id": user.id, "label": f"{user.name} {user.surname}", "email": user.email}
            for user in users if _valid_email(user.email)
        ]
    elif recipient_type == "customer":
        registries = BusinessRegistry.query.filter(
            BusinessRegistry.kind == "customer",
            BusinessRegistry.is_active.is_(True),
            db.or_(
                BusinessRegistry.display_name.ilike(pattern),
                BusinessRegistry.legal_name.ilike(pattern),
                BusinessRegistry.source_code.ilike(pattern),
            ),
        ).order_by(BusinessRegistry.display_name.asc()).limit(20).all()
        items = []
        for registry in registries:
            contacts = [
                contact for contact in registry.contacts
                if contact.contact_type == "email" and _valid_email(contact.value)
            ]
            if contacts:
                items.append({
                    "id": registry.id,
                    "label": registry.display_name or registry.legal_name or registry.source_code,
                    "code": registry.source_code,
                    "contacts": [{"id": item.id, "email": item.value, "label": item.label or item.contact_type.upper()} for item in contacts],
                })
    else:
        return jsonify({"ok": False, "error": "Tipo destinatario non valido."}), 400
    return jsonify({"ok": True, "items": items})


@administration_bp.post("/payment-links")
@login_required
@role_required(40, roles=["office"])
@log_task(logger)
def create_payment_link():
    if not current_app.config.get("NEXI_XPAY_API_KEY"):
        return jsonify({"ok": False, "error": "Configura prima la API key Nexi XPay nelle impostazioni."}), 409
    payload_in = request.get_json(silent=True) or {}
    amount = _parse_positive_amount(payload_in.get("amount"))
    description = str(payload_in.get("description") or "").strip()
    if amount is None:
        return jsonify({"ok": False, "error": "Inserisci un importo valido maggiore di zero."}), 400
    if not description or len(description) > 255:
        return jsonify({"ok": False, "error": "Inserisci una descrizione (massimo 255 caratteri)."}), 400
    try:
        recipient = _payment_link_recipient(payload_in)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    expires_at = (datetime.now(timezone.utc) + timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=0)
    payment_link = AdministrationPaymentLink(
        created_by_user_id=current_user.id,
        amount=amount,
        currency="EUR",
        description=description,
        status="creating",
        provider="nexi_xpay",
        expires_at=expires_at,
    )
    db.session.add(payment_link)
    db.session.flush()
    payment_link.provider_order_id = f"PL{_base36(payment_link.id)}"
    db.session.commit()

    amount_minor = str(int((amount * 100).quantize(Decimal("1"))))
    provider_payload = {
        "order": {
            "orderId": payment_link.provider_order_id,
            "amount": amount_minor,
            "currency": "EUR",
            "description": description,
            "customField": payment_link.public_id[:255],
        },
        "paymentSession": {
            "actionType": "PAY",
            "amount": amount_minor,
            "captureType": "IMPLICIT",
            "language": "ita",
            "resultUrl": _public_url("administration.payment_link_result"),
            "cancelUrl": _public_url("administration.payment_link_cancelled"),
            "notificationUrl": _public_url("administration.payment_link_nexi_notification"),
            "expirationDate": expires_at.strftime("%Y-%m-%d"),
        },
    }
    if recipient and recipient.get("email"):
        provider_payload["customerInfo"] = {"cardHolderEmail": recipient["email"]}
    try:
        result = NexiXPayClient.from_app().create_paybylink(provider_payload)
        payment_link.provider_reference = result.link_id
        payment_link.provider_security_token = result.security_token
        payment_link.payment_url = result.payment_url
        payment_link.status = "active"
        payment_link.last_error = None
        db.session.commit()
    except NexiXPayUncertainError as exc:
        db.session.rollback()
        payment_link = AdministrationPaymentLink.query.get(payment_link.id)
        payment_link.status = "provider_uncertain"
        payment_link.last_error = str(exc)[:1000]
        db.session.commit()
        logger.error("Creazione PayByLink incerta id=%s order=%s", payment_link.id, payment_link.provider_order_id)
        return jsonify({"ok": False, "uncertain": True, "error": str(exc)}), 502
    except NexiXPayError as exc:
        db.session.rollback()
        payment_link = AdministrationPaymentLink.query.get(payment_link.id)
        payment_link.status = "failed"
        payment_link.last_error = str(exc)[:1000]
        db.session.commit()
        return jsonify({"ok": False, "error": str(exc)}), 502
    except Exception:
        db.session.rollback()
        logger.exception("Errore inatteso creazione PayByLink id=%s", payment_link.id)
        payment_link = AdministrationPaymentLink.query.get(payment_link.id)
        if payment_link:
            payment_link.status = "provider_uncertain"
            payment_link.last_error = "Errore tecnico durante il salvataggio della risposta Nexi."
            db.session.commit()
        return jsonify({"ok": False, "uncertain": True, "error": "Esito Nexi incerto: non generare un secondo link."}), 502

    delivery = _queue_payment_link_delivery(payment_link, recipient)
    return jsonify({
        "ok": True,
        "item": {
            "id": payment_link.id,
            "url": payment_link.payment_url,
            "status": payment_link.status,
            "amount": str(payment_link.amount),
            "description": payment_link.description,
            "expires_at": payment_link.expires_at.isoformat() if payment_link.expires_at else None,
            "delivery": ({"id": delivery.id, "status": delivery.status, "email": delivery.recipient_email} if delivery else None),
        },
    }), 201


@administration_bp.post("/payment-links/<int:payment_link_id>/send")
@login_required
@role_required(40, roles=["office"])
@log_task(logger)
def send_payment_link(payment_link_id):
    payment_link = AdministrationPaymentLink.query.get_or_404(payment_link_id)
    if payment_link.status == "active" and payment_link.expires_at and payment_link.expires_at <= datetime.now(timezone.utc):
        payment_link.status = "expired"
        db.session.commit()
    if payment_link.status != "active" or not payment_link.payment_url:
        return jsonify({"ok": False, "error": "Il link non e' attivo e non puo' essere inviato."}), 409
    payload = request.get_json(silent=True) or {}
    try:
        recipient = _payment_link_recipient(payload)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    if recipient is None:
        return jsonify({"ok": False, "error": "Seleziona un destinatario email."}), 400
    delivery = _queue_payment_link_delivery(payment_link, recipient)
    return jsonify({"ok": True, "delivery": {"id": delivery.id, "status": delivery.status, "email": delivery.recipient_email}}), 202


@administration_bp.post("/payment-links/nexi/notification")
def payment_link_nexi_notification():
    if request.content_length is not None and request.content_length > 128 * 1024:
        abort(413)
    payload = request.get_json(silent=True)
    operation = payload.get("operation") if isinstance(payload, dict) else None
    if not isinstance(operation, dict):
        abort(400)
    order_id = str(operation.get("orderId") or "").strip()
    payment_link = AdministrationPaymentLink.query.filter_by(provider="nexi_xpay", provider_order_id=order_id).first()
    if payment_link is None:
        abort(404)
    supplied_token = str(payload.get("securityToken") or "")
    expected_token = str(payment_link.provider_security_token or "")
    if not expected_token or not hmac.compare_digest(supplied_token, expected_token):
        abort(400)
    event_id = str(payload.get("eventId") or "").strip()[:80]
    if event_id and event_id == payment_link.provider_last_event_id:
        return ("", 200)
    try:
        expected_amount = int((Decimal(payment_link.amount) * 100).quantize(Decimal("1")))
        notified_amount = int(str(operation.get("operationAmount")))
    except (TypeError, ValueError, ArithmeticError):
        abort(400)
    if notified_amount != expected_amount or str(operation.get("operationCurrency") or "").upper() != payment_link.currency:
        abort(400)
    channel_detail = str(operation.get("channelDetail") or "").upper()
    if channel_detail not in {"PAY_BY_LINK", "POST_PAYMENT_OPERATION"}:
        abort(400)
    result = str(operation.get("operationResult") or "").upper()
    operation_type = str(operation.get("operationType") or "").upper()
    payment_link.provider_last_event_id = event_id or payment_link.provider_last_event_id
    payment_link.provider_operation_id = str(operation.get("operationId") or "").strip()[:160] or payment_link.provider_operation_id
    if result == "EXECUTED" and operation_type == "CAPTURE":
        payment_link.status = "paid"
        payment_link.provider_confirmed_at = datetime.now(timezone.utc)
    elif result in {"DECLINED", "DENIED_BY_RISK", "THREEDS_FAILED", "FAILED"}:
        payment_link.status = "failed"
    elif result == "CANCELED":
        payment_link.status = "cancelled"
    db.session.commit()
    return ("", 200)
