import tempfile

from flask import Blueprint, send_from_directory, current_app
import requests
import os

file_bp = Blueprint("file_bp", __name__)

# Cartella dove il gestionale esporta i file
ESTRAZIONI_FOLDER = "/dati/discorete/estrazioni"


@file_bp.route("/<filename>")
def serve_risorsa(filename):
    """Serve il file dal percorso locale o lo scarica dal server se non presente."""
    local_folder = current_app.config['EXPORT_FOLDER']
    local_file_path = os.path.join(local_folder, filename.upper())
    remote_file_url = current_app.config['EXPORT_FOLDER_URL'].rstrip('/') + '/' + filename.upper()
    remote_file_url = remote_file_url.replace("\\", "/")

    if os.path.exists(local_file_path):
        print(f"restituisco il file locale: {local_file_path}")
        return send_from_directory(local_folder, filename.upper(), as_attachment=True)
    else:
        # Scarica il file remoto
        print(f"restituisco il file remoto: {remote_file_url}")
        response = requests.get(remote_file_url, stream=True)
        print(f"DEBUG: HTTP Status Code: {response.status_code}")
        print(f"DEBUG: Content-Type: {response.headers.get('Content-Type', 'N/A')}")
        print(f"DEBUG: Risposta ricevuta (primi 500 caratteri): \n{response.text[:500]}")

        # Se la risposta è solo un percorso e non il contenuto, allora il file non viene servito direttamente
        if response.text.strip().startswith("/") and ".CSV" in response.text.upper():
            print("❌ Il server sta restituendo solo il percorso, non il file. Devi scaricarlo manualmente.")
            raise ValueError("Il server ha restituito solo il percorso, non il file. Modifica la richiesta.")

        # ✅ Se il contenuto è corretto, salviamo il file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode='wb') as temp_file:
            for chunk in response.iter_content(chunk_size=8192):
                temp_file.write(chunk)
            temp_file_path = temp_file.name

        print(f"✅ File scaricato correttamente in: {temp_file_path}")
        return temp_file_path


@file_bp.route('/get/<filename>')
def get_exported_file(filename):
    print(f"DEBUG: get_exported_file: {filename}")
    print(f"DEBUG: current_app.config['EXPORT_FOLDER_URL'] = {current_app.config['EXPORT_FOLDER_URL']}")
    return send_from_directory(current_app.config['EXPORT_FOLDER_URL'], filename.upper(), as_attachment=True)
