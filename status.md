TEST_SYNC_CODEX_20260507_185518
# STATUS.md — aggiornamento Agenda / Cassa
Data aggiornamento: 2026-05-14

---

## 🔄 Stato generale modulo Agenda / Cassa

La base del modulo è attiva e utilizzabile.
Le principali CRUD della giornata risultano operative.
La preview dei KPI e il report diagnostico giornata sono attivi.

Dopo le ultime correzioni, la parte **spese** non fa più esplodere l’applicazione e sono state allineate diverse logiche della modale pagamenti rispetto agli incassi.

---

## Task corrente (metodologia Codex)

- Stato aggiornato al ciclo corrente di sviluppo Agenda / Cassa / Ordini:
  - report giornata completo/fiscale rifinito e collegato a menù
  - modalità fiscale allineata su KPI e report
  - gestione assegni avviata con endpoint, CRUD, stati e status bar riepilogativa
  - gestione menu riparata e resa applicabile senza cambio pagina
  - parser Slack ordini esteso per allegati e indicazioni consegna
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
- Nota upgrade futura menu/permessi:
  - oggi il menu confronta `Menu.weight` con `current_user.max_role_weight`;
  - da valutare una plancia developer per attribuire il peso alle funzioni/route e derivare da li' anche la visibilita' menu, evitando di dichiarare il peso direttamente sulla voce menu.
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
