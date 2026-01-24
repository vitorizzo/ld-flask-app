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
- Dispatcher centralizzato (`automation_dispatcher`)
- Executor separati per app (Slack / Trello)
- Trigger normalizzati
- Actions sequenziali con ordine (`order_index`)
- Logging esteso e tracciabile

### Trello
- Webhook funzionanti
- Trigger `moveCard`
- Actions:
  - `addComment`
  - `createCard`
- Gestione corretta dei template Jinja

### Slack
- Ricezione eventi via Events API
- Trigger:
  - `message.channels`
  - `reaction_added`
- Actions:
  - `addReaction`
  - `sendMessage`
- Gestione dedup eventi
- Gestione errori Slack API (`already_reacted`)

### Stabilità sistema
- Risolti import circolari
- Avvio Gunicorn stabile
- Logging coerente su tutti i moduli
- Sistema pronto per estensione UI

---

## Obiettivi in corso 🚧

### Automations V2 – UI (NUOVA)

**Obiettivo principale attuale**

- Creazione **UI ex-novo** per Automations V2
- Nessuna dipendenza dalla UI legacy Trello
- Gestione:
  - automazioni
  - trigger (multi-app)
  - actions (multi-app)
  - ordine di esecuzione
- UI destinata a **sostituire completamente** le interfacce legacy

Stato: **da iniziare (backend pronto)**

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

### Task: UI Automations V2
- Stato: **non iniziato**
- Backend: **completato**
- Note:
  - UI legacy Trello **da dismettere**
  - progettazione UI completamente nuova
  - forte attenzione a chiarezza e scalabilità

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

- Versione: **1.0**
- Stato: stabile
- Ultimo aggiornamento: manuale
