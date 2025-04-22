from flask import Blueprint, jsonify, redirect, flash, url_for, request
from flask_login import login_required
from routes.decorators import role_required
from tools.task_monitor import get_task_status, kill_task

task_bp = Blueprint("task_bp", __name__, url_prefix="/task_manage")


@task_bp.route("/status/<task_id>")
def task_status(task_id):
    return jsonify(get_task_status(task_id))


@task_bp.route("/kill/<task_id>", methods=["POST"])
def task_kill(task_id):
    return jsonify(kill_task(task_id))


@task_bp.route("/clear_all_tasks", methods=["GET", "POST"])
@login_required  # se hai login richiesto
@role_required(500)  # opzionale, se vuoi che solo admin lo faccia
def clear_all_tasks():
    from tools.redis_utils import clear_all_task_statuses
    clear_all_task_statuses()
    flash("Tutti i task sono stati eliminati dalla memoria temporanea.", "success")
    return redirect(request.referrer or url_for("task_bp.task_status"))

