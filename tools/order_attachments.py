"""Percorsi locali e pubblicazione degli allegati degli ordini."""
from pathlib import Path
from flask import current_app


UPLOAD_ROOTS = ('uploads/route_orders/', 'uploads/shared_orders/', 'uploads/customer_orders/')


def local_order_attachment_path(attachment):
    rel = str(attachment.get('static_path') or '').strip().replace('\\', '/')
    if not rel and str(attachment.get('url') or '').startswith('/static/'):
        rel = attachment['url'][len('/static/'):]
    prefix = next((root for root in UPLOAD_ROOTS if rel.startswith(root)), None)
    if not prefix:
        return None
    static_root = Path(current_app.static_folder).resolve()
    upload_root = (static_root / prefix).resolve()
    candidate = (static_root / rel).resolve()
    if not upload_root.is_relative_to(static_root) or not candidate.is_relative_to(upload_root):
        return None
    return str(candidate) if candidate.is_file() else None


def post_order_message(api, channel_id, text, attachments, *, client_msg_id=None):
    """Un messaggio principale con testo e file; il percorso senza file resta invariato."""
    uploads = []
    for attachment in attachments or []:
        path = local_order_attachment_path(attachment)
        if not path:
            raise RuntimeError(f"Allegato non trovato: {attachment.get('name') or 'file'}")
        filename = attachment.get('filename') or attachment.get('name') or Path(path).name
        uploads.append({'file': path, 'filename': filename, 'title': attachment.get('title') or filename})
    if not uploads:
        return api.post_message(channel_id, text, client_msg_id=client_msg_id)
    response = api.post_message_with_files(channel_id, text, uploads)
    for local, remote in zip(attachments, response.get('files') or []):
        # Manteniamo ID/percorso locale per gli ordini gia' archiviati e aggiungiamo
        # il riferimento Slack come fallback e per riconciliare gli eventi webhook.
        local['slack_file_id'] = remote.get('id')
        for key in ('url_private', 'url_private_download', 'permalink', 'thumb_360', 'thumb_480', 'thumb_720', 'thumb_1024'):
            if remote.get(key):
                local[key] = remote[key]
    return response
