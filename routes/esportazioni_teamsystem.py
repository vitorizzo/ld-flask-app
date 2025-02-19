from flask import Blueprint, send_from_directory, abort, current_app, Response, render_template
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
    local_folder = current_app.config['EXPORT_FOLDER']
    local_file_path = os.path.join(local_folder, filename)
    remote_file_url = current_app.config['EXPORT_FOLDER_URL'].rstrip('/') + '/' + filename

    message = ""
    print(f"DEBUG: local_file_path = {local_file_path}")
    if os.path.exists(local_file_path):
        message = f"File trovato in locale: {local_file_path}"
    elif os.path.exists(local_folder):
        message = f"❌ File non trovato localmente. 📡 Tentativo di download da: {remote_file_url}"
        try:
            response = requests.get(remote_file_url, stream=True)
            response.raise_for_status()  # Se il download fallisce, genera un'eccezione

            # 📌 **Salva il file scaricato nella cartella locale**
            with open(local_file_path, 'wb') as file:
                for chunk in response.iter_content(chunk_size=8192):
                    file.write(chunk)

            message += f"\n ✅ File scaricato e salvato in: {local_file_path}"

        except requests.exceptions.RequestException as e:
            message += f"\n ❌ Errore nel download del file: {e}"
            return render_template('test.html', message=message)
    else:
        message = "\n ❌ La cartella di esportazione non esiste. Procedo alla creazione."
        os.makedirs(local_folder, exist_ok=True)
        message += f"\n 📁 Cartella creata: {local_folder}\n"
        try:
            response = requests.get(remote_file_url, stream=True)
            response.raise_for_status()  # Se il download fallisce, genera un'eccezione

            # 📌 **Salva il file scaricato nella cartella locale**
            with open(local_file_path, 'wb') as file:
                for chunk in response.iter_content(chunk_size=8192):
                    file.write(chunk)

            message += f"\n ✅ File scaricato e salvato in: {local_file_path}"

        except requests.exceptions.RequestException as e:
            message += f"\n ❌ Errore nel download del file: {e}"
            return render_template('test.html', message=message)
    return render_template('test.html', message=message)

@file_bp.route('/test/<filename>')
def get_exported_file(filename):
    return send_from_directory(current_app.config['EXPORT_FOLDER'], filename)