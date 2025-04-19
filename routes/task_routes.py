from flask import Blueprint, jsonify
from tools.task_monitor import get_task_status, kill_task

task_bp = Blueprint("task_bp", __name__, url_prefix="/task_manage")


@task_bp.route("/status/<task_id>")
def task_status(task_id):
    return jsonify(get_task_status(task_id))


@task_bp.route("/kill/<task_id>", methods=["POST"])
def task_kill(task_id):
    return jsonify(kill_task(task_id))
