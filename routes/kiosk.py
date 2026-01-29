import logging
from datetime import datetime, timezone
from flask import Blueprint, request, make_response

from tools.log_utils import get_logger

kiosk_bp = Blueprint("kiosk", __name__, url_prefix="/kiosk")

logger = get_logger("kiosk", level=logging.INFO)
logger.debug("Logger 'kiosk' inizializzato correttamente - test DEBUG")


@kiosk_bp.get("/test")
def kiosk_test():
    # Best effort IP (se dietro reverse proxy, usa X-Forwarded-For)
    xff = request.headers.get("X-Forwarded-For", "")
    client_ip = xff.split(",")[0].strip() if xff else request.remote_addr

    now = datetime.now(timezone.utc).astimezone()  # locale server
    html = f"""<!doctype html>
            <html lang="it">
            <head>
              <meta charset="utf-8"/>
              <meta name="viewport" content="width=device-width, initial-scale=1"/>
              <meta http-equiv="refresh" content="10"/>
              <title>Kiosk Test</title>
              <style>
                html, body {{ height: 100%; margin: 0; }}
                body {{
                  display: flex; align-items: center; justify-content: center;
                  font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
                  background: #111; color: #eee;
                }}
                .card {{
                  width: min(900px, 92vw);
                  border: 2px solid #444;
                  border-radius: 18px;
                  padding: 28px 32px;
                  box-shadow: 0 10px 30px rgba(0,0,0,.45);
                }}
                h1 {{ margin: 0 0 14px; font-size: clamp(28px, 4vw, 44px); }}
                .ok {{ display: inline-block; padding: 6px 12px; border-radius: 999px; background: #1b5; color: #031; font-weight: 800; }}
                .row {{ margin-top: 14px; font-size: clamp(16px, 2vw, 20px); line-height: 1.35; }}
                code {{ color: #9ef; }}
              </style>
            </head>
            <body>
              <div class="card">
                <h1><span class="ok">KIOSK TEST OK</span></h1>
                <div class="row">Ora server: <code>{now.strftime('%Y-%m-%d %H:%M:%S %Z')}</code></div>
                <div class="row">Client IP: <code>{client_ip}</code></div>
                <div class="row">User-Agent: <code>{request.headers.get('User-Agent','')}</code></div>
                <div class="row" style="opacity:.8;margin-top:18px;">Auto refresh ogni 10s (disattivabile).</div>
              </div>
            </body>
            </html>"""

    resp = make_response(html, 200)
    # Evita cache aggressiva in kiosk
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp
