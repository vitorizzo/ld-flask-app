# STATUS.md — v1.4
Data aggiornamento: 2026-03-18

---

## 🔄 Stato generale progetto

Applicazione stabile in produzione.  
Gunicorn + Nginx funzionanti.  
Migrazioni database allineate.  
Nessun errore bloccante in avvio applicazione.

---

## 🧾 Modulo Cassa / Agenda — Stato attuale

### ✅ Completato backend

- Implementate tabelle:
  - `cash_deposits`
  - `cash_deposit_checks`
- Collegamento versamenti ↔ assegni tramite tabella ponte.
- Campo `deposit_type`:
  - `versamento_incasso`
  - `versamento_intermedio`

- Endpoint attivi:
  - `/cassa/api/checks/due`
  - `/cassa/api/day/<date>/preview`
  - `/cassa/api/day/<day_date>/sales`
  - `/cassa/api/day/<day_date>/expenses`
  - `/cassa/api/day/<day_date>/cash_moves`
  - `/cassa/api/day/<day_date>/pos_moves`
  - `/cassa/api/coins/balance`
  - `/cassa/api/customers/suggest`
  - `/cassa/api/customers`
  - `/cassa/api/banks`
  - `/cassa/api/pos/devices`
  - `/cassa/api/pos/devices/<device_id>/circuits`

- Logica cutoff bancabile:
  - `next_banking_day(ref_date)`
  - `due_date <= cutoff_bancabile`

- KPI calcolati lato backend con:
  - Q (versabile giornata)
  - S (progressivo)
  - IC
  - delta fondo
  - delta quadratura
  - versamenti intermedi e totali

---

## 🆕 Gestione fondo cassa serale

### ✅ Backend

- Implementate nuove tabelle:
  - `cash_drawer_counts`
  - `cash_drawer_count_lines`

- Endpoint:
  - `GET /cassa/api/day/<day_date>/drawer-count`
  - `POST /cassa/api/day/<day_date>/drawer-count`
  - `DELETE /cassa/api/day/<day_date>/drawer-count`

### ✅ Logica

- Un solo conteggio per giornata (vincolo DB)
- Il salvataggio aggiorna il conteggio esistente
- Possibilità di eliminazione completa del conteggio
- Totale fondo calcolato da righe per taglio

### ✅ Tagli gestiti

- 0.10
- 0.20
- 0.50
- 1.00
- 2.00
- 5.00
- 10.00
- 20.00
- 50.00
- 100.00

---

## 🧠 Logica fondo cassa stabilizzata

### Fondo cassa finale

Derivato da:

- `CashClosure.closing_cash_drawer`
- `CashDrawerCount` (somma righe)

👉 Se entrambe presenti:
- vince il valore più recente (timestamp)

---

### Fondo cassa iniziale

Regola attuale:

- il fondo iniziale = ultimo saldo finale valido nei giorni precedenti
- non dipende solo dal giorno precedente
- continua a cercare indietro se necessario
- funziona anche con giorni senza attività

---

## 🧩 Agenda / Cassa — UI operativa raggiunta

### ✅ Completato frontend

- `agenda.html`, `agenda.css`, `agenda.js` consolidati
- Uniformata la grafica delle modali
- Sistemato stacking modali
- Implementata modale operazione `opModal`
- Implementata modale fondo cassa

---

### ✅ KPI Fondo Cassa

- KPI completamente interattivo
- Click su tutta la card
- Apertura modale conteggio
- Eliminazione conteggio disponibile
- Feedback UX:
  - hover
  - bordo attivo
  - icona
  - tooltip
  - cursor pointer

---

### ✅ Cliente

- Ricerca progressiva cliente via datalist
- Ricerca avanzata in modale
- Creazione cliente
- Tabelle:
  - `CashCustomer`
  - `CashCustomerAlias`

---

### ✅ Carrier pagamento lato UI

Carrier attualmente gestiti:

- `cash`
- `pos`
- `bank`
- `check`
- `multi`

---

### ✅ Modalità multipla (COMPLETATA)

Supporto per:

- più assegni
- più POS
- combinazioni miste
- contanti + POS + assegni + banca

---

### ✅ Logica attiva

- payload unificato `payments[]`
- validazioni per carrier
- salvataggio reale backend
- `opAmount` auto-calcolato in modalità multipla
- conferma cambio modalità (multipli → singolo)
- blocco save se incoerente

---

### ✅ POS

- selezione dispositivo
- selezione circuito
- importo
- caricamento dinamico
- default device

---

### ✅ Banca

- tabella `CashBank`
- endpoint `/cassa/api/banks`
- selezione banca
- gestione default

---

### ✅ Assegno

- UI completa:
  - banca descrittiva
  - ABI
  - CAB
  - numero
  - scadenza
  - importo
- integrazione con:
  - `CashCheck`
  - `CashSaleCheck`
- cliente obbligatorio correttamente gestito

---

### ✅ Correzioni stabilizzate

- backend sales/expenses non più placeholder
- gestione completa multi-carrier
- fix selezione cliente
- fix aggiornamento automatico opAmount
- reset coerente campi carrier
- UX stabile e consistente

---

## 🧠 Logica Q / S formalizzata

Q = incassi_cash_odierni + assegni_versabili_odierni  

S = S_precedente  
    - totale_versato_oggi  
    + Q_odierno  
    + assegni_postdatati_odierni  

Totale titolare = contenuto reale cassetto fine giornata

Distinzione:

- `incasso_consegnato`
- `totale_versato_oggi`

---

### ✅ Progressivo versabile corretto

- non riparte più da 0
- `iniziale` = storico precedente
- `attuale` = iniziale + movimenti del giorno

---

## 🚧 Prossimo Step Operativo

### 🎯 KPI Movimenti

Ridefinizione del riquadro:

- `movimenti` → **vendite online**
- `versamenti`:
  - versamento incasso
  - versamento intermedio

👉 Logica e struttura verranno definite nella prossima chat

---

## ⚠️ Nota architetturale

Due fonti per fondo cassa:

- `CashClosure`
- `CashDrawerCount`

Regola:

👉 vince il valore più recente

Questa logica è già attiva e deve restare coerente nel sistema.

---

## ⚠️ Nota Migrazioni

Risolto:

- constraint `pos_device_circuits`

Nuove strutture:

- `CashCustomer`
- `CashCustomerAlias`
- `CashBank`
- `CashDrawerCount`
- `CashDrawerCountLine`

Schema attuale stabile.