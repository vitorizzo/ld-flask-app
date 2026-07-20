from datetime import datetime

from flask import Blueprint, render_template
from flask_login import login_required
from sqlalchemy import and_, func, or_

from extensions import db
from models import AppVisitor, Role, User, UserRole
from tools.role_required import role_required


developer_bp = Blueprint("developer", __name__)


def _active_user_role_condition(now):
    return or_(
        UserRole.type == "lifetime",
        and_(
            UserRole.type == "until",
            or_(UserRole.valid_until.is_(None), UserRole.valid_until >= now),
        ),
        and_(
            UserRole.type == "period",
            UserRole.valid_from <= now,
            or_(UserRole.valid_until.is_(None), UserRole.valid_until >= now),
        ),
    )


@developer_bp.get("/dashboard")
@login_required
@role_required(999)
def dashboard():
    now = datetime.now()
    active_condition = _active_user_role_condition(now)
    role_counts = (
        db.session.query(
            Role.name,
            Role.description,
            Role.weight,
            func.count(func.distinct(UserRole.user_id)).label("user_count"),
        )
        .outerjoin(UserRole, and_(UserRole.role_id == Role.id, active_condition))
        .group_by(Role.id, Role.name, Role.description, Role.weight)
        .order_by(Role.weight.desc(), Role.name.asc())
        .all()
    )
    active_user_ids = db.session.query(UserRole.user_id).filter(active_condition)
    users_without_active_role = User.query.filter(~User.id.in_(active_user_ids)).count()

    return render_template(
        "developer/dashboard.html",
        unique_visitors=AppVisitor.query.count(),
        total_visits=db.session.query(func.coalesce(func.sum(AppVisitor.visit_count), 0)).scalar(),
        total_users=User.query.count(),
        users_without_active_role=users_without_active_role,
        role_counts=role_counts,
    )
