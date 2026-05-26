# routes/logs_diplay.py
import os
import re
import logging
from pathlib import Path

from flask import Blueprint, render_template, request

from config.paths_config import LOGS_FOLDER
from tools.log_utils import get_logger

logger = get_logger("logs_viewer", level=logging.DEBUG)

logs_bp = Blueprint("logs_bp", __name__, url_prefix="/logs")

BASE_LOG_RE = re.compile(r"^(?P<name>.+)\.log$")
ROTATED_LOG_RE = re.compile(r"^.+\.log\.\d+$")


def _available_log_files() -> list[str]:
    log_dir = Path(LOGS_FOLDER)
    if not log_dir.exists():
        return []

    files = []
    for entry in log_dir.iterdir():
        if not entry.is_file():
            continue
        name = entry.name
        if name == ".gitkeep":
            continue
        if name.startswith(".__") and name.endswith(".lock"):
            continue
        if ROTATED_LOG_RE.match(name):
            continue
        if not BASE_LOG_RE.match(name):
            continue
        files.append(name)

    return sorted(files, key=lambda name: (0 if name == "main.log" else 1, name.lower()))


@logs_bp.route("/view")
def visualizza_logs():
    logger.info(f"chiamata route visualizza logs")
    files = _available_log_files()
    selected_file = request.args.get("file", "main.log")
    selected_level = request.args.get("level", "").upper()

    if selected_file not in files:
        selected_file = "main.log" if "main.log" in files else (files[0] if files else "main.log")

    file_path = os.path.join(LOGS_FOLDER, selected_file)
    logs = []

    if os.path.exists(file_path):
        with open(file_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                #logger.debug(f"linea letta:\n{line}")
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
                           files=files,
                           selected_file=selected_file,
                           selected_level=selected_level,
                           log_content=logs)
