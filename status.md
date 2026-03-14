# STATUS.md — v1.3
Data aggiornamento: 2026-03-14

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

## 🧩 Agenda / Cassa — UI operativa raggiunta

### ✅ Completato frontend

- `agenda.html`, `agenda.css`, `agenda.js` consolidati e resi coerenti.
- Uniformata la grafica delle modali agenda/cassa.
- Sistemato stacking visivo delle modali sovrapposte.
- Implementata modale operazione `opModal`.

### ✅ Cliente

- Ricerca progressiva cliente via datalist.
- Ricerca avanzata cliente in modale dedicata.
- Creazione nuovo cliente in modale dedicata.
- Aggiunte anagrafiche:
  - `CashCustomer`
  - `CashCustomerAlias`

### ✅ Carrier pagamento lato UI

Carrier attualmente gestiti nella modale operazione:

- `cash`
- `pos`
- `bank`
- `check`

Logica attiva:

- quadratura carrier su `opAmount`
- ricalcolo automatico
- pulsanti `TOT`
- blocco salvataggio se i carrier non quadrano
- pulsante di fix per aggiornare il totale operazione dai carrier

### ✅ POS

- UI con:
  - dispositivo POS
  - circuito
  - importo
- caricamento dinamico dispositivi e circuiti
- supporto device default

### ✅ Banca

- Aggiunta tabella `CashBank`
- endpoint `/cassa/api/banks`
- UI con select banca + importo
- gestione default banca

### ✅ Assegno

- UI con:
  - banca assegno
  - ABI
  - CAB
  - numero assegno
  - scadenza
  - importo
- reset completo campi assegno quando deselezionato
- reset corretto quando si usa `TOT` su altro carrier

### ✅ Correzioni stabilizzate

- `cash` ora è trattato come carrier normale, non sempre attivo.
- `TOT` su un carrier:
  - seleziona solo quel carrier
  - deseleziona gli altri
  - azzera e resetta i campi non pertinenti
- `save` disabilitato in caso di mancata quadratura
- bottone “Aggiorna totale” reso visibile e funzionante

---

## 🧠 Logica Q / S formalizzata

Esempi validati manualmente:

Q = incassi_cash_odierni + assegni_versabili_odierni

S = S_precedente
    - totale_versato_oggi
    + Q_odierno
    + assegni_postdatati_odierni

Totale titolare = contenuto reale cassetto fine giornata.

Distinzione chiara tra:
- incasso_consegnato
- totale_versato_oggi

---

## 🚧 Prossimo Step Operativo

### Priorità immediata

Completare il salvataggio reale della modale operazione con carrier multipli nel backend.

Ordine previsto:

1. Adeguare il payload frontend a `payments[]`
2. Adeguare:
   - `POST /cassa/api/day/<day_date>/sales`
   - `POST /cassa/api/day/<day_date>/expenses`
3. Salvare correttamente:
   - `cash`
   - `pos` con `pos_device_id` e `pos_circuit_id`
   - `bank` con `bank_id`
   - `check` con creazione e collegamento di `CashCheck`
4. Validazioni frontend prima del save:
   - POS richiede device + circuito
   - Banca richiede banca selezionata
   - Assegno richiede cliente + banca/ABI/CAB/numero/scadenza/importo
5. Collegare `opSaveBtn`
6. Al successo:
   - chiudere modale
   - ricaricare KPI e quadranti

### Step successivo, ma NON ancora da iniziare

- introdurre righe multiple per carrier tramite pulsante `+`
- supportare:
  - più righe banca
  - più assegni
  - più righe POS
  - più righe contanti se necessario

Questo refactor va fatto **solo dopo** avere stabile il salvataggio della versione corrente a riga singola per carrier.

---

## ⚠️ Nota Migrazioni

Risolto in precedenza problema constraint duplicato:
- `pos_device_circuits`
- PK coerente con modello

Nuove strutture introdotte nel modulo cassa:
- `CashCustomer`
- `CashCustomerAlias`
- `CashBank`
- campo default sul device POS

Schema attuale stabile.