import tempfile
from datetime import datetime
from email.utils import parsedate_to_datetime

import requests
import os
from flask import Blueprint, send_from_directory, current_app, jsonify
from tools.log_utils import log_task, get_logger

logger = get_logger('teamsystem_export')

file_bp = Blueprint("file_bp", __name__)

# Fallback di produzione; EXPORT_FOLDER da ambiente/config resta prioritario.
DEFAULT_EXPORT_FOLDER = "/dati/DISCORETE/estrazioni/export"
ALLOWED_EXPORT_EXTENSIONS = {".csv", ".txt", ".pdf"}


def _export_folder():
    return (
        os.getenv("EXPORT_FOLDER")
        or current_app.config.get("EXPORT_FOLDER")
        or DEFAULT_EXPORT_FOLDER
    )


def _resolve_export_file(filename):
    safe_name = os.path.basename(filename or "")
    if not safe_name:
        raise FileNotFoundError("Nome file non valido")

    _, ext = os.path.splitext(safe_name)
    if ext.lower() not in ALLOWED_EXPORT_EXTENSIONS:
        raise FileNotFoundError(f"Estensione file non consentita: {safe_name}")

    folder = _export_folder()
    direct_path = os.path.join(folder, safe_name)
    if os.path.exists(direct_path):
        return folder, safe_name, direct_path

    upper_name = safe_name.upper()
    upper_path = os.path.join(folder, upper_name)
    if os.path.exists(upper_path):
        return folder, upper_name, upper_path

    lower_name = safe_name.lower()
    lower_path = os.path.join(folder, lower_name)
    if os.path.exists(lower_path):
        return folder, lower_name, lower_path

    if os.path.isdir(folder):
        safe_lower = safe_name.lower()
        for existing_name in os.listdir(folder):
            if existing_name.lower() == safe_lower:
                resolved_path = os.path.join(folder, existing_name)
                if os.path.isfile(resolved_path):
                    return folder, existing_name, resolved_path

    raise FileNotFoundError(f"File non trovato: {os.path.join(folder, safe_name)}")


def _download_export_file(filename):
    safe_name = os.path.basename(filename or "")
    if not safe_name:
        raise FileNotFoundError("Nome file non valido")

    _, ext = os.path.splitext(safe_name)
    if ext.lower() not in ALLOWED_EXPORT_EXTENSIONS:
        raise FileNotFoundError(f"Estensione file non consentita: {safe_name}")

    base_url = current_app.config.get("EXPORT_FOLDER_URL")
    if not base_url:
        raise FileNotFoundError(f"File non trovato e EXPORT_FOLDER_URL non configurato: {safe_name}")

    candidate_names = []
    for candidate in (safe_name, safe_name.upper(), safe_name.lower()):
        if candidate not in candidate_names:
            candidate_names.append(candidate)

    response = None
    last_error = None
    for candidate in candidate_names:
        for remote_file_url in (
            f"{base_url.rstrip('/')}/get/{candidate}",
            f"{base_url.rstrip('/')}/{candidate}",
        ):
            remote_file_url = remote_file_url.replace("\\", "/")
            logger.warning("File export locale non trovato. Provo download remoto: %s", remote_file_url)
            try:
                response = requests.get(remote_file_url, stream=True, timeout=60)
                logger.info("Download export %s: HTTP %s", candidate, response.status_code)
                if response.status_code == 404:
                    last_error = FileNotFoundError(f"File remoto non trovato: {remote_file_url}")
                    response = None
                    continue
                response.raise_for_status()
                break
            except requests.RequestException as exc:
                last_error = exc
                response = None
        if response is not None:
            break

    if response is None:
        raise FileNotFoundError(f"Impossibile scaricare {safe_name}: {last_error}")

    content_type = response.headers.get("Content-Type", "")
    if "text/html" in content_type.lower():
        preview = response.text[:300]
        raise ValueError(f"Il server ha restituito HTML invece del file {safe_name}: {preview}")

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext.lower(), mode="wb") as temp_file:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                temp_file.write(chunk)
        temp_file_path = temp_file.name

    last_modified = response.headers.get("Last-Modified")
    if last_modified:
        try:
            modified_at = parsedate_to_datetime(last_modified)
            os.utime(temp_file_path, (modified_at.timestamp(), modified_at.timestamp()))
        except (TypeError, ValueError, OSError):
            logger.warning("Last-Modified non applicabile per %s: %s", safe_name, last_modified)

    logger.info("File export %s scaricato in: %s", safe_name, temp_file_path)
    return temp_file_path


def serve_risorsa_back(filename):
    local_folder = _export_folder()
    _, resolved_name, local_file_path = _resolve_export_file(filename)
    remote_file_url = current_app.config['EXPORT_FOLDER_URL'].rstrip('/') + '/' + filename.upper()
    remote_file_url = remote_file_url.replace("\\", "/")

    if os.path.exists(local_file_path):
        logger.info(f"File locale trovato: {local_file_path}")
        return send_from_directory(local_folder, resolved_name, as_attachment=True)
    else:
        logger.warning(f"File locale non trovato. Cerco di scaricare: {remote_file_url}")
        response = requests.get(remote_file_url, stream=True)
        logger.debug(f"HTTP Status: {response.status_code}")
        logger.debug(f"Content-Type: {response.headers.get('Content-Type', 'N/A')}")
        logger.debug(f"Contenuto (500 char): {response.text[:500]}")

        if response.text.strip().startswith("/") and ".CSV" in response.text.upper():
            logger.error("❌ Il server ha restituito solo un percorso, non un file.")
            raise ValueError("Il server ha restituito solo il percorso, non il file. Modifica la richiesta.")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode='wb') as temp_file:
            for chunk in response.iter_content(chunk_size=8192):
                temp_file.write(chunk)
            temp_file_path = temp_file.name

        logger.info(f"✅ File scaricato in: {temp_file_path}")
        return temp_file_path


@file_bp.route("/<filename>")
@log_task(logger)
def serve_risorsa(filename):
    """
    Funzione compatibile anche fuori dal contesto Flask (es. nei Celery task)
    """
    try:
        _, _, file_path = _resolve_export_file(filename)
        return file_path  # restituisce il path, non l'oggetto file o una response Flask
    except FileNotFoundError:
        return _download_export_file(filename)


@file_bp.route("/lista_export")
def lista_export():
    folder = _export_folder()
    logger.debug(f"Percorso EXPORT_FOLDER = {folder}")
    if not os.path.exists(folder):
        return jsonify({"error": "Cartella di export non trovata"}), 500

    files_info = []
    for f in os.listdir(folder):
        logger.debug(f"Esaminando file: {f}")
        if f.lower().endswith(".csv"):
            path = os.path.join(folder, f)
            stat = os.stat(path)
            files_info.append({
                "name": os.path.join(folder, f),
                "size": round(stat.st_size / 1024, 1),  # KB
                "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%d/%m/%Y %H:%M")
            })

    # Ordina per data di modifica, più recente prima
    files_info.sort(key=lambda x: x["mtime"], reverse=True)
    logger.debug(f"Files trovati: {files_info}")
    return jsonify({"files": files_info})


@file_bp.route('/get/<filename>')
@log_task(logger)
def get_exported_file(filename):
    logger.info(f"Richiesta di esportazione file: {filename}")
    folder, resolved_name, _ = _resolve_export_file(filename)
    logger.debug(f"Percorso EXPORT_FOLDER = {folder}")
    return send_from_directory(folder, resolved_name, as_attachment=True)
