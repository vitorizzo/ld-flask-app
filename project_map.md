# project_map.md
Versione: 1.5.0  
Ultimo aggiornamento: 2026-01-21

## Raw file map (main) + descrizioni

### Root
/project_map.md        → https://raw.githubusercontent.com/vitorizzo/ld-flask-app/main/project_map.md  
  - [MAP] Mappa dei file leggibili via raw + regole operative

/new_chat.md           → https://raw.githubusercontent.com/vitorizzo/ld-flask-app/main/new_chat.md  
  - [BOOT] Prompt/istruzioni per avviare nuove chat (bootstrap + regole)

/models.py             → https://raw.githubusercontent.com/vitorizzo/ld-flask-app/main/models.py  
  - [DB][MODELS] Modelli SQLAlchemy (incluse entità legacy e V2 automations)

/app.py                → https://raw.githubusercontent.com/vitorizzo/ld-flask-app/main/app.py  
  - [ENTRY] Entrypoint WSGI: crea app via create_app()

/README.md             → https://raw.githubusercontent.com/vitorizzo/ld-flask-app/main/README.md  
  - [DOC] Documentazione generale progetto (setup/uso)

/config.py             → https://raw.githubusercontent.com/vitorizzo/ld-flask-app/main/config.py  
  - [CONF] Config Flask (env, DB, feature flags/chiavi)

/celery_worker.py      → https://raw.githubusercontent.com/vitorizzo/ld-flask-app/main/celery_worker.py  
  - [CELERY][ENTRY] Entrypoint processi Celery (worker/beat)

/requirements.txt      → https://raw.githubusercontent.com/vitorizzo/ld-flask-app/main/requirements.txt  
  - [DEPS] Dipendenze Python (pip)

---

### Config
/config/celeryconfig.py → https://raw.githubusercontent.com/vitorizzo/ld-flask-app/main/config/celeryconfig.py  
  - [CELERY][CONF] Configurazione Celery (queue/beat/etc)

/config/celery_app.py   → https://raw.githubusercontent.com/vitorizzo/ld-flask-app/main/config/celery_app.py  
  - [CELERY][APP] Factory/istanza Celery e wiring con Flask

/config/paths_config.py → https://raw.githubusercontent.com/vitorizzo/ld-flask-app/main/config/paths_config.py  
  - [PATHS] Percorsi filesystem condivisi (log, export, import, ecc.)

/config/tasks.py        → https://raw.githubusercontent.com/vitorizzo/ld-flask-app/main/config/tasks.py  
  - [CELERY][TASKS] Definizione/registrazione task

/config/capabilities.py → https://raw.githubusercontent.com/vitorizzo/ld-flask-app/main/config/capabilities.py  
  - [CAPS] Catalogo backend di trigger/actions/fields/placeholders per UI dinamica (no hardcoding JS)

---

### Forms
/forms/forms.py         → https://raw.githubusercontent.com/vitorizzo/ld-flask-app/main/forms/forms.py  
  - [FORMS] WTForms (login/registrazione/varie)

---

### Routes
/routes/trello.py       → https://raw.githubusercontent.com/vitorizzo/ld-flask-app/main/routes/trello.py  
  - [API][TRELLO] Blueprint Trello: webhook, connessioni, gestione (legacy), integrazione con processor

/routes/slack.py        → https://raw.githubusercontent.com/vitorizzo/ld-flask-app/main/routes/slack.py  
  - [API][SLACK] Blueprint Slack: Events API, firma/dedup, connessioni, integrazione con SlackProcessor

---

### Tools
/tools/processor.py     → https://raw.githubusercontent.com/vitorizzo/ld-flask-app/main/tools/processor.py  
  - [TRELLO][LEGACY+V2] Processor eventi Trello: normalizzazione trigger + esecuzione legacy + hook V2 dispatcher

/tools/trello_client.py → https://raw.githubusercontent.com/vitorizzo/ld-flask-app/main/tools/trello_client.py  
  - [TRELLO][HTTP] Client low-level verso Trello (requests, auth, chiamate base)

/tools/trello_api.py    → https://raw.githubusercontent.com/vitorizzo/ld-flask-app/main/tools/trello_api.py  
  - [TRELLO][API] API wrapper alto livello (add comment, create card, ecc.)

/tools/app_factory.py   → https://raw.githubusercontent.com/vitorizzo/ld-flask-app/main/tools/app_factory.py  
  - [FACTORY] create_app(): init estensioni, blueprint, logging, wiring app (no duplicazioni gunicorn/celery)

/tools/slack_client.py  → https://raw.githubusercontent.com/vitorizzo/ld-flask-app/main/tools/slack_client.py  
  - [SLACK][HTTP] Client Slack (token, WebClient init, helper)

/tools/slack_api.py     → https://raw.githubusercontent.com/vitorizzo/ld-flask-app/main/tools/slack_api.py  
  - [SLACK][API] API wrapper Slack (send_message, add_reaction, gestione errori mirata)

/tools/slack_processor.py → https://raw.githubusercontent.com/vitorizzo/ld-flask-app/main/tools/slack_processor.py  
  - [SLACK][LEGACY+V2] Normalizzazione eventi Slack + find actions + execute actions + hook V2 dispatcher

---

### Templates — Trello
/templates/base.html                    → https://raw.githubusercontent.com/vitorizzo/ld-flask-app/main/templates/base.html  
  - [UI][BASE] Layout base (navbar/footer/assets comuni)

/templates/trello_connections_list.html → https://raw.githubusercontent.com/vitorizzo/ld-flask-app/main/templates/trello_connections_list.html  
  - [UI][TRELLO] Lista connessioni Trello

/templates/trello_connections.html      → https://raw.githubusercontent.com/vitorizzo/ld-flask-app/main/templates/trello_connections.html  
  - [UI][TRELLO] Dettaglio/gestione connessione Trello

/templates/trello_actions.html          → https://raw.githubusercontent.com/vitorizzo/ld-flask-app/main/templates/trello_actions.html  
  - [UI][LEGACY] Pagina actions legacy (markup minimale; gran parte UI è in JS legacy)

---

### Static - service worker
/static/service_worker.js → https://raw.githubusercontent.com/vitorizzo/ld-flask-app/main/static/service-worker.js  
  - [PWA] Service worker (cache/strategia offline)

---

### Static JS — Trello
/static/js/editor.js          → https://raw.githubusercontent.com/vitorizzo/ld-flask-app/main/static/js/editor.js  
  - [UI][JS] Componenti/utility JS riusabili per editor (form dinamici, helper UI)

/static/js/trello_editor.js   → https://raw.githubusercontent.com/vitorizzo/ld-flask-app/main/static/js/trello_editor.js  
  - [UI][JS][TRELLO] Logica editor Trello (legacy/utility specifiche)

/static/js/trello_actions.js  → https://raw.githubusercontent.com/vitorizzo/ld-flask-app/main/static/js/trello_actions.js  
  - [UI][JS][LEGACY] UI legacy hardcoded per triggers/actions Trello + fields

---

### Static CSS — Trello
/static/css/trello.css        → https://raw.githubusercontent.com/vitorizzo/ld-flask-app/main/static/css/trello.css  
  - [UI][CSS] Stili pagine Trello (connections/actions/editor)

---

## Regole operative
- L’assistente può leggere SOLO i file presenti in questa mappa.  
- Per leggere file non presenti:  
  - deve richiederlo esplicitamente  
  - un solo step  
- La mappa vale sempre per l’ultimo commit del branch `main`.

## Convenzione tag (glossario rapido)
- [LEGACY] = sistema pre-automazioni cross-app
- [V2] = automazioni cross-app (Automation + actions ordinate)
- [CAPS] = capabilities backend per UI dinamica
- [API] = route Flask / endpoint
- [FACTORY] = create_app wiring
- [DB] = modelli/migrazioni/struttura dati
