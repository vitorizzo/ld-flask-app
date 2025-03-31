import tempfile
import requests
import os
from flask import Blueprint, send_from_directory, current_app
from tools.log_utils import log_task, get_logger

logger = get_logger('teamsystem_export')

file_bp = Blueprint("file_bp", __name__)

# Cartella dove il gestionale esporta i file
ESTRAZIONI_FOLDER = "/dati/discorete/estrazioni"


@file_bp.route("/<filename>")
@log_task(logger)
def serve_risorsa(filename):
    local_folder = current_app.config['EXPORT_FOLDER']
    local_file_path = os.path.join(local_folder, filename.upper())
    remote_file_url = current_app.config['EXPORT_FOLDER_URL'].rstrip('/') + '/' + filename.upper()
    remote_file_url = remote_file_url.replace("\\", "/")

    if os.path.exists(local_file_path):
        logger.info(f"File locale trovato: {local_file_path}")
        return send_from_directory(local_folder, filename.upper(), as_attachment=True)
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


@file_bp.route('/get/<filename>')
@log_task(logger)
def get_exported_file(filename):
    logger.info(f"Richiesta di esportazione file: {filename}")
    logger.debug(f"Percorso EXPORT_FOLDER_URL = {current_app.config['EXPORT_FOLDER_URL']}")
    return send_from_directory(current_app.config['EXPORT_FOLDER_URL'], filename.upper(), as_attachment=True)
