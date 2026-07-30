from collections import defaultdict
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
        level=level,
        area=area,
        zone=zone,
        total_exposure=total_exposure,
        customer_count=sum(item["customer_count"] for item in chart_items),
        back_url=back_url,
        breadcrumbs=breadcrumbs,
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
    back_url = (
        url_for("administration.customer_credit", area=area, zone=zone)
        if area and zone else url_for("administration.customer_credit")
    )
    return render_template(
        "settings/customer_account_statement_detail.html",
        current_import=current_import,
        customer=customer,
        entries=entries,
        totals=totals,
        back_url=back_url,
        area=area,
        zone=zone,
    )
