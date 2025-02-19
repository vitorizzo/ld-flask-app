from flask import Blueprint, send_from_directory, abort, current_app, Response
from routes.decorators import role_required
from flask_login import login_required
import requests
import os

file_bp = Blueprint("file_bp", __name__)

# Cartella dove il gestionale esporta i file
ESTRAZIONI_FOLDER = "/dati/discorete/estrazioni"


@file_bp.route("/<filename>")
@login_required
@role_required(100)
def serve_risorsa(filename):
    """Serve il file dal percorso locale o lo scarica dal server se non presente."""

    local_file_path = os.path.join(current_app.config['EXPORT_FOLDER'], filename)
    print(f"DEBUG: local_file_path = {local_file_path}")

    if current_app.config['EXPORT_FOLDER'] and os.path.exists(local_file_path):
        # 📂 Serve il file locale se esiste
        print(f"📂 Servendo file locale: {local_file_path}")  # Debug
        return send_from_directory(current_app.config['EXPORT_FOLDER'], filename)

    elif current_app.config['EXPORT_FOLDER_URL']:
        # 📡 Scarica il file da remoto se non trovato in locale
        remote_file_url = current_app.config['EXPORT_FOLDER_URL'] + filename
        print(f"📡 Scaricando file da remoto: {remote_file_url}")  # Debug

        try:
            response = requests.get(remote_file_url, stream=True)
            response.raise_for_status()
            return Response(response.content, content_type="text/csv")
        except requests.exceptions.RequestException as e:
            print(f"❌ Errore nel download del file: {e}")
            abort(404)

    print("❌ File non trovato né in locale né su remoto!")
    abort(404)


    @file_bp.route('/test/<filename>')
    def get_exported_file(filename):
        return send_from_directory(current_app.config['EXPORT_FOLDER'], filename)