from flask import Blueprint, jsonify, redirect, flash, url_for, request
from flask_login import login_required
from routes.decorators import role_required
from tools.task_monitor import get_task_status, kill_task

task_bp = Blueprint("task_bp", __name__, url_prefix="/task_manage")


@task_bp.route("/status/<task_id>")
@login_required
def task_status(task_id):
    return jsonify(get_task_status(task_id))


@task_bp.route("/kill/<task_id>", methods=["POST"])
@login_required
def task_kill(task_id):
    payload = request.get_json(silent=True) or {}
    return jsonify(kill_task(task_id, revoke=not bool(payload.get("remove_only"))))


@task_bp.route("/clear_errors", methods=["POST"])
@login_required
def clear_errors():
    from tools.redis_utils import clear_terminal_task_statuses
    cleared = clear_terminal_task_statuses()
    return jsonify({"message": f"Rimossi {cleared} errori o stati residui dal monitor.", "cleared": cleared})


@task_bp.route("/clear_all_tasks", methods=["GET", "POST"])
@login_required  # se hai login richiesto
@role_required(500)  # opzionale, se vuoi che solo admin lo faccia
def clear_all_tasks():
    from tools.redis_utils import clear_all_task_statuses
    clear_all_task_statuses()
    flash("Tutti i task sono stati eliminati dalla memoria temporanea.", "success")
    return redirect(request.referrer or url_for("home"))

