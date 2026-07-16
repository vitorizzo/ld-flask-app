# PROJECT_MAP.md — v2.4

## Regola prioritaria modali

Le modali nuove o modificate devono inizializzare esplicitamente il bottone di conferma su `shown.bs.modal` e ripulire lo stato su `hidden.bs.modal`.
Nel codice esistente il solo stato iniziale del DOM non è affidabile perché spesso lascia il bottone disabilitato al primo uso.

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

## Menu applicativi

- albero DB-driven tramite `Menu.parent_id` e `sort_order`, gestito da `/settings/menus`;
- editor gerarchico con drag/drop tra tutti i livelli, placeholder di inserimento, zone figlio vuote e rami collassabili;
- `reorder_menus` salva contestualmente ordine e nuovo `parent_id`, con controllo dei cicli;
- i badge dei menu figli vengono aggregati ricorsivamente sugli antenati visibili; `Servizio clienti` espone la somma di `Assistenza LDApp` e `Attivazioni Horeca`.

## Associazione anagrafiche Agenda

- `CashCustomer` resta l'anagrafica operativa usata da incassi e assegni; `BusinessRegistry` resta l'anagrafica gestionale/importata;
- `CashCustomerRegistryLink` (`cash_customer_registry_links`) persiste l'associazione tra i due archivi, con un solo cliente Agenda per ogni anagrafica gestionale;
- migration `3d4e5f607182_add_cash_customer_registry_links.py` con backfill deterministico per codice cliente e, in fallback, P.IVA univoca;
- il resolver `/cassa/api/customers/resolve-registry` consulta prima il link persistente e non sceglie arbitrariamente in presenza di match multipli.

## Ordini fornitori

- `routes/supplier_orders.py` gestisce gruppi fornitore, articoli espliciti e lookup remoto sul catalogo;
- `templates/supplier_orders/index.html`, `static/js/supplier_orders.js` e `static/css/supplier_orders.css` espongono gestione e consultazione giacenze in modali dedicate;
- la lista gruppi e' tabellare con consultazione per matrice/giacenza e azioni rapide di gestione prodotti, modifica ed eliminazione;
- il gestore prodotti a doppio pannello usa `GET /supplier-orders/groups/<id>/items`, `POST /supplier-orders/groups/<id>/items/batch` e `/supplier-orders/api/articles` per ricerca e associazioni multiple;
- le modali vengono spostate nel `body` e aperte manualmente sopra il backdrop globale; dopo la creazione `?group_id=<id>&modal=manage` apre automaticamente il gestore prodotti del nuovo gruppo.

---

# MODULO EVENTI

## Stato Architetturale

Modulo DB-driven per pubblicare degustazioni, partecipazioni ad eventi e attivita' varie.

Route:
- `/events/` - consultazione pubblica dei prossimi eventi;
- `POST /events/` - creazione evento, solo `office` in su;
- `POST /events/<id>/update` - modifica evento, solo `office` in su;
- `POST /events/<id>/delete` - eliminazione evento, solo `office` in su.

Blueprint:
- `routes/events.py`, registrato in `tools/app_factory.py` con prefisso `/events`.

Frontend:
- `templates/events/index.html`
- stili in `static/css/style.css`
- pulsante home in `templates/home.html`, visibile a tutti.

Modello:
- `Event` in `models.py`
- `poster_path` opzionale per locandina evento salvata in `static/uploads/events`.

Migrazione:
- `migrations/versions/7a8b9c0d1e2f_add_events.py`
- `migrations/versions/9c0d1e2f3a4b_add_event_poster.py`

Regola permessi:
- tutti possono visualizzare gli eventi pubblicati futuri;
- da `office` in su (`weight >= 40`) possono inserire, modificare, pubblicare/nascondere ed eliminare eventi.

---

# MODULO ORDINI CLIENTI HORECA

## Stato Architetturale

Bozza DB-driven per consentire ai clienti Horeca di inviare ordini dalla home.

Route:
- `/customer-orders/` - pagina cliente per invio ordine, visibile a `customer_horeca` e staff+;
- `POST /customer-orders/` - creazione ordine cliente;
- `POST /customer-orders/<id>/revise` - aggiunta o sostituzione su ordine gia' inviato;
- `/customer-orders/manage` - ricezione staff degli ordini cliente;
- `/settings/customer-order-options` - configurazione opzioni consegna ordini Horeca, da office in su;
- `/settings/customer-order-links` - associazione account utente ad anagrafica cliente, da office in su.

Blueprint:
- `routes/customer_orders.py`, registrato in `tools/app_factory.py` con prefisso `/customer-orders`.

Frontend:
- `templates/customer_orders/index.html`
- `templates/customer_orders/manage.html`
- `templates/settings/customer_order_options.html`
- `templates/settings/customer_order_links.html`
- stili in `static/css/style.css`
- pulsanti home in `templates/home.html`: `Fai un ordine` solo per clienti Horeca, `Ordini Horeca` per staff+.

Modelli:
- `CustomerOrderDeliveryOption`
- `CustomerOrder`
- `CustomerOrderRevision`
- `User.customer_registry_id` come collegamento account-anagrafica cliente.

Migrazione:
- `migrations/versions/8b9c0d1e2f3a_add_customer_orders.py`

Funzioni bozza:
- ordine con testo, foto da camera, allegati file e registrazione vocale via `MediaRecorder`;
- scelta consegna da menu configurabile, con valore aggiuntivo quando richiesto;
- aggancio automatico al giro tramite `DeliveryRouteCustomer`;
- modifiche ordine salvate come revisioni `addition` o `replacement`.

Pubblicazione operativa:
- la creazione da `/customer-orders/` pubblica sul canale Slack configurato nel giro del cliente;
- nello stesso flusso vengono creati/collegati `SlackOrder` e `RouteOrderBoardEntry`, rendendo l'ordine immediatamente disponibile nella bacheca;
- i riferimenti `route_board_entry_id` e `slack_order_id` impediscono la doppia pubblicazione applicativa, mentre `client_msg_id` protegge anche il post Slack;
- gli eventi Slack originati da bot/app non vengono inoltrati alle automazioni Slack, per evitare ricorsioni.
- in cancellazione, i messaggi Slack del bot vengono rimossi; quelli appartenenti ad altri autori vengono conservati ma marcati con commento nominativo nel thread e reaction `:wastebasket:`.

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
Le immagini sono raggruppate per `family_key` cosi' le copie dello stesso asset restano correlate tra LDApp e piattaforme pubblicate.
Le preview delle immagini non-LDApp passano da un endpoint proxy di LDApp invece di puntare direttamente a `www.ldenoteca.it`, cosi' il browser non apre il prompt HTTP basic.

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
- pubblicazione immagini attiva su Prestashop con `POST /search/scheda_articolo/<cod_art>/images/publish`;
- pubblicazione immagini attiva anche su Poleepo tramite `PoleepoConnector.upload_image()` con endpoint upload configurabile; il connettore prova piu' candidati di path, nome campo file, upload da URL pubblica, PUT binario e infine `PUT /products/{id}` con `images`, ma l'upload resta da verificare sul server Poleepo reale;
- avviata pubblicazione prodotto verso piattaforme:
  - schema iniziale campi per Prestashop e Poleepo in `routes/search.py`;
  - endpoint bozza `GET/POST /search/scheda_articolo/<cod_art>/publish/<platform>/draft`;
  - endpoint publish reale `POST /search/scheda_articolo/<cod_art>/publish/prestashop`;
  - mappatura proposta dai dati LDApp (`Articoli`, `SchedeProdotti`, barcode, giacenza web);
  - salvataggio bozza in `ProductPlatformField` prima dell'invio remoto;
  - UI scheda prodotto con pulsanti `Pubblica su ...` per piattaforme assenti e modale di revisione campi;
  - creazione prodotto Prestashop tramite webservice XML e creazione `ProductPlatformLink` dopo risposta remota;
  - campi lista Prestashop `id_category_default` e `id_tax_rules_group` caricati dal webservice e mostrati come select filtrabili nella modale;
  - liste Prestashop cache in memoria per 30 minuti; `Salva bozza` non ricarica opzioni remote e non crea prodotto remoto.
- azione `Imposta come default` sulla famiglia immagine con `POST /search/scheda_articolo/<cod_art>/images/<asset_id>/primary`;
- rimozione immagini con perimetro esplicito tramite `POST /search/scheda_articolo/<cod_art>/images/delete`;
- delete remoto implementato su Prestashop e Poleepo; Poleepo usa `PoleepoConnector.delete_image()` con fallback configurabile sul path remoto;
- preview immagini remota con `GET /search/scheda_articolo/<cod_art>/images/<asset_id>/preview` e proxy server-side per asset non-LDApp;
- menu contestuale esteso con `Imposta come default` e `Rimuovi immagine`;
- badge visivo `Default` sulla primaria e preview slot piattaforma che privilegia la copia primaria della piattaforma.

La pubblicazione prodotto remota e' attiva per Prestashop solo quando la bozza ha tutti i campi obbligatori. Poleepo ha un primo backend di creazione prodotto, ma resta da validare con un publish remoto reale controllato.
Primo publish reale validato: `BB03308` creato su Prestashop come prodotto `32361`, non attivo (`active=0`), con link locale `ProductPlatformLink` in stato `present`.
Prossimo passo: leggere documentazione Prestashop/Poleepo per completare lo schema campi, gestire creazione di categorie/caratteristiche mancanti, attivazione/disattivazione/eliminazione prodotto remoto e publish prodotto Poleepo.

Aggiornamento 2026-06-23:
- Poleepo e' trattato nel breve periodo come aggregatore verso gli store collegati; nel medio/lungo termine l'obiettivo e' sostituirlo con publish diretto LDApp verso i singoli store.
- Verificato payload reale `GET /products` Poleepo e `OPTIONS /products` con `POST` disponibile.
- Aggiunto primo backend di creazione prodotto Poleepo con `PoleepoConnector.create_product()` su `POST /products`.
- Payload minimo verificato: `sku`, `title`, `price`, `vat_rate`, `quantity`, `active`, `main_category_id`.
- La bozza Poleepo della scheda prodotto ora espone `title`, `vat_rate` e `main_category_id`; la categoria default e' `POLEEPO_DEFAULT_CATEGORY_ID` o fallback `8360` (`NON CATEGORIZZATO`).
- Il bottone `Pubblica` nella modale e' abilitato anche per Poleepo.
- Non ancora eseguito un publish remoto Poleepo reale di test; prima di considerarlo stabile va provato su articolo controllato e va verificata la propagazione agli store gestiti da Poleepo.

Aggiornamento 2026-06-24:
- Publish Poleepo testato dall'utente con creazione remota riuscita, ma con dati ancora minimali.
- Aggiunta azione `Modifica su Poleepo` per prodotti gia' collegati con `ProductPlatformLink.external_id`.
- Nuova route `POST /search/scheda_articolo/<cod_art>/publish/<platform>/update` per aggiornare il prodotto remoto senza ricrearlo.
- Update remoto attivo solo per Poleepo; Prestashop resta da implementare con update XML dedicato.
- Create/update Poleepo usano lo stesso filtro payload minimo verificato, evitando di inviare campi non confermati come `description` e `barcode`.
- La categoria Poleepo (`main_category_id`) non deve essere mostrata come numero muto: la bozza prova a costruire una select `ID - descrizione` dai prodotti Poleepo gia' presenti usando `main_category_path`; se l'ID non e' risolvibile viene evidenziato come `descrizione non disponibile`.
- Il default categoria Poleepo supporta anche `POLEEPO_DEFAULT_CATEGORY_LABEL` per rendere leggibili default numerici configurati, ad esempio `59271`, quando non sono ancora ricavabili dalle API.
- Prossimo step: test reale di modifica su prodotto controllato, poi gestione esplicita attiva/disattiva/elimina remoto e completamento mapping dati.
- La modale di modifica Poleepo deve partire dai valori remoti letti con `GET /products/<id>`, non dai mapping LDApp; i mapping LDApp possono comparire solo come suggerimento quando divergono.
- Per i prodotti nuovi, il titolo Poleepo proposto usa `Articoli.descrizione + Articoli.descrizione_aggiuntiva`, cosi' informazioni identitarie come produttore/tenuta non vengono perse.
- I campi remoti Poleepo non modificabili sono mostrati in sola lettura nella modale per aiutare la mappatura futura: `id`, `type`, `price_with_tax`, `sales`, `main_category_path`, date, immagini, disponibilita' e tag.
- Aggiunta copia immagine da altro prodotto nella scheda articolo:
  - UI in modale dalla toolbar immagini;
  - `GET /search/scheda_articolo/<cod_art>/images/copy-candidates`;
  - `POST /search/scheda_articolo/<cod_art>/images/copy`;
  - copia basata su `ProductAsset`, salvata sul target come asset `ldapp` con metadata di provenienza;
  - se l'immagine sorgente ha solo `remote_url`, LDApp la scarica in `static/images/products/ldapp` e salva un `local_path`, per permettere la successiva pubblicazione su Poleepo/Prestashop;
  - gli asset gia' copiati solo-remoti vengono riparati automaticamente al primo tentativo di pubblicazione immagine;
  - il fallback upload immagini Poleepo usa un PUT interno grezzo su prodotto con `images`, separato da `update_product()` che resta validato sui campi prodotto obbligatori;
  - non copia ancora immagini legacy non migrate a `ProductAsset`;
  - implementato: la modale consente selezione multipla delle immagini sorgente, con checkbox su ogni immagine e comandi `Seleziona tutte` / `Deseleziona tutte`, cosi' per nuove annate si possono copiare tutte le immagini della vecchia annata oppure solo quelle ancora valide;
  - endpoint `POST /search/scheda_articolo/<cod_art>/images/copy` accetta sia il vecchio `asset_id` singolo sia il nuovo array `asset_ids`.
- Da progettare come step successivo: `Crea prodotto da altro prodotto` per nuove annate, probabilmente nella scheda articolo/prodotto e non nella scheda cliente, con copia controllata di dati, bozze piattaforma, immagini e campi descrittivi/tecnici interni.
  - Prima copertura implementata nel flusso esistente `Copia valori da altro prodotto`: quando si copiano valori da un articolo sorgente, LDApp copia anche dati locali collegati.
  - La modale `Modifica su Poleepo` usa una matrice comparativa: immagini in alto, ricerca prodotto padre tra immagini e tabella, tabella campi con colonne `Poleepo`, `LDApp` e `Prodotto padre`; i valori applicabili si scelgono con radio button.
  - La colonna padre viene popolata dopo la ricerca prodotto sorgente; le immagini padre sono selezionabili con checkbox e vengono usate da `Copia dati locali`.
  - `Copia dati locali` trasferisce scheda tecnica (`SchedeProdotti`) se il target non ne ha gia' una, immagini `ProductAsset` selezionate e barcode `Barcode` solo se il target non ha gia' barcode.
- Nella modale `Modifica su Poleepo` e' presente anche `Copia valori da altro prodotto`:
  - `GET /search/scheda_articolo/<cod_art>/publish/poleepo/copy-candidates`;
  - `GET /search/scheda_articolo/<cod_art>/publish/poleepo/copy-values`;
  - vengono proposti solo articoli origine gia' collegati a Poleepo;
  - origine e target devono avere `cod_art` diverso e coppia `descrizione + descrizione_aggiuntiva` diversa;
  - ogni campo editabile viene precompilato col valore remoto dell'origine e mostra accanto il valore letto dall'origine, poi puo' essere variato prima dell'update.
  - il box valore origine viene inserito in modo tollerante sui layout campo annidati, evitando errori DOM `insertBefore`.

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
- bootstrap home:
  - `inject_menus` in `tools/app_factory.py` degrada a `menu_tree: []` se il DB non e' raggiungibile, cosi' la home non va subito in 500.
- agenda template:
  - `templates/agenda.html` e' stato riscritto in UTF-8 dopo un salvataggio con byte non validi che rompevano il render Jinja.
  - i simboli euro e gli accenti rimasti corrotti sono stati normalizzati.
- resta da implementare:
  - UI per mostrare/revertire gli eventi di audit.

- scheda prodotto articoli:
  - la scheda espone la pubblicazione immagini dalle immagini LDApp verso le piattaforme attive dell'articolo;
  - Prestashop ha un upload reale via webservice, mentre gli altri target restano disabilitati fino a implementazione del connettore;
  - il menu contestuale e i drop slot rispettano lo stato `active/supported` per ogni piattaforma.

- impostazioni applicative:
  - nuova pagina hub `/settings`;
  - dashboard iniziale a tile di categoria, con `Utenti` come accesso principale;
  - aggiunti i tile `Banche`, `Circuiti Carte` e `Dispositivi POS` con pagine di gestione dedicate;
  - le aree `Banche`, `Circuiti Carte` e `Dispositivi POS` usano lo stesso pattern del widget utenti: tabella compatta, click riga per modale dettaglio/modifica, form di creazione in modale e azioni rapide di riga;
  - le modali delle aree impostazioni vengono spostate in `document.body` e inizializzate su `shown.bs.modal`/`hidden.bs.modal` per evitare il bug ricorrente di focus/stacking;
  - i POS permettono anche l'associazione dei circuiti;
  - i circuiti carte hanno picker icone in modale e upload logo con preview grafica;
  - il picker icone usa Font Awesome gia' presente nel layout e la modale viene riattaccata al `body` per evitare stacking issues;
  - il logo del circuito non viene azzerato al salvataggio: resta quello esistente finché non si carica un nuovo file;
  - i dispositivi POS presentano i circuiti associati come checkbox invece del multiselect;
  - i record nuovi validano il nome prima dell'insert, per evitare oggetti vuoti lasciati pendenti in sessione;
  - le stesse aree espongono anche azioni esplicite di disattivazione e cancellazione, con blocco se esistono riferimenti storici o associazioni;
  - nuova pagina `/settings/preferences` per configurazioni divise per categoria;
  - nuova pagina `/settings/users` in sola lettura per elenco utenti, ruoli attivi e dati principali;
  - `/settings/users` e' stata resa operativa:
    - click riga utente apre modale dettaglio/modifica;
    - azioni rapide: cambio ruolo, autorizzazioni speciali, reset password, eliminazione;
    - reset password admin usa `PasswordResetToken` con scadenza 24 ore e invio email;
    - autorizzazioni speciali usano `SpecialPermission` e `UserSpecialPermission`;
    - ruoli temporanei riusano `UserRole.valid_from` / `valid_until`.
  - tabella `app_preferences` per persistenza runtime dei parametri;
  - reload runtime delle preferenze ad ogni richiesta dinamica con fallback sui valori base di avvio;
  - editing ruoli nella stessa area impostazioni;
  - `/settings/menus` gestisce la struttura menu con drag&drop, creazione/modifica via modale, azioni rapide inline per ogni riga e restyling dedicato in `static/css/menus.css`;
  - `/settings/import_conflicts` offre risoluzione guidata dei conflitti import con confronto CSV/DB, card dato certo, contatori coda/posizione/duplicati e azioni Usa CSV/Usa DB/Sempre CSV/Sempre DB/Salta;
  - l'import articoli consulta le regole `ImportConflictResolution` e non reinserisce conflitti pending identici gia' in coda;
  - `/settings/api-keys` separa dal vecchio widget configurazione le chiavi e i parametri delle integrazioni esterne:
    - UI tabellare con righe Prestashop, Poleepo, Trello, Slack e VAPID;
    - le tabelle hanno scroll verticale interno per non uscire dal box del widget;
    - azioni per integrazione: modifica in modale, disattiva via override DB vuoto, elimina override DB;
    - creazione/modifica/eliminazione di chiavi custom in `.env.local`, mostrate solo se marcate con commento `LDAPP_DESC`.
  - `/settings/database` gestisce la configurazione `DATABASE_URL`:
    - UI tabellare coerente con gli altri widget impostazioni;
    - campi separati per tipo DB, indirizzo, porta, nome DB, nome utente e password;
    - stringa di collegamento calcolata da form e salvata in `.env.local`;
    - azioni modifica/elimina; le modifiche richiedono riavvio app per applicarsi al motore SQLAlchemy gia' avviato.
  - `/settings/email` gestisce account SMTP codificati e DB-driven:
    - modello `EmailAccount`, con password cifrata tramite `EncryptedString`;
    - account di sistema `general` per reset/notifiche applicative e `assistance` per ticket/attivazioni Horeca;
    - fallback compatibile su `MAIL_*` e `ASSISTANCE_MAIL_*` finche' il relativo account non viene salvato nel DB;
    - elenco compatto degli account e modale unica per creazione/modifica di nome, codice, server, porta, TLS/SSL, username, password, mittente e stato;
    - account aggiuntivi richiamabili dal backend tramite codice con `send_account_mail(code, message)`;
    - configurazione posta in entrata per account: server/porta IMAP, TLS/SSL, username, password cifrata, cartella e flag abilitazione;
    - modali spostate nel `body` prima dell'inizializzazione Bootstrap, con layer dedicato e reset dei pulsanti su apertura/chiusura.
  - Help Desk utente e ticket assistenza:
    - la navbar espone `Help Desk`; `Servizio clienti` resta il menu operativo interno per staff/office;
    - utenti autenticati vedono `Nuova richiesta` e `I miei ticket`, con elenco stato/aggiornamento e accesso alla conversazione;
    - `SupportTicket.public_token` e' un token non prevedibile, distinto dall'ID progressivo, usato per accessi anonimi controllati;
    - il dettaglio ticket consente risposta web e allegati anche senza login quando si possiede il link sicuro;
    - `SupportTicketMessage.source`, `external_message_id` e `in_reply_to` gestiscono origine, deduplica e correlazione RFC;
    - `tools/support_mailbox.py` acquisisce via IMAP risposte e allegati, correla prima gli header RFC e poi `[Ticket #ID]`, e valida il mittente contro l'email del ticket;
    - Celery Beat esegue `config.tasks.sync_support_mailbox_task` ogni 2 minuti; `/settings/email` espone anche sincronizzazione manuale;
    - `SupportTicketMessage.read_by_user_at` e `read_by_support_at` mantengono stati di lettura separati e persistenti;
    - bollino utente sulla voce `Help Desk` e sui ticket con nuove risposte assistenza; bollino staff sulla voce `Assistenza LDApp` e sulle righe con nuovi messaggi cliente;
    - entrambi i conteggi hanno endpoint dedicato e polling frontend ogni 60 secondi; si azzerano solo aprendo il relativo dettaglio dal lato destinatario;
    - le email in uscita includono `[Ticket #ID]`, `Message-ID` e link sicuro alla conversazione;
    - il solo numero ticket non costituisce autorizzazione all'accesso web.
  - `/settings/roles-permissions` separa dal vecchio widget configurazione la gestione ruoli e autorizzazioni:
    - ruoli: creazione, modifica peso/descrizione, eliminazione con ricanalizzazione degli utenti assegnati;
    - autorizzazioni speciali: CRUD su `SpecialPermission.code`/nome/descrizione/stato attivo;
    - cancellazione autorizzazioni: controllo assegnazioni `UserSpecialPermission` e ricanalizzazione verso altro permesso;
    - la pagina mostra anche i riferimenti operativi disponibili: utenti collegati e voci menu con stessa soglia numerica del ruolo.
  - il vecchio widget Configurazione e' stato rimosso dalla dashboard; `/settings/preferences` resta solo come redirect informativo verso `/settings`.
  - entry "Impostazioni" nel menu profilo per gli utenti con peso >= 900.
  - migration audit resa idempotente sui DB dove `cash_day_audit_events` esiste gia', cosi' `db upgrade` non fallisce su `DuplicateTable`.
  - la pagina preferenze ora mostra un warning e non va in 500 se `app_preferences` non e' ancora disponibile nel DB.
  - fix template preferenze: accesso esplicito a `section["items"]` per evitare il conflitto con il metodo `dict.items` in Jinja.
  - le banche (`CashBank`) supportano `logo_path`;
  - la pagina `/settings/banks` permette upload e preview del logo banca;
  - i loghi banca sono salvati in `static/images/banks` e serviti dalla route `settings.bank_logo`;
  - `/cassa/api/banks` restituisce anche `logo_path`.

- chiusura report giornaliero:
  - la route `POST /cassa/api/day/<day_date>/close` aggiorna una `CashClosure` esistente invece di reinserirla;
  - la relazione `CashDay.closure` viene caricata normalmente per evitare falsi negativi sul record gia' salvato;
  - il recupero snapshot usa la stessa relazione caricata, non un `noload`.
  - lo snapshot viene passato attraverso `_json_safe` prima del commit, per evitare errori di serializzazione nel JSONB.
  - il bottone di stampa su giornata chiusa usa lo snapshot gia' salvato e salta la chiamata di chiusura.
  - se la stampa chiude una giornata in modalita' `complete` con vault PRI sbloccato, `/close` restituisce al client il payload completo appena inviato, evitando che la prima stampa usi lo snapshot fiscale privo dei movimenti PRI.
  - su giornate chiuse, `/preview?view=complete` prova a usare la preview salvata nel report completo del vault; se non disponibile, ricalcola live invece di riusare automaticamente lo snapshot fiscale DB.

---

# Versione

Versione: 2.4  
Stato: modulo Agenda/Cassa operativo con CRUD principali attivi, versamenti ed eliminazione versamenti attivi, logica assegni/eventi introdotta, prossimo focus sul KPI Quadratura
- 2026-07-14 cancellazione ordini: la rimozione di uno `SlackOrder` elimina in cascata i relativi `SlackOrderEvent`; su Slack vengono eliminate prima le risposte/allegati dell'app e poi la radice, mentre un thread non interamente eliminabile viene marcato con autore della cancellazione e reaction `:wastebasket:`.
- 2026-07-14 attivazioni Horeca: l'associazione account-anagrafica usa `/settings/api/customer-registries/search`, lookup remoto su tutti i clienti attivi per nome, ragione sociale, codice e partita IVA, condiviso tra elenco attivazioni e dettaglio ticket.
- 2026-06-18: POS configurazione ora gestisce validita' temporale dei circuiti/dispositivi e la lettura storica dei movimenti su giornate chiuse.
- 2026-06-18 compatibilita' retroattiva: `pos_circuits` e `pos_devices` vengono letti senza richiedere subito le nuove colonne di validita' quando il DB non e' ancora migrato.
- 2026-06-18 schema POS: i campi di validita' vengono aggiunti automaticamente a `pos_circuits` e `pos_devices` se mancanti, cosi' le pagine di configurazione non bloccano il lavoro quando il deploy precede la migrazione.
- 2026-06-18 POS circuiti/dispositivi: logo in `static/images/pos`, picker icone custom, relazione `PosDevice.circuits` lasciata dinamica senza eager loading.
- 2026-06-18 POS final: logo in `static/images/pos`, icon picker Bootstrap standard, query esplicita dei circuiti per dispositivo.
- 2026-06-18 POS fix UI: il picker icone dei circuiti viene inizializzato in `extra_js` dopo il bundle Bootstrap, e i preview logo passano dalla route `settings.pos_circuit_logo`.
- 2026-06-19 POS fix loghi circuiti: upload e route dedicata usano `current_app.static_folder`, quindi i loghi caricati dalla gestione circuiti finiscono nel path static reale `static/images/pos`.
- 2026-06-19 banche: aggiunto `CashBank.logo_path` con migration `5e6f708192a3`; gestione upload/preview logo in `/settings/banks`, storage in `static/images/banks`.
- 2026-06-19 chiusura report: `api_close_cash_day()` carica/recupera sempre la `CashClosure` esistente prima di creare una nuova riga, rendendo idempotente la ristampa dopo riapertura e modifica giornata.
- 2026-06-19 snapshot report: `CashClosure.fiscal_snapshot` contiene anche `report_payload` fiscale completo; la stampa di una giornata aperta chiude e stampa lo snapshot appena salvato, mentre una giornata chiusa stampa dallo snapshot salvato o lo rigenera se stale. Le chiusure successive vengono marcate stale e ricalcolate in cascata.
- 2026-06-20/22 report/quadratura: correzione snapshot/report validata dall'utente su due giornate reali e sospensione rimossa.
- 2026-06-20 utenti impostazioni: aggiunti `SpecialPermission`/`UserSpecialPermission` con migration `6f708192a3b4`; `/settings/users` ora supporta modali di modifica, cambio ruolo, autorizzazioni temporanee/speciali, eliminazione e reset password 24 ore.
- 2026-06-20 UI impostazioni: `/settings/banks`, `/settings/pos-circuits` e `/settings/pos-devices` sono state uniformate allo stile `/settings/users` con tabelle, modali detail/edit, azioni rapide e fix preventivo focus/stacking modali.
- 2026-07-13 utenti impostazioni: corretto lo stacking delle modali sopra il backdrop globale e serializzata la transizione tra dettaglio e azioni Ruolo/Autorizzazioni/Reset/Elimina per evitare finestre fuori fuoco.
