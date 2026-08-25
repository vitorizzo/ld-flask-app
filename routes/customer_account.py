from flask import Blueprint, abort, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import load_only

from extensions import db
from models import BusinessRegistry, CustomerAccountEntry, CustomerAccountStatementImport, CustomerPaymentCase
from tools.customer_memberships import active_customer_memberships, customer_registry_for_user


customer_account_bp = Blueprint("customer_account", __name__)
ALLOWED_ROLE_NAMES = {"customer_horeca", "dev"}


def _active_role_names():
    return {str(getattr(role, "name", "")).strip().lower() for role in current_user.active_roles or []}


@customer_account_bp.get("/")
@login_required
def index():
    role_names = _active_role_names()
    if not role_names.intersection(ALLOWED_ROLE_NAMES):
        abort(403)

    is_developer = "dev" in role_names
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

    current_import = (
        CustomerAccountStatementImport.query
        .order_by(CustomerAccountStatementImport.imported_at.desc(), CustomerAccountStatementImport.id.desc())
        .first()
    )
    entries = None
    totals = None
    open_cases = []
    if registry is not None and current_import is not None:
        ownership_filter = or_(
            CustomerAccountEntry.registry_id == registry.id,
            and_(
                CustomerAccountEntry.registry_id.is_(None),
                CustomerAccountEntry.source_customer_code == registry.source_code,
            ),
        )
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
        open_cases = (
            CustomerPaymentCase.query
            .filter(
                CustomerPaymentCase.registry_id == registry.id,
                CustomerPaymentCase.status.notin_(("accounted", "rejected", "expired", "cancelled", "failed")),
            )
            .order_by(CustomerPaymentCase.created_at.desc())
            .limit(20)
            .all()
        )

    return render_template(
        "customer_account/index.html",
        registries=registries,
        registry=registry,
        current_import=current_import,
        entries=entries,
        totals=totals,
        open_cases=open_cases,
        is_developer=is_developer,
    )


@customer_account_bp.get("/select/<int:registry_id>")
@login_required
def select_registry(registry_id):
    role_names = _active_role_names()
    if not role_names.intersection(ALLOWED_ROLE_NAMES):
        abort(403)
    if "dev" in role_names:
        registry = BusinessRegistry.query.filter_by(id=registry_id, kind="customer", is_active=True).first()
    else:
        registry = customer_registry_for_user(current_user, registry_id)
    if registry is None:
        abort(403)
    return redirect(url_for("customer_account.index", customer=registry_id))
