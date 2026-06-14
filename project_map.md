# PROJECT_MAP.md — v2.4

## Repository source of truth

Repo:
https://github.com/vitorizzo/ld-flask-app

Branch:
main

Fonte di verità:
ultimo commit del branch main.

---

## File di coordinamento chat

- `new_chat.md` — manifesto per flusso ChatGPT con file incollati / RAW
- `new_chat_codex.md` — manifesto per flusso Codex locale con lettura diretta repository
- `project_map.md`
- `status.md`

Nel flusso Codex locale la lettura avviene direttamente dai file del repository, senza incollare file in chat.

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

# MODULO SPEDIZIONI / CORRIERI / POLEEPO

## Stato Architetturale

Modulo creato come hub separato per:
- tracking spedizioni affidate a corrieri
- integrazioni BRT / GLS / DHL
- import ordini esterni da Poleepo

Il modulo e' volutamente separato dalla bacheca ordini Slack/Kiosk, ma prevede riferimenti opzionali verso:
- anagrafiche clienti `BusinessRegistry`
- ordini esterni `ExternalOrder`
- spedizioni `Shipment`

Route principale:
- `/shipping`
- redirect operativo verso `/shipping/shipments`

Route operative:
- `/shipping/shipments` - consultazione tracking spedizioni
- `/shipping/orders` - ordini Poleepo
- `/shipping/accounts` - account corrieri

Blueprint:
- `/routes/shipping.py`

Connettori:
- `/tools/shipping_connectors.py`

Frontend:
- `templates/shipping/shipments.html`
- `templates/shipping/orders.html`
- `templates/shipping/accounts.html`
- `templates/shipping/_nav.html`
- `static/js/shipping_common.js`
- `static/js/shipping_shipments.js`
- `static/js/shipping_orders.js`
- `static/js/shipping_accounts.js`
- `static/css/shipping.css`

Migrazione:
- `migrations/versions/c4d5e6f7a8b9_add_shipping_tracking.py`
- `migrations/versions/d5e6f7a8b9c0_add_courier_accounts.py`
- `migrations/versions/e6f7a8b9c0d1_add_courier_account_validity.py`
- `migrations/versions/f7a8b9c0d1e2_split_shipping_menu.py`

## Modelli coinvolti

- `CourierIntegration`
- `CourierAccount`
- `Shipment`
- `ShipmentTrackingEvent`
- `ExternalOrder`

## Tabelle create

- `courier_integrations`
- `courier_accounts`
- `shipments`
- `shipment_tracking_events`
- `external_orders`

## Menu

La migrazione aggiunge voce menu:
- nome: `Spedizioni`
- route: `/shipping`
- peso: `30`

La voce `Spedizioni` e' un contenitore con tre voci figlie:
- `Consultazione spedizioni` -> `/shipping/shipments`
- `Ordini Poleepo` -> `/shipping/orders`
- `Account corrieri` -> `/shipping/accounts`

La dashboard riepilogativa resta sospesa finche' consultazione, ordini e account non sono stabilizzati.

## Corrieri

Seed iniziale in `courier_integrations`:
- `brt`
- `gls`
- `dhl`
- `poleepo`

I connettori BRT/GLS/DHL sono predisposti ma non ancora collegati alle API reali: servono specifiche endpoint, autenticazione e formato risposta.

## Account corrieri

Gli account corriere sono separati dalle integrazioni generali per supportare piu' credenziali per lo stesso corriere:
- `portal`: spedizioni create dal portale del corriere, ad esempio EasySpedWeb;
- `webservice`: spedizioni create via ecommerce/Poleepo/API.

Tabella:
- `courier_accounts`

Campi principali:
- `courier_code`
- `account_type`
- `name`
- `base_url`
- `username`
- `password_encrypted`
- `valid_from`
- `valid_to`
- `extra_config`
- `is_enabled`

Le password sono cifrate con `tools.crypto.EncryptedString` e `FERNET_KEY`; non sono restituite al frontend, che riceve solo `has_password`.

Le spedizioni possono avere `courier_account_id`; se non presente, il refresh tracking prova gli account attivi del corriere.

La scelta automatica account considera la data spedizione o, se manca, la data ordine/creazione:
- account collegato alla spedizione provato per primo solo se coerente con la validita';
- account con `valid_from`/`valid_to` compatibile preferiti agli account fuori periodo;
- account senza date restano validi come fallback.

## Poleepo

Variabili lette da configurazione:
- `POLEEPO_URL`
- `POLEEPO_PKEY`
- `POLEEPO_PPKEY`

Documentazione usata:
- `https://developers.poleepo.cloud/docs/api/`

Flusso implementato:
- `POST /oauth/access_token`
- `GET /orders`
- `GET /shippings/{id}`
- normalizzazione record verso `ExternalOrder`
- normalizzazione spedizioni Poleepo verso `Shipment`
- import ordini Poleepo paginato con `offset`/`max` fino a esaurimento pagine;
- UI con import incrementale e import storico completo.
- import/sync storici avviati come task Celery in background con avanzamento nel monitor task globale.
- Celery Beat pianifica import ordini Poleepo, sync spedizioni Poleepo e refresh tracking spedizioni aperte.
- il monitor task usa Redis; `tools/redis_utils.py` legge `REDIS_HOST` oppure il fallback da `CELERY_BROKER_URL`.

Stato reale ultimo test:
- chiamata HTTP a Poleepo riuscita;
- autenticazione OAuth riuscita con `POLEEPO_PKEY` come `client_id` e `POLEEPO_PPKEY` come `client_secret`;
- `GET /orders` restituisce ordini reali;
- import iniziale completato con 100 ordini;
- import incrementale corretto: `updated_after` viene inviato in formato UTC/RFC3339 senza microsecondi.

Conclusione operativa:
- codice integrazione Poleepo presente;
- credenziali OAuth validate;
- endpoint `POST /shipping/api/poleepo/import` operativo.
- endpoint `POST /shipping/api/poleepo/sync-shipments` operativo.
- endpoint `GET /shipping/api/external-orders` restituisce `total` e mostra gli ultimi 200 ordini locali.
- lo sync spedizioni supporta modalita' storica con `include_old=true` e `sync_all=true`, processando tutti gli ordini Poleepo locali.
- l'arricchimento BRT aggiorna spedizioni gia' salvate usando il payload tracking: data spedizione, riferimento, destinatario/indirizzo quando disponibili.
- UI spedizioni: lista tracking e dettaglio hanno scroll indipendenti; comandi import spedizioni ordinario/storico sono nella pagina `/shipping/shipments`; filtri disponibili per corriere, account corriere, ciclo attiva/chiusa e stato.

## Tracking BRT

Endpoint tracking provato:
- `GET https://api.brt.it/rest/v1/tracking/parcelID/{parcel_id}`

Uso previsto:
- solo tracking, nessuna creazione spedizione dalla webapp;
- le spedizioni vengono create da Poleepo e importate in LD Flask App;
- il refresh usa l'account corriere BRT `webservice`.
- la lista spedizioni e' ordinata per `shipped_at` decrescente;
- filtri supportati: corriere, stato e ciclo `active/closed`;
- ordini Poleepo ordinati per `ordered_at` decrescente e mostrati con data ordine;
- sync spedizioni Poleepo ordinata/filtrata per `ordered_at`, non per `updated_at`;
- default sync spedizioni: solo ordini negli ultimi 180 giorni;
- spedizioni storiche oltre 180 giorni marcate `expired`/`Storica` e escluse dal filtro `active`;
- il dettaglio spedizione include riepilogo BRT ed eventi tracking con data/ora;
- gli eventi tracking vengono aggiornati in modo idempotente, senza duplicati per stesso evento.

Stato ultimo test:
- Poleepo restituisce `tracking_code` e `parcel_id` da `/shippings/{id}`;
- sincronizzazione spedizioni Poleepo riuscita;
- creati record `Shipment` BRT con `source='poleepo'`;
- `OPTIONS` su endpoint tracking espone WADL con header obbligatori `userID` e `password`;
- chiamata BRT tracking funzionante usando header `userID`/`password`, non Basic Auth;
- eventi tracking BRT salvati in `shipment_tracking_events`.

---

# MODULO SCHEDE PRODOTTO / IMMAGINI PIATTAFORME

## Stato Architetturale

La scheda prodotto e' esposta da:
- `/search/scheda_articolo/<cod_art>`

File principali:
- `routes/search.py`
- `templates/scheda_articolo.html`
- `static/js/scheda_articolo.js`

Modelli coinvolti:
- `Articoli`
- `Immagini` come fallback legacy
- `ProductAsset`
- `ProductPlatformLink`
- `ProductPlatformField`
- `SchedeProdotti`

Il sistema immagini moderno usa `ProductAsset` con:
- `cod_art`
- `asset_type='image'`
- `source_platform`
- `local_path`
- `remote_url`
- `source_external_id`
- `content_hash`
- `mime_type`
- `is_primary`
- `sort_order`

Le immagini importate da Prestashop e Poleepo vengono tracciate con la piattaforma sorgente.
La scheda prodotto mostra badge di provenienza sulle immagini e badge presenza piattaforma.

## Intervento corrente 2026-06-11

La scheda prodotto e' stata estesa con:
- barra superiore di thumbnail per piattaforma sopra il carousel immagini;
- slot piattaforme: Prestashop, Poleepo, Ebay, Amazon, LDApp;
- immagini legacy e vecchi asset `manual` mostrati nello slot LDApp;
- upload immagine da PC tramite LDApp con `POST /search/scheda_articolo/<cod_art>/images`;
- salvataggio upload in `static/images/products/ldapp/`;
- creazione/aggiornamento record `ProductAsset(source_platform='ldapp')`;
- deduplica per `content_hash` sullo stesso articolo;
- pulsante creazione nuova immagine presente ma disabilitato;
- menu contestuale sulle immagini con voci `Aggiungi a Prestashop/Poleepo/Ebay/Amazon` presenti ma disabilitate;
- drag/drop sugli slot predisposto lato UI, con invio a piattaforme esterne non ancora implementato.

Le integrazioni di upload verso Prestashop, Poleepo, Ebay e Amazon non sono ancora operative.
Il prossimo step tecnico sara' implementare endpoint/adapter specifici per pubblicare una immagine esistente verso una piattaforma abilitata.

## Permessi scheda prodotto

Soglia ruolo:
- `office` = weight `40`

Regole operative:
- utenti con `max_role_weight >= 40` possono vedere provenienza immagini, badge piattaforme e strumenti di gestione immagini;
- utenti sotto `office` vedono solo la gallery immagini, senza badge provenienza e senza badge piattaforme;
- upload immagini LDApp e invio immagini a piattaforme sono consentiti solo da `office` in su;
- pubblicazione prodotto verso piattaforme sara' consentita solo da `office` in su;
- se un articolo non risulta presente su una piattaforma (`ProductPlatformLink` assente o status `absent/error`), non si deve poter inviare/cambiare immagine su quella piattaforma.

---

# MODULO PLANCIA ORDINI / BACHECA SLACK

## Stato Architetturale

La plancia ordini giri e' esposta da:
- `/route-orders/board`

File principali:
- `routes/route_orders.py`
- `templates/route_orders/board.html`
- `routes/kiosk.py` per la bacheca ordini
- `tools/slack_processor.py` per import/normalizzazione messaggi Slack

Modelli coinvolti:
- `SlackOrder`
- `SlackOrderEvent`
- `DeliveryRoute`
- `DeliveryRouteCustomer`
- `RouteOrderBoardEntry`
- `BusinessRegistry`

Gli ordini arrivati da Slack possono avere `SlackOrder.customer_key` derivata dal nome libero del messaggio, quindi non sempre coincidono con `BusinessRegistry.source_code` o `BusinessRegistry.id`.

## Associazione ordini Slack a clienti

Intervento 2026-06-11:
- `/route-orders/api/board` restituisce anche `unmatched_orders`, cioe' ordini del giro/data che non si risolvono su un cliente del giro;
- la plancia mostra un box `Ordini da associare` sopra la tabella clienti quando esistono ordini non agganciati;
- nuovo endpoint `POST /route-orders/api/orders/<order_id>/customer` per associare manualmente un ordine a una anagrafica cliente;
- l'associazione aggiorna `SlackOrder.customer_display` e `SlackOrder.customer_key` usando label e `source_code`/ID del cliente;
- l'operazione viene storicizzata in `SlackOrderEvent(type='customer_link')`;
- la risoluzione ordini della plancia usa `_registry_for_order()` anche per match esatti su `display_name`/`legal_name`, non solo chiavi `source_code`/ID.

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

## Snapshot chiusura e Vault PRI

Per ridurre i tempi di apertura giornata, la preview non deve ricalcolare ricorsivamente il saldo versabile su tutta la storia.

Regola architetturale:

- dati aziendali/fiscali: DB;
- dati privati: vault PRI cifrato;
- snapshot fiscale/AZ: persistito nel DB e utilizzabile anche con vault bloccato;
- snapshot PRI: persistito nel vault annuale cifrato e leggibile solo con vault sbloccato;
- report fiscale: mostra solo snapshot/dati AZ;
- report completo: compone runtime AZ + PRI mantenendo il confine tra le fonti;
- modifiche su giornate chiuse: solo eventi/audit non distruttivi, con `before/after`, utente, data/ora, motivo e impatto sui progressivi;
- se una giornata chiusa viene modificata, gli snapshot dal giorno modificato in avanti vanno marcati/ricalcolati.

Stato implementazione 2026-06-14:

- `CashClosure` contiene i campi per snapshot fiscale/AZ e saldo versabile progressivo finale;
- migrazione `1a2b3c4d5e6f_add_cash_closure_fiscal_snapshot.py` applicata al DB;
- `routes/cassa.py` usa un calcolo progressivo aggregato per la preview al posto della ricorsione storica;
- la preview usa un calcolo giornaliero aggregato e non carica piu' tutte le righe incasso/spesa in eager loading;
- `static/js/agenda.js` carica preview e liste in parallelo nella normale apertura giornata;
- `POST /cassa/api/day/<day_date>/close` salva la chiusura:
  - snapshot fiscale nel DB su `CashClosure`;
  - snapshot PRI/complete nel vault annuale sotto la giornata;
  - `printCompleteDayReport()` lo chiama prima di aprire la stampa;
  - `GET /cassa/api/day/<day_date>/closure-snapshot` riusa lo snapshot quando il report viene riaperto;
  - la preview delle giornate chiuse riusa il payload snapshot quando disponibile.
- audit non distruttivo in corso:
  - tabella `cash_day_audit_events` per create/update/delete sulle entita' cassa;
  - listener SQLAlchemy che registra audit quando la giornata e' chiusa;
  - `_bump_agenda_day_version()` marca stale gli snapshot chiusi dalla data interessata in avanti.
- controllo stato giornata:
  - badge in alto a destra cliccabile per passare `open/closed`;
  - inserimenti su giornata chiusa chiedono conferma e offrono riapertura o passaggio a oggi;
  - i mutatori principali della cassa sono bloccati anche lato backend sulle giornate chiuse.
- resta da implementare:
  - UI per mostrare/revertire gli eventi di audit.

---

# Versione

Versione: 2.4  
Stato: modulo Agenda/Cassa operativo con CRUD principali attivi, versamenti ed eliminazione versamenti attivi, logica assegni/eventi introdotta, prossimo focus sul KPI Quadratura
