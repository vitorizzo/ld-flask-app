Data aggiornamento: 2026-02-08

STATUS — LD-Flask-App

Focus corrente: Kiosk Ordini (Slack)
✅ Completato / stabile

Kiosk overview operativo con caricamento board via:
- GET /kiosk/api/board/all
- GET /kiosk/api/board/<route_id>

Order status da DB: tabella order_statuses (o OrderStatus) usata lato backend + Slack processor.

Slack reactions: gestione reazioni aggiornata per leggere slack_reaction, order_index, is_terminal da DB (non più hardcoded).

Cambio stato da UI con sync Slack:
- menu “…” sulle card → cambio stato
- downgrade: rimozione reaction dello stato attuale su Slack (es. :cactus: quando si torna indietro)
- jump avanti: aggiunge solo la reaction target (non inferenze sugli stati intermedi)

Frecce / hot-zone laterali per cambio stato di 1 step:
- aree cliccabili su fianco sinistro/destro della card
- gradiente + freccia in hover su qualunque punto del fianco

Colore card per giro (pastello):
- applicato via background multilayer con var(--route-bg)
- corretto il valore di alpha (prima troppo alto: effetto “bianco” percettivo)

⚠️ Note / Debiti tecnici accettati (per ora)
Stile Kiosk “ibrido” (CSS iniettato + CSS file):
- alcune regole iterate rapidamente; pulizia/normalizzazione rimandata dopo test sul campo.

_compute_next_delivery_dt:
- default_weekday=0 = consegna “tempestiva/ASAP” → non deve dipendere da orario fisso (weekday schedulati ok).
- frequenze (bisettimanale/mensile) non ancora supportate.

----------------------------------------------------------------

Focus completato: Reset password (“Ho dimenticato la password”)
✅ Completato / stabile

Flusso implementato:
- Pagina richiesta reset (forgot password) con risposta neutra (anti user-enumeration).
- Generazione token raw + hash in DB, scadenza, IP e user-agent.
- Invio email con link assoluto a /auth/reset/<token>.
- Pagina reset con form nuova password + conferma.
- Token monouso: dopo reset viene marcato used_at e non riutilizzabile.
- Link riusato / scaduto → errore gestito.

Hardening aggiunto:
- Cooldown 60s: per utente esistente non vengono generati nuovi token né inviata una seconda email entro 60 secondi.
- Comando CLI: `flask cleanup-reset-tokens --retention-days 30` per pulizia token usati/scaduti oltre retention.
  Nota operativa: eseguire comandi flask con virtualenv attivo (venv).

File/aree principali coinvolte
Backend:
- /routes/auth.py
- /models.py (PasswordResetToken)
- /tools/app_factory.py (registrazione comando CLI cleanup-reset-tokens)
- /extensions.py (Mail)

Frontend:
- /templates/forgot_password.html
- /templates/reset_password.html
- /templates/login.html (link corretto a forgot_password)

----------------------------------------------------------------

Nuovo focus: Dashboard gestione menù
🎯 Obiettivo immediato

Completare la sezione UI/CRUD per creare e modificare i menù da interfaccia
(attualmente gestione parziale: inserimenti manuali nel DB).

Prossimi step (ordine)
- Allineare modello dati menù (tabelle/relazioni) con UI e permessi/ruoli.
- Completare CRUD + ordinamento voci.
- Validazioni e test end-to-end (creazione menù, visibilità per ruolo/utente, rendering navbar).
