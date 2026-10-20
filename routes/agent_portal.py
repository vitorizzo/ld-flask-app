from decimal import Decimal
from types import SimpleNamespace

from flask import Blueprint, abort, jsonify, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy import case, func, or_
from sqlalchemy.orm import raiseload, selectinload

from extensions import db
from models import (
    AgentCustomer,
    BusinessRegistry,
    BusinessRegistryContact,
    BusinessRegistryContactLink,
    CustomerAccountEntry,
    CustomerAccountStatementImport,
    RegistryContact,
    RegistryContactPoint,
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
    balances_by_registry = {}
    if current_import and registries:
        assigned_ids = {registry.id for registry in registries}
        assigned_codes = {registry.source_code for registry in registries if registry.source_code}
        filters = [CustomerAccountEntry.registry_id.in_(assigned_ids)]
        if assigned_codes:
            filters.append(CustomerAccountEntry.source_customer_code.in_(assigned_codes))
        account_rows = db.session.query(
            CustomerAccountEntry.source_customer_code.label("source_customer_code"),
            func.max(CustomerAccountEntry.registry_id).label("registry_id"),
            func.sum(CustomerAccountEntry.signed_amount).label("balance"),
            func.count(CustomerAccountEntry.id).label("movement_count"),
        ).filter(
            CustomerAccountEntry.import_id == current_import.id,
            CustomerAccountEntry.is_balance_relevant.is_(True),
            or_(*filters),
        ).group_by(CustomerAccountEntry.source_customer_code).all()
        balances_by_code = {row.source_customer_code: row for row in account_rows}
        balances_by_registry = {row.registry_id: row for row in account_rows}
    customers = []
    for registry in registries:
        account = balances_by_registry.get(registry.id) or balances_by_code.get(registry.source_code)
        customers.append({
            "registry": registry,
            "balance": Decimal(str(account.balance or 0)) if account else Decimal("0"),
            "movement_count": int(account.movement_count or 0) if account else 0,
        })
    customers.sort(key=lambda item: (item["registry"].display_name or item["registry"].legal_name or "").casefold())
    total_exposure = sum((item["balance"] for item in customers if item["balance"] > 0), Decimal("0"))
    search = (request.args.get("q") or "").strip()
    only_outstanding = request.args.get("outstanding") == "1"
    if search:
        folded = search.casefold()
        customers = [item for item in customers if any(
            folded in str(value or "").casefold()
            for value in (item["registry"].display_name, item["registry"].legal_name,
                          item["registry"].source_code, item["registry"].city)
        )]
    if only_outstanding:
        customers = [item for item in customers if item["balance"] > 0]
    return render_template(
        "agent_portal/customer_credit.html",
        current_import=current_import,
        customers=customers,
        total_exposure=total_exposure,
        search=search,
        only_outstanding=only_outstanding,
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
    ).filter(or_(
        CustomerAccountEntry.registry_id == registry.id,
        CustomerAccountEntry.source_customer_code == source_customer_code,
    ))
    all_entries = base_query.order_by(CustomerAccountEntry.row_number.asc()).all()
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
        or_(CustomerAccountEntry.registry_id == registry.id,
            CustomerAccountEntry.source_customer_code == source_customer_code),
        CustomerAccountEntry.is_balance_relevant.is_(True),
    ).one()
    return render_template(
        "agent_portal/customer_credit_detail.html",
        current_import=current_import,
        registry=registry,
        customer=all_entries[0] if all_entries else SimpleNamespace(
            customer_name=registry.display_name or registry.legal_name,
            source_customer_code=source_customer_code,
        ),
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
        agent_customer_assignment=True,
        agent_api_url=url_for("agent_portal.customer_contacts_data"),
    )


@agent_portal_bp.get("/api/customer-search")
@login_required
def search_company_customers_for_agent():
    _require_agent()
    search = (request.args.get("q") or "").strip()
    if len(search) < 2:
        return jsonify(ok=True, customers=[])
    pattern = f"%{search}%"
    assigned_ids = agent_customer_registry_query(current_user).with_entities(BusinessRegistry.id)
    rows = BusinessRegistry.query.options(raiseload("*")).filter(
        BusinessRegistry.kind == "customer",
        BusinessRegistry.is_active.is_(True),
        or_(
            BusinessRegistry.display_name.ilike(pattern),
            BusinessRegistry.legal_name.ilike(pattern),
            BusinessRegistry.source_code.ilike(pattern),
            BusinessRegistry.city.ilike(pattern),
        ),
        ~BusinessRegistry.id.in_(assigned_ids),
    ).order_by(BusinessRegistry.display_name.asc(), BusinessRegistry.id.asc()).limit(30).all()
    return jsonify(ok=True, customers=[{
        "id": item.id,
        "code": item.source_code,
        "name": item.display_name or item.legal_name or item.source_code,
        "city": item.city,
    } for item in rows])


@agent_portal_bp.post("/api/customers")
@login_required
def add_company_customer_to_agent():
    _require_agent()
    data = request.get_json(silent=True) or {}
    try:
        registry_id = int(data.get("registry_id"))
    except (TypeError, ValueError):
        return jsonify(ok=False, error="Cliente non valido"), 400
    registry = BusinessRegistry.query.options(raiseload("*")).filter_by(
        id=registry_id, kind="customer", is_active=True
    ).first_or_404()
    customer_data = {
        "id": registry.id,
        "code": registry.source_code,
        "name": registry.display_name or registry.legal_name or registry.source_code,
    }
    if agent_customer_registry_query(current_user).options(raiseload("*")).filter(BusinessRegistry.id == registry.id).first():
        return jsonify(ok=True, already_assigned=True, customer={"id": registry.id})
    db.session.add(AgentCustomer(user_id=current_user.id, registry_id=registry.id))
    db.session.commit()
    return jsonify(ok=True, already_assigned=False, customer={
        **customer_data,
    })


@agent_portal_bp.post("/api/contacts")
@login_required
def add_customer_contact_for_agent():
    """Create a customer contact in the shared company registry from the agent book."""
    _require_agent()
    data = request.get_json(silent=True) or {}
    try:
        registry_id = int(data.get("registry_id"))
    except (TypeError, ValueError):
        return jsonify(ok=False, error="Cliente non valido"), 400
    registry = agent_customer_registry_query(current_user).options(raiseload("*" )).filter(
        BusinessRegistry.id == registry_id
    ).first_or_404()
    registry_id = registry.id

    raw_name = data.get("display_name")
    raw_role = data.get("role")
    display_name = raw_name.strip() if isinstance(raw_name, str) else ""
    role = raw_role.strip() if isinstance(raw_role, str) else ""
    points = data.get("points")
    if not display_name or len(display_name) > 255:
        return jsonify(ok=False, error="Inserisci un nome valido per il contatto."), 400
    if role and len(role) > 120:
        return jsonify(ok=False, error="L’etichetta del contatto è troppo lunga."), 400
    if not isinstance(points, list) or not points:
        return jsonify(ok=False, error="Inserisci almeno un numero di telefono."), 400

    contact_points = []
    for point in points[:10]:
        if not isinstance(point, dict):
            continue
        raw_type = point.get("contact_type") or point.get("type") or ""
        raw_value = point.get("value") or ""
        raw_label = point.get("label") or ""
        contact_type = raw_type.strip().lower() if isinstance(raw_type, str) else ""
        value = raw_value.strip() if isinstance(raw_value, str) else ""
        label = raw_label.strip()[:80] or None if isinstance(raw_label, str) else None
        if contact_type not in {"phone", "mobile"} or not value or len(value) > 255 or not any(char.isdigit() for char in value):
            continue
        contact_points.append((contact_type, value, label))
    if not contact_points:
        return jsonify(ok=False, error="Inserisci un numero di telefono valido."), 400

    contact = RegistryContact(display_name=display_name, role=role or None, is_active=True)
    for index, (contact_type, value, label) in enumerate(contact_points):
        contact.points.append(RegistryContactPoint(
            contact_type=contact_type,
            value=value,
            label=label,
            is_primary=index == 0,
        ))
    link = BusinessRegistryContactLink(
        registry=registry,
        contact=contact,
        role=role or None,
        is_primary=not BusinessRegistryContactLink.query.filter_by(
            registry_id=registry.id, is_active=True, is_primary=True
        ).first(),
        is_active=True,
    )
    db.session.add_all([contact, link])
    db.session.flush()
    contact_data = contact.to_dict()
    db.session.commit()
    return jsonify(ok=True, message="Contatto aggiunto alla rubrica agente e alla rubrica aziendale.",
                   contact=contact_data, registry_id=registry_id), 201


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
