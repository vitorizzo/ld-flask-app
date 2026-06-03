TEST_SYNC_CODEX_20260507_185518
# STATUS.md — aggiornamento Agenda / Cassa
Data aggiornamento: 2026-06-02

---

## 🔄 Stato generale modulo Agenda / Cassa

La base del modulo è attiva e utilizzabile.
Le principali CRUD della giornata risultano operative.
La preview dei KPI e il report diagnostico giornata sono attivi.

Dopo le ultime correzioni, la parte **spese** non fa più esplodere l’applicazione e sono state allineate diverse logiche della modale pagamenti rispetto agli incassi.

---

## Task corrente (metodologia Codex)

- Aggiornamento 2026-06-02:
  - creato modulo `Spedizioni` raggiungibile da `/shipping`;
  - aggiunta voce menu `Spedizioni` con peso `30`;
  - aggiunta migrazione `c4d5e6f7a8b9_add_shipping_tracking.py`, gia' applicata localmente:
    - `courier_integrations`;
    - `shipments`;
    - `shipment_tracking_events`;
    - `external_orders`;
  - aggiunti modelli:
    - `CourierIntegration`;
    - `Shipment`;
    - `ShipmentTrackingEvent`;
    - `ExternalOrder`;
  - aggiunti file:
    - `routes/shipping.py`;
    - `tools/shipping_connectors.py`;
    - `templates/shipping/index.html`;
    - `static/js/shipping.js`;
    - `static/css/shipping.css`;
  - UI spedizioni:
    - elenco tracking;
    - ricerca per tracking/cliente/riferimento;
    - filtro corriere;
    - creazione manuale spedizione;
    - dettaglio spedizione con eventi tracking;
    - sezione ordini Poleepo importati;
  - seed integrazioni:
    - `brt`;
    - `gls`;
    - `dhl`;
    - `poleepo`;
  - connettori BRT/GLS/DHL:
    - predisposti ma non ancora collegati alle API reali;
    - servono credenziali, endpoint e formato risposta;
  - Poleepo:
    - lette da app config le variabili `POLEEPO_URL`, `POLEEPO_PKEY`, `POLEEPO_PPKEY`;
    - implementato `PoleepoConnector` secondo documentazione ufficiale API `2022-03`;
    - flusso implementato:
      - `POST /oauth/access_token`;
      - `GET /orders`;
      - normalizzazione verso `ExternalOrder`;
    - endpoint import:
      - `POST /shipping/api/poleepo/import`;
    - test reale API:
      - chiamata raggiunge Poleepo;
      - OAuth riuscito con `POLEEPO_PKEY` come `client_id` e `POLEEPO_PPKEY` come `client_secret`;
      - `GET /orders` restituisce ordini reali;
      - import iniziale completato con 100 ordini;
      - import incrementale corretto: `updated_after` ora viene inviato in UTC/RFC3339 senza microsecondi;
      - test rotta import: `200`, importati 2 nuovi ordini;
      - corretto `ExternalOrder.to_dict`: un metodo duplicato degli alert sovrascriveva la serializzazione degli ordini e causava `HTTP 500` nel box ordini Poleepo;
      - test rotta elenco ordini Poleepo: `200`;
      - aggiunto dettaglio spedizioni Poleepo via `GET /shippings/{id}`;
      - aggiunto endpoint `POST /shipping/api/poleepo/sync-shipments`;
      - sincronizzazione reale su 20 ordini: create 15 spedizioni BRT da payload Poleepo;
      - le spedizioni importate usano `parcel_id` come `tracking_number` e `source='poleepo'`;
    - stato operativo:
      - codice pronto;
      - credenziali validate;
      - endpoint `POST /shipping/api/poleepo/import` operativo.
    - Account corrieri:
      - aggiunto modello `CourierAccount`;
      - aggiunta migrazione `d5e6f7a8b9c0_add_courier_accounts.py`, applicata localmente;
      - aggiunta migrazione `e6f7a8b9c0d1_add_courier_account_validity.py`, applicata localmente;
      - creata tabella `courier_accounts`;
      - aggiunto `shipments.courier_account_id`;
      - aggiunti `valid_from` e `valid_to` agli account corriere;
      - password account cifrata con `EncryptedString`/`FERNET_KEY`;
      - aggiunta UI nella pagina `/shipping` per creare/modificare account corriere;
      - le spedizioni possono selezionare un account specifico oppure usare selezione automatica;
      - il refresh tracking prova account compatibili con la data spedizione/ordine, usando account senza date come fallback;
    - BRT tracking-only:
      - implementato connettore su `GET https://api.brt.it/rest/v1/tracking/parcelID/{tracking_number}`;
      - risolto `MISSING PARAM`: il WADL esposto da `OPTIONS` indica header obbligatori `userID` e `password`;
      - il tracking BRT usa header `userID`/`password`, non Basic Auth;
      - test reale su spedizione recente: tracking BRT `200`, eventi salvati e `last_error` pulito;
      - lista spedizioni ordinata per data spedizione dalla piu' recente alla piu' vecchia;
      - aggiunti filtri UI/API per corriere, stato e ciclo `attive/chiuse`;
      - aggiunta visualizzazione data ordine su ordini Poleepo e data spedizione su spedizioni;
      - corretta sync spedizioni Poleepo: ora usa `ordered_at` e non `updated_at`, evitando di importare vecchi ordini 2023 toccati dall'import 2026;
      - spedizioni storiche oltre 180 giorni marcate `expired`/`Storica` e rimosse dalle attive;
      - dettaglio tracking arricchito con riepilogo reale BRT ed eventi con data/ora;
      - inserimento eventi tracking reso idempotente per evitare duplicati sui refresh successivi;
      - endpoint `POST /shipping/api/shipments/refresh-open` operativo;
      - notifiche PWA predisposte su cambi stato `out_for_delivery`, `delivered`, `exception`;
    - GLS/DHL ancora da collegare agli endpoint reali.
  - notifiche/PWA ultimi interventi:
    - introdotto controllo versione app tramite `/app-version.json`;
    - aggiunto `static/js/app_update.js` per polling versione e reload controllato;
    - notifiche ordine arricchite con categoria/tag/azioni testuali;
    - creato dettaglio ordine standalone `/kiosk/order/<id>`;
    - le notifiche ordine ora puntano al dettaglio ordine invece della bacheca generale;
    - per compatibilita' mobile sono stati rimossi SVG e action icon dal payload notifiche, mantenendo PNG sicuro `icon-192.png`;
    - service worker portato fino a `ldapp-cache-v12`;
    - nota: su PC le azioni notifica risultavano visibili; su dispositivi mobili il comportamento dipende da browser/PWA e `Notification.maxActions`.
  - verifiche eseguite:
    - `python -m py_compile` su moduli shipping/Poleepo/app factory;
    - `node --check static/js/shipping.js`;
    - `flask db upgrade` ok fino a `e6f7a8b9c0d1`;
    - route `/shipping/*` registrate.
  - Aggiornamento 2026-06-03:
    - separata la pagina monolitica `/shipping` in tre viste operative:
      - `/shipping/shipments` per consultazione tracking spedizioni;
      - `/shipping/orders` per ordini Poleepo e sync spedizioni collegate;
      - `/shipping/accounts` per gestione account corrieri;
    - `/shipping` resta route padre e reindirizza a `/shipping/shipments`;
    - aggiunta sottNavigazione interna tra le tre sezioni;
    - aggiunti template dedicati:
      - `templates/shipping/shipments.html`;
      - `templates/shipping/orders.html`;
      - `templates/shipping/accounts.html`;
      - `templates/shipping/_nav.html`;
    - aggiunti script dedicati:
      - `static/js/shipping_common.js`;
      - `static/js/shipping_shipments.js`;
      - `static/js/shipping_orders.js`;
      - `static/js/shipping_accounts.js`;
    - aggiunta migrazione `f7a8b9c0d1e2_split_shipping_menu.py` per creare le tre voci figlie del menu `Spedizioni`;
    - dashboard riepilogativa rimandata a quando account, ordini e tracking saranno stabilizzati.
  - Correzione ordini Poleepo 2026-06-03:
    - sistemato layout pagina ordini con scroll interno lista e wrapping testi lunghi;
    - individuata causa ordini mancanti: il connettore leggeva solo `offset=0&max=100`;
    - `PoleepoConnector.import_orders` ora pagina con `offset`/`max` fino a esaurimento pagine;
    - aggiunto pulsante `Importa storico` che invia `force_full=true`;
    - l'import incrementale resta disponibile come `Importa ordini`;
    - `GET /shipping/api/external-orders` restituisce conteggio totale locale e limite visualizzato;
    - verifica lettura remota non distruttiva: Poleepo restituisce 383 ordini nelle prime pagine, contro 102 presenti localmente prima dell'import storico.
  - Correzione spedizioni Poleepo 2026-06-03:
    - lo sync spedizioni non e' piu' limitato a massimo 300 ordini quando viene richiesta la modalita' storica;
    - `POST /shipping/api/poleepo/sync-shipments` accetta `sync_all=true` e `include_old=true` per processare tutti gli ordini Poleepo locali;
    - la risposta espone `processed_orders` e `total_orders`;
    - aggiunto pulsante `Sync storico spedizioni` nella pagina `/shipping/orders`;
    - il pulsante standard `Sincronizza spedizioni` resta limitato agli ultimi ordini/recenti per uso ordinario.

- Stato aggiornato al ciclo corrente di sviluppo Agenda / Cassa / Ordini:
  - report giornata completo/fiscale rifinito e collegato a menù
  - modalità fiscale allineata su KPI e report
  - gestione assegni avviata con endpoint, CRUD, stati e status bar riepilogativa
  - gestione menu riparata e resa applicabile senza cambio pagina
  - parser Slack ordini esteso per allegati e indicazioni consegna
  - notebook tab deduplicato per pagina: riapertura modulo esistente porta il tab in primo piano senza crearne uno nuovo
  - tab log viewer etichettato come `log viewer`
  - layout di gestione menù e visualizzazione log riportati a shell piena con scroll interno
  - gestione menù e log viewer riallineati alla stessa logica di overflow della agenda
  - separata la visuale kiosk: `/kiosk` per la versione dentro la webapp, `/kiosk/board/all` per i display fullscreen esterni
  - rimossi i tab laterali dalla base fullscreen kiosk: la vista pura non monta più il notebook della webapp
  - rubriche clienti/fornitori convertite in pagine dirette con ricerca e indice alfabetico laterale
  - fixato il restack dell'agenda per non spegnere le modali non-agenda (rubriche, gestione menu, ecc.)
  - modale di modifica menu spostata nel body per evitare il piano disabilitato
  - ricerca prodotto per descrizione uniformata alla shell agenda e arricchita con scansione barcode diretta
- Rimossa dal manifesto Codex la procedura RAW/incolla-file e allineato il workflow a lettura diretta repository locale
- Prospettiva AI futura annotata:
  - introdurre un modulo astratto `AIProvider` configurabile, inizialmente su OpenAI API e in futuro sostituibile/affiancabile da provider locale tipo Ollama
  - funzioni previste: trascrizione audio Slack, OCR/riconoscimento testo immagini Slack, assistente vini su catalogo prodotti
  - per l'assistente vini usare approccio RAG: schede tecniche/documentazione indicizzate, risposte basate solo sui dati di catalogo disponibili
  - prevedere cache dei risultati AI su DB, limiti di costo/configurazione, log dei consumi e flag di abilitazione tipo `AI_PROVIDER` / `SLACK_AI_EXTRACTION_ENABLED`
  - evitare di legare il codice applicativo a un singolo vendor: il resto dell'app deve chiamare interfacce interne, non direttamente le API del provider

---

## ✅ Completato / stabile

### Report giornata
- Creato report giornata con vista completa/fiscale:
  - titolo “Report completo giornata dd.mm.yyyy” se vault sbloccato
  - titolo “Report fiscale giornata dd.mm.yyyy” se vault bloccato
- Collegamenti menu previsti:
  - `/cassa/agenda/report` per visualizzare report
  - `/cassa/agenda/report/print` per stampa diretta
- Nel report fiscale:
  - `Totale consegnato` visualizzato uguale a `Totale atteso nel cassetto`
  - dati PRI esclusi
- Nel report completo:
  - intestazione Chiusura senza header colonne
  - aggiunti `Totale x` e `Totale +` sotto `Totale Versabile`
  - `Totale consegnato` resta il valore reale
- Sezione incassi corretta:
  - flag `+` dettagliati
  - `Totale Privati` somma solo flag `x` del cliente `Privato` / `Privati`

### Gestione assegni
- Aggiunta route menu:
  - `/cassa/agenda/checks`
- Aggiunte API:
  - `GET /cassa/api/checks`
  - `POST /cassa/api/checks`
  - `GET /cassa/api/checks/<id>`
  - `PUT /cassa/api/checks/<id>`
  - `DELETE /cassa/api/checks/<id>`
- Aggiunta modale `Gestione assegni`:
  - lista filtrabile per testo, stato, data ricezione da/a
  - creazione assegno
  - modifica dati assegno
  - aggiornamento stato
  - eliminazione solo se non collegato a movimenti/versamenti/prelievi
- Stati gestiti:
  - in pancia / ricevuto
  - spostato
  - anticipato
  - versato
  - incassato
  - insoluto
  - protestato
  - ritirato
- Ogni cambio stato passa da `CashCheckEvent`.
- Aggiunta status bar in fondo alla modale con:
  - totale assegni in pancia
  - totale assegni versati
  - totale assegni insoluti/protestati
- Nota: la gestione assegni è un buon punto di partenza, da rifinire con l’uso reale.

### Modalità fiscale / full
- KPI `Cassetto` in modalità fiscale visualizzato uguale al `Totale di Giornata`.
- In modalità fiscale il click su `Cassetto` non apre la modale.
- In modalità fiscale il pulsante `+` dei movimenti di cassa mostra:
  - “Attenzione! Funzione ancora non implementata”
- Corretto caricamento iniziale vault:
  - UI e movimenti privati ora vengono riallineati allo stato reale all’avvio.

### Filtri quadranti
- Aggiunti filtri contestuali POS:
  - per device
  - per circuito
  - reset filtri
  - totale POS filtrato racchiuso tra parentesi quando un filtro è attivo
- I filtri POS sono sottomenù con valori presenti nel quadrante e voci `tutti` / `nessuno`.
- Aggiunti filtri per:
  - incassi: tipo incasso, flag, cassa/fuori cassa
  - spese: tipo incasso/pagamento, flag, cassa/fuori cassa
  - movimenti di cassa: tipo movimento, direzione
- Corretto comportamento livelli menù contestuali:
  - click su pulsante riga: solo menù riga
  - click destro quadrante: menù riga + quadrante + generale

### Gestione Menu
- Riparata app `Gestione Menu`:
  - drag & drop funzionante anche per sottomenù
  - azioni menù riga ripristinate
  - `Nuovo Menù (root)` ripristinato
  - aggiunto pulsante `Applica`
  - modifiche operative senza cambiare pagina
- Aggiunta gestione separatori.
- Aggiunto flag `visibile/non visibile`.
- Semantica attuale:
  - attivo: voce visibile e funzionante
  - non attivo ma visibile: voce visibile in grigio, funzione non ancora attiva

### Ordini Slack / consegne
- Parser Slack esteso per messaggi con allegati:
  - didascalia usata come testo ordine
  - foto/audio allegati alla card ordine
- Annotata prospettiva AI:
  - trascrizione audio
  - OCR immagini
  - valutazione costi OpenAI API vs locale
- Migliorato parsing consegna:
  - `domani mattina`, `domattina`, `dopo le 17`, fasce orarie e indicazioni simili
  - badge consegna accanto alle azioni card
  - route/pulsante `Riprogramma` per ricalcolare consegne attive
- Aggiunte evidenze card:
  - prossime alla consegna
  - lampeggio se in orario consegna e non in stato `in Consegna`
  - rosso/lampeggio se consegna oltrepassata
  - esclusi gli ordini `annullato` dal lampeggio
- Aggiunta gestione giri:
  - modale gestione giri
  - variazioni una tantum / periodo / definitive
  - giorno, orario e frequenza
  - CRUD giri
  - possibilità di spostare consegna card cliccando sul badge

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

### Consolidamento Agenda / Cassa
- Testare in uso reale la nuova gestione assegni:
  - CRUD
  - cambio stato
  - status bar riepilogativa
  - interazione con versamenti, cassetto e versabile
- Rifinire la modale gestione assegni in base ai casi reali emersi.
- Proseguire rifinitura report giornata:
  - impaginazione finale
  - verifica stampa su una/due pagine
  - eventuali totali aggiuntivi richiesti dall’uso.
- Continuare test regressione modalità fiscale/full:
  - KPI
  - report
  - lock/unlock vault
  - visibilità movimenti PRI.
- Proseguire test ordini Slack:
  - parsing consegna
  - allegati
  - giri e riprogrammazione.

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
- Verificare in produzione la gestione assegni appena avviata:
  - totali status bar
  - duplicati banca/numero
  - cancellazione assegni collegati
  - stati `versato`, `incassato`, `insoluto`, `protestato`, `ritirato`.
- Verificare report fiscale/completo dopo le ultime correzioni:
  - `Totale consegnato` in fiscale uguale ad atteso cassetto
  - `Totale x` / `Totale +` solo in completo
  - `Totale Privati` solo per cliente Privato con flag `x`.
- Valutare sostituzione futura del bump manuale con hook centralizzato SQLAlchemy.
- Sistemare definitivamente gestione robusta chiavetta USB:
  - rimozione improvvisa
  - reinserimento
  - automount
  - recovery da stato autofs/mount incoerente.
- Rimuovere password vault hardcoded nel JS (`TEST123`) quando si passa a soluzione definitiva.

---

## Aggiornamento situazione - 2026-05-19

### Task Agenda / Cassa

- La fase Agenda / Cassa descritta sopra e' da considerare chiusa per il lavoro immediato.
- Le formule e la chiusura cassa sono state trattate nel ciclo precedente; se si dovra' riaprire il tema, rileggere sempre i file reali prima di intervenire.
- Punto da ricordare: `cash_math.py` non va ricostruito da memoria, perche' era gia' stato corretto manualmente e va preso come fonte effettiva.

### Task corrente: import anagrafiche da gestionale

Il lavoro da riprendere dopo aggiornamento Codex e' l'importazione delle anagrafiche esportate dal gestionale.

Stato noto:
- prima di riprendere l'import, e' stata corretta la cancellazione dei task nel monitor basso:
  - `static/js/task_status.js` ora usa `task.task_id` invece di `task.id`;
  - `tools/task_monitor.py` revoca il task e rimuove lo stato Redis dal monitor;
  - `tools/redis_utils.py` scrive le nuove chiavi come `task_status:<id>` e cancella anche le vecchie `task_status: <id>`;
- import anagrafiche corretto e verificato manualmente il 2026-05-19:
  - causa 1: `serve_risorsa()` cercava solo file locali in `EXPORT_FOLDER`; ora usa fallback remoto su `EXPORT_FOLDER_URL/get/<file>`;
  - causa 2: `BusinessRegistry` veniva flushato prima di valorizzare `display_name`, violando il NOT NULL;
  - causa 3: lo storico errori poteva fallire se `Importazione.messaggio` superava 255 caratteri;
  - causa 4: il monitor task nascondeva gli errori, facendo sparire il task anche in caso di fallimento;
  - import manuale verificato: `business_registries=2935`, `business_registry_contacts=2485`, `cash_customers=1970`;
  - riesecuzione idempotente verificata: clienti `unchanged=2002`, fornitori `unchanged=933`, fornitori saltati `3`;
- Prima separazione clienti/fornitori in Agenda/Cassa:
  - `/cassa/api/customers/suggest` ora accetta `kind=customer|supplier|all`;
  - modale incasso cerca solo clienti;
  - modale spesa cerca solo fornitori e non valorizza `customer_id`;
  - dedup risultati per tipo+codice, cosi' CashCustomer e BusinessRegistry con stesso codice non appaiono come doppioni;
  - verificato DB: nessun duplicato per `CashCustomer.codice_cliente`, nessun duplicato per `CashCustomer.partita_iva`, nessun duplicato per `BusinessRegistry(kind, source_code)`.
- Bozza 2026-05-20 per funzioni anagrafiche successive:
  - migration applicata `d4e5f6a7b8c9`;
  - nuove tabelle:
    - `delivery_route_customers`: associa clienti (`BusinessRegistry.kind=customer`) ai giri (`DeliveryRoute`);
    - `registry_contacts`: contatti autonomi riusabili su piu' anagrafiche;
    - `registry_contact_points`: telefoni/email/PEC del contatto;
    - `business_registry_contact_links`: ponte contatto-anagrafica, dissociabile senza cancellare il contatto;
  - nuovo blueprint `/registry`;
  - endpoint pagina da mettere a menu:
    - `/registry/customer-routes` = modale associazione clienti-giri;
    - `/registry/customers` = rubrica clienti;
    - `/registry/suppliers` = rubrica fornitori;
  - API bozza:
    - `GET /registry/api/routes/customers`;
    - `POST /registry/api/routes/<route_id>/customers`;
    - `GET /registry/api/registries?kind=customer|supplier&q=...`;
    - `POST /registry/api/registries/<registry_id>/contacts`;
    - `DELETE /registry/api/registries/<registry_id>/contacts/<contact_id>`;
  - verifiche dopo migration: `DeliveryRoute=8`, `BusinessRegistry customer=2002`, `BusinessRegistry supplier=933`;
  - test API lettura: clienti `A.B.S.` = 3 risultati, fornitori `BAKER` = 1 risultato, clienti-giri `A.B.S.` = 3 clienti + 8 giri.
  - fix permessi 2026-05-20: `routes/registry.py` deve usare `tools.role_required.role_required`, non `routes.decorators.role_required`, per rispettare `active_roles`, `max_role_weight` e wildcard ruoli;
  - verificato con utente `dev` peso `999`: `/registry/customer-routes`, `/registry/customers`, `/registry/suppliers` rispondono `200`.
  - revisione UX associazione clienti-giri:
    - pagine registry dentro `section.welcome-section`;
    - `/registry/customer-routes` mostra in pagina tendina giri e box anagrafiche associate;
    - ogni riga associata ha pulsante `Elimina` che disattiva l'associazione;
    - aggiunti endpoint puntuali:
      - `POST /registry/api/routes`;
      - `POST /registry/api/routes/<route_id>/customers/<registry_id>`;
      - `DELETE /registry/api/routes/<route_id>/customers/<registry_id>`;
    - anagrafiche gia' associate a un giro sono esposte con `assigned_route_id/assigned_route_name` e visualizzate in corsivo/sbiadite;
    - se si seleziona un'anagrafica gia' associata a un altro giro, API risponde `409 needs_confirm` e UI chiede conferma per sostituire;
    - test scrivi/rimuovi eseguito su giro `marsica` e cliente `A.B.S. SPA`: associazione persistita e poi rimossa correttamente.
    - fix visualizzazione multi-associazione: `GET /registry/api/routes/customers` restituisce anche `assigned_customers` separato dai risultati di ricerca, cosi' il box del giro mostra tutte le anagrafiche associate anche dopo una ricerca filtrata;
  - test controllato: due clienti associati allo stesso giro restano entrambi visibili in `assigned_customers` anche con ricerca senza risultati, poi rimossi.
- Bozza 2026-05-20 per plancia ordini giri:
  - migration applicata `e5f6a7b8c9d0`;
  - nuove tabelle:
    - `route_order_board_entries`: stato operativo per cliente/giro/data plancia, nota ordine, consegna pianificata, flag lista fatta e riferimenti Slack;
    - `business_registry_alerts`: avvisi attivi sul cliente con periodo opzionale;
  - nuovo blueprint `/route-orders`, registrato in app factory;
  - endpoint pagina da mettere a menu:
    - `/route-orders/board` = plancia ordini giri, peso funzione staff `30`;
  - API bozza:
    - `GET /route-orders/api/board`;
    - `POST /route-orders/api/entries`;
    - `POST /route-orders/api/routes/<route_id>/delivery-date`;
    - `POST /route-orders/api/entries/<entry_id>/send-slack`;
    - `GET /route-orders/api/registries/<registry_id>/alerts`;
    - `POST /route-orders/api/registries/<registry_id>/alerts`;
    - `DELETE /route-orders/api/alerts/<alert_id>`;
  - UI dentro `section.welcome-section`:
    - tendina giri;
    - data prossima consegna del giro calcolata da `DeliveryRoute` + `DeliveryScheduleRule`;
    - box clienti del giro con telefoni, stato, nota ordine, lista fatta, invio Slack e gestione avvisi;
    - click sulla data in alto crea/aggiorna una variazione una tantum del giro;
    - click sulla data nella riga posticipa la consegna del singolo cliente;
  - reset plancia:
    - la board usa la prossima consegna corrente come `board_date`;
    - quando la consegna avanza, le righe della vecchia plancia non sono piu' caricate, salvo quelle con `planned_delivery_at` posticipata oltre la nuova board date;
  - Slack:
    - invio messaggio su canale del giro con nome cliente e nota ordine;
    - se `lista fatta` e' attiva viene aggiunta reaction `white_check_mark`;
    - se il giro non ha canale Slack reale o manca `SLACK_BOT_TOKEN`, l'API restituisce errore esplicito;
  - verifiche:
    - `py_compile` ok su modelli, blueprint e app factory;
    - `flask db upgrade` ok;
    - test lettura `/route-orders/api/board` con utente `office` peso 40: 200 OK;
    - test scrittura controllato su `route_order_board_entries`: creazione riga, risposta JSON e cancellazione riga test ok.
  - fix 2026-05-21 dopo test utente:
    - recupero telefoni plancia reso esplicito da `business_registry_contacts` e dai contatti riusabili collegati, senza dipendere dalle relationship gia' caricate;
    - gli alert futuri non scaduti sono ora mostrati in plancia come hint/indicatore, non solo quelli gia' attivi alla data odierna;
    - l'errore Slack sull'aggiunta reaction `white_check_mark` non blocca piu' l'invio/salvataggio dell'ordine: viene restituito come warning;
    - verificato API: giro `aquila` mostra i telefoni importati; giro `lago` mostra l'alert futuro di `AMELIE SRL`.
  - revisione 2026-05-21:
    - i telefoni in plancia sono ora visualizzati uno per riga con etichetta e numero cliccabile;
    - aggiunta gestione contatti direttamente dalla riga cliente:
      - pulsante `Contatto` per aggiungere un numero;
      - pulsanti modifica/cancellazione su ogni numero;
      - endpoint dedicati `phone-contacts` per contatti importati e contatti riusabili;
    - l'invio Slack dalla plancia crea/aggancia anche uno `SlackOrder`, cosi' la bacheca ordini puo' gestire gli stati;
    - la reaction `listato` usa la configurazione `OrderStatus.slack_reaction` (`:white_check_mark:`) ed e' obbligatoria: se fallisce, la chiamata torna errore invece che warning;
    - aggiunto pulsante `Annulla ordine`, che applica la reaction dello stato `annullato` (`:x:`), resetta nota/lista fatta nella plancia e aggiorna lo `SlackOrder` ad annullato se presente;
    - verifiche: `py_compile` ok, template Jinja caricato, endpoint route-orders registrati, test controllato creazione/rimozione contatto ok.
  - fix reaction 2026-05-21:
    - `SlackAPI.post_message()` ora restituisce `resp.data` come gia' faceva `send_message`, cosi' la plancia recupera correttamente il `ts` del messaggio Slack;
    - se Slack non restituisce `ts`, `/route-orders/api/entries/<id>/send-slack` torna errore esplicito invece di saltare silenziosamente la reaction;
    - le reaction `lista fatta` e `annulla ordine` vengono aggiunte usando lo stesso percorso delle automazioni: `SlackProcessor.execute_actions()` con action `addReaction`;
    - verificato che gli stati leggono le reaction configurate: `listato -> white_check_mark`, `annullato -> x`.
  - revisione grafica 2026-05-21:
    - aggiunto stylesheet condiviso `static/css/registry_tools.css` per plancia ordini giri, associazione clienti-giri e rubriche;
    - corretto il problema testo bianco su fondo bianco forzando contrasto scuro su pannelli, tabelle, modali, input e liste delle pagine create;
    - la `welcome-section` della plancia/anagrafiche usa larghezza `80vw` con `max-width: 1600px`, cosi' la plancia ordini giri ha piu' spazio utile;
    - verificato caricamento template Jinja: `route_orders/board.html`, `registry/customer_routes.html`, `registry/registry_book.html`.
  - micro-fix 2026-05-21:
    - centrata la `welcome-section` della plancia ordini giri anche quando supera la larghezza del container Bootstrap;
    - rimossa l'evidenza lampeggiante delle card in stato `inconsegna` nella visualizzazione ordini.
- PWA 2026-05-21:
  - implementato primo strato `share_target` nel manifest:
    - action `/pwa/share`;
    - supporto a `title`, `text`, `url` e file `image/*`, `audio/*`, `text/plain`, `application/pdf`;
  - nuovo blueprint `/pwa` registrato in app factory;
  - nuova pagina review condivisione:
    - `/pwa/share/<intent_id>`;
  - nuove API push:
    - `GET /pwa/api/push/config`;
    - `POST /pwa/api/push/subscribe`;
    - `POST /pwa/api/push/unsubscribe`;
    - `POST /pwa/api/push/test`;
  - nuove tabelle migrate con revision `f6a7b8c9d0e1`:
    - `shared_order_intents`;
    - `push_subscriptions`;
  - service worker aggiornato a cache `ldapp-cache-v4` con gestione `push` e `notificationclick`;
  - aggiunto JS globale `static/js/pwa_push.js`;
  - aggiunta voce profilo `Abilita notifiche`;
  - installata dipendenza `pywebpush==2.0.3` e aggiornata `requirements.txt`;
  - generate chiavi VAPID locali:
    - `private_key.pem` / `public_key.pem` ignorate da git;
    - `.env.local` aggiornato con `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY_FILE`, `VAPID_SUBJECT`;
    - corretto encoding `.env.local` rimuovendo BOM iniziale che impediva a `python-dotenv` di leggere `DATABASE_URL`;
  - verifiche:
    - `flask db upgrade` ok;
    - `py_compile` ok;
    - endpoint `/pwa/*` registrati;
    - `GET /pwa/api/push/config` torna `enabled=True`;
    - test controllato share target: creazione redirect `/pwa/share/<id>` e cancellazione bozza ok.
    - test reale notifiche push da browser completato: subscription salvata e notifica ricevuta correttamente;
    - endpoint test push arricchito con dettagli `errors` per diagnosi futura di invii falliti.
  - micro-fix share target 2026-05-21:
    - dopo reinstallazione PWA il target di condivisione compare correttamente tra le destinazioni del telefono;
    - rimossa dalla pagina `/pwa/share/<id>` la nota provvisoria "Bozza ricevuta..." mostrata all'utente;
    - aggiunti pulsanti rapidi `Copia` e `Plancia giri` nella pagina di ricezione ordine condiviso;
    - verificato caricamento template Jinja della pagina share review.
  - evoluzione share target 2026-05-21:
    - la pagina `/pwa/share/<id>` ora permette di selezionare il giro, cercare un cliente appartenente al giro e modificare la nota ordine precompilata;
    - aggiunto invio diretto su Slack dalla pagina share, con creazione/aggiornamento della riga in `route_order_board_entries`;
    - se `Lista fatta` e' spuntato, l'invio applica la stessa reaction usata dalla plancia ordini giri;
    - nuovi endpoint staff:
      - `GET /pwa/api/share/<intent_id>/options`;
      - `GET /pwa/api/share/<intent_id>/customers`;
      - `POST /pwa/api/share/<intent_id>/send`;
    - test controllato endpoint options/clienti ok: 8 giri attivi e clienti restituiti per il primo giro.
  - integrazione ordini condivisi 2026-05-22:
    - aggiunta scelta `Ordine di giro` / `Ordine diretto - Carsoli` nella pagina share;
    - in modalita' diretta la ricerca cliente non e' vincolata al giro e l'ordine viene inviato sul canale del giro `carsoli` (`CAX2A3C9F` nel DB locale);
    - gli allegati condivisi da telefono vengono salvati con metadata persistenti (`id`, `static_path`, `content_type`, `size`) e caricati nel thread Slack dell'ordine;
    - la visualizzazione ordini ora sa servire anche allegati locali `pwa_share`, non solo file privati Slack;
    - gli ordini creati dalla webapp scrivono eventi `SlackOrderEvent` con allegati, cosi' la card in visualizzazione ordini mostra foto/file condivisi;
    - primo allineamento Slack -> app:
      - `message_deleted` marca l'ordine come `cancellato`, lo chiude e resetta l'eventuale riga plancia;
      - `message_changed` aggiorna `raw_text` dell'ordine e la nota plancia collegata;
      - reaction di stato annullato/cancellato da Slack resetta anche la riga della plancia;
    - verifiche: `py_compile` ok su PWA, kiosk, Slack API e Slack processor; endpoint share testati in modalita' giro e diretta; rendering template ok.
  - fix integrazione ordini 2026-05-22:
    - la share page non espone piu' l'azione come invio Slack: pulsante e messaggi parlano di invio a LDApp, con Slack trattato come display collegato;
    - manifest PWA allargato per share file:
      - accetta sia parametro `files` sia parametro `file`;
      - aggiunti `video/*` e fallback `*/*`;
      - i file condivisi senza filename vengono salvati con nome generato da mimetype;
    - aggiunta API Slack `chat_delete` per cancellare messaggi pubblicati dal bot;
    - plancia ordini giri:
      - aggiunto pulsante `Elimina ordine`;
      - nuovo endpoint `DELETE /route-orders/api/entries/<entry_id>` che cancella messaggio Slack, card `SlackOrder` e riga plancia;
      - `Annulla ordine` resta separato e applica la reaction di annullamento;
    - corretto doppio processamento:
      - lo Slack processor ignora i messaggi bot/app non gia' agganciati;
      - se arriva un evento Slack con timestamp gia' presente in `SlackOrder`, non crea una seconda card e al massimo aggancia allegati;
    - notifiche push:
      - aggiunto `send_push_to_staff`;
      - invio push su nuovo ordine da share PWA, da plancia giri e da Slack processor;
    - verifiche: `py_compile` ok su PWA, route-orders, kiosk, Slack API, Slack processor e push notifications; rendering pagina share ok; canale diretto locale risolto su `carsoli` / `CAX2A3C9F`.
  - fix follow-up 2026-05-22:
    - PWA share allegati:
      - `/pwa/share` ora acquisisce tutti i file presenti in `request.files`, indipendentemente dal nome campo usato dal browser (`files`, `file`, chiavi custom, ecc.);
      - se non arrivano file, viene loggata diagnostica con `form_keys`, `file_keys` e `content_type`;
      - test controllato ok: file inviato sotto chiave arbitraria `weirdkey` salvato in `SharedOrderIntent.files` con metadata e path statico;
    - aggiornamento PWA:
      - cache service worker portata a `ldapp-cache-v6`;
      - aggiunto listener `SKIP_WAITING`;
      - manifest link versionato `v=20260522-2`;
      - registrazione service worker forza `registration.update()` e reload su `controllerchange`;
      - manifest e `/pwa/*` esclusi dal cache-first, sempre network-first/no-store;
    - eliminazione ordini:
      - plancia ordini: `DELETE /route-orders/api/entries/<entry_id>` non fallisce piu' tutta l'operazione se Slack non cancella il messaggio; cancella comunque DB/plancia/bacheca e torna eventuale `warning`;
      - bacheca ordini: aggiunto endpoint `DELETE /kiosk/api/order/<order_id>` e voce `Elimina ordine` nel menu della card;
      - eliminazione da bacheca rimuove anche eventuali righe plancia collegate e prova a cancellare il messaggio Slack scritto dal bot;
    - verifiche:
      - `py_compile` ok;
      - rendering PWA ok;
      - test controlled share file con chiave arbitraria ok.
  - diagnostica share allegati 2026-05-22:
    - dal DB locale le ultime condivisioni reali PWA risultavano con `SharedOrderIntent.files=[]`, quindi il file non arrivava al backend dal browser/PWA;
    - aggiunta diagnostica persistente nella bozza quando `/pwa/share` non riceve file:
      - `form_keys`;
      - `file_keys`;
      - `content_type`;
      - `content_length`;
    - la pagina share mostra il box diagnostico "Nessun allegato ricevuto dal dispositivo" invece di fallire silenziosamente;
    - `_upload_shared_files_to_slack` ignora le righe diagnostiche;
    - test controllato ok: share multipart senza file crea diagnostica in `SharedOrderIntent.files`.
  - fix manifest share allegati 2026-05-22:
    - test reale utente: share foto produce POST multipart ma senza campi form e senza campi file (`form_keys=[]`, `file_keys=[]`);
    - manifest PWA reso piu' conservativo:
      - un solo parametro file `name=file`;
      - aggiunti MIME espliciti `image/jpeg`, `image/png`, `image/webp`, `image/heic`, `image/heif`;
      - aggiunte estensioni `.jpg`, `.jpeg`, `.png`, `.webp`, `.heic`, `.heif`, `.pdf`;
      - rimosso doppio descrittore `files/file` e fallback generico `*/*`, che su alcuni Web Share Target puo' dare comportamento ambiguo;
    - manifest versionato a `v=20260522-3` e service worker portato a `ldapp-cache-v7`.
  - fallback Samsung Internet 2026-05-22:
    - test reale utente da Samsung Galaxy S25 / Samsung Internet: share foto continua a produrre multipart vuoto (`form_keys=[]`, `file_keys=[]`), quindi il browser apre la PWA ma non passa il file al Web Share Target;
    - aggiunto fallback operativo nella pagina `/pwa/share/<id>`:
      - input `Aggiungi allegato`;
      - endpoint `POST /pwa/api/share/<intent_id>/files`;
      - upload manuale sostituisce la diagnostica e aggiorna `SharedOrderIntent.files`;
    - test controllato ok: intent con diagnostica + upload manuale `foto.jpg` salva correttamente metadata e path statico.
  - fix cancellazione Slack 2026-05-22:
    - test reale: cancellando da bacheca/Slack, Slack emette talvolta `message_changed` con testo `This message was deleted.` invece di `message_deleted`;
    - lo Slack processor ora tratta quel testo come cancellazione:
      - marca `SlackOrder.status = cancellato`;
      - chiude l'ordine;
      - elimina le righe `RouteOrderBoardEntry` collegate, invece di copiare il testo nella nota plancia;
    - bonifica DB locale eseguita sugli ordini `1059` e `1060`, che erano rimasti con raw text `This message was deleted.`; eliminata la riga plancia collegata `22`;
    - test controllato endpoint `DELETE /kiosk/api/order/<id>` ok: anche se Slack risponde `channel_not_found`, l'ordine locale viene eliminato e la risposta e' `ok=True` con `warning`, non 500.
  - micro-fix share UX 2026-05-22:
    - dopo invio riuscito dell'ordine a LDApp, la pagina `/pwa/share/<id>` tenta `window.close()`;
    - se il browser non consente la chiusura automatica, dopo breve fallback reindirizza a `/kiosk` invece di lasciare la pagina di condivisione aperta.
- Nota upgrade futura menu/permessi:
  - oggi il menu confronta `Menu.weight` con `current_user.max_role_weight`;
  - da valutare una plancia developer per attribuire il peso alle funzioni/route e derivare da li' anche la visibilita' menu, evitando di dichiarare il peso direttamente sulla voce menu.
- Plancia ordini giri / layout operativo 2026-05-23:
  - aggiunta migrazione `a2b3c4d5e6f7_add_document_flag_to_slack_orders.py`;
  - `SlackOrder` ora ha `document_issued` e `document_issued_at` per distinguere ordini con documento emesso / da emettere;
  - `RouteOrderBoardEntry` ora conserva `order_attachments` temporanei, usati per allegare file dalla plancia prima dell'invio Slack;
  - backend plancia:
    - `/route-orders/api/board` restituisce gli ordini reali collegati a ogni cliente, permettendo ordini multipli per lo stesso cliente;
    - filtro `only_with_orders=1` per mostrare solo clienti con ordini;
    - `POST /route-orders/api/direct-orders` crea ordini diretti con allegati e li invia a LDApp/Slack;
    - `GET /route-orders/api/direct-orders` mostra gli ordini diretti attuali;
    - `POST /route-orders/api/orders/<id>/document` aggiorna il flag documento;
    - `POST /route-orders/api/orders/bulk-status` consente evasione massiva/parziale degli ordini selezionati;
    - `POST /route-orders/api/entries/<id>/attachments` salva allegati della plancia prima del post;
    - `POST /route-orders/api/orders/<id>/attachments` aggiunge allegati a ordini gia' postati;
  - UI plancia:
    - due modalita': `Giro` e `Diretti`;
    - righe clienti con ordini multipli visualizzati in schede interne;
    - checkbox documento per ogni ordine;
    - selezione ordini e pulsante `Segna evasi`;
    - inserimento ordine diretto con ricerca cliente, testo, data personalizzata e allegati;
    - il post da plancia porta lo stato chiamata a `Ordine fatto`; l'annullamento porta a `Ordine annullato`;
  - layout applicazione:
    - aggiunti fold laterali rapidi per Agenda, Plancia ordini e Bacheca ordini;
    - visibilita' fold con logica peso: staff vede plancia/bacheca, agenda da peso 40 in su, cliente/visitatore non vede i fold;
    - home trasformata in pulsantiera rapida con inserisci ordine, rubrica clienti, bacheca, informazioni articoli, LD Selection e agenda dove consentita;
    - link LD Selection predisposto su `/static/documents/LD_Selection.pdf` (file PDF da posizionare nel deploy se non presente);
  - verifiche:
    - `flask db upgrade` locale eseguito fino a `a2b3c4d5e6f7`;
    - `py_compile` ok su `routes/route_orders.py`, `routes/kiosk.py`, `models.py`;
    - rendering template plancia ok;
    - endpoint `/route-orders/api/board` testato con utente staff/dev: risposta `ok=True`, 8 giri, 10 clienti nel primo giro locale.
  - follow-up documento 2026-05-23:
    - se un ordine gia' marcato con documento emesso riceve una nuova aggiunta, il flag viene tolto automaticamente;
    - casi coperti:
      - risposta/nota nel thread Slack;
      - nuovo messaggio Slack accodato allo stesso cliente/giorno;
      - modifica del testo root su Slack;
      - allegati aggiunti dalla plancia a ordine gia' esistente;
    - viene registrato un evento `SlackOrderEvent` con motivo del reset;
    - verifica: `py_compile` ok su `routes/route_orders.py` e `tools/slack_processor.py`.
  - correzioni UI plancia 2026-05-23:
    - fold laterali trasformati in tab verticali stile notebook;
    - link Agenda corretto da `/agenda` a `/cassa/agenda`;
    - larghezza plancia portata a `90vw` per migliorare leggibilita';
    - switch `Giro | Diretti` reso esclusivo: la sezione giri viene nascosta quando si passa a Diretti;
    - badge documento spostato sotto il nome cliente:
      - `documenti emessi` se tutti gli ordini del cliente sono flaggati;
      - `doc da emettere` se almeno un ordine non e' flaggato;
    - verifica route Flask: Agenda risulta esposta su `/cassa/agenda`;
    - verifica: `py_compile` ok su `routes/route_orders.py` e `tools/slack_processor.py`.
  - rifinitura notebook/plancia 2026-05-23:
    - linguette rese piu' piccole e aderenti al bordo del foglio, stile rubrica telefonica;
    - linguetta attiva in negativo: sfondo bianco e testo marrone;
    - partial unico `templates/partials/context_tabs.html`;
    - CSS dedicato `static/css/context_tabs.css`;
    - linguette incluse anche in `base_kiosk.html`, quindi visibili anche sulla bacheca ordini;
    - box Diretti uniformato al box clienti del giro con tabella `Cliente / Ordini / Azioni`;
    - colori del pannello plancia rinforzati per evitare note/testi bianco su bianco;
    - render test autenticato ok:
      - plancia contiene tabs, Agenda e sezione `Clienti fuori giro`;
      - bacheca contiene tabs e linguetta Bacheca attiva;
    - verifica: `py_compile` ok su route ordini, Slack processor e kiosk.
  - allineamento funzionale Diretti 2026-05-23:
    - endpoint `/route-orders/api/direct-orders` ora restituisce anche righe cliente con `phones`, `alerts` e `orders`, non solo la lista piatta degli ordini;
    - aggiunti endpoint:
      - `POST /route-orders/api/orders/<id>/status`;
      - `POST /route-orders/api/orders/<id>/delivery`;
    - box Diretti allineato alla struttura del box Giro:
      - colonna cliente;
      - colonna contatti;
      - colonna stato con `Ordine annullato`;
      - colonna lista;
      - colonna ordini;
      - azioni ordine, consegna, avvisi, invia su Slack, annulla;
    - lo stato dei singoli ordini ora e' modificabile anche dalla scheda ordine interna;
    - `Ordine` e `Invia su Slack` nei Diretti aprono la modale di inserimento ordine diretto;
    - `Consegna` nei Diretti aggiorna la data dell'ultimo ordine diretto del cliente;
    - `Avvisi` e contatti nei Diretti usano gli stessi endpoint della vista Giro;
    - verifica endpoint Diretti ok: risposta con `customers`, `phones`, `alerts`, `orders`;
    - render test plancia ok: presenti contatti, stato ordine, annulla e invia Slack per Diretti;
    - verifica: `py_compile` ok su `routes/route_orders.py`.
  - fix Diretti bulk/stati/documenti 2026-05-23:
    - aggiunti nel box Fuori giro i pulsanti `Seleziona ordini` e `Segna evasi`;
    - distinta la differenza tra stato tecnico bacheca e stato operativo plancia:
      - `acquisito`, `listato`, `controllato`, `evaso` vengono mostrati in plancia come `Ordine fatto`;
      - `annullato` viene mostrato come `Ordine annullato`;
      - l'endpoint ora ritorna anche `board_status`;
    - la select degli ordini diretti usa stati operativi `Ordine fatto` / `Ordine annullato`, evitando il fallback errato su `Da chiamare`;
    - `POST /route-orders/api/orders/<id>/status` traduce `ordine_fatto` nello stato tecnico corretto (`acquisito`, oppure mantiene `listato` se gia' listato);
    - reset automatico `documento emesso` esteso:
      - nuovo ordine diretto dello stesso cliente;
      - nuovo ordine da PWA/share dello stesso cliente;
      - oltre ai casi gia' coperti di note/allegati/modifiche sullo stesso ordine;
    - bonifica DB produzione:
      - normalizzato ordine diretto `1074` da `da_chiamare` ad `acquisito`;
      - aggiunto evento `status_change` con `via=normalize_direct_order_status`;
    - verifiche:
      - `py_compile` ok su `routes/route_orders.py` e `routes/pwa.py`;
      - endpoint Diretti ok: primo ordine tecnico `acquisito`, `board_status=ordine_fatto`.
  - fix integrazione plancia/bacheca 2026-05-23:
    - corretto errore 500 dopo invio Slack da plancia Giro:
      - `_ensure_slack_order` usava una variabile `channel_id` non definita dopo il post Slack;
      - ora usa `entry.slack_channel_id`, quindi la card bacheca viene creata nello stesso flusso;
    - invio Slack da Giro e Diretti ora intercetta eccezioni Slack e ritorna errore JSON esplicito `502`, evitando HTTP 500 generici;
    - nuovo ordine diretto resetta eventuali flag `documento emesso` sugli altri ordini aperti dello stesso cliente/canale;
    - aggiunto timbro stato bacheca su ogni ordine in plancia:
      - `Acquisito`, `Listato`, `Preparato`, `Controllato`, `In consegna`, `Evaso`, `Annullato`;
    - gli ordini `Evaso` risultano sbiaditi e non selezionabili per il bulk `Segna evasi`;
    - selezione massiva Giro e Diretti ignora le checkbox disabilitate;
    - bulk status lato backend ignora ordini gia' nello stato target;
    - verifica:
      - `py_compile` ok su `routes/route_orders.py` e `routes/pwa.py`;
      - test `_ensure_slack_order` su DB produzione con rollback ok su entry `26`, senza creazione persistente di nuovi ordini.
  - layout notebook 2026-05-24:
    - `base.html` e `base_kiosk.html` portati a layout a viewport fisso:
      - navbar ancorata in alto;
      - footer ancorato in basso;
      - linguette notebook in colonna fissa a sinistra tra navbar e footer;
      - contenuto della webapp in area centrale scrollabile senza sovrapposizioni;
    - le linguette usano variabili CSS per allinearsi al layout sia in base standard sia in kiosk;
    - il messaggio flash e' stato spostato in overlay fisso sotto la navbar per restare visibile nel nuovo frame;
    - verifica: `py_compile` ok su `routes/route_orders.py` e `routes/pwa.py`.
  - tab pagina dinamico 2026-05-24:
    - aggiunto nel notebook un secondo livello di linguette per le pagine aperte fuori dai tre contesti fissi:
      - le pagine dinamiche si registrano in `sessionStorage`;
      - ogni linguetta ha il titolo pagina e un pulsante `x` di chiusura;
      - la chiusura di un tab dinamico riporta al tab precedente se presente, altrimenti all'ultima linguetta fissa visitata;
    - linguette fisse mantenute immutate:
      - `Agenda`;
      - `Plancia ordini`;
      - `Bacheca ordini`;
    - le route fisse sono state rese precise sulle sole pagine richieste, senza inglobare prefissi più ampi;
    - il layout centrale si allarga solo quando esistono pagine dinamiche aperte;
    - la barra dinamica e' disabilitata sui layout kiosk;
    - verifica: modifiche in `templates/base.html`, `templates/partials/context_tabs.html`, `static/css/context_tabs.css`, `static/css/style.css`, `static/js/base.js`.
  - etichette esplicite tab dinamici 2026-05-24:
    - aggiunta in `static/js/base.js` una mappa label per le pagine aperte piu' comuni, cosi' le linguette non usano piu' nomi grezzi o tecnici;
    - esempi coperti:
      - `Gestione menù`;
      - `Associazione clienti-giri`;
      - `Rubrica clienti`;
      - `Rubrica fornitori`;
      - `Conflitti import`;
      - `Gestione azioni Trello`;
      - `Connessioni Trello`;
      - `Condivisione ordine`;
      - `Installazione app`;
      - `Gestione foto profilo`;
      - `Modifica profilo`;
    - fallback finale ancora basato su titolo pagina e poi sul path leggibile;
    - verifica: route reali allineate con i path usati nella mappa.
  - shell pagina uniforme 2026-05-24:
    - `Agenda`, `Plancia ordini` e `Status ordini` sono state portate tutte a una `welcome-section` piena altezza:
      - la sezione riempie l'area di lavoro;
      - il contenuto interno scorre solo quando supera lo spazio disponibile;
      - sono stati evitati sbordi fuori dal frame della `welcome-section`;
    - `Plancia ordini` non usa piu' il centraggio/traslazione a `90vw`, ma occupa tutta la shell con flex layout;
    - `Status ordini` e' stata racchiusa in una `welcome-section` dedicata, cosi' non resta piu' allo stato brado;
    - le linguette dinamiche restano aggiunte a quelle statiche e la barra notebook continua a vivere nel layout fisso;
    - verifiche:
      - `node --check static/js/base.js` ok;
      - `git diff --check` senza errori di patch.
  - tab dinamici verticali 2026-05-24:
    - le linguette dinamiche sono state riallineate allo stesso orientamento verticale delle fisse;
    - la colonna dinamica resta sotto le fisse e non apre piu' una fascia orizzontale separata;
    - la larghezza laterale occupata dal notebook resta quella delle tab verticali, senza allargare ulteriormente la shell;
    - verifica: `node --check static/js/base.js` ok.
  - bordo pagina notebook 2026-05-24:
    - aggiunta una linea verticale separatrice sul lato destro del notebook per simulare il bordo della pagina;
    - aumentata la spaziatura tra le tab fisse e quelle dinamiche per dare piu' respiro visivo;
    - il bordo viene nascosto sui layout mobili;
    - verifica: `git diff --check` e `node --check static/js/base.js` ok.
  - rifinitura bordo notebook 2026-05-24:
    - il bordo pagina ha ora una linea piu' sottile con lieve ombra e un alone laterale per effetto carta/rubrica;
    - le tab mantengono la stessa geometria verticale, ma il margine visivo lato contenuto e' piu' morbido;
    - verifica: `git diff --check` su `static/css/context_tabs.css` e `node --check static/js/base.js` ok.
  - allineamento linguette notebook 2026-05-24:
    - le linguette ora risultano agganciate alla linea verticale con margine negativo sul lato destro;
    - la linguetta attiva nasconde il tratto di bordo lato contenuto, cosi' non mostra la linea di selezione;
    - le label delle linguette dinamiche sono ruotate di 180 gradi per uniformarle al verso richiesto;
    - verifica: `git diff --check` su `static/css/context_tabs.css` e `node --check static/js/base.js` ok.
  - stack modali notebook 2026-05-24:
    - abbassato il `z-index` del notebook sotto il piano delle modali Bootstrap/Agena per evitare ombre e blocchi di interazione;
    - la linea pagina e le linguette restano visibili sulle viste normali ma non interferiscono con i dialoghi;
    - la linea separatrice e' stata avvicinata al bordo delle linguette per migliorare l'aggancio visivo;
    - verifica: `git diff --check` su `static/css/context_tabs.css` e `static/css/style.css` ok, `node --check static/js/base.js` ok.
  - fix modale agenda 2026-05-24:
    - rimosso il blocco `pointer-events: none` dalla modal underlay dell'agenda, cosi' una modale eventualmente classificata come underlay resta interagibile;
    - il notebook resta piu' basso nel piano degli z-index per non coprire i dialoghi;
    - verifica: `git diff --check` su `static/css/context_tabs.css` e `static/css/agenda.css` ok.
  - modal stack agenda 2026-05-24:
    - la pila delle modali dell'agenda ora segue l'ordine di apertura effettivo invece dell'ordine DOM;
    - l'ultima modale aperta viene forzata in cima con `modal-top`;
    - il blocco agenda risulta verificato con `node --check static/js/agenda.js`;
    - il notebook resta sotto il piano modali anche dopo il restack.
  - z-index modali agenda 2026-05-24:
    - alzati i livelli delle modali/backdrop agenda sopra navbar e footer fissi (`2055/2050`);
    - aggiunta una regola CSS esplicita per `modal.show` e `modal-backdrop.show` dell'agenda;
    - la modale top torna completamente opaca e interagibile;
    - verifica: `git diff --check` e `node --check` ok su agenda/base scripts.
  - modali sopra navbar/footer 2026-05-24:
    - portate le variabili Bootstrap `--bs-modal-zindex` e `--bs-backdrop-zindex` a `2100/2090` sia in `style.css` sia via JS su `body`, per tenere modale sopra navbar/footer senza spegnere tutta la UI;
    - abbassata l'opacita' della backdrop agenda a `0.22` e rimosso il blur, per evitare l'effetto "schermo spento";
    - la backdrop della modale agenda e' stata confinata all'area di lavoro tra navbar, footer e colonne laterali, cosi' header e footer restano liberi;
    - i backdrop multipli non vengono piu' impilati sopra la modale: tutti restano al medesimo livello inferiore al dialogo attivo;
    - le modali agenda vengono spostate nel `body` al bootstrap del JS, per evitare che restino intrappolate nello stacking del contenitore pagina e risultino visibili ma non interagibili;
    - rimossa l'opacita' residua dalla modal underlay dell'agenda, lasciando solo lo spostamento e la saturazione ridotta;
    - la modale attiva deve ora restare pienamente leggibile e cliccabile sopra al notebook e sopra ai fixed header/footer;
    - verifica: `node --check static/js/agenda.js` ok.
  - ld selection notebook tab 2026-05-26:
    - il pulsante home LD Selection punta ora a una route interna `/ld-selection` invece che al PDF statico diretto;
    - aggiunta la pagina contenitore `templates/documents/ld_selection.html` con iframe del PDF;
    - registrata la nuova label in `static/js/base.js` cosi' la pagina apre una linguetta del notebook;
    - verifica: `python -m py_compile routes/documents.py` ok.
  - ld selection per ruolo 2026-05-26:
    - la route `/ld-selection` sceglie ora il PDF in base al ruolo attivo: `LD_Selection_top.pdf` per staff e superiori, `LD_Selection.pdf` per customer, `LD_Selection_pro.pdf` per horeca;
    - per staff e superiori e' rimasto un solo flusso di condivisione con modale intermedia di scelta versione, share nativo e copia link;
    - il PDF viene passato come URL assoluto alla pagina per rendere la condivisione immediata;
    - verifica: `python -m py_compile routes/documents.py tools/app_factory.py` ok.
  - modale share ld selection 2026-05-26:
    - la modale intermedia di condivisione non usa piu' la classe agenda-modal e ha un proprio z-index dedicato (`5000+`) per non ereditare le regole dell'agenda;
    - il backdrop della share modal resta sotto il dialogo e sopra l'iframe del PDF, cosi' la finestra torna cliccabile;
    - il nodo della modale viene spostato nel `body` all'avvio dello script, cosi' non resta intrappolato nella section che contiene l'iframe;
    - prima del `navigator.share` la modale viene chiusa, cosi' lo share sheet non resta sovrapposto al dialogo aperto;
    - la modale apre il focus sulla tendina versione per migliorare l'usabilita';
  - audit log progetto 2026-05-26:
    - il viewer dei log mostra solo i file `.log` base, esclude backup rotati e lock file, e ordina la lista mettendo `main.log` in testa;
    - il viewer valida la selezione e ripiega su `main.log` se arriva un file non ammesso;
    - i log dispersi in `current_app.logger` nei moduli principali (`route_orders`, `pwa`, `trello`, `trello_client`) sono stati riportati ai logger di modulo, cosi' finiscono anche nei file dedicati oltre che in `main.log`;
    - verifica: `python -m py_compile routes/logs_display.py routes/route_orders.py routes/pwa.py routes/trello.py tools/trello_client.py tools/log_utils.py` ok.
  - layout log e plancia 2026-05-26:
    - la pagina log ora usa una `welcome-section page-shell` piena altezza, con il viewer interno che scrolla senza sbordare dal contenitore;
    - la plancia ordini torna a usare un layout flex reale su `routeBoard` e `directBoard`, cosi' la tabella clienti del giro ha overflow verticale raggiungibile oltre le righe iniziali;
    - la modalita' attiva della plancia non viene piu' forzata a `display:block`, evitando il blocco del chain di altezza;
    - il viewer log ha ora un wrapper intermedio `d-flex flex-column` con `min-height: 0`, necessario per attivare lo scroll interno reale;
  - notebook riapertura tab 2026-05-26:
    - il notebook ora identifica i tab dinamici per chiave di pagina (path) e non li duplica quando la stessa vista viene riaperta;
    - il tab della visualizzazione log e' etichettato `Log Viewer`;
    - la pagina `Gestione menù` e' stata portata a layout `page-shell` pieno, con card e tree scrollabili senza sbordo;
- il gestionale espone/esportava file collegati a clienti e fornitori;
- erano stati considerati nomi come `EXP_CLIENTI`, `EXP_FORNITORI`, `ECCLI.CSV`, `ECFOR.CSV` e endpoint sotto `https://ldapp.ldenoteca.it/exported/`;
- nella cartella locale `esportazioni/` risultano presenti al momento `ARTICOLI.CSV`, `GIAC_LD.CSV` e `STAECCLI.pdf`, ma non i CSV anagrafiche clienti/fornitori;
- il task Celery collegato e' `config.tasks.import_anagrafiche_task`, che chiama `tools.importazioni.import_anagrafiche`.

Punto di ripartenza consigliato:
- rileggere `tools/importazioni.py`;
- verificare come vengono risolti percorso/nome file per clienti e fornitori;
- controllare se l'import si aspetta CSV locali, file remoti da `/exported`, oppure entrambi;
- verificare struttura dei modelli anagrafica/business registry in `models.py`;
- riprodurre l'errore con un comando mirato prima di modificare codice.

### Nota operativa per nuova chat / post aggiornamento

Se la chat viene riaperta dopo aggiornamento, ripartire da:

`Import anagrafiche gestionale non funzionante: controllare tools/importazioni.py, config.tasks.import_anagrafiche_task, file esportati clienti/fornitori e mapping verso modelli anagrafica.`
