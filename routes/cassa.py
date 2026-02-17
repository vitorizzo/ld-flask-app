import logging
import os
from datetime import date, datetime, timezone, timedelta

from flask import Blueprint, render_template, request, jsonify, session
from flask_login import login_required
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


@cassa_bp.route("/api/private/status", methods=["GET"])
@login_required
def api_private_status():
    """
    Stato vault privato (PRI).
    - vault_dir: directory mount (es. /mnt/archive/runtime)
    - mounted: True se la directory è un mountpoint attivo
    - year_file_exists: True se esiste il file dell'anno corrente (es. 2026.enc)
    - unlocked: flag sessione (per ora sarà quasi sempre False finché non implementiamo /unlock)
    """
    vault_dir = os.environ.get("PRIVATE_VAULT_DIR", "/mnt/archive/runtime")
    year = date.today().year
    year_file = os.path.join(vault_dir, f"{year}.enc")

    mounted = os.path.ismount(vault_dir)
    year_file_exists = os.path.isfile(year_file)

    unlocked = bool(session.get("pri_vault_unlocked", False))

    return jsonify({
        "ok": True,
        "vault": {
            "vault_dir": vault_dir,
            "mounted": mounted,
            "year": year,
            "year_file_exists": year_file_exists,
            "unlocked": unlocked,
        }
    })
