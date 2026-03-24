# PROJECT_MAP.md — v2.4

## Repository source of truth

Repo:
https://github.com/vitorizzo/ld-flask-app

Branch:
main

Fonte di verità:
ultimo commit del branch main.

---

## 🔗 LETTURA FILE — NUOVA REGOLA OPERATIVA

ChatGPT NON deve più costruire automaticamente i link RAW partendo da LINK_BASE_RAW.

Quando serve leggere un file:

ChatGPT deve fornire il percorso nel formato:

https://raw.githubusercontent.com/vitorizzo/ld-flask-app/main/percorso/file.ext

e chiedere esplicitamente:

"Incollami il link RAW di questo file"

Sarà l’utente a incollare il link completo:

https://raw.githubusercontent.com/...

Senza link RAW diretto → il file NON è leggibile.

È vietato:
- ricostruire link
- assumere contenuti
- usare memoria storica

---

## Architettura generale

- Web app: Flask
- DB: PostgreSQL
- ORM: SQLAlchemy
- Migrazioni: Alembic
- Frontend: Jinja2
- Static:
  - /static/js
  - /static/css
  - /static/images
- Logs: /logs
- Tools backend riusabili: /tools
- Blueprint: /routes
- Form: /forms

---

# MODULO AGENDA / CASSA

## Stato Architetturale

Backend matematico e logico separato dalla UI.

Moduli backend principali coinvolti:

- `/routes/cassa.py`
- `/tools/cash_math.py`
- `/tools/check_utils.py`
- `/tools/agenda_flags.py`

---

## File chiave del modulo

### `/routes/cassa.py`

Contiene:
- route pagina agenda
- endpoint CRUD principali del modulo cassa
- preview giornata
- CRUD clienti
- CRUD ecommerce
- CRUD drawer count
- CRUD versamenti
- eliminazione versamenti
- gestione disponibilità assegni per versamento
- lettura assegni in scadenza
- lettura saldo spicci
- endpoint POS e banche

### `/tools/cash_math.py`

Contiene:
- funzione principale `calculate_closure_pure(...)`
- calcolo:
  - versabile giornata
  - versabile residuo
  - saldo versabile progressivo
  - incasso calcolato / totale di giornata
  - delta fondo
  - delta quadratura
  - totale versato oggi
  - totale versato intermedio
  - assegni odierni
  - assegni postdatati
  - assegni in pancia
  - massimo contanti consentito
  - debito contanti da recuperare
- logica bancaria:
  - festività bancarie italiane
  - `next_banking_day(...)`

### `/tools/check_utils.py`

Contiene:
- logica centralizzata di cambio stato assegno
- scrittura eventi in `CashCheckEvent`
- supporto alla storicizzazione degli stati assegno

### `/tools/agenda_flags.py`

Contiene:
- regole centralizzate dei flag agenda
- separazione tra semantica UI e semantica contabile
- supporto alle logiche fiscali / complete lato agenda

---

## Modelli coinvolti

- CashDay
- CashClosure
- CashClosurePos
- CashSale
- CashSalePayment
- CashExpense
- CashExpensePayment
- CashMove
- PosMove
- PosDevice
- PosCircuit
- CashCustomer
- CashCustomerAlias
- CashBank
- CashCheck
- CashCheckEvent
- CashSaleCheck
- CashDeposit
- CashDepositCheck
- CashDrawerCount
- CashDrawerCountLine
- CashEcommerce

Relazioni stabilizzate:
- evitare `lazy="dynamic"` dove interferisce con eager loading
- uso prevalente di `selectinload(...)`

Approccio adottato:
- query pure
- logica matematica separata
- logica assegni/eventi separata
- UI scollegata dai calcoli backend

---

## Stato UI Agenda / Cassa

### Template / static principali

- template agenda: `templates/agenda.html`
- script principale: `static/js/agenda.js`
- css agenda: `static/css/agenda.css`

### Modali attive

- operazione (`opModal`)
- ricerca cliente
- nuovo cliente
- versamenti
- ecommerce
- conteggio fondo

### Modale Operazione

La modale operazione gestisce:

- flag
- importo operazione
- descrizione
- cliente
- fuori cassa
- carrier pagamento

Carrier supportati lato frontend:
- cash
- pos
- bank
- check
- multi

### Logica carrier frontend

Implementata e stabilizzata:

- quadratura rispetto a `opAmount`
- ricalcolo automatico
- blocco salvataggio se la somma carrier non quadra
- reset corretto campi dipendenti
- supporto riga singola e multi-carrier
- gestione device/circuit POS
- gestione banca
- gestione assegni

### Cliente

Gestione cliente presente in UI:

- ricerca progressiva via datalist
- ricerca avanzata in modale
- creazione nuovo cliente

### KPI agenda

KPI attualmente presenti con backend attivo:
- saldo versabile iniziale
- saldo versabile attuale
- versabile odierno / residuo
- fondo iniziale
- fondo finale
- totale di giornata (ex incasso calcolato)
- delta fondo
- delta quadratura
- totale ecommerce
- totale versamenti
- corrispettivi
- incasso consegnato

Per il KPI “Totale di Giornata”:
- se mancano fondo iniziale/finale o corrispettivi il valore resta visibile
- viene però marcato come indicativo/parziale lato UI
- badge stato:
  - corrispettivi
  - fondo cassa

---

## Stato backend CRUD Agenda

### Attivo

- `GET /cassa/api/day`
- `GET /cassa/api/day/<date>/preview`
- `GET /cassa/api/days/active`

### Clienti
- `GET /cassa/api/customers/suggest`
- `POST /cassa/api/customers`

### Incassi / Spese
- `POST /cassa/api/day/<day_date>/sales`
- `GET /cassa/api/day/<day_date>/sales`
- `POST /cassa/api/day/<day_date>/expenses`
- `GET /cassa/api/day/<day_date>/expenses`

### POS / banche
- `GET /cassa/api/pos/devices`
- `GET /cassa/api/pos/devices/<id>/circuits`
- `GET /cassa/api/banks`
- `POST /cassa/api/day/<day_date>/pos_moves`
- `GET /cassa/api/day/<day_date>/pos_moves`

### Movimenti di cassa
- `POST /cassa/api/day/<day_date>/cash_moves`
- `GET /cassa/api/day/<day_date>/cash_moves`
- `GET /cassa/api/coins/balance`

### Drawer count
- `GET /cassa/api/day/<day_date>/drawer-count`
- `POST /cassa/api/day/<day_date>/drawer-count`
- `DELETE /cassa/api/day/<day_date>/drawer-count`

### Ecommerce
- `GET /cassa/api/day/<day_date>/ecommerce`
- `POST /cassa/api/day/<day_date>/ecommerce`
- `DELETE /cassa/api/ecommerce/<id>`

### Assegni / versamenti
- `GET /cassa/api/checks/due`
- `GET /cassa/api/day/<day_date>/deposit-available-checks`
- `GET /cassa/api/day/<day_date>/deposits`
- `POST /cassa/api/day/<day_date>/deposits`
- `DELETE /cassa/api/deposits/<id>`

---

## Logica versamenti — stato attuale

Sono attivi due tipi di versamento:

- `versamento_incasso`
- `versamento_intermedio`

### `versamento_incasso`

Concepito per versare:
- contanti disponibili già “in pancia”
- assegni già detenuti da prima della giornata e versabili entro cutoff bancabile

Logica max contanti:
- basata su saldo versabile attuale
- sottrae assegni ancora in pancia
- mostra warning ma non blocca
- l’eventuale eccedenza genera debito contanti che riduce il versabile residuo mostrato nei KPI

### `versamento_intermedio`

Concepito per versare:
- assegni ricevuti oggi
- contanti anticipati durante la giornata

Logica max contanti:
- basata sul residuo versabile odierno
- sottrae gli assegni odierni ancora ricevuti / non versati
- warning visivo senza blocco
- aggiornamento lato frontend nella modale versamenti

### Eliminazione versamenti

Attiva:
- elimina il record `CashDeposit`
- elimina i collegamenti `CashDepositCheck`
- per gli assegni collegati ripristina lo stato precedente tramite storico eventi
- in caso di versamento solo contanti non sono coinvolti assegni

Nota:
- la cancellazione è pensata per correzione errori di imputazione
- non per gestire eventi successivi di vita assegno (richiami, ripresentazioni, insoluti, ecc.)

---

## Logica assegni — stato attuale

Gli assegni sono ormai trattati come entità con storia.

### Stato assegno
Gestito tramite:
- `CashCheck.status`
- `CashCheckEvent`

### Eventi assegno
Ogni cambio stato rilevante deve essere storicizzato.

Stati effettivamente usati nel flusso attuale:
- `received`
- `moved` / `spostato` (retrocompatibilità da uniformare)
- `deposited`

Altri stati e sottocasi:
- verranno regolamentati nella futura gestione completa assegni
- non fanno parte della chiusura attuale del discorso versamenti

---

## Preview giornata

Endpoint attivo:

`/cassa/api/day/<date>/preview?view=fiscal`

La preview attuale usa solo DB aziendale.

Il risultato include:
- versabile giornata
- versabile residuo
- saldo versabile progressivo
- massimo contanti incasso
- debito contanti incasso
- presenza/assenza corrispettivi
- presenza/assenza fondo iniziale/finale
- flag `totale_giornata_is_partial`

---

## Formula ufficiale attuale

### Contanti fisici
Contanti_fisici =
incassi_cash
− spese_cash
− totale_pos

### Assegni odierni
Assegni_odierni =
Σ assegni flag `*`

### Assegni postdatati
Assegni_postdatati =
Σ assegni flag `**`

### Versabile giornata
Versabile_giornata =
Contanti_fisici
+ Assegni_odierni

### Totale versato oggi
Totale_versato_oggi =
depositi_cash_oggi
+ depositi_assegni_oggi

### Saldo versabile attuale
Saldo_versabile =
Saldo_versabile_precedente
+ Versabile_giornata
+ Assegni_postdatati
− Totale_versato_oggi

### Versabile residuo
Versabile_residuo =
Versabile_giornata
− Totale_versato_intermedio
− Debito_contanti_incasso

### Totale di giornata
Se fondo iniziale e finale esistono:
Totale_giornata =
Contanti_fisici
+ Corrispettivi
− Delta_fondo

Se mancano dati fondo:
Totale_giornata =
Contanti_fisici
+ Corrispettivi

### Delta quadratura
Delta_quadratura =
Incasso_consegnato
− Totale_giornata

---

## Stato reale rispetto alla versione precedente

Correzioni rispetto a v2.3:

- NON è più vero che il backend save `sales/expenses` sia da completare
- i carrier multipli sono supportati lato payload UI/backend
- la gestione versamenti è attiva
- l’eliminazione versamenti è attiva
- la gestione assegni con eventi è entrata nel flusso
- il modulo `cash_math.py` è ormai centrale e deve essere sempre considerato file critico
- `agenda_flags.py` e `check_utils.py` sono file critici da leggere quando si lavora su agenda/cassa

---

# TODO AGENDA

## Priorità alta attuale

- sistemare KPI `Quadratura`
- consolidare formula e significato funzionale di quadratura
- chiarire relazioni tra:
  - totale di giornata
  - corrispettivi
  - incasso consegnato
  - fondo iniziale/finale
  - eventuali dati mancanti

## Priorità successiva

- uniformare naming stati assegni (`moved` / `spostato`, eventuali altri legacy)
- completare gestione storica assegni
- migliorare robustezza cancellazione versamenti su dati legacy sporchi
- eventuale refactor dei controlli di disponibilità contanti tra preview e modale

## Step successivo ma non immediato

- simulazione chiusura completa
- scrittura CashClosure / CashClosurePos
- integrazione Vault
- persistenza saldo versabile progressivo
- gestione completa ciclo vita assegni
- regole per insoluti / richiamati / ripresentati

---

# Versione

Versione: 2.4  
Stato: modulo Agenda/Cassa operativo con CRUD principali attivi, versamenti ed eliminazione versamenti attivi, logica assegni/eventi introdotta, prossimo focus sul KPI Quadratura