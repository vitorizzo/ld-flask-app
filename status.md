# STATUS — LD-Flask-App

Data aggiornamento: 2026-02-06

## Focus corrente: Kiosk Ordini (Slack)

### ✅ Completato / stabile
- **Kiosk overview** operativo con caricamento board via:
  - `GET /kiosk/api/board/all`
  - `GET /kiosk/api/board/<route_id>`
- **Order status da DB**: tabella `order_statuses` (o `OrderStatus`) usata lato backend + Slack processor.
- **Slack reactions**: gestione reazioni aggiornata per leggere `slack_reaction`, `order_index`, `is_terminal` da DB (non più hardcoded).
- **Menu “…” sulle card**:
  - Popola correttamente *tutte* le voci di stato disponibili.
  - UI sistemata: background non trasparente, voci una per riga.
  - Problemi di stacking risolti (menu sopra le card, senza clipping dei parent).

### ⚠️ Note / Debiti tecnici accettati (per ora)
- `_compute_next_delivery_dt`:
  - `default_weekday=0` = consegna “tempestiva/ASAP” → **non deve dipendere da un orario fisso** (gestione orario per weekday schedulati ok).
  - Frequenze (bisettimanale/mensile) **non ancora supportate**.

## Prossimi step (ordine)
1. **Drag&Drop** sulle card per cambio stato (con validazioni + update UI immediata).
2. **Regole cambio stato**:
   - Consentire passaggi a qualunque stato (avanti/indietro) dove previsto (UI + backend).
3. **Gestione consegne scadute (successivo)**:
   - Alert se `planned_delivery_at` passata e status non terminale.
   - Azioni: conferma consegna (set `closed_at`) oppure ripianifica al prossimo giro.

## File/aree principali coinvolte
- Backend:
  - `/routes/kiosk.py`
  - `/tools/slack_processor.py`
  - `/models.py` (DeliveryRoute, SlackOrder, SlackOrderEvent, OrderStatus)
- Frontend:
  - `/templates/kiosk_overview.html`
  - `/static/js/kiosk_overview.js`
  - CSS kiosk (regole .order-actions / menu / z-index)
