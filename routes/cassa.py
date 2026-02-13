import logging

from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required
from datetime import date, datetime, timezone, timedelta
from sqlalchemy import and_

from tools.log_utils import get_logger
from extensions import db
from models import CashDay, CashClosure

cassa_bp = Blueprint("cassa", __name__, url_prefix="/cassa")
logger = get_logger("cassa", level=logging.INFO)


@cassa_bp.route("/agenda", methods=["GET"])
@login_required
def agenda():
    return render_template("agenda.html")


@cassa_bp.route("/api/day", methods=["GET"])
@login_required
def api_get_or_create_day():
    date_str = (request.args.get("date") or "").strip()

    if date_str:
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"ok": False, "error": "Invalid date format. Use YYYY-MM-DD"}), 400
    else:
        target_date = date.today()

    day = CashDay.query.filter_by(day_date=target_date).first()

    if not day:
        prev_date = target_date - timedelta(days=1)

        prev_day = CashDay.query.filter_by(day_date=prev_date).first()
        opening_float = 0

        if prev_day and prev_day.closure and prev_day.closure.closing_cash_drawer is not None:
            opening_float = float(prev_day.closure.closing_cash_drawer)

        day = CashDay(
            day_date=target_date,
            opening_float=opening_float,
            status="open",
        )
        db.session.add(day)
        db.session.commit()

    return jsonify({
        "ok": True,
        "day": {
            "id": day.id,
            "day_date": day.day_date.isoformat(),
            "status": day.status,
            "opening_float": float(day.opening_float or 0),
        }
    })
