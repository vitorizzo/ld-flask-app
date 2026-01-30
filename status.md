STATUS.md — v1.2 (aggiornato)
Stato generale del progetto

Progetto: LD-Flask-App

Stato: attivo – sviluppo continuo

Branch di riferimento: main

Timezone di riferimento: Europe/Rome

Obiettivi completati ✅

(immutato rispetto a v1.1)

Automations V2 – Backend (cross-platform, dispatcher, executors, trigger normalizzati)

Trello (webhook + trigger/actions principali)

Slack (Events API + trigger/actions + dedup + gestione errori)

Automations V2 – UI (nuova UI completa + trigger Slack message con config avanzata)

Stabilità sistema (Gunicorn/Redis/logging coerenti)

Obiettivi in corso 🚧
1) Slack – Channels API

Endpoint NON ancora presente:

/api/connections/slack/<id>/channels

UI pronta, JS con fallback.

Stato: da implementare

2) Workflow “Ordini da Slack” + Kiosk Board (progettazione chiusa, implementazione da avviare)

Obiettivo

Trasformare messaggi Slack nei canali “giro consegne” in entità Ordine con stato e tracciamento operativo.

Visualizzare gli ordini su endpoint kiosk (display magazzino) con pipeline grafica degli stati.

Strategia (definita)

Fonte: messaggi Slack nei canali (area = canale).

Ordine creato anche se il messaggio contiene solo il cliente (segnalazione ordine trasmesso in ufficio).

Dettaglio ordine non parsato: si salva come raw_text multilinea.

Replies nel thread = note operative/anomalie.

Reactions = eventi di avanzamento stato (solo upgrade, mai retrocessione).

Mappatura reaction → stato

✅ :white_check_mark: → listato (ufficio ha emesso lista di carico)

🌵 :cactus: → controllato

💯 :100: → evaso (chiusura)

Regole di aggregazione cliente

customer_key normalizzato (lower/strip/punteggiatura/spazi), con rimozione suffissi finali: numeri, bis, tris, ter, ordinale.

Un ordine per (channel, customer_key, giorno) finché non è evaso.

Caso post-evasione: nuovo messaggio cliente = nuovo ordine (scelta A).

Kiosk

Visualizzazione per area/canale, raggruppata per stato.

Badge “note/issue” se presenti replies/keyword issue.

Stato: pronto per implementazione (da innestare in tools/slack_processor.py)

Prossimi obiettivi 📌 (backlog strategico)

(immutato + aggiunta)

Password dimenticata

Integrazione Poleepo

Kanban gestione consegne stile McDonald’s

Sistemazione UI menù dinamici

Integrazione tracking corrieri

Miglioramento integrazione server di posta

Nuovo (derivato dal lavoro sugli ordini)

Calendario Giri Consegne (route/canali con giorno prefissato + eccezioni)

giorni prefissati per canale (es. marsica mercoledì mattina, aquila venerdì mattina, ecc.)

override permanenti o contingenti (festività, consegna extra, spostamento)

vista “giro X questa settimana” con elenco ordini + stati

Stato: da progettare ora (schema) / implementare dopo (UI e logica completa)

Task attivi 🔧
Task: Automations V2 – Slack Channels API

Stato: da iniziare

UI: pronta

Backend: da implementare

Task: Ordini da Slack → Entità + Stati + Kiosk

Stato: da iniziare

Backend:

nuove tabelle orders (+ consigliata order_events)

ingest in tools/slack_processor.py

gestione reactions e replies

Frontend:

endpoint kiosk per visualizzazione pipeline ordini

Task: Calendario giri consegne

Stato: in progettazione

Strategia (minimo da predisporre subito):

tabella route (mappatura canale→giro + weekday/time default)

tabella override (shift/extra/cancel)

campo su orders.planned_delivery_at calcolato (default + override)

Versione

Versione: 1.2

Stato: aggiornata

Ultimo aggiornamento: 2026-01-30