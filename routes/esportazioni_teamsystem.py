import tempfile

from pprint import pprint
from flask import Blueprint, send_from_directory, current_app, render_template, send_file
from routes.decorators import role_required
from flask_login import login_required
import requests
import os

file_bp = Blueprint("file_bp", __name__)

# Cartella dove il gestionale esporta i file
ESTRAZIONI_FOLDER = "/dati/discorete/estrazioni"


#@file_bp.route("/<filename>")
#@login_required
#@role_required(100)
def get_risorsa(filename):
    """Serve il file dal percorso locale o lo scarica dal server se non presente."""
    local_folder = current_app.config['EXPORT_FOLDER']
    local_file_path = os.path.join(local_folder, filename.upper())
    remote_file_url = current_app.config['EXPORT_FOLDER_URL'].rstrip('/') + '/' + filename.upper()
    remote_file_url = remote_file_url.replace("\\", "/")

    message = ""
    print(f"DEBUG: local_file_path = {local_file_path}")
    if os.path.exists(local_file_path):
        message = f"File trovato in locale: {local_file_path}"
    elif os.path.exists(local_folder):
        message = f"❌ File non trovato localmente in {local_file_path}. 📡 Tentativo di download da: {remote_file_url}"
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


def test_risorsa(filename):
    """Serve il file dal percorso locale o lo scarica dal server se non presente."""
    local_folder = current_app.config['EXPORT_FOLDER']
    local_file_path = os.path.join(local_folder, filename.upper())
    remote_file_url = current_app.config['EXPORT_FOLDER_URL'].rstrip('/') + '/' + filename.upper()
    remote_file_url = remote_file_url.replace("\\", "/")

    message = ""
    print(f"DEBUG: local_file_path = {local_file_path}")
    if os.path.exists(local_file_path):
        message = f"File trovato in locale: {local_file_path}"
    elif os.path.exists(local_folder):
        message = f"❌ File non trovato localmente in {local_file_path}. 📡 Tentativo di download da: {remote_file_url}"
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

@file_bp.route("/<filename>")
# @login_required
# @role_required(100)
def serve_risorsa(filename):
    """Serve il file dal percorso locale o lo scarica dal server se non presente."""
    local_folder = current_app.config['EXPORT_FOLDER']
    local_file_path = os.path.join(local_folder, filename.upper())
    remote_file_url = current_app.config['EXPORT_FOLDER_URL'].rstrip('/') + '/' + filename.upper()
    remote_file_url = remote_file_url.replace("\\", "/")

    if os.path.exists(local_file_path):
        print(f"restituisco il file locale: {local_file_path}")
        return get_exported_file(filename)
    else:
        # Scarica il file remoto
        print(f"restituisco il file remoto: {remote_file_url}")
        response = requests.get(remote_file_url, stream=True)
        pprint(response.content)
        #if response.status_code != 200:
        #    return f"Errore: impossibile scaricare il file {remote_file_url}", 404
            # Debug: Stampiamo cosa restituisce il server
        print(f"DEBUG: HTTP Status Code: {response.status_code}")
        print(f"DEBUG: Content-Type: {response.headers.get('Content-Type', 'N/A')}")
        print(f"DEBUG: Risposta ricevuta (primi 500 caratteri):\n{response.text[:500]}")

        # Se la risposta è solo un percorso e non il contenuto, allora il file non viene servito direttamente
        if response.text.strip().startswith("/") and ".CSV" in response.text.upper():
            print("❌ Il server sta restituendo solo il percorso, non il file. Devi scaricarlo manualmente.")
            raise ValueError("Il server ha restituito solo il percorso, non il file. Modifica la richiesta.")

        # Verifica se il contenuto è veramente un CSV
        # content_type = response.headers.get("Content-Type", "")
        # if "text/html" in content_type:
        #    print("❌ Errore: il server ha restituito una pagina HTML invece del file CSV!")
        #    print(response.text[:500])  # Mostra il contenuto della risposta
        #    raise ValueError("Il server ha restituito una pagina HTML invece del file CSV.")

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
