from collections import defaultdict
from datetime import date
from decimal import Decimal

from flask import Blueprint, abort, render_template, request, url_for
from flask_login import login_required
from sqlalchemy import case, func

from extensions import db
from models import BusinessRegistry, CustomerAccountEntry, CustomerAccountStatementImport
from tools.log_utils import get_logger, log_task
from tools.role_required import role_required


administration_bp = Blueprint("administration", __name__)
logger = get_logger("administration")

UNKNOWN_AREA = "Provincia non definita"
UNKNOWN_ZONE = "Comune non definito"
MONTH_LABELS = (
    "Gen", "Feb", "Mar", "Apr", "Mag", "Giu",
    "Lug", "Ago", "Set", "Ott", "Nov", "Dic",
)


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
        .filter(CustomerAccountEntry.import_id == import_id)
        .group_by(CustomerAccountEntry.source_customer_code)
        .having(balance > 0)
        .all()
    )


def _history_area_options(import_id):
    rows = (
        db.session.query(BusinessRegistry.province)
        .join(CustomerAccountEntry, CustomerAccountEntry.registry_id == BusinessRegistry.id)
        .filter(CustomerAccountEntry.import_id == import_id)
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
    remaining_credit = sum(
        (entry.amount for entry in entries if entry.accounting_side == "A"),
        Decimal("0"),
    )
    debit_entries = sorted(
        (entry for entry in entries if entry.accounting_side == "D"),
        key=lambda entry: (
            entry.due_date or entry.document_date or entry.registration_date or date.min,
            entry.row_number,
        ),
    )
    buckets = [
        {"label": "0–30 gg", "value": Decimal("0")},
        {"label": "31–60 gg", "value": Decimal("0")},
        {"label": "61–90 gg", "value": Decimal("0")},
        {"label": "91–120 gg", "value": Decimal("0")},
        {"label": "Oltre 120 gg", "value": Decimal("0")},
    ]
    weighted_days = Decimal("0")
    outstanding_total = Decimal("0")
    for entry in debit_entries:
        outstanding = entry.amount
        if remaining_credit > 0:
            allocated = min(outstanding, remaining_credit)
            outstanding -= allocated
            remaining_credit -= allocated
        if outstanding <= 0:
            continue

        reference_date = entry.due_date or entry.document_date or entry.registration_date or today
        age_days = max(0, (today - reference_date).days)
        bucket_index = 0 if age_days <= 30 else 1 if age_days <= 60 else 2 if age_days <= 90 else 3 if age_days <= 120 else 4
        buckets[bucket_index]["value"] += outstanding
        outstanding_total += outstanding
        weighted_days += outstanding * age_days

    average_days = int((weighted_days / outstanding_total).quantize(Decimal("1"))) if outstanding_total else 0
    return {
        "average_days": average_days,
        "outstanding_total": outstanding_total,
        "buckets": buckets,
    }


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
    )
