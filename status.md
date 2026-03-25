# STATUS.md — v1.4
Data aggiornamento: 2026-03-25

---

## 🔄 Stato generale progetto

Applicazione stabile in produzione.  
Gunicorn + Nginx funzionanti.  
Migrazioni database allineate.  
Nessun errore bloccante in avvio applicazione.

---

## 🧾 Modulo Cassa / Agenda — Stato attuale

### ✅ Backend attivo

Sono attivi e funzionanti gli endpoint principali per:

- gestione giornata (`/cassa/api/day`)
- preview KPI (`/cassa/api/day/<date>/preview`)
- incassi
- spese
- movimenti di cassa
- movimenti POS
- assegni versabili
- banche
- dispositivi POS / circuiti
- conteggio fondo cassa (`drawer-count`)
- e-commerce
- versamenti bancari
- corrispettivi
- prelievi titolare / cassetto

---

## ✅ Funzionalità completate lato Agenda / Cassa

### 1. KPI principali collegati al backend

Attualmente vengono valorizzati correttamente:

- Versabile iniziale / attuale / odierno
- Fondo cassa iniziale / finale / delta fondo
- Totale giornata
- Totale e-commerce
- Totale versamenti
- Corrispettivi
- Cassetto
- Delta quadratura

---

### 2. Corrispettivi

Completata la gestione dei corrispettivi con:

- inserimento
- modifica
- eliminazione
- formattazione importi uniforme
- parsing corretto valori con virgola o punto
- aggiornamento della modale e della lista storica
- integrazione con il KPI `Corrispettivi`
- integrazione nel calcolo preview tramite `CashReceiptClosure`

---

### 3. Fondo cassa

Completata la gestione del fondo cassa con:

- conteggio per tagli
- totale automatico
- salvataggio
- eliminazione
- aggiornamento del KPI `Fondo cassa`
- utilizzo nel preview per il calcolo del `fondo_finale`

---

### 4. Versamenti bancari

Completata la gestione dei versamenti con:

- versamento incasso
- versamento intermedio
- selezione assegni disponibili
- totalizzazione automatica
- eliminazione versamento
- ripristino stato assegni collegati alla cancellazione
- aggiornamento preview e KPI

---

### 5. Prelievi titolare / Cassetto

Completata la nuova gestione del cassetto tramite tabella dedicata ai prelievi titolare.

Funzionalità attive:

- selezione tipo prelievo:
  - `parziale`
  - `serale`
- inserimento contanti
- selezione assegni ricevuti in giornata ancora disponibili
- totalizzazione automatica contanti + assegni
- storicizzazione dei prelievi
- modifica prelievo (`PUT`)
- eliminazione prelievo (`DELETE`)
- gestione corretta dei collegamenti con `CashOwnerTakeCheck`
- aggiornamento KPI `Cassetto`
- integrazione nel preview con:
  - `owner_take_cash_amount`
  - `owner_take_check_amount`
  - `incasso_consegnato`

---

### 6. Quadratura

Completato primo affinamento della quadratura:

- il valore viene mostrato solo quando esistono i dati minimi necessari
- in assenza dei dati necessari viene mostrato `-`
- aggiunta logica visuale a soglie
- aggiunti LED di stato per la quadratura

Soglie attuali:

- rosso: quadratura < -5,00
- giallo: -5,00 <= quadratura < -2,00
- verde: -2,00 <= quadratura <= 2,00
- giallo: 2,00 < quadratura <= 5,00
- rosso: quadratura > 5,00

---

## ✅ Frontend / UI completata

### Modali attive e funzionanti

- operazioni incasso / spesa
- ricerca e creazione cliente
- fondo cassa
- e-commerce
- versamenti
- corrispettivi
- cassetto / prelievi titolare

---

### KPI card

Le card KPI sono state ristrutturate per mostrare i valori in formato:

- simbolo euro fisso a sinistra
- importo dinamico a destra

È stato individuato e corretto un errore HTML strutturale in una card KPI che alterava il layout.

---

## ⚠️ Stato reale del modulo

Il modulo Agenda / Cassa è ora ad uno stato molto più avanzato e già utilizzabile per test funzionali concreti.

Tuttavia:

- sono emersi ulteriori bug e omissioni
- alcune rifiniture UI / logiche restano da completare
- è necessario aprire una nuova sessione di lavoro per gestire in modo pulito:
  - bug residui
  - mancanze funzionali
  - eventuali rifiniture della quadratura
  - eventuali CRUD mancanti in altre sezioni

---

## 📌 Appunti per la prossima chat

Nella prossima chat si ripartirà dal modulo Agenda / Cassa per:

- elenco bug trovati durante i test
- elenco omissioni funzionali residue
- eventuali correzioni UI
- eventuale completamento della porzione quadratura
- verifica finale di coerenza tra KPI, preview e dati persistiti

---

## 🧭 Note operative

Nessuna modifica necessaria a `project_map.md` in questa fase.

Lo stato del progetto va aggiornato solo in `STATUS.md`.

La prossima chat dovrà partire in modalità repo, leggendo i file necessari prima di proporre modifiche strutturali o nomi di variabili.