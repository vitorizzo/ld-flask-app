# STATUS.md

## Scopo

Questo file descrive **lo stato attuale del progetto LD-Flask-App**.

Contiene:
- obiettivi completati
- obiettivi in corso
- prossimi obiettivi (backlog)
- task attivi con stato e note

NON contiene:
- regole operative (→ `new_chat.md`)
- mappa dei file (→ `project_map.md`)

È la **fonte di verità sul “dove siamo”** nel progetto.

---

## Stato generale del progetto

- Progetto: **LD-Flask-App**
- Stack principale:
  - Backend: Python / Flask (app factory)
  - Database: PostgreSQL + SQLAlchemy + Alembic
  - Task async: Celery + Redis
  - Integrazioni: Trello, Slack, TeamSystem, PrestaShop (parziale)
- Stato: **attivo – sviluppo continuo**
- Branch di riferimento: **main**

---

## Obiettivi completati ✅

### Automations V2 – Backend
- Sistema **automazioni cross-platform** (Trello ↔ Slack)
- Dispatcher centralizzato (`automations_dispatcher`)
- Executor separati per app (Slack / Trello)
- Trigger normalizzati
- Actions sequenziali con ordine (`order_index`)
- Logging esteso e tracciabile

### Trello
- Webhook funzionanti
- Trigger:
  - `moveCard`
  - `createCard`
  - `updateCard`
- Actions:
  - `addComment`
  - `createCard`
  - `mirrorCard`
- Gestione corretta dei template Jinja

### Slack
- Ricezione eventi via **Slack Events API**
- Trigger:
  - `message`
  - `reaction_added`
- Actions:
  - `addReaction`
  - `sendMessage`
- Gestione dedup eventi
- Gestione errori Slack API (`already_reacted`)
- Persistenza eventi (`SlackEvent`) con dedup

### Automations V2 – UI (NUOVA) ✅
- UI **completamente nuova**, indipendente dalla UI legacy Trello
- Gestione completa:
  - lista automazioni
  - creazione automazione
  - modifica automazione
  - eliminazione automazione
- Trigger multi-app con:
  - selezione app
  - selezione connessione
  - selezione trigger
- **Trigger Slack / message – Config avanzata**:
  - selezione canali Slack con dialog e checkbox
  - badge canali privati 🔒
  - keyword con input + chips
  - visibility con selezione multipla (`any`, `public`, `private`, `dm`, `group_dm`)
  - struttura `trigger_config` normalizzata:
    ```json
    {
      "channels": [],
      "keywords": [],
      "visibility": ["any"]
    }
    ```
- Salvataggio corretto:
  - POST per creazione
  - PUT per aggiornamento
  - DELETE per eliminazione
- Refresh automatico lista automazioni
- Reset editor dopo salvataggio per evitare ambiguità di stato

### Stabilità sistema
- Avvio Gunicorn stabile
- Redis operativo
- Logging coerente su tutti i moduli
- Eliminati comportamenti ambigui di cache lato UI

---

## Obiettivi in corso 🚧

### Slack – Canali
- Endpoint **NON ancora presente** per:
  - lista canali Slack per connection
- Attualmente:
  - UI pronta
  - JS con fallback gestito
- Prossimo step: endpoint `/api/connections/slack/<id>/channels`

Stato: **da implementare**

---

## Prossimi obiettivi 📌 (backlog strategico)

- Implementazione **“Password dimenticata”**
  - richiesta reset
  - invio email
  - token temporaneo
  - definizione nuova password

- Integrazione con **Poleepo**
  - ricezione ordini dagli shop
  - normalizzazione dati
  - inserimento nel flusso gestionale

- **Kanban gestione consegne**
  - stile “McDonald’s order board”
  - stato ordine visuale
  - avanzamento step-by-step

- Sistemazione **UI gestione menù dinamici**
  - miglior UX
  - manutenzione semplificata

- Integrazione con **siti corrieri**
  - tracking spedizioni
  - aggiornamento stato consegna

- Miglioramento integrazione **server di posta**
  - invio email affidabile
  - analisi email ricevute
  - base per automazioni future

---

## Task attivi 🔧

### Task: Automations V2 – Slack Channels API
- Stato: **da iniziare**
- UI: **pronta**
- Backend: **da implementare**
- Note:
  - endpoint REST per canali Slack
  - supporto a public / private / DM / group DM
  - riuso SlackConnection + bot_token

---

## Convenzioni operative

- Quando l’utente scrive:
  > **“aggiorna situazione”**

  ChatGPT deve:
  - aggiornare questo file (`status.md`)
  - aggiornare `project_map.md` se necessario
  - NON modificare `new_chat.md` salvo richiesta esplicita

---

## Versione

- Versione: **1.1**
- Stato: aggiornata
- Ultimo aggiornamento: **2026-01-28**
