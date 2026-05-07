TEST_SYNC_CODEX_20260507_185518
# STATUS.md — aggiornamento Agenda / Cassa
Data aggiornamento: 2026-04-12

---

## 🔄 Stato generale modulo Agenda / Cassa

La base del modulo è attiva e utilizzabile.
Le principali CRUD della giornata risultano operative.
La preview dei KPI e il report diagnostico giornata sono attivi.

Dopo le ultime correzioni, la parte **spese** non fa più esplodere l’applicazione e sono state allineate diverse logiche della modale pagamenti rispetto agli incassi.

---

## Task corrente (metodologia Codex)

- Rimossa dal manifesto Codex la procedura RAW/incolla-file e allineato il workflow a lettura diretta repository locale

---

## ✅ Completato / stabile

### Giornata / preview / KPI
- Creazione o recupero giornata tramite `/cassa/api/day`
- Preview giornata tramite `/cassa/api/day/<day_date>/preview`
- KPI collegati alla preview
- Gestione fondo cassa tramite `CashDrawerCount`
- Gestione corrispettivi
- Gestione prelievi titolare / cassetto
- Gestione movimenti spicci
- Gestione versamenti bancari
- Report diagnostico giornata apribile dal menù contestuale

### Incassi
- Inserimento incassi singoli funzionante:
  - cash
  - pos
  - bank
  - check
- Inserimento incassi multipli funzionante
- Correzione bug grave su `api_create_sale`:
  - i pagamenti multipli non vanno più in errore con `sale_id = NULL`
- Divergenza logica assegni incasso vs assegni spesa correttamente ripristinata
- Modifica ed eliminazione incassi operative

### Spese
- Inserimento spese singole cash funzionante
- Inserimento spese singole POS funzionante con nuova logica descrittiva:
  - niente dispositivo POS
  - niente circuito POS
  - uso di `pos_card_label`
  - uso di `pos_is_personal`
- Inserimento spese singole bank funzionante
- Inserimento spese singole check funzionante
- Inserimento spese multiple funzionante
- Correzione dei pannelli dinamici della modale spese:
  - i pannelli assegno spesa ora divergono da quelli assegno incasso
- Correzione validazione importi e campi obbligatori nella modale spese
- Modifica ed eliminazione spese operative

### POS
- CRUD movimenti POS operative
- Lista POS operativa
- Modifica / eliminazione movimenti POS operative

### Movimenti di cassa
- CRUD movimenti cassa operative
- Separazione `kind="altro"` e `kind="spicci"`
- Lista movimenti cassa operativa
- Modifica / eliminazione movimenti cassa operative

### Spunte di controllo righe
- Toggle spunte su:
  - incassi
  - spese
  - POS
  - movimenti cassa

---

## ✅ Modifiche strutturali recenti

### `CashExpensePayment`
La logica POS sulle spese è stata cambiata.

Rimossi:
- `pos_device_id`
- `pos_circuit_id`

Aggiunti:
- `pos_card_label`
- `pos_is_personal`

Questa modifica è già migrata.

### Nuovo archivio assegni emessi
È stata introdotta e migrata la tabella dedicata agli assegni emessi per le spese.

Scopo:
- separare completamente gli assegni emessi dagli assegni clienti
- tracciare assegni di pagamento con:
  - banca emittente
  - numero assegno
  - data scadenza
  - importo

Gli assegni emessi:
- non stanno nella tabella assegni clienti
- non concorrono al versabile
- serviranno per scadenze e gestione futura

---

## ⚠️ Nota importante sulle formule
Le formule di `cash_math.py` sono state corrette manualmente localmente dall’utente dopo diversi aggiustamenti.
Quindi:

- il contenuto attuale di `cash_math.py` **non va dedotto dalla memoria storica**
- prima di qualunque modifica futura bisogna rileggere il file reale aggiornato
- evitare interventi speculativi sulle formule

---

## 📌 Stato attuale della modale operazioni
La modale unica `opModal` è ancora condivisa tra incassi e spese, ma ora contiene logiche differenziate lato JS.

### Incassi
- POS con device/circuit
- assegni cliente con dati banca cliente

### Spese
- POS descrittivo con carta aziendale / carta personale
- assegni emessi con:
  - banca nostra
  - numero assegno
  - scadenza

La divergenza funzionale è stata già avviata e funziona sui casi testati.

---

## 🧪 Ultimo esito test
Ultimi test riferiti a:
- spese singole
- spese multiple
- incassi multipli
- assegni incasso / assegni spesa
- POS spesa descrittivo

Esito:
- nessun errore bloccante riscontrato nei casi testati
- i flussi principali coinvolti risultano funzionanti

---

## 🔜 Prossimo task
Il prossimo step previsto è:

### Doppio archivio DB / chiavetta criptata
Implementazione della logica a doppio archivio come discusso in precedenza:
- archivio standard su database
- archivio riservato su chiavetta criptata
- coordinamento tra i due livelli di persistenza
- relativa integrazione nel modulo Agenda / Cassa

---

## Nota operativa per la prossima chat
Prima di intervenire:
- rileggere i file reali aggiornati
- non assumere il contenuto di `cash_math.py`
- non riusare versioni vecchie della modale pagamenti
- partire dallo stato attuale effettivo del codice

## Aggiornamento situazione — Agenda / Cassa

### Completato

- Implementata sincronizzazione multi-client tramite Redis:
  - `_bump_agenda_day_version(day_date)`
  - endpoint `/cassa/api/day/<day_date>/version`
  - polling frontend con `pollAgendaVersion()`
- Agganciate alla sincronizzazione le principali CRUD:
  - incassi
  - spese
  - movimenti di cassa
  - POS
  - row-check
  - fondo cassa / drawer-count
  - corrispettivi
  - prelievi titolare / cassetto
  - versamenti
  - eCommerce
- Aggiunta route `PUT /api/ecommerce/<id>` e gestione frontend modifica eCommerce.
- Sistemata sincronizzazione stato vault:
  - `private_vault:unlocked`
  - `private_vault:state_version`
  - polling frontend dedicato.
- Sistemato caricamento iniziale agenda:
  - stato grafico vault e dati caricati risultano coerenti.
- Sistemati KPI fiscal/full:
  - preview ora usa `view=fiscal|complete`
  - modalità fiscale esclude PRI
  - modalità full include PRI.
- Corretta quadratura:
  - incassi banca non devono entrare nel cassetto atteso.
- Corretta UI “Fuori cassa”:
  - disponibile solo per pagamenti cash.
  - disabilitata per banca/POS/assegno/multipli.
- Corretto parser importi JS:
  - `12,50` e `12.50` vengono interpretati entrambi come `12.50`.
- Disabilitato watchdog `vault-healthcheck`, risultato non adatto con automount/autofs.

### In sospeso / prossima chat

- Proseguire test regressione generale Agenda:
  - insert/update/delete su tutte le sezioni
  - sync tra più client
  - KPI fiscal/full
  - lock/unlock vault
  - mount/unmount chiavetta.
- Valutare sostituzione futura del bump manuale con hook centralizzato SQLAlchemy.
- Sistemare definitivamente gestione robusta chiavetta USB:
  - rimozione improvvisa
  - reinserimento
  - automount
  - recovery da stato autofs/mount incoerente.
- Rimuovere password vault hardcoded nel JS (`TEST123`) quando si passa a soluzione definitiva.
