Data aggiornamento: 2026-02-07

STATUS — LD-Flask-App
Focus corrente: Kiosk Ordini (Slack)
✅ Completato / stabile

Kiosk overview operativo con caricamento board via:

GET /kiosk/api/board/all

GET /kiosk/api/board/<route_id>

Order status da DB: tabella order_statuses (o OrderStatus) usata lato backend + Slack processor.

Slack reactions: gestione reazioni aggiornata per leggere slack_reaction, order_index, is_terminal da DB (non più hardcoded).

Cambio stato da UI con sync Slack:

menu “…” sulle card → cambio stato

downgrade: rimozione reaction dello stato attuale su Slack (es. :cactus: quando si torna indietro)

jump avanti: aggiunge solo la reaction target (non inferenze sugli stati intermedi)

Frecce / hot-zone laterali per cambio stato di 1 step:

aree cliccabili su fianco sinistro/destro della card

gradiente + freccia in hover su qualunque punto del fianco

Colore card per giro (pastello):

applicato via background multilayer con var(--route-bg)

corretto il valore di alpha (prima troppo alto: effetto “bianco” percettivo)

⚠️ Note / Debiti tecnici accettati (per ora)

Stile Kiosk “ibrido” (CSS iniettato + CSS file):

attualmente alcune regole sono state iterate rapidamente; pulizia/normalizzazione rimandata dopo test sul campo.

_compute_next_delivery_dt:

default_weekday=0 = consegna “tempestiva/ASAP” → non deve dipendere da orario fisso (weekday schedulati ok).

frequenze (bisettimanale/mensile) non ancora supportate.

Nuovo focus: Iscrizione / Password dimenticata
🎯 Obiettivo immediato

Riprendere e completare la funzionalità “password dimenticata / reset password” lasciata in sospeso.

Prossimi step (ordine)

Definire flusso completo reset password (token, scadenza, invalidazione, UX).

Implementare endpoint + email reset + pagina impostazione nuova password.

Hardening sicurezza (rate limit, token monouso, logging, messaggi non enumeranti utenti).

Test end-to-end (utente esistente, email errata, token scaduto, doppio uso token).

File/aree principali coinvolte
Kiosk

Backend:

/routes/kiosk.py

/tools/slack_processor.py

/tools/slack_api.py

/models.py (DeliveryRoute, SlackOrder, SlackOrderEvent, OrderStatus)

Frontend:

/templates/kiosk_overview.html

/static/js/kiosk_overview.js

/static/css/kiosk_overview.css

Reset password (da riprendere)

Backend:

/routes/auth.py (o blueprint auth corrente)

eventuali nuovi model/token (se previsto)

/tools/... (email / token utils se già presenti)

Frontend:

template/reset password (da verificare o creare)

eventuale JS minimo (se necessario)