from flask import Blueprint, jsonify
from tools.redis_utils import get_all_tasks_status

status_bp = Blueprint('status_bp', __name__, url_prefix='/task')


@status_bp.route("/status")
def tasks_status():
    tasks = get_all_tasks_status()
    return jsonify({"tasks": tasks})
