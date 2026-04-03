# STATUS.md — v1.4
Data aggiornamento: 2026-04-03

---

## 🔄 Stato generale progetto

Applicazione stabile in produzione.  
Gunicorn + Nginx funzionanti.  
Migrazioni database allineate.  
Nessun errore bloccante in avvio applicazione.

---

## 🧾 Modulo Cassa / Agenda — Stato attuale

### ✅ Backend

- KPI completamente funzionanti:
  - Versabile
  - Fondo cassa
  - Quadratura
  - Ecommerce
  - Versamenti
  - Corrispettivi

- Endpoint attivi e funzionanti:
  - `/cassa/api/day`
  - `/cassa/api/day/<date>/preview`
  - `/cassa/api/day/<day_date>/sales`
  - `/cassa/api/day/<day_date>/expenses`
  - `/cassa/api/day/<day_date>/cash_moves`
  - `/cassa/api/day/<day_date>/pos_moves`
  - `/cassa/api/day/<day_date>/deposits`
  - `/cassa/api/day/<day_date>/receipt-closures`
  - `/cassa/api/checks/due`
  - `/cassa/api/coins/balance`

- Gestione:
  - Incassi (multi-pagamento, assegni, POS, banca, contanti)
  - Spese
  - Movimenti di cassa
  - Movimenti POS
  - Versamenti (con assegni collegati)
  - Prelievi titolare (owner takes)
  - Corrispettivi
  - Conteggio fondo cassa

---

### ✅ Frontend (Agenda)

- Layout completo a quadranti:
  - Incassi
  - Spese
  - Movimenti di cassa
  - POS

- UI stabilizzata:
  - Tabelle uniformate stile “table-row”
  - Badge coerenti (POS, banca, assegni, fuori cassa)
  - KPI visivamente coerenti
  - Modali funzionanti (stack gestito correttamente)

- Calendario:
  - Evidenzia giorni con movimenti
  - Caricamento dinamico giornata

---

### ✅ Quadrante POS — COMPLETATO (baseline)

- Lista POS funzionante
- Checkbox per riga (con stato persistente backend)
- Toggle stato riga (`row-check`)
- Menu contestuale:
  - Apertura da bottone riga
  - Apertura da click destro
- Azioni disponibili:
  - Eliminazione funzionante (`DELETE pos_move`)
- Struttura pronta per:
  - Modifica
  - Filtri (device / circuito)

➡️ Il quadrante POS è il riferimento architetturale per gli altri quadranti.

---

## ⚠️ Stato attuale sviluppo

È stata completata la **prima verticalizzazione completa (POS)**:

- UI
- Interazioni
- Context menu
- Backend integrazione

Gli altri quadranti (**Incassi, Spese, Movimenti di cassa**)  
NON sono ancora allineati a questo standard.

---

## 🎯 Prossimo step (nuova chat)

Estendere il modello POS agli altri 3 quadranti:

### Obiettivo

Uniformare:

- comportamento UI
- menu contestuale
- gestione checkbox
- azioni CRUD

### Quadranti da aggiornare

1. Movimenti di cassa
2. Incassi
3. Spese

---

## 📌 Task previsti

Per ogni quadrante:

- [ ] Checkbox riga (come POS)
- [ ] Stato riga persistente (backend row-check)
- [ ] Menu contestuale riga + pannello
- [ ] Azioni:
  - [ ] Inserisci
  - [ ] Modifica
  - [ ] Elimina
- [ ] Pulsante "+" nel titolo quadrante
- [ ] Coerenza UI con POS

---

## 🧠 Note tecniche

- Il sistema context menu è già centralizzato (`contextMenu`)
- Il pattern `data-entity-type` + `data-entity-id` è già definito
- Il sistema `row-check` è già riutilizzabile
- Le modali esistono già → riuso, non reinventare

---

## 🚫 Vincoli operativi

- NON rompere il funzionamento attuale dei quadranti
- NON fare refactor massivi
- Procedere **un quadrante alla volta**
- Validare ogni step prima di passare al successivo

---

## 📌 Stato generale

Sistema stabile  
Architettura definita  
Primo quadrante completato (POS)  
Pronto per estensione controllata agli altri moduli