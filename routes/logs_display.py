# routes/logs_diplay.py
import re

from flask import Blueprint, render_template, request
import os

logs_bp = Blueprint("logs_bp", __name__, url_prefix="/logs")


@logs_bp.route("/view")
def visualizza_logs():
    log_dir = os.path.join(os.getcwd(), "logs")
    selected_file = request.args.get("file", "main.log")
    selected_level = request.args.get("level", "").upper()

    file_path = os.path.join(log_dir, selected_file)
    logs = []

    if os.path.exists(file_path):
        with open(file_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                match = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - ([^ ]+) - ([A-Z]+) - (.+)$", line)
                if match:
                    level = match.group(3)
                    if not selected_level or selected_level == level:
                        logs.append({
                            "timestamp": match.group(1),
                            "module": match.group(2),
                            "level": level,
                            "message": match.group(4),
                            "raw": line,
                            "match": True,
                        })
                elif line:
                    logs.append({
                        "raw": line,
                        "match": False
                    })

    return render_template("logs_display.html",
                           files=os.listdir(log_dir),
                           selected_file=selected_file,
                           log_content=logs)
