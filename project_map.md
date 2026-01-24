# PROJECT_MAP.md — v2.0

## Repository source of truth

Repo: https://github.com/vitorizzo/ld-flask-app  
Branch: main

LINK_BASE_RAW:
https://raw.githubusercontent.com/vitorizzo/ld-flask-app/main

Regola link:
- `/percorso/file.ext` → `LINK_BASE_RAW + /percorso/file.ext`

---

## Architettura (panoramica)

- Web app: Flask (backend Python)
- DB: PostgreSQL
- ORM: SQLAlchemy
- Migrazioni: Alembic (directory `/migrations`)
- Frontend: Jinja templates in `/templates`
- Static assets:
  - JS: `/static/js`
  - CSS: `/static/css`
  - Immagini: `/static/images` (incl. `/static/images/products`)
- Logging: directory `/logs`
- Strumenti backend riusabili: package `/tools`
- Route/Blueprint: directory `/routes`
- Form: directory `/forms`

---

## Struttura cartelle (macro)

- `/app.py` — entrypoint Flask
- `/extensions.py` — init estensioni (SQLAlchemy, Mail, ecc.)
- `/models.py` — modelli DB
- `/routes/` — blueprint e route
- `/tools/` — API wrapper, processor, dispatcher, executors, utils
- `/templates/` — pagine HTML Jinja + partials
- `/static/` — js/css/images/icons/uploads
- `/migrations/` — Alembic env + versions
- `/docs/` — deploy/operations/readme docs progetto

---

## File principali (core)

- `/app.py` — entrypoint e create_app / bootstrap app (se presente)
- `/extensions.py` — inizializzazione estensioni Flask
- `/models.py` — SQLAlchemy models (incl. automations V2)
- `/requirements.txt` — dipendenze
- `/README.md` — overview
- `/new_chat.md` — regole operative (bootstrap chat)
- `/project_map.md` — questa mappa
- `/status.md` — stato progetto (obiettivi/task)

---

## Backend: routes (Blueprint)

- `/routes/__init__.py` — init blueprint package
- `/routes/auth.py` — login/registrazione/utente
- `/routes/trello.py` — integrazione Trello (webhook, editor legacy, ecc.)
- `/routes/slack.py` — Slack Events API + gestione connessioni/azioni
- `/routes/automations_v2.py` — UI/API automazioni cross-app (V2)
- `/routes/inventario.py` — gestione inventario
- `/routes/search.py` — ricerca articoli (barcode/descrizione, JSON)
- `/routes/articoli.py` — pagine articoli/schede
- `/routes/settings.py` — impostazioni (menu, ecc.)
- `/routes/task_routes.py` — status/kill task Celery
- `/routes/logs_display.py` — viewer log da webapp
- `/routes/importazioni_routes.py` — importazioni & storico
- `/routes/esportazioni_teamsystem.py` — export verso TeamSystem
- `/routes/status_routes.py` — eventuale pagina stato

---

## Backend: tools (motore automazioni e integrazioni)

- `/tools/processor.py` — normalizzazione eventi + dispatch trigger (Trello/Slack)
- `/tools/automation_dispatcher.py` — match automazioni + invocazione executors (V2)
- `/tools/executors/base.py` — base executor
- `/tools/executors/trello_executor.py` — azioni Trello (createCard, addComment, ecc.)
- `/tools/executors/slack_executor.py` — azioni Slack (sendMessage, addReaction, ecc.)
- `/tools/trello_api.py` — wrapper API Trello (metodi operativi)
- `/tools/slack_api.py` — wrapper API Slack (metodi operativi)
- `/tools/slack_processor.py` — parse Slack events + context per automazioni
- `/tools/trello_client.py` — client/low-level Trello (se presente)
- `/tools/slack_client.py` — client/low-level Slack (se presente)
- `/tools/log_utils.py` — factory logger
- `/tools/db_utils.py` — util DB
- `/tools/redis_utils.py` — util Redis
- `/tools/task_monitor.py` — monitor task Celery
- `/tools/auth_manager.py` — helper auth (se presente)
- `/tools/esportazioni.py` — logiche export
- `/tools/importazioni.py` — logiche import

---

## Frontend: templates (pagine)

- `/templates/base.html` — layout base + navbar + inclusioni globali
- `/templates/partials/navbar.html` — navbar
- `/templates/automations_v2.html` — UI Automations V2 (da costruire/aggiornare)
- `/templates/trello_actions.html` — UI legacy Trello actions (esistente)
- `/templates/trello_connections.html` — UI connessioni Trello
- `/templates/inventario.html` — UI inventario
- `/templates/articoli_codebar.html` — UI barcode
- `/templates/articoli_description.html` — UI ricerca descrizione
- `/templates/scheda_articolo.html` — UI scheda articolo
- `/templates/logs_display.html` — UI viewer log
- `/templates/storico_importazioni.html` — UI importazioni
- `/templates/settings/menus.html` — UI gestione menu
- `/templates/settings/import_conflicts.html` — UI gestione conflitti import

---

## Frontend: static JS/CSS (principali)

JS:
- `/static/js/trello_actions.js` — legacy trello actions editor
- `/static/js/editor.js` — editor json/azioni (se usato)
- `/static/js/scanner.js` — scanner barcode
- `/static/js/inventario.js` — logica inventario
- `/static/js/menu.js` — menu dinamico
- `/static/js/menu_management.js` — gestione menu
- `/static/js/logs_display.js` — viewer log
- `/static/js/task_status.js` — monitor task
- `/static/js/import_conflicts.js` — UI conflitti import
- `/static/js/base.js` — common client logic

CSS:
- `/static/css/style.css` — stile generale
- `/static/css/editor.css` — editor
- `/static/css/inventario.css` — inventario
- `/static/css/task_status.css` — task monitor
- `/static/css/logs_display.css` — viewer log
- `/static/css/install_banner.css` — PWA banner
- `/static/css/app_installation.css` — PWA install page

---

## Migrazioni DB (Alembic)

- `/migrations/env.py` — configurazione Alembic
- `/migrations/versions/` — scripts migrazione (molti)

---

## Note

- Evitare di mappare singolarmente `/static/images/products/*` (troppi file). Tenerli come directory.
