from decimal import Decimal

from flask import Blueprint, abort, jsonify, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy import case, func, or_
from sqlalchemy.orm import raiseload, selectinload

from extensions import db
from models import (
    BusinessRegistry,
    BusinessRegistryContact,
    BusinessRegistryContactLink,
    CustomerAccountEntry,
    CustomerAccountStatementImport,
    RegistryContact,
)
from routes.registry import _registry_to_dict
from tools.agent_customer_access import agent_customer_registry_query, user_is_agent
from tools.contact_imports import resolve_photo_path
from tools.customer_account_rows import open_account_entries


agent_portal_bp = Blueprint("agent_portal", __name__)


def _require_agent():
    if not user_is_agent(current_user):
        abort(403)


def _latest_statement_import():
    return CustomerAccountStatementImport.query.order_by(
        CustomerAccountStatementImport.imported_at.desc(),
        CustomerAccountStatementImport.id.desc(),
    ).first()


@agent_portal_bp.get("/customers")
@login_required
def customer_credit_index():
    _require_agent()
    current_import = _latest_statement_import()
    registries = agent_customer_registry_query(current_user).options(raiseload("*" )).order_by(
        BusinessRegistry.display_name.asc(), BusinessRegistry.id.asc()
    ).all()
    balances_by_code = {}
    if current_import and registries:
        registry_ids = [registry.id for registry in registries]
        source_codes = list({registry.source_code for registry in registries if registry.source_code})
        filters = []
        if registry_ids:
            filters.append(CustomerAccountEntry.registry_id.in_(registry_ids))
        if source_codes:
            filters.append(CustomerAccountEntry.source_customer_code.in_(source_codes))
        account_rows = (
            db.session.query(
                CustomerAccountEntry.source_customer_code,
                func.max(CustomerAccountEntry.customer_name).label("customer_name"),
                func.sum(CustomerAccountEntry.signed_amount).label("balance"),
                func.count(CustomerAccountEntry.id).label("movement_count"),
            )
            .filter(
                CustomerAccountEntry.import_id == current_import.id,
                CustomerAccountEntry.is_balance_relevant.is_(True),
                or_(*filters),
            )
            .group_by(CustomerAccountEntry.source_customer_code)
            .all()
        )
        balances_by_code = {row.source_customer_code: row for row in account_rows}
    customers = []
    for registry in registries:
        account = balances_by_code.get(registry.source_code)
        customers.append({
            "registry": registry,
            "balance": Decimal(str(account.balance or 0)) if account else Decimal("0"),
            "movement_count": int(account.movement_count or 0) if account else 0,
        })
    return render_template(
        "agent_portal/customer_credit.html",
        current_import=current_import,
        customers=customers,
    )


@agent_portal_bp.get("/customers/<source_customer_code>")
@login_required
def customer_credit_detail(source_customer_code):
    _require_agent()
    registry = agent_customer_registry_query(current_user).options(raiseload("*" )).filter(
        BusinessRegistry.source_code == source_customer_code
    ).first_or_404()
    current_import = _latest_statement_import()
    if current_import is None:
        abort(404)
    base_query = CustomerAccountEntry.query.filter_by(
        import_id=current_import.id,
        source_customer_code=source_customer_code,
    )
    all_entries = base_query.order_by(CustomerAccountEntry.row_number.asc()).all()
    if not all_entries:
        abort(404)
    visible_ids = [entry.id for entry in open_account_entries(all_entries)]
    entries = base_query.filter(CustomerAccountEntry.id.in_(visible_ids)).order_by(
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
    return render_template(
        "agent_portal/customer_credit_detail.html",
        current_import=current_import,
        registry=registry,
        customer=all_entries[0],
        entries=entries,
        totals=totals,
        back_url=url_for("agent_portal.customer_credit_index"),
    )


@agent_portal_bp.get("/contacts")
@login_required
def customer_contacts():
    _require_agent()
    return render_template(
        "registry/registry_book.html",
        kind="customer",
        title="Rubrica clienti agente",
        readonly=True,
        agent_api_url=url_for("agent_portal.customer_contacts_data"),
    )


@agent_portal_bp.get("/api/contacts")
@login_required
def customer_contacts_data():
    _require_agent()
    query = agent_customer_registry_query(current_user).options(
        raiseload("*"),
        selectinload(BusinessRegistry.contacts),
        selectinload(BusinessRegistry.contact_links)
        .selectinload(BusinessRegistryContactLink.contact)
        .selectinload(RegistryContact.points),
    )
    search = (request.args.get("q") or "").strip()
    if search:
        like = f"%{search}%"
        matching_contact_registry_ids = db.session.query(BusinessRegistryContact.registry_id).filter(
            BusinessRegistryContact.value.ilike(like)
        )
        query = query.filter(or_(
            BusinessRegistry.display_name.ilike(like),
            BusinessRegistry.legal_name.ilike(like),
            BusinessRegistry.source_code.ilike(like),
            BusinessRegistry.vat_number.ilike(like),
            BusinessRegistry.tax_code.ilike(like),
            BusinessRegistry.city.ilike(like),
            BusinessRegistry.id.in_(matching_contact_registry_ids),
        ))
    registries = query.order_by(BusinessRegistry.display_name.asc(), BusinessRegistry.id.asc()).all()
    result = []
    for registry in registries:
        data = _registry_to_dict(registry, include_contacts=True)
        for link in data["contact_links"]:
            contact = link.get("contact") or {}
            if contact.get("photo_url"):
                contact["photo_url"] = url_for("agent_portal.customer_contact_photo", contact_id=contact["id"])
        result.append(data)
    return jsonify(ok=True, kind="customer", count=len(result), limited=bool(search), registries=result)


@agent_portal_bp.get("/api/contacts/<int:contact_id>/photo")
@login_required
def customer_contact_photo(contact_id):
    _require_agent()
    contact = RegistryContact.query.filter_by(id=contact_id, is_active=True).first_or_404()
    registry_ids = agent_customer_registry_query(current_user).with_entities(BusinessRegistry.id).subquery()
    link = (
        BusinessRegistryContactLink.query
        .join(BusinessRegistry, BusinessRegistry.id == BusinessRegistryContactLink.registry_id)
        .filter(
            BusinessRegistryContactLink.contact_id == contact.id,
            BusinessRegistryContactLink.is_active.is_(True),
            BusinessRegistry.id.in_(registry_ids),
        )
        .first()
    )
    if not link:
        abort(404)
    path = resolve_photo_path(contact.photo_path)
    if not path:
        abort(404)
    return send_file(path, mimetype=contact.photo_mime or "image/jpeg", conditional=True, max_age=0)
