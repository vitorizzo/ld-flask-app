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
                html, body {{
                  height: 100%;
                  margin: 0;
                }}
        
                body {{
                  font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
                  background: 
                    linear-gradient(rgba(0,0,0,.55), rgba(0,0,0,.55)),
                    url('/static/images/home-kiosk.jpg') center / cover no-repeat;
                  color: #fff;
                  display: flex;
                  align-items: center;
                  justify-content: center;
                }}
        
                .welcome-section {{
                  width: min(900px, 92vw);
                  background: rgba(0,0,0,.65);
                  border: 1px solid rgba(255,255,255,.15);
                  border-radius: 22px;
                  padding: 36px 42px;
                  box-shadow: 0 20px 60px rgba(0,0,0,.6);
                  backdrop-filter: blur(4px);
                  text-align: center;
                }}
        
                .logo {{
                  height: 64px;
                  margin-bottom: 24px;
                }}
        
                h1 {{
                  margin: 0 0 18px;
                  font-size: clamp(30px, 4vw, 46px);
                }}
        
                .ok {{
                  display: inline-block;
                  padding: 6px 14px;
                  border-radius: 999px;
                  background: #2ecc71;
                  color: #062;
                  font-weight: 800;
                  font-size: 0.9em;
                }}
        
                .row {{
                  margin-top: 14px;
                  font-size: clamp(16px, 2vw, 20px);
                  line-height: 1.4;
                  opacity: .9;
                }}
        
                code {{
                  color: #9fdcff;
                }}
              </style>
            </head>
        
            <body>
              <section class="welcome-section">
                <img class="logo"
                     src="/static/images/logo-ldenoteca-bianco.png"
                     alt="LD Enoteca">
        
                <h1><span class="ok">KIOSK TEST OK</span></h1>
        
                <div class="row">
                  Ora server:
                  <code>{now.strftime('%Y-%m-%d %H:%M:%S %Z')}</code>
                </div>
        
                <div class="row">
                  Client IP:
                  <code>{client_ip}</code>
                </div>
        
                <div class="row">
                  User-Agent:
                  <code>{request.headers.get('User-Agent', '')}</code>
                </div>
        
                <div class="row" style="opacity:.75; margin-top:20px;">
                  Auto refresh ogni 10s
                </div>
              </section>
            </body>
            </html>"""

    resp = make_response(html, 200)
    # Evita cache aggressiva in kiosk
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp
