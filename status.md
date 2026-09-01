TEST_SYNC_CODEX_20260507_185518
# STATUS.md — aggiornamento Agenda / Cassa
Data aggiornamento: 2026-08-29

## 2026-08-29 - PayByLink autonomi da Amministrazione

- Predisposta la voce `Manda un link di pagamento` per `office`: importo e descrizione, generazione Nexi, copia negli appunti, invio a email libera, utente LDApp o cliente e storico dei link/invii.
- Il workflow usa tabelle proprie e non interferisce con pratiche contabili, fatture selezionate o checkout XPay HPP dei clienti Horeca.
- Invii SMTP eseguiti esclusivamente in background e registrati come `queued/sent/failed`; ricerca utenti/clienti limitata e caricata su richiesta.
- Payload e webhook seguono le specifiche ufficiali `POST /v2/orders/paybylink`: ordine univoco massimo 18 caratteri, scadenza a data, URL pubblici senza slash finale, token e validazione completa della notifica `PAY_BY_LINK`.
- Interfaccia mobile responsive con modale spostata nel `body` per evitare il noto problema di stacking/focus. API key assente: pagina consultabile e generazione disabilitata fino alla configurazione Nexi.
- Nuova migration head `b9c0d1e2f4a6`; dopo il deploy eseguire `python -m flask --app app.py db upgrade` prima del riavvio di web app e worker Celery.

## 2026-08-26 - Comunicazione bonifici dall'area contabile Horeca

- Coordinate bancarie rifinite: IBAN italiano mostrato nel formato `XX X XX XXXXX XXXXX XXXXXXXXXXXX` senza modificare il valore canonico copiato; la modalita' di impostazione `dev` e' piu' larga e usa testi, campi, switch e pulsanti maggiorati anche su smartphone. Cache key `payments3`.
- Correzione compensazione: oltre alle fatture `001` sono selezionabili le note di credito `002`; il totale e le allocazioni conservano il segno contabile. Sul caso reale cliente `01978`, 5.051,91 euro di fatture meno 923,67 euro di NC produce correttamente un bonifico netto di 4.128,24 euro; resta possibile scegliere una fattura e una NC soltanto. Il netto comunicato deve comunque essere maggiore di zero.
- Attivata la selezione delle fatture pagabili nell'ultimo snapshot, con conteggio e totale in tempo reale e barra azione compatibile con quella dei processi in background.
- Il cliente puo' allegare una contabile PDF o immagine (massimo 12 MB), indicare data, CRO/riferimento e nota. La richiesta crea una pratica `awaiting_accounting`, blocca le partite da nuove comunicazioni e conserva allegato e audit in area privata.
- La pagina mostra le pratiche ancora aperte e permette di riscaricare la contabile soltanto agli utenti autorizzati per la stessa anagrafica o al ruolo esatto `dev`.
- Aggiunte coordinate bancarie centralizzate con pulsante di consultazione e copia IBAN. Il ruolo `dev` modifica intestatario, IBAN, banca, BIC/SWIFT, indirizzo, causale, note e visibilita'; l'IBAN e' validato anche con checksum MOD-97.
- Selezione, upload e coordinate sono ottimizzati sia per smartphone standard sia per touch ad alta risoluzione, con modali fullscreen scrollabili e senza sovrapposizioni.
- Nuova migration head `c4d5e6f7a0b1`; dopo il deploy eseguire `python -m flask --app app.py db upgrade` prima del riavvio.

## 2026-08-25 - Prime basi area contabile clienti Horeca

- L'intera area contabile e' touch-first: intestazione, filtro/selettore Developer, riepiloghi, avvisi, paginazione e movimenti sono ottimizzati per smartphone. Le righe contabili diventano schede verticali e non richiedono zoom o scorrimento orizzontale.
- Come nelle altre aree LDApp sono previste due scale: smartphone standard fino a 820 px (o qualunque dispositivo touch) e touch ad alta risoluzione da 821 px, con controlli da 92 px, tipografia e spazi maggiorati per Galaxy S25. Inclusi safe-area e cache key `payments2`.
- Accesso reso esplicito per ruolo, senza soglie di peso: `customer_horeca` vede soltanto i clienti assegnati; `dev` (nome verificato nella tabella `roles`) apre la medesima vista in modalita' anteprima e dispone del selettore filtrabile di tutte le anagrafiche cliente attive.
- Aggiunta l'associazione molti-a-molti `CustomerRegistryMembership`: un utente puo' operare per piu' clienti e piu' utenti possono essere autorizzati sullo stesso cliente, mantenendo `User.customer_registry_id` come cliente principale compatibile con i flussi esistenti.
- La migration `b3c4d5e6f9a0` crea le associazioni e importa automaticamente tutti i collegamenti Horeca gia' presenti, senza rimuovere o riscrivere l'associazione storica.
- L'attivazione Horeca e la configurazione dei collegamenti ordine registrano ora anche la nuova membership; l'inserimento ordini continua a usare il cliente principale.
- Nuova area protetta `/customer-account/`, disponibile ai clienti Horeca, con scelta dell'anagrafica autorizzata, ultimo aggiornamento, totali Dare/Avere/saldo e movimenti contabili paginati. La pagina e' responsive e mostra soltanto dati dell'anagrafica effettivamente assegnata all'utente.
- Predisposto il dominio delle pratiche di pagamento: checkout online tramite provider esterni, comunicazione bonifico e contestazione di una partita, con allocazioni, allegati privati, audit degli eventi e stato operativo LDApp separato dallo stato contabile TeamSystem.
- Le azioni usano una chiave deterministica composta dai campi stabili MATRIXWS e mai l'ID volatile della riga importata. Una futura chiave nativa della scadenza esposta dal servizio potra' sostituire questa composizione senza legare le pratiche agli snapshot.

## 2026-08-16 - Cambio stato ordine da notifica su smartphone

- Il click sulla push ordine continua ad aprire `/kiosk/order/<id>`, ma il dettaglio ha ora una UI mobile dedicata: stato corrente leggibile, select a piena larghezza, pulsante esplicito `Aggiorna stato` e feedback accessibile senza alert.
- Su smartphone il pannello stato resta sticky durante lo scorrimento, usa target touch da almeno 50 px e safe-area; intestazione, metadati, testo e pannelli sono stati compattati per viewport stretti.
- Da 680 px in su rimane la griglia rapida desktop di tutti gli stati. Dopo un aggiornamento, select, badge, griglia e stato interno vengono sincronizzati senza reload.
- Aggiornate le cache key di CSS e JavaScript del dettaglio ordine.
- Correzione Galaxy S25 e dispositivi touch ad alta risoluzione: la variante desktop richiede ora anche mouse e supporto hover, non soltanto una viewport larga. Il dettaglio usa cache key `mobile-status3` e risposta HTTP `no-store`.
- Aggiunta la seconda scala mobile gia' adottata nel resto dell'app: sui dispositivi touch con viewport dichiarata da almeno 821 px (come S25) contenitore, testi, metadati, selettore, pulsante, pannelli e allegati hanno dimensioni maggiorate. Cache key aggiornata a `mobile-status4`.

## 2026-08-16 - Inserisci ordine ottimizzato per smartphone

- La modale `Inserisci ordine` della Plancia ordini e' ora fullscreen sui dispositivi touch, con corpo scrollabile, header/footer fissi, campi e lista clienti dimensionati per il tocco.
- Sono previste due scale: smartphone standard fino a 820 px e touch ad alta risoluzione da 821 px, con controlli da 92-94 px e tipografia maggiorata per Galaxy S25.
- La modale si apre subito mostrando il caricamento clienti; la ricerca e' temporizzata, scarta risposte superate e l'invio espone validazione, avanzamento ed errori inline. Cache key `direct-order-mobile1`.

## 2026-08-16 - Rubrica clienti e contatti su smartphone

- La fisarmonica anagrafica mostra i contatti con nome, ruolo, telefono/email e note su righe separate; numeri ed email sono direttamente azionabili con `tel:` e `mailto:`.
- Sezioni, testi e pulsanti Modifica/Dissocia sono dimensionati per il tocco nelle due scale mobile standard e ad alta risoluzione S25.
- Il form Nuovo/Modifica contatto e' fullscreen, scrollabile e a campi impilati su tutti i touch; tastiera telefono/email coerente col tipo selezionato, validazione e stato salvataggio inline. Cache key aggiornata a `book2`.
- Integrato il Contact Picker nativo: su browser Android compatibili e contesto HTTPS il pulsante `Importa dalla rubrica del telefono` acquisisce, previa scelta esplicita dell'utente, nome e primo telefono condiviso oppure email. Browser non compatibili mantengono l'inserimento manuale; cache key `book3`.
- Aggiunto il fallback vCard alla rubrica clienti: Safari/iOS e gli altri browser privi di Contact Picker possono selezionare un file `.vcf`; nome e recapiti vengono mostrati nell'anteprima prima del salvataggio. Limite file 2 MB; cache key `book4`.
- Esteso il Web Share Target PWA alle vCard: su Android/Chrome con LDApp installata, la condivisione di un contatto apre l'anteprima con scelta del cliente; lo stesso flusso viene usato dal selettore `.vcf` della rubrica.
- Il parser vCard importa tutti i telefoni/email e, quando incorporata, la foto `PHOTO`; l'immagine viene validata, ridimensionata a 512x512, convertita in JPEG e conservata nell'area privata `instance/registry_contact_photos`, mentre il file `.vcf` originale non viene salvato.
- Aggiunti avatar nella rubrica, riuso del contatto quando un recapito identico esiste gia' e migration `ce5f60718293`; manifest versionato `20260816-vcard1`. Su iOS resta necessario il selettore file per assenza di Web Share Target in Safari.

## 2026-08-13 - QR home e totale consegnato nel report Agenda

- Identificata la causa residua della modale QR: il backdrop globale e' a `z-index: 12040`, mentre la modale QR conservava lo z-index Bootstrap `2100`; pur essendo nel `body`, risultava quindi visivamente presente ma non interattiva. `appQrModal` e' ora esplicitamente a `12050` e la cache CSS e' stata aggiornata.
- Nel riepilogo di chiusura del report Agenda, `Totale consegnato` mostra come importo la somma dei soli prelievi titolare `take_type=serale`. La somma di tutti i prelievi, serali e parziali, viene riportata tra parentesi nell'etichetta come `totale prelevato`; i calcoli contabili e le API restano invariati.
- Aggiornata la cache key di `agenda.js` per rendere immediata la nuova stampa dopo il deploy.

## 2026-08-13 - Home e monitor processi in background

- La modale QR della home viene trasferita direttamente nel `body` e aperta con un'istanza Bootstrap esplicita; rimosso il trigger dichiarativo duplicato che poteva lasciare backdrop/focus sopra la modale.
- Il monitor dei task e' sempre visibile nelle pagine degli utenti autenticati, anche quando non esistono attivita', e mostra separatamente conteggio attivi, errori e avanzamento medio dei soli processi attivi.
- L'elenco dettagli ha altezza massima e scroll verticale su desktop, tablet e mobile; messaggi e nomi provenienti da Redis vengono sottoposti a escaping prima del rendering.
- Causa degli circa 80 errori: le chiavi `task_status:*` di errore venivano salvate senza TTL e l'endpoint escludeva soltanto lo stato `completato`, presentando per sempre ogni errore storico come processo attivo. I nuovi stati hanno timestamp e TTL (24 ore per attivi, 7 giorni per errori).
- Gli errori terminali mostrano `Rimuovi` invece di `Stop`; il comando cumulativo `Rimuovi errori archiviati` elimina soltanto errori/revoche dal monitor Redis senza inviare revoke ai task attivi. Lo stop di un processo vero resta disponibile e non forza piu' il segnale Unix `SIGKILL`.
- Endpoint di stato, dettaglio, stop e pulizia sono ora autenticati. Verificati sintassi Python/Jinja/JavaScript, lifecycle Redis simulato e `git diff --check`.

## 2026-08-11 - Verifica situazioni contabili via MATRIXWS

- Il catalogo CONFWS identifica `1011/1 - Estrazione scadenze` come servizio standard read-only piu' vicino all'attuale `EC_CLI.CSV`.
- Le schermate CONFWS confermano che `1011/1` usa la Vista `251 - Scadenze per WS`, archivio tecnico `WKSCADWS`, senza Adattatore e con versione configurata `20260100`.
- La scheda Request e' vuota: il servizio standard non accetta filtri configurati, quindi la lettura restituisce l'intera vista. La Response contiene esattamente sette campi tecnici: `WKSCADWS-DTDOC`, `WKSCADWS-DTSCAD`, `WKSCADWS-NRDOC`, `WKSCADWS-TEFF`, `WKSCADWS-STATO-EFF`, `WKSCADWS-IMPEFF`, `WKSCADWS-CODCF`.
- La chiamata sincrona senza filtri viene accettata ma termina con HTTP 408 interno TeamSystem. Lo stesso payload tramite `EVWSASYNC` parte correttamente e il polling `/www/matrixws/batch/response` completa il batch in circa due minuti; durante l'elaborazione il server usa HTTP 500 + `BATCH_NOT_FINISHED` come stato transitorio.
- Il batch reale contiene 98.291 scadenze: 96.098 chiuse e 2.193 aperte. La Response standard espone soltanto `CodCli`, `Data Doc.`, `Data Scadenza`, `NrDoc`, `Tipo Effetto`, `Stato effetto` e `Importo`.
- Il servizio standard non e' equivalente allo snapshot contabile dell'app: l'ultimo `EC_CLI.CSV` contiene 1.814 movimenti di 186 clienti e richiede Dare/Avere, data registrazione, descrizioni, causale e riferimento. Sulle scadenze aperte del `1011`, 956 righe hanno un codice presente sia tra clienti sia tra fornitori e manca il discriminante del tipo; il confronto esatto su codice/date/documento/importo non trova sovrapposizioni con lo snapshot corrente.
- L'importazione produttiva resta quindi file-based. Per la sostituzione REST occorre una personalizzazione che replichi `MOESEQ-LD` oppure arricchisca una copia del `1011` almeno con tipo cliente/fornitore, segno Dare/Avere, data registrazione, ragione sociale, descrizioni, causale, riferimento e numero rata; il trasporto dovra' usare il batch asincrono.
- Il servizio e' stato duplicato come `500003/1` e nella Request e' stato aggiunto `WKSCADWS-STATO-EFF`. Il diagnostico usa ora versione `20260100` e filtro esatto `Stato effetto = Aperto`; questa prova non modifica ancora l'importazione produttiva.
- La prima prova di `500003/1` restituisce HTTP di trasporto 200 ma errore applicativo `ERR_PARAM_REQUEST - Non sono presenti tutti i parametri della request`: il filtro non e' stato ancora eseguito. Prima di correggere il payload occorre acquisire il JSON prodotto dal comando CONFWS `Salva request`, che rappresenta il contratto effettivo della copia personalizzata.
- L'export reale `docs/transport/500003_1.json` spiega l'errore: nella Request e' presente soltanto `WKSCADWS-TIPODIST`, non `WKSCADWS-STATO-EFF`; riporta inoltre `Versione=20260001`. Prima di ripetere il test bisogna sostituire il campo Request con `WKSCADWS-STATO-EFF` e riesportare il contratto.
- CONFWS sostituisce sistematicamente `WKSCADWS-STATO-EFF` con `WKSCADWS-TIPODIST` anche dopo rimozione e nuovo inserimento. Non e' un errore dell'utente: nella vista `WKSCADWS` lo stato e' disponibile in output ma non come parametro di selezione; il solo input esposto dalla vista e' il tipo distinta. Il `500003/1` non puo' quindi filtrare lato server le sole righe `Aperto` con la configurazione standard della vista.

## 2026-08-10 - Import anagrafiche ogni 30 minuti in background

- Celery Beat accoda `config.tasks.import_anagrafiche_task` ai minuti `.00` e `.30` di ogni ora.
- Il messaggio scade dopo 25 minuti se non e' ancora stato preso in carico, evitando il recupero tardivo di esecuzioni ormai obsolete.
- L'intero flusso resta nel worker Celery e anche l'avvio manuale usa `.delay()`, senza eseguire l'importazione nel processo web.

## 2026-08-10 - Clienti e fornitori dalla stessa chiamata MATRIXWS

- Ogni ciclo esegue una sola lettura del servizio `500001/1` e partiziona la risposta CLIFOR esclusivamente tramite `CF-TIPO`: `1` nei registry `customer`, `2` nei registry `supplier`, `0` scartato come record tecnico.
- `CFCOD` viene normalizzato a cinque cifre per entrambi i tipi. Lo stesso codice puo' esistere una volta per tipo grazie alla chiave distinta `(kind, source, source_code)`; solo il ramo cliente sincronizza `CashCustomer` e relativi alias.
- Deduplicazione, controllo delle identita' discordanti e guardia sui precedenti record contaminati vengono applicati separatamente a clienti e fornitori prima dell'upsert transazionale.
- Il file `exp_for.csv` non viene piu' letto. Clienti e fornitori sono stati rimossi dalla configurazione dei trasferimenti file-based; restano file-based articoli, giacenze, barcode e situazioni contabili.

## 2026-08-09 - Import anagrafiche clienti tramite MATRIXWS

- Il task anagrafiche non legge piu' il file export clienti: usa `POST EVWSSYNC`, servizio personalizzato `500001/1`, versione `20260001`, operazione `read`, ditta `1`.
- Dal 2026-08-10 anche i fornitori provengono dalla stessa risposta MATRIXWS; entrambi i rami condividono lo stesso upsert idempotente di `BusinessRegistry` e contatti, mentre `CashCustomer` riguarda soltanto i clienti.
- Il mapping salva area, zona e codici statistici 1-5; `CF-STAT2` e' la chiave cluster Action. Le descrizioni non esposte non vengono azzerate su record gia' presenti.
- Il rinnovo del secret scaduto e il salvataggio cifrato vengono eseguiti automaticamente anche dal task di importazione.
- Il riepilogo del task segnala chiavi tecniche mancanti e annota i campi da aggiungere alla Response: descrizioni area/zona/categoria/sottocategoria/statistici, cellulare, fax e PEC/email alternativa.
- `BusinessRegistry` e' stato esteso con colonne dedicate e indice `(kind, statistical_code_2)`; migration `cd4e5f607182_add_business_registry_matrixws_fields.py`.
- Verificati mapping campione, sintassi Python, head Alembic `cd4e5f607182` e `git diff --check`. La chiamata reale e l'upsert DB richiedono deploy, migration e test dal server con accesso Tailscale.

## 2026-08-09 - Isolamento modale test MATRIXWS

- Il pulsante `Verifica connessione` e' annidato nella riga che apre la configurazione API; il suo handler ora blocca esplicitamente default e propagazione del click prima di mostrare `matrixwsTestModal`.
- Rimosso il trigger Bootstrap dall'intera riga API: l'apertura della configurazione e' ora gestita esplicitamente solo per click su zone non interattive, eliminando alla radice la doppia apertura e i conflitti di focus/backdrop.
- Tutte le modali della pagina Chiavi API sono trascinabili dall'intestazione su viewport desktop; posizione e stili vengono ripristinati alla chiusura, mentre su mobile rimane il comportamento responsive standard.

## 2026-08-09 - Contratto codici cliente MATRIXWS

- Il servizio personalizzato `500001/1` e' stato alleggerito in TeamSystem e restituisce ora chiavi JSON univoche per area, zona, categoria, sottocategoria e `CF-STAT1`...`CF-STAT5`, senza espansioni descrittive.
- Il cliente `CFCOD=11` conferma un caso Action valorizzato: `CF-STAT2=1`.
- Il diagnostico passa temporaneamente al servizio dizionario `3/1` e cerca la chiave esatta `TIPOREC=02`, `CODICEX=000001`, `TIPO=0` per verificare la descrizione dell'Action 1.
- La prima chiave esatta `02/000001/0` ha restituito `ERR_REC_NOT_FOUND`. Il test prova ora in una sola esecuzione 11 combinazioni controllate di padding `CODICEX` e `GT05-TIPO` (`1`, `0`, spazio), interrompendosi al primo record valido e mostrando tutti gli esiti senza segreti.
- Tutte le 11 combinazioni hanno restituito `ERR_REC_NOT_FOUND`: il problema non e' il padding di `CODICEX` ne' `GT05-TIPO`; non e' verificato che il gruppo Action corrisponda tecnicamente a `GT05-TIPOREC=02`.
- Prossimo punto: duplicare `3/1` nelle personalizzazioni (proposto `500002/1`), lasciare vuota la Request ed esporre in Response `GT05-TIPOREC`, `GT05-CODICEX`, `GT05-TIPO`, `GT05-DESC`; una lettura senza filtri fornira' il dizionario reale.
- Il servizio personalizzato `500002/1` e' stato creato. Il diagnostico interroga ora il dizionario completo con `Operazione=read` e `TabellaCampi=[]`, mostrando al massimo 25 righe e il totale ricevuto.
- La lettura senza filtri di `500002/1` restituisce ancora `ERR_REC_NOT_FOUND`: la personalizzazione ha conservato una semantica di lettura puntuale per chiave e non sta enumerando GTAB0500. Prima di altri payload occorre verificare in CONFWS Parametri, Gestione campi, Request e Response del nuovo servizio.
- Screenshot CONFWS verificati: `500002/1` e' attivo, Output JSON, Request realmente vuota e Response corretta sui quattro campi; la sorgente e' pero' `Gestione campi = Tabellare`, tabella `GTAB0500-X` (Raggruppamenti statistici alfanumerici), archivio `GTABE`. Il comportamento conferma che questa modalita' esegue una lettura per chiave, non una scansione completa come la Vista CLIFOR.
- Poiche' la sorgente Tabellare e' bloccata e `Adattatore` richiede codice TeamSystem specifico, nella Request di `500002/1` e' stato aggiunto soltanto `GT05-TIPOREC`. Il primo tentativo ha usato la chiave minima a lunghezza fissa (due spazi) con operatore `>=`.
- Anche la chiave minima a spazi con `>=` ha restituito `ERR_REC_NOT_FOUND`; il test ha quindi provato quattro forme esatte del solo gruppo Action (`02`, spazio+`2`, `2`+spazio, `2`).
- Il test delle varianti ha stabilito che `GT05-TIPOREC` e' numerico: `02` e' valido ma inesistente, mentre spazio+`2` produce `ERR_NUMERIC_FIELD`. Il diagnostico usa ora il minimo numerico `0` con `>=`, mantenendo come unico campo Request `GT05-TIPOREC`.
- Anche `GT05-TIPOREC=0` con `>=` restituisce `ERR_REC_NOT_FOUND`: `500002/1` Tabellare non enumera GTAB0500 tramite Request parziale. I tentativi sul dizionario diretto vengono sospesi.
- Strategia corretta: importare direttamente da `500001/1` tutti i codici anagrafici e statistici; `CF-STAT2` e' gia' sufficiente come chiave di cluster Action. Le descrizioni, attualmente vuote, sono un arricchimento successivo e non bloccano importazione o clusterizzazione.

## 2026-08-08 - Accesso persistente dal menu profilo

- Il checkbox `Ricordami` gia' presente nel login e' nuovamente collegato a `login_user(..., remember=True)` quando selezionato.
- Il menu profilo espone `Rimani connesso` / `Non restare connesso`; il comando agisce sul solo dispositivo corrente e la disattivazione non chiude la sessione in corso.
- Il remember cookie e' HttpOnly, SameSite Lax, dura 365 giorni e rinnova la scadenza durante l'uso dell'app.
- Nuova route autenticata `POST /profile/remember-login`; gli eventi sono registrati dal logger `auth` senza salvare token.
- Verificati sintassi Python, parsing Jinja e `git diff --check`.

## 2026-08-08 - Estrazione clienti personalizzata MATRIXWS

- Connessione, autenticazione, rinnovo secret e lettura sincrona verificati sul servizio standard `1000/1`: risposta applicativa `200` con 3.234 anagrafiche.
- Il servizio standard e' stato duplicato dall'utente nelle personalizzazioni come `500001/1`, aggiungendo area, zona e i codici statistici 1-5 sia come codice sia come descrizione.
- Il diagnostico `POST /settings/api-keys/matrixws/test` interroga ora `500001/1` con versione `20260001`, operazione `read`, ditta `1` e nessun filtro; la risposta resta limitata a 25 record in UI con conteggio totale.
- La lettura reale di `500001/1` risponde correttamente con stato applicativo `200` e restituisce anagrafiche, area, categoria/sottocategoria e campi statistici personalizzati.
- Il contratto non e' ancora importabile in sicurezza: la chiave JSON `CF-ZONA` compare ripetutamente nello stesso record e un parser JSON conserva soltanto l'ultima occorrenza. Anche le uscite statistiche `GT05-*|9000xx|` devono essere associate con certezza ai campi 1-5.
- Dopo l'aggiunta delle descrizioni il servizio puo' superare i 25 secondi del client sincrono; il solo diagnostico `500001/1` usa ora un timeout di lettura di 120 secondi. L'import periodico definitivo dovra' usare il dispatcher asincrono MATRIXWS, senza tenere aperta una richiesta browser.
- Il tentativo di filtro `CFCOD = 11` non e' stato applicato dal servizio perche' il campo non e' configurato nella Request; l'anteprima applicativa ha comunque limitato a 25 i 3.234 record ricevuti.
- Nota storica superata il 2026-08-09: la Response e' stata semplificata con alias univoci e l'estrazione e' ora collegata all'upsert di `BusinessRegistry`; le descrizioni restano l'arricchimento successivo.

## 2026-08-04 - Configurazione TeamSystem MATRIXWS

- Aggiunta al tile `Chiavi API` la sezione `TeamSystem MATRIXWS`.
- Campi disponibili: indirizzo server, ambiente, start, applicativo (default `MULTI`) e secret Bearer.
- Il secret segue il sistema esistente `AppPreference`: storage cifrato, campo vuoto dopo il salvataggio e mantenimento del valore se non viene reinserito.
- I valori sono caricati nella configurazione runtime tramite le chiavi `MATRIXWS_*`; non sono ancora eseguite chiamate verso TeamSystem.
- Corretto il focus delle modali del tile Chiavi API: sono portate nel `body`, hanno lifecycle esplicito dei pulsanti e `z-index` superiore al backdrop globale.
- Verificati compilazione Python, parsing Jinja e `git diff --check`.
- Prossimo punto: inserire i dati noti e reperire sull'installazione lo Swagger statico, la start e il servizio di lettura anagrafiche/clienti.

## 2026-08-05 - Test read-only TeamSystem MATRIXWS

- Aggiunto nella riga MATRIXWS del tile `Chiavi API` il pulsante `Verifica connessione`.
- Il backend usa server, ambiente, start, applicativo e secret cifrato gia' presenti nella configurazione runtime.
- Il test replica la richiesta GET con body della collection Postman verso `EVWSSYNC`, usando `CodiceWS 500008` e `Operazione: read`.
- Il secret e' utilizzato solo nell'header Authorization e non viene restituito alla UI o incluso nei messaggi diagnostici.
- La verifica TLS resta abilitata; un certificato non valido o non corrispondente all'IP produce un'indicazione esplicita verso l'uso del DNS Tailscale.
- Verificati compilazione Python, costruzione endpoint, parsing Jinja e `git diff --check`. Nessuna chiamata reale e' stata eseguita dall'ambiente locale.
- Prossimo punto: deploy, compilazione di `start=gamma` e `applicativo=GAMMA`, quindi esecuzione del test dalla UI e analisi della risposta.
- Dopo un `401`, il test richiama una sola volta `pgsecrenew` con il Bearer scaduto, valida il nuovo valore, lo salva cifrato in `AppPreference` e ritenta la richiesta originale.
- Se rinnovo o persistenza falliscono, il vecchio secret non viene sovrascritto; nessun valore vecchio o nuovo viene inviato al browser o scritto nei log diagnostici.
- Il parser del rinnovo riconosce anche i nomi campo TeamSystem prefissati/suffissati (es. `JSsecret`); in caso di formato ancora ignoto espone solo nomi, tipi e lunghezze della risposta, mai i valori.
- Verificato dal manuale TeamSystem e dalla risposta reale che `pgsecrenew` restituisce `auth.headers.Authorization: Bearer PGAUTH-...`; il parser rimuove il solo prefisso `Bearer ` e salva cifrato il token `PGAUTH-...`.
- Letta l'esportazione reale `docs/transport/CONFWS-000.xlsx`: `CodiceWS 500008` non e' configurato in `GALASSIA`; il test usa ora `CodiceWS 3`, schema 1, `Estrazione informazioni statistiche (GTAB0500)`, attivo e read-only.
- Servizi reali rilevanti per i prossimi passi: `25/1 CFEST08 - READ` e `1000/1 Estrazione clienti/fornitori`; non vengono ancora richiamati per evitare estrazioni anagrafiche non filtrate.
- Il successivo export testuale `CONFWS-000.gam` conserva esplicitamente `Codice 3`: l'ipotesi degli zeri iniziali e' stata rimossa e il diagnostico usa nuovamente il codice esatto esportato. Il file e' solo un catalogo e non include versione, Request o Response.
- Quattro screenshot CONFWS del servizio `3/1` mostrano la versione reale `20260001` (la collection esterna usava erroneamente `20250005`), azienda/ditta 1, Request `GT05-TIPOREC`, `GT05-CODICEX`, `GT05-TIPO` e Response `GT05-CODICEX`, `GT05-DESC`, `GT05-TIPOREC`.
- Il test statistico usa ora `Versione 20260001` e filtra `GT05-TIPOREC = 02`, corrispondente al secondo raggruppamento statistico `Action` indicato dall'utente.
- Metodo HTTP allineato al manuale TeamSystem/Postman: `EVWSSYNC` viene chiamato con `POST` e body JSON; la collection esterna usava invece un GET con body non standard.
- Letto `docs/transport/3_1.json`, generato dal pulsante CONFWS `Salva request`: per questo servizio `Operazione` deve essere vuota e `TabellaCampi` deve contenere nello stesso oggetto tutti i campi `GT05-TIPOREC`, `GT05-CODICEX`, `GT05-TIPO`, inizialmente vuoti e senza `operatore`.
- Il diagnostico replica ora esattamente il template TeamSystem; eventuali filtri Action verranno aggiunti solo dopo una prima risposta valida.
- Dopo che `POST + request CONFWS` ha restituito lo stesso `500 UnhandledException`, il diagnostico usa esplicitamente `GET + body`, come la collection Postman (`disableBodyPruning`). E' la prima prova che combina metodo della collection e payload reale dell'ambiente.
- La pagina ufficiale `MANUALE_WEBSERVICE.1.25.htm` chiarisce il formato dei servizi standard in lettura: `CodiceWS`, `Schema` e `Ditta` numerici, nessun campo `Versione`, `Operazione: read`, `TabellaCampi: []` per lettura senza filtri. Il test `3/1` replica ora questo formato con metodo POST.
- `3_1.json` viene trattato come template dei campi configurati (utile per nomi Request), non come prova che valori vuoti e `Operazione` vuota costituiscano una chiamata eseguibile.
- Il test temporaneo sul servizio standard `1/1` ha isolato con successo infrastruttura e autenticazione. Il diagnostico e' tornato al servizio obiettivo `3/1`, usando la struttura esportata da CONFWS in `3_1.json` e valorizzando `Operazione: read`.
- 2026-08-06: individuata la chiave risorsa case-sensitive dell'ambiente: la sigla amministrativa `GALASSIA` e' registrata in `mwsresources.json` come `env:galassia`; con `MATRIXWS_ENVIRONMENT=galassia` EVWSSYNC risponde HTTP 200 e autentica correttamente.
- La risposta applicativa `ERR_PARAM_REQUEST` ha confermato il trasporto funzionante. Il confronto con l'esempio ufficiale TeamSystem conferma il payload `1/1` senza `Versione`; occorre confrontarlo con la scheda Request della configurazione locale CONFWS, che puo' richiedere campi diversi.
- Il servizio `3/1` risponde HTTP 200 e, con i tre campi esportati valorizzati a stringa vuota, restituisce `ERR_REC_NOT_FOUND`: MATRIXWS interpreta quindi quel record come chiave esatta vuota. Il diagnostico usa ora la lettura senza limiti documentata (`TabellaCampi: []`, identificativi numerici e nessuna `Versione`).
- La lettura `3/1` con `TabellaCampi: []` restituisce `ERR_PARAM_REQUEST`, confermando che la configurazione locale rende obbligatori tutti i campi Request. Il test usa ora la chiave composta minima del gruppo Action (`GT05-TIPOREC: 02`, altri segmenti vuoti) con operatore `>` per estrarre i record successivi senza cercare una chiave vuota esatta.
- CONFWS indica lunghezze fisse Request `GT05-TIPOREC=2`, `GT05-CODICEX=6`, `GT05-TIPO=1`. Le stringhe di lunghezza zero spiegano il precedente errore COBOL `Reference modifier range error ... length = 0`; il test riempie ora i segmenti vuoti con rispettivamente 6 e 1 spazi.
- Il manuale MATRIXWS definisce l'operatore `A partire` come `>=`. Poiche' la chiave `02` con segmenti a spazi non trova record, il diagnostico parte dalla chiave minima completa a lunghezza fissa (`00`, `000000`, `0`) con `>=`, rimandando il filtro Action alla risposta.
- Il test usa il secret rinnovato gia' cifrato nell'app, evitando di esporlo o copiarlo in Postman.

## Regola prioritaria modali

Quando si implementa o si modifica una modale, il bottone di conferma va inizializzato su `shown.bs.modal` e ripulito su `hidden.bs.modal`.
Non va mai lasciato affidato al solo stato iniziale del DOM perché nel progetto tende a restare disabilitato o con handler residui al primo utilizzo.

## Regola universale logging

Ogni modulo nuovo o modificato deve usare il sistema centralizzato `tools.log_utils.get_logger("<nome_modulo>")`.
Gli eventi operativi e gli errori devono essere scritti contemporaneamente:

- nel file dedicato `logs/<nome_modulo>.log`;
- nel log aggregato `logs/main.log`.

Il logger di modulo deve coprire almeno avvio, conclusione, identificativi tecnici utili, conteggi, cambi di stato, errori gestiti e traceback degli errori imprevisti.
I task asincroni devono usare nel decorator `log_task` il logger del modulo funzionale, non soltanto il logger generico `tasks`.
Gli errori gestiti e assorbiti dal flusso devono comunque essere registrati nel logger di modulo.
Nei log non devono mai comparire password, token, cookie, chiavi API o altri segreti; dati identificativi come email o ID vanno registrati soltanto quando sono necessari alla diagnosi amministrativa.
Ogni implementazione deve verificare che almeno un evento significativo compaia sia nel file dedicato sia in `main.log`.

---

## 🔄 Stato generale modulo Agenda / Cassa

La base del modulo è attiva e utilizzabile.
Le principali CRUD della giornata risultano operative.
La preview dei KPI e il report diagnostico giornata sono attivi.

Dopo le ultime correzioni, la parte **spese** non fa più esplodere l’applicazione e sono state allineate diverse logiche della modale pagamenti rispetto agli incassi.

---

## Task corrente (metodologia Codex)

- Aggiornamento 2026-07-21 - menu Eventi:
  - `Eventi > Calendario Eventi` ora punta a `/events/`, la stessa pagina aperta dal pulsante Eventi della home;
  - modifica distribuita tramite migrazione dati `a4b5c6d7e8f9_update_events_calendar_menu_route.py`.

- Aggiornamento 2026-07-21 - ritaglio intelligente scansione assegni:
  - dopo foto/selezione viene aperto il confronto tra originale e assegno estratto;
  - OpenCV rileva il quadrilatero, elimina sfondo/contorno e corregge la prospettiva;
  - l'utente conferma il ritaglio oppure mantiene l'originale;
  - se i bordi non sono affidabili il ritaglio viene disabilitato con indicazione di usare uno sfondo contrastato;
  - endpoint protetto `/cassa/api/checks/scan/crop-preview`, testato con immagine prospettica sintetica.

- Aggiornamento 2026-07-21 - scansione assegni:
  - acquisizione da fotocamera posteriore o file nella Gestione assegni e nell'inserimento Agenda, anche per pagamenti multipli;
  - upload protetto JPG/PNG/WebP, massimo 8 MB, con verifica reale dell'immagine tramite Pillow;
  - file conservati in `instance/check_scans`, non esposti nella cartella pubblica `static`;
  - anteprima, sostituzione e rimozione nella modale assegno;
  - stampa costo collegata automaticamente alla scansione;
  - migrazione `93a4b5c6d7e8_add_cash_check_scan.py` applicata e test upload/lettura/rimozione superato.

- Aggiornamento 2026-07-21 - stampa professionale calcolo assegno:
  - titolo centrato e intestazione cliente/numero assegno bianca su fascia scura;
  - storia organizzata in tabella senza bordi con colonne data, voce, note, addebiti e pagamenti;
  - riepilogo contabile allineato con dovuto, pagamenti, residuo ed eventuale saldo e stralcio;
  - sezione finale predisposta per l'immagine dell'assegno, con segnaposto finché la scansione non sarà disponibile.

- Aggiornamento 2026-07-21 - separazione storia assegni / Agenda:
  - spese, penali e pagamenti registrati nello storico assegno non generano movimenti Agenda;
  - modifica o cancellazione di un evento storico non aggiorna e non elimina eventuali vecchie spese Agenda collegate;
  - rimossa dalla modale evento la selezione della banca contabile;
  - gli eventuali movimenti Agenda preesistenti restano invariati e sono gestibili manualmente.

- Aggiornamento 2026-07-21 - seconda revisione UI assegni e pagamenti:
  - Gestione assegni ridotta a filtri persistenti, tabella, totali e pulsanti finali;
  - form assegno reso parte reale della modale nuovo/modifica, eliminando il trasferimento della card errata;
  - sottotitolo storico reso bianco e leggibile;
  - cambio stato spostato in una modale dedicata;
  - aggiunta modale pagamenti con inserimento, modifica e cancellazione in cronologia;
  - calcolo costo spostato in modale dedicata e stampabile, con pagamenti sottratti dal dovuto;
  - migrazione `8293a4b5c6d7_add_cash_check_payments.py` applicata e CRUD pagamenti testata end-to-end.

- Aggiornamento 2026-07-21 - leggibilità e correzione storico assegni clienti:
  - filtri persistenti con pulsanti `Applica` e `Ripristina`;
  - form nuovo/modifica assegno spostato in una modale dedicata;
  - apertura dello storico anche cliccando la riga dell'assegno;
  - modifica e cancellazione di ogni evento, compresi gli step iniziali importati, con riallineamento dello stato corrente;
  - sincronizzazione delle spese Agenda collegate durante modifica/cancellazione evento;
  - prospetto costo (importo, spese, penali e totale dovuto) e saldo e stralcio persistente;
  - migrazione `718293a4b5c6_add_check_settlement_amount.py` applicata e verificata;
  - test end-to-end superato per correzione insoluto→versato, nuova spesa, saldo e stralcio e cancellazione evento.

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
    - aggiunto pulsante `Importa storico spedizioni` nella pagina `/shipping/orders`;
    - il pulsante standard `Importa spedizioni` resta limitato agli ultimi ordini/recenti per uso ordinario.
  - Correzioni UI/processo spedizioni 2026-06-03:
    - nella lista spedizioni viene mostrato esplicitamente il nome account corriere associato;
    - aggiunto filtro `Account corriere` nella pagina `/shipping/shipments`, oltre al filtro macro `Corriere`;
    - lista spedizioni e dettaglio hanno scroll indipendenti;
    - i pulsanti `Importa spedizioni` e `Importa storico spedizioni` sono stati spostati nella pagina `/shipping/shipments`;
    - import storico ordini e import storico spedizioni vengono avviati come task Celery in background;
    - il monitor task globale mostra avanzamento tramite Redis;
    - corretto monitor task globale:
      - non va piu' in HTTP 500 se Redis non e' raggiungibile;
      - usa `CELERY_BROKER_URL` come fallback per host/porta/db Redis se `REDIS_HOST` non e' impostato;
      - la barra task viene posizionata sopra il footer fisso;
    - aggiunti task Celery:
      - `config.tasks.import_poleepo_orders_task`;
      - `config.tasks.sync_poleepo_shipments_task`;
      - `config.tasks.refresh_open_shipments_task`;
    - Celery Beat pianifica import ordini Poleepo, sync spedizioni Poleepo e refresh tracking aperte;
    - arricchimento dati BRT da payload tracking salvato: data spedizione, riferimento e destinatario/indirizzo quando BRT li restituisce;
    - verifica non distruttiva su payload BRT: recuperati `shipped_at`, riferimento e localita/provincia destinatario da record esistente.

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

`Schede prodotto: completare la gestione immagini per piattaforma partendo da ProductAsset, routes/search.py, templates/scheda_articolo.html e static/js/scheda_articolo.js.`

---

## Aggiornamento 2026-06-11 - Schede prodotto / immagini piattaforme

Contesto ripreso:
- ristrutturato import articoli da Prestashop;
- dati prodotto targetizzati per fonte/piattaforma;
- campi piattaforma gia' visualizzati nella scheda prodotto;
- immagini prodotto con badge di provenienza;
- badge presenza piattaforme per Prestashop, Poleepo, Ebay, Amazon;
- import prodotti Poleepo gia' presente.

Intervento eseguito localmente:
- esteso `routes/search.py` con metadati immagine piu' completi e slot piattaforme;
- aggiunto endpoint `POST /search/scheda_articolo/<cod_art>/images`;
- upload immagini da PC tramite LDApp salvato in `static/images/products/ldapp/`;
- nuovo asset registrato come `ProductAsset(source_platform='ldapp')`;
- deduplica tramite `content_hash` per articolo;
- immagini legacy e vecchi asset `manual` mappati nello slot `LDApp`;
- aggiornata `templates/scheda_articolo.html` con barra thumbnail piattaforme sopra il carousel;
- aggiunto pulsante upload manuale e pulsante creazione immagine disabilitato;
- aggiunto menu contestuale su immagine con azioni verso Prestashop/Poleepo/Ebay/Amazon disabilitate;
- predisposto drag/drop su slot piattaforma, con azione esterna ancora non implementata;
- aggiornato `static/js/scheda_articolo.js` per upload async, context menu, drag/drop e selezione immagine da slot.

Verifiche eseguite:
- `python -m py_compile routes/search.py` ok;
- `node --check static/js/scheda_articolo.js` ok;
- render template scheda prodotto su articolo reale `BB01502` ok;
- serializzazione `BB01502`: 1 immagine, slot `prestashop` popolato.

Stato operativo:
- upload immagini LDApp implementato;
- pubblicazione immagine verso piattaforme esterne non implementata;
- Ebay/Amazon restano disabilitati;
- creazione nuova immagine resta disabilitata, da discutere in seguito.

Follow-up 2026-06-11:
- aggiunto pulsante `Chiudi` nella testata della scheda prodotto;
- il pulsante torna alla pagina precedente tramite `history.back()`;
- se non esiste cronologia utile, ripiega su `/search/ricerca_x_descrizione`;
- verifica `node --check static/js/scheda_articolo.js` ok;
- render template scheda prodotto `BB01502` ok con pulsante presente.

Fix plancia ordini 2026-06-11:
- individuato errore di associazione ordini tra `PIZZERIA CORRADO SAS di MOSCA S.` e `BALLISTIC SRLS`;
- causa: `_orders_for_customers()` interpretava una `SlackOrder.customer_key` numerica prima come `BusinessRegistry.id` e solo dopo come `BusinessRegistry.source_code`;
- caso reale:
  - Pizzeria Corrado: `BusinessRegistry.id=1178`, `source_code=01232`;
  - Ballistic SRLS: `BusinessRegistry.id=1232`, `source_code=01286`;
  - la chiave ordine `01232` veniva convertita in intero `1232`, finendo sulla riga Ballistic;
- correzione in `routes/route_orders.py`: match esatto su `source_code` prima del fallback su ID numerico;
- verifica mapping giro `marsica`:
  - Ballistic -> ordine `1172`;
  - Pizzeria Corrado -> ordini `1174`, `1241`.

Follow-up scheda prodotto permessi 2026-06-11:
- verificati ruoli reali DB:
  - `staff=30`;
  - `office=40`;
  - `admin=100`;
- aggiunta soglia `OFFICE_ROLE_WEIGHT = 40` in `routes/search.py`;
- `get_product_by_code()` espone `can_manage_images` e `can_publish_products`;
- utenti sotto office non vedono:
  - badge provenienza immagini;
  - badge piattaforme;
  - barra thumbnail piattaforme;
  - upload immagini;
  - menu contestuale invio piattaforme;
- endpoint `POST /search/scheda_articolo/<cod_art>/images` rifiuta utenti sotto office;
- verifiche:
  - `python -m py_compile routes/search.py` ok;
  - `node --check static/js/scheda_articolo.js` ok;
  - render simulato ruoli `20/30/40/100`: strumenti visibili solo da `40` in su;
  - helper ruolo: `30=False`, `40=True`.

Follow-up plancia ordini / associazione Slack 2026-06-11:
- problema affrontato: ordini arrivati da Slack con nome cliente diverso dall'anagrafica non comparivano sulla riga cliente del giro;
- causa tecnica: `tools/slack_processor.py` salva `SlackOrder.customer_key` come chiave normalizzata dal testo Slack, mentre la plancia agganciava gli ordini a `BusinessRegistry` tramite `source_code`/ID;
- aggiunta funzione `_route_orders_for_board()` in `routes/route_orders.py` per avere una base unica degli ordini del giro/data;
- aggiornata `_orders_for_customers()` per risolvere gli ordini tramite `_registry_for_order()`, includendo anche match esatti su `display_name`/`legal_name`;
- aggiunta `_unmatched_orders_for_customers()` e campo API `unmatched_orders` in `GET /route-orders/api/board`;
- aggiunto endpoint `POST /route-orders/api/orders/<order_id>/customer`:
  - valida `BusinessRegistry(kind='customer', is_active=True)`;
  - aggiorna `SlackOrder.customer_display` e `SlackOrder.customer_key`;
  - registra `SlackOrderEvent(type='customer_link')` con valori precedenti e nuovi;
- aggiornata UI `templates/route_orders/board.html`:
  - box `Ordini da associare` sopra la tabella clienti;
  - modale di ricerca cliente e conferma associazione;
  - pulsante link sulle card ordine gia' visibili per correggere manualmente associazioni;
- verifica DB reale:
  - giro `aquila`, data consegna `2026-06-12`;
  - `matched_orders 1`;
  - `unmatched [1281]`;
- verifiche tecniche:
  - `python -m py_compile routes/route_orders.py` ok;
  - `node --check` sullo script estratto da `templates/route_orders/board.html` ok;
  - render template `route_orders/board.html` ok con `associateOrderModal` e `unmatchedOrdersPanel` presenti.

Fix layout plancia ordini 2026-06-11:
- corretto box `Ordini da associare` in `templates/route_orders/board.html`;
- aggiunti `min-width: 0`, contenitore body interno e wrapping forzato su testo/metadati degli ordini;
- su viewport stretti il pulsante `Associa` passa sotto il testo per evitare overflow orizzontale;
- verifica `node --check` sullo script estratto dal template ok.

Secondo fix layout box ordini da associare 2026-06-11:
- rimossa la griglia a due colonne dalle card degli ordini non associati;
- ogni card ora e' verticale, con azione `Associa` sotto il testo;
- aggiunti limiti espliciti `width/max-width/min-width/overflow` su panel, lista, card e body;
- applicato `word-break: break-all` sui testi ordine/metadati per impedire overflow anche con token lunghi;
- verifica `node --check` sullo script estratto dal template ok.

Fix associazione clienti-giri 2026-06-11:
- corretto overflow dati in `templates/registry/customer_routes.html`;
- aggiunti vincoli locali su pagina, panel, `table-responsive`, tabella e risultati rapidi;
- tabella associazioni impostata a `table-layout: fixed` con scroll orizzontale interno al box;
- risultati di `Aggiungi anagrafica` resi verticali e wrappabili;
- le modali `.registry-tools-modal` della pagina vengono spostate in `document.body` prima dell'istanza Bootstrap;
- gestita classe `registry-tools-modal-open` per mantenere z-index/backdrop coerenti;
- verifiche:
  - `node --check` sullo script estratto da `templates/registry/customer_routes.html` ok;
  - render template `/registry/customer-routes` ok con `routeCustomerAddModal` presente.

Follow-up scroll associazione clienti-giri 2026-06-11:
- la sezione `customer-routes-page` ora usa layout flex verticale;
- il panel `Anagrafiche associate` occupa lo spazio disponibile con `min-height: 0`;
- la `.table-responsive` interna ha `overflow: auto`, quindi la lista clienti del giro scorre dentro il box;
- verifica `node --check` sullo script estratto da `templates/registry/customer_routes.html` ok.

Diagnosi versabile 2026-06-12:
- ricostruita sequenza saldo versabile giorno per giorno dal DB;
- sul 2026-06-12 il calcolo restituisce:
  - saldo precedente `29794.22`;
  - versabile giornata `-218.81`;
  - assegni postdatati `678.85`;
  - totale versato oggi `2080.00`;
  - debito contanti incasso `0.00`;
  - saldo versabile risultante `28174.26`;
- non risulta un versamento contanti oltre il massimo consentito: il debito incasso resta zero;
- dati reali del 2026-06-12:
  - `CashDeposit id=35`, tipo `versamento_incasso`, contanti `2080.00`, banca `MPS`;
  - `total_corrispettivi=0`;
  - incassi cash `625.90`;
  - incassi POS da pagamenti `405.92`;
  - POS da `PosMove` `1250.63`;
- causa probabile del disallineamento visibile: giornata 2026-06-12 con corrispettivi non ancora registrati, mentre i POS sono gia' sottratti dal versabile fisico;
- simulazione 2026-06-12:
  - con corrispettivi `0`: versabile giornata `-218.81`, saldo `28174.26`;
  - con corrispettivi `1250.63`: versabile giornata `1031.82`, saldo `29424.89`;
  - con corrispettivi `1710.73`: versabile giornata `1491.92`, saldo `29884.99`;
- da verificare funzionalmente: se il deposito MPS `2080.00` del 2026-06-12 e' corretto come versamento incasso di saldo pregresso oppure se appartiene a un'altra giornata/tipologia.

UX modale POS Agenda 2026-06-13:
- aggiornata `static/js/agenda.js` per la modale `#posModal`;
- all'apertura, focus automatico su `#posMoveAmount` con valore selezionato;
- premendo `Tab` dall'importo il focus passa direttamente alla tendina `#posMoveCircuit`;
- premendo `Enter` nella modale viene eseguito `savePosMove()`;
- premendo `Esc` la modale viene chiusa senza salvare;
- verifica `node --check static/js/agenda.js` ok.

UX modale movimenti di cassa Agenda 2026-06-13:
- aggiornata `static/js/agenda.js` per la modale `#cashMoveModal`;
- all'apertura, focus automatico su `#cashMoveAmount` con valore selezionato;
- premendo `Tab` dall'importo il focus passa direttamente al campo `#cashMovePerformedBy` (`Chi`);
- premendo `Enter` nella modale viene eseguito `saveCashMove()`;
- premendo `Esc` la modale viene chiusa senza salvare;
- verifica `node --check static/js/agenda.js` ok.

UX modale Incasso/Spesa Agenda 2026-06-13:
- aggiornata `static/js/agenda.js` per la modale unica `#opModal`;
- premendo `Enter` nella modale viene eseguito `saveOperation()` sia per incassi sia per spese;
- premendo `Esc` la modale viene chiusa senza salvare;
- alla chiusura viene riabilitato `#opSaveBtn` in caso di stato residuo;
- verifica `node --check static/js/agenda.js` ok.

UX modale conteggio fondocassa Agenda 2026-06-13:
- aggiornata `static/js/agenda.js` per la modale `#drawerCountModal`;
- all'apertura, focus automatico sulla quantita' della moneta `0.10` / `0,10`, con valore selezionato;
- in assenza del taglio `0.10`, fallback sul primo campo quantita' disponibile;
- la navigazione successiva resta affidata al `Tab` naturale sui tagli successivi;
- premendo `Enter` nella modale viene eseguito `saveDrawerCount()`;
- premendo `Esc` la modale viene chiusa senza salvare;
- `#drawerSaveBtn` viene disabilitato durante il salvataggio e riabilitato in uscita;
- verifica `node --check static/js/agenda.js` ok.

Fix selezione iniziale conteggio fondocassa 2026-06-13:
- reso robusto il lookup del taglio `0.10` usando confronto numerico su `data-denom`;
- i campi quantita' `.drawer-qty` passano da `type="number"` a `type="text"` con `inputmode="numeric"` e `pattern="[0-9]*"`, per permettere selezione completa del valore;
- il focus/selezione viene applicato sia con `requestAnimationFrame` sia con fallback `setTimeout(120)`, evitando race con il focus trap della modale Bootstrap;
- verifica `node --check static/js/agenda.js` ok.

UX modale e-commerce Agenda 2026-06-13:
- aggiornati `templates/agenda.html` e `static/js/agenda.js` per la modale `#ecommerceModal`;
- campo `#ecoAmount` convertito a `type="text"` con `inputmode="decimal"` per selezione affidabile del valore;
- all'apertura, focus automatico su `#ecoAmount` con valore selezionato;
- premendo `Tab` dall'importo il focus passa direttamente a `#ecoDescription`;
- premendo `Enter` nella modale viene eseguito `saveEcommerce()` come click su `Aggiungi` / `Salva modifica`;
- `#ecoAddBtn` viene disabilitato durante il salvataggio e riabilitato in uscita;
- verifica `node --check static/js/agenda.js` ok.

UX modale versamenti Agenda 2026-06-13:
- aggiornata `static/js/agenda.js` per la modale `#depositModal`;
- all'apertura, focus automatico su `#depositCashAmount` con valore selezionato;
- ordine Tab esplicito:
  - importo contanti;
  - checkbox assegni disponibili, nell'ordine della tabella;
  - banca `#depositBank`;
  - data `#depositDate`;
- `Tipo versamento`, `Totale versamento` e `Nota` vengono esclusi dalla tabulazione standard ma restano selezionabili col mouse;
- l'ordine Tab viene ricalcolato dopo ogni reload degli assegni disponibili;
- premendo `Enter` nella modale viene eseguito `saveDeposit()` come click su `Salva versamento`;
- verifica `node --check static/js/agenda.js` ok.

UX modale corrispettivi Agenda 2026-06-13:
- aggiornati `templates/agenda.html` e `static/js/agenda.js` per la modale `#receiptModal`;
- all'apertura, focus automatico su `#rc_amount` con valore selezionato;
- premendo `Tab` dall'importo il focus passa direttamente alla tendina `#rc_type`;
- premendo `Enter` nella modale viene eseguito `saveReceiptClosure()` come click su `Aggiungi` / `Salva`;
- rimosso dal footer della modale il pulsante `Stampa report completo`;
- verifica `node --check static/js/agenda.js` ok.

UX modale Cassetto / Prelievi titolare Agenda 2026-06-13:
- aggiornata `static/js/agenda.js` per la modale `#ownerTakeModal`;
- all'apertura, focus automatico su `#ownerTakeCashAmount` con valore selezionato;
- ordine Tab esplicito:
  - contanti;
  - tipo prelievo `#ownerTakeType`;
  - checkbox assegni disponibili, nell'ordine della tabella;
- `Nota` e pulsante `Salva prelievo` vengono esclusi dalla tabulazione standard ma restano selezionabili col mouse;
- l'ordine Tab viene ricalcolato dopo ogni reload degli assegni disponibili;
- premendo `Enter` nella modale viene eseguito `saveOwnerTake()` come click su `Salva prelievo`;
- verifica `node --check static/js/agenda.js` ok.

UX modale Spicci Agenda 2026-06-13:
- aggiornata `static/js/agenda.js` per la modale `#spicciModal`;
- all'apertura, focus automatico su `#spicciMoveAmount` con valore selezionato;
- ordine Tab esplicito:
  - importo;
  - chi `#spicciMovePerformedBy`;
  - tipo `#spicciMoveType`;
- `Note` e pulsante `Salva` vengono esclusi dalla tabulazione standard ma restano selezionabili col mouse;
- premendo `Enter` nella modale viene eseguito `saveSpicciMove()` come click su `Salva`;
- premendo `Esc` la modale viene chiusa senza salvare;
- verifica `node --check static/js/agenda.js` ok.

Barra giornata Agenda 2026-06-13:
- aggiunti in alto a destra nella card `#agendaDayHeader` due pulsanti icon-only:
  - `#btnDayReportView` con icona report e tooltip `Visualizza report`;
  - `#btnDayReportPrint` con icona stampa e tooltip `Stampa report`;
- i pulsanti richiamano rispettivamente `openDayReport()` e `printCompleteDayReport()`;
- il click sui pulsanti non propaga alla card giornata, evitando il toggle del vault;
- aggiunto CSS dedicato in `static/css/agenda.css`;
- verifica `node --check static/js/agenda.js` ok.

Misura tempi apertura giornata Agenda 2026-06-13:
- richiesta diagnostica su `2026-06-13` vuoto e `2026-06-12` pieno;
- misura fatta sugli endpoint Flask reali con accesso DB remoto, bypassando solo i decorator di autenticazione nel test locale per evitare redirect del test client;
- `loadDay()` chiama `/api/day`, poi `preview`, poi in parallelo incassi/spese/POS/movimenti/saldo spicci/assegni rientranti; assegni in scadenza parte fuori dal blocco atteso;
- endpoint `preview` (`api_cash_day_preview`) non termina entro 90s su entrambi i giorni;
- il collo di bottiglia e' `_calculate_progressive_saldo_versabile()`, che ricostruisce ricorsivamente il saldo su tutte le giornate precedenti;
- misura senza `preview`, processo caldo:
  - `2026-06-12` pieno: stima UI `3.545s` (`/api/day` `0.629s`, massimo parallelo `2.917s`);
  - `2026-06-13` vuoto: stima UI `3.242s` (`/api/day` `0.673s`, massimo parallelo `2.569s`);
- rispetto ai target indicati: pieno nel range 3/4s solo escludendo preview; vuoto sopra il target 1/2s anche escludendo preview; con preview il caricamento reale e' nettamente fuori target.

Decisione architetturale snapshot chiusura Agenda 2026-06-13:
- obiettivo: raggiungere apertura giornata entro 3/4s evitando il ricalcolo ricorsivo del saldo versabile progressivo;
- vincolo funzionale confermato: dati aziendali/fiscali restano nel DB, dati privati restano nel vault PRI;
- lo snapshot non deve essere un totale unico indistinto:
  - snapshot fiscale/AZ persistito nel DB, leggibile anche a vault bloccato;
  - snapshot PRI persistito nel vault cifrato annuale, leggibile solo a vault sbloccato;
  - snapshot completo = composizione runtime di AZ + PRI solo in modalita' report completa;
- in modalita' report fiscale devono essere mostrati solo dati AZ/DB;
- in modalita' report completa devono essere mostrati AZ + PRI, mantenendo evidenza del perimetro dati;
- modifiche su giornate gia' chiuse non devono essere distruttive:
  - registrare audit con utente, data/ora, entita', before/after, motivo e impatto sui progressivi;
  - permettere visualizzazione degli effetti prima/dopo;
  - permettere rimozione/reversione tramite evento compensativo, non cancellazione silenziosa;
  - ricalcolare snapshot dal giorno modificato in avanti solo quando serve.

Performance apertura giornata Agenda 2026-06-13:
- aggiunta migrazione `1a2b3c4d5e6f_add_cash_closure_fiscal_snapshot.py`;
- aggiunti su `CashClosure` campi snapshot fiscale/AZ:
  - `fiscal_snapshot_version`;
  - `fiscal_snapshot`;
  - `fiscal_snapshot_created_at`;
  - `fiscal_snapshot_stale`;
  - `saldo_versabile_precedente`;
  - `versabile_giornata`;
  - `saldo_versabile_finale`;
- migrazione applicata al DB remoto (`flask db upgrade`: `c0d1e2f3a4b5 -> 1a2b3c4d5e6f`);
- `api_cash_day_preview()` non usa piu' `_calculate_progressive_saldo_versabile()` ricorsiva;
- aggiunto calcolo progressivo veloce:
  - usa l'ultimo snapshot fiscale chiuso valido, se presente;
  - in assenza di snapshot ricostruisce il saldo precedente con una singola query aggregata SQL;
- aggiunto calcolo giornaliero fast per la preview con una query aggregata invece di molte query separate;
- rimosso eager loading non necessario di incassi/spese nella preview;
- ridotte da due a una le letture dello stato vault dentro la preview;
- `refreshAgendaData()` ora carica preview e liste in parallelo, non piu' preview prima e liste dopo;
- stima apertura warm con DB remoto:
  - `2026-06-12` pieno: `3.607s`;
  - `2026-06-13` vuoto: `3.627s`;
- primo giro freddo del processo ancora piu' lento (`2026-06-12` pieno `5.356s`) per costo iniziale DB/cache;
- verifiche ok: `python -m py_compile routes/cassa.py models.py`, `node --check static/js/agenda.js`.
- chiusura giornata in corso di implementazione:
  - aggiunto endpoint `POST /cassa/api/day/<day_date>/close` per salvare snapshot di chiusura;
  - il snapshot fiscale viene salvato nel DB su `CashClosure`;
  - il snapshot PRI/complete viene salvato nel vault annuale sotto la giornata;
  - `GET /cassa/api/day/<day_date>/closure-snapshot` riusa lo snapshot quando il report viene riaperto;
  - la preview delle giornate chiuse riusa lo snapshot DB quando disponibile e non stantio;
  - `printCompleteDayReport()` ora chiama la chiusura prima della stampa.
- audit non distruttivo in corso:
  - aggiunta tabella `cash_day_audit_events`;
  - listener SQLAlchemy per tracciare create/update/delete sulle entita' cassa quando la giornata e' chiusa;
  - le chiusure successive alla modifica marcano `fiscal_snapshot_stale` sulle giornate chiuse dalla data toccata in avanti.
- stato giornata operabile dalla badge in alto a destra:
  - toggle `open/closed` sulla giornata corrente;
  - se si prova a inserire o modificare un movimento su giornata chiusa, la UI chiede se riaprire la giornata oppure passare a oggi;
  - backend bloccato su create/update/delete per le principali entita' cassa anche nei rami PRI e AZ.
- bootstrap home reso tollerante se il DB non e' raggiungibile: `inject_menus` ora degrada a menu vuoto invece di mandare in 500 la pagina iniziale.
- crash agenda risolto: `templates/agenda.html` era stato salvato con encoding non UTF-8 e Jinja falliva con `UnicodeDecodeError`; il file e' stato riscritto in UTF-8.
- pulizia encoding Agenda completata: simboli `€`, trattini e accenti italiani nel template sono stati normalizzati.
- ancora da fare: eventuale UI per mostrare/revertire gli eventi di audit.

- scheda prodotto articoli:
  - attivata la pubblicazione immagini dalla scheda verso le piattaforme presenti sull'articolo;
  - la pubblicazione e' effettiva su Prestashop tramite upload webservice;
  - il menu contestuale mostra solo i target attivi e supportati, con disabilitazione esplicita per quelli non ancora implementati;
  - le immagini caricate dall'app possono ora essere inviate anche alla piattaforma scelta o trascinate sul relativo slot;
  - introdotto raggruppamento immagini per famiglia con badge `prestashop | poleepo | ldapp` quando la stessa immagine e' presente su piu' target;
  - introdotto default immagine per famiglia con azione esplicita `Imposta come default` e badge visivo `Default` sulla primaria;
  - introdotta rimozione immagini con perimetro esplicito: da piattaforma o da LDApp si selezionano le copie da eliminare, mantenendo la distinzione tra archivio locale e copie pubblicate; su Prestashop la rimozione esegue anche la cancellazione remota della copia fisica.
  - attivata anche la pubblicazione immagini verso Poleepo con `PoleepoConnector.upload_image()`, usando un path upload configurabile e gli stessi asset LDApp come sorgente;
  - l'upload Poleepo prova piu' candidati di path e di nome campo file (`image/file/media/upload`), poi una variante JSON con URL pubblica e infine un PUT binario grezzo prima di fallire; il fallback finale prova anche `PUT /products/{id}` con il campo `images` del prodotto;
  - resta da verificare sul server Poleepo quale combinazione di endpoint/payload immagini sia effettivamente accettata: finora i candidati upload dedicati rispondono `502 Bad Gateway`;
  - aggiunta cancellazione remota anche per Poleepo tramite `PoleepoConnector.delete_image()`, con fallback configurabile sul path di delete e uso dei dati gia' persistiti sull'asset (`source_external_id`, `remote_url`);
  - migliorato il feedback frontend della pubblicazione immagini: ora il popup mostra l'errore per piattaforma quando Poleepo non risponde con il path giusto o con un payload valido;
  - le immagini provenienti da Prestashop/non-LDApp ora passano da un proxy server-side di LDApp, cosi' il browser non chiede piu' credenziali HTTP basic per `www.ldenoteca.it`.
  - corretto il delete frontend della scheda prodotto: gli endpoint usano il prefisso corrente del blueprint, quindi non tornano piu' HTML 404 quando si prova a eliminare una copia remota;
  - il parsing delle risposte delete/default e' stato reso robusto per non esplodere su pagine HTML di errore;
  - la modale di rimozione immagini e' stata resa piu' uniforme con il resto dell'app usando un dialog Bootstrap standard centrato e scrollabile.

- regola trasversale modali:
  - quando si implementa una nuova modale, il pulsante di conferma non va lasciato nel solo stato iniziale del DOM;
  - l'abilitazione/disabilitazione, il testo e l'azione del bottone di conferma vanno impostati all'apertura `shown.bs.modal` e ripristinati su `hidden.bs.modal`;
  - se la modale contiene una conferma critica, il default deve essere esplicito e non ereditato da uno stato precedente di riuso del nodo;
  - questa regola serve a evitare il problema ricorrente del bottone conferma disabilitato al primo utilizzo o dopo aperture successive.
- chiusura report giornaliero:
  - resa idempotente la route di chiusura; se la giornata ha gia' una `CashClosure` esistente, ora la aggiorna invece di provare a ricrearla;
  - rimosso il `noload` sulla relazione `CashDay.closure` nella chiusura e nel recupero snapshot, che impediva di vedere la chiusura gia' salvata.
  - snapshot e report payload vengono normalizzati con `_json_safe` prima del commit e del salvataggio nel vault, per evitare 500 causati da oggetti non serializzabili.
  - stampa report su giornata gia' chiusa: il bottone usa lo snapshot salvato e non richiama piu' la chiusura.

- pannello impostazioni/preferenze:
  - aggiunta pagina `/settings` come hub di configurazione;
  - dashboard trasformata in tile di categoria, con voce `Utenti` in apertura;
  - aggiunti i tile `Banche`, `Circuiti Carte` e `Dispositivi POS`, collegati a pagine read-only di riepilogo;
  - rese modificabili le aree `Banche`, `Circuiti Carte` e `Dispositivi POS` con salvataggio inline e associazione circuiti per il POS;
  - i circuiti carte mostrano ora icona e logo in forma grafica, con picker icone tramite modale e upload logo da file;
  - il picker icone dei circuiti usa Font Awesome gia' caricato nel layout e la modale viene portata nel `body` per evitare problemi di stacking;
  - il logo del circuito resta invariato finché non viene caricato un nuovo file;
  - i dispositivi POS usano checkbox leggibili per i circuiti associati invece del multiselect;
  - la validazione dei record nuovi avviene prima della creazione per evitare inserimenti vuoti lasciati in sessione;
  - aggiunte azioni esplicite di disattivazione e cancellazione, con blocco quando esistono riferimenti storici o associazioni;
  - aggiunta pagina `/settings/preferences` con configurazioni divise per categoria;
  - aggiunta pagina `/settings/users` read-only per vedere utenti, ruoli attivi e dati anagrafici principali;
  - introdotta tabella `app_preferences` per le preferenze runtime persistenti;
  - il runtime ricarica le preferenze dal DB mantenendo fallback sui valori base di avvio;
  - aggiunta modifica ruoli nella stessa area impostazioni;
  - aggiunto link "Impostazioni" nel menu profilo per gli utenti con peso >= 900;
  - i principali parametri di integrazione (`PS_*`, `POLEEPO_*`, `TRELLO_*`, `SLACK_*`, `VAPID_*`) e la soglia `OFFICE_ROLE_WEIGHT` possono essere governati dal pannello senza intervenire sui file `.env` per i valori salvati.
  - la migration `2b3c4d5e6f70_add_cash_day_audit_events.py` e' stata resa tollerante ai DB che hanno gia' la tabella `cash_day_audit_events`, cosi' `flask db upgrade` non si ferma piu' su `DuplicateTable`.
  - la pagina preferenze e i loader runtime ora degradano con warning invece di andare in 500 se la tabella `app_preferences` non e' ancora disponibile o il DB non e' allineato.
  - fix pagina preferenze: nel template `section["items"]` sostituisce `section.items`, evitando il crash Jinja `builtin_function_or_method object is not iterable`.
- 2026-06-18: aggiunti `valid_from`/`valid_to` a `PosCircuit` e `PosDevice`; la dashboard POS ora filtra i lookup per data e la lista movimenti POS non blocca piu' la lettura sulle giornate chiuse.
- 2026-06-18: la modale icone dei circuiti e' stata portata direttamente nel `body` e aperta via JS per evitare lo stacking issue ricorrente.
- 2026-06-18 fix emergenza: le pagine POS e l'agenda non vanno piu' in errore se `valid_from`/`valid_to` non sono ancora presenti nel DB; le query ora leggono solo le colonne realmente disponibili e degradano in modo compatibile.
- 2026-06-18 fix emergenza 2: il runtime prova a creare automaticamente `valid_from`/`valid_to` su `pos_circuits` e `pos_devices` se il DB non e' ancora migrato, per evitare blocchi sulla pagina dispositivi/circuiti e sull'agenda.
- 2026-06-18 fix emergenza 3: la select dei circuiti associati ai dispositivi POS ora viene eager-loaded, evitando query lazy che potevano rompere la pagina su DB non allineato.
- 2026-06-18 fix emergenza 4: la modale icon picker dei circuiti usa un layer Bootstrap piu' robusto con `modal-content` attivo e z-index molto alto.
- 2026-06-18 fix POS: rimossa l'eager loading sulla relazione dinamica `PosDevice.circuits`, che generava `object population` e rompeva la pagina dispositivi.
- 2026-06-18 fix POS: i logo dei circuiti ora vengono salvati in `static/images/pos` e serviti da `images/pos/...`, in modo coerente con gli altri asset dell'app.
- 2026-06-18 fix POS: la modale icon picker dei circuiti e' stata resa custom e auto-gestita, senza dipendere dal layering Bootstrap che la teneva invisibile.
- 2026-06-18 fix POS: i simboli valuta corrotti nella UI Agenda sono stati ripuliti nel file `static/js/agenda.js`.
- 2026-06-18 fix finale POS: la modale icone dei circuiti torna ad essere una vera Bootstrap modal con backdrop e dialog attivo; il picker ora si apre correttamente in primo piano.
- 2026-06-18 fix finale POS: i logo dei circuiti vengono salvati in `static/images/pos` e serviti da `images/pos/...`, cosi' il browser li carica davvero.
- 2026-06-18 fix finale POS: la ricerca dei circuiti del device usa una query esplicita sulla tabella di associazione, evitando dipendenze da `dynamic` relationship.
- 2026-06-18 fix finale Agenda: ripulite le sequenze valuta corrotte residue in `static/js/agenda.js`.
- 2026-06-18 fix UI POS: il picker icone dei circuiti gira ora in `{% block extra_js %}` dopo Bootstrap, e il logo del circuito viene servito dalla route `settings.pos_circuit_logo` per evitare cache/percorso static errati.
- 2026-06-19 fix POS loghi circuiti: `_save_uploaded_logo()` e `settings.pos_circuit_logo` usano ora `current_app.static_folder`; i nuovi upload vanno realmente in `static/images/pos` invece che nel percorso errato derivato da `current_app.root_path`.
- 2026-06-19 loghi banche:
  - aggiunto `CashBank.logo_path`;
  - aggiunta migration `5e6f708192a3_add_cash_bank_logo_path.py`, applicata localmente fino a head `5e6f708192a3`;
  - la pagina `/settings/banks` consente upload e preview del logo banca;
  - i loghi banca vengono salvati in `static/images/banks`;
  - aggiunta route `settings.bank_logo` per servire i loghi con cache disabilitata;
  - `/cassa/api/banks` espone anche `logo_path`.
- 2026-06-19 fix ristampa report giornata riaperta:
  - corretto `api_close_cash_day()` in `routes/cassa.py`;
  - la route ora carica `CashDay.closure` con `selectinload` e ha fallback esplicito su `CashClosure.query.filter_by(cash_day_id=...)`;
  - risolto il caso giornata gia' chiusa, poi riaperta e modificata: alla ristampa aggiorna la `CashClosure` esistente invece di tentare un secondo insert bloccato da `uq_cash_closure_day`;
  - verifica read-only su DB: `2026-06-19 open` vede correttamente `closure.id=7`.
- 2026-06-19 fix snapshot report giornata:
  - la chiusura ora salva nel DB anche `fiscal_snapshot["report_payload"]`, cioe' il payload fiscale completo del report con liste movimenti, POS, versamenti, ecommerce, corrispettivi e banche;
  - la chiusura manuale e la stampa report usano lo stesso snapshot backend, quindi una giornata chiusa puo' ristampare valori e movimenti dallo snapshot salvato;
  - se la giornata e' aperta, `Stampa report` chiude la giornata, riceve lo snapshot appena salvato e stampa quello;
  - il badge stato agenda viene aggiornato subito a `CLOSED` dopo chiusura da stampa;
  - gli snapshot fiscali delle giornate chiuse successive vengono marcati stale e rigenerati in cascata dopo la chiusura di una giornata modificata;
  - se una giornata chiusa ha snapshot stale, `/cassa/api/day/<day_date>/closure-snapshot` lo rigenera prima di restituirlo;
  - in modalita' fiscale la costruzione dello snapshot forza il vault PRI come non sbloccato, evitando righe private nel DB fiscale;
  - in modalita' completa il vault continua a salvare il payload completo ricevuto dal client quando disponibile;
  - verifiche: `python -m py_compile routes/cassa.py` ok, `node --check static/js/agenda.js` ok.
- 2026-06-20 nota operativa report/quadratura:
  - validazione utente completata su due giornate reali: report/quadratura risultano coerenti;
  - la sospensione operativa viene rimossa e la correzione snapshot/report viene considerata chiusa, salvo nuovi casi reali da analizzare.
- 2026-06-21 fix prima stampa report completa:
  - caso reale validato: con vault PRI/completo la prima `Stampa report` dopo chiusura usava lo snapshot fiscale restituito da `/cassa/api/day/<day_date>/close`, mentre la seconda stampa poteva usare il payload completo client/vault;
  - sintomo: nella prima stampa mancavano movimenti nei box incassi e la quadratura era fiscale/sballata; alla seconda stampa comparivano i movimenti e la quadratura completa corretta;
  - `api_close_cash_day()` ora restituisce in `snapshot` il payload completo ricevuto dal client quando `view=complete` e il vault e' sbloccato, invece di sovrascriverlo con il report fiscale backend;
  - `/cassa/api/day/<day_date>/preview?view=complete` su giornata chiusa prova prima a leggere la preview del report completo dal vault; se non la trova non rientra nello snapshot fiscale e prosegue col ricalcolo live completo;
  - verifica diagnostica DB: snapshot fiscali 2026-06-19/20 contenevano delta fiscali `39.30` e `652.93`, coerenti col bug;
  - verifica controllata: giornata temporanea `2099-01-01` chiusa con payload completo sentinella restituisce subito `delta_quadratura=-123.45` e riga incasso sentinella; cleanup eseguito;
  - verifiche: `python -m py_compile routes/cassa.py`, `git diff --check`.
- 2026-06-21 UI Chiavi API tabellare:
  - `templates/settings/api_keys.html` trasformato da form lungo a widget tabellare coerente con gli altri widget impostazioni;
  - righe integrazione per Prestashop, Poleepo, Trello, Slack e VAPID, con azioni modifica, disattiva ed elimina override;
  - modifica apre modale con i campi dell'integrazione; i segreti restano vuoti con placeholder "Lascia vuoto per mantenere";
  - disattiva crea override DB vuoti per svuotare la config runtime senza cancellare `.env.local`;
  - elimina rimuove gli override DB e ripristina eventuali valori `.env.local`/default;
  - aggiunta creazione/modifica/eliminazione di chiavi ambiente custom in `.env.local` con marker descrittivo `# LDAPP_DESC KEY: ...`;
  - le chiavi custom mostrate sono solo quelle create/marcate dal widget, evitando di esporre tutte le variabili ambiente esistenti;
  - verifiche: `python -m py_compile routes/settings.py tools/preferences.py`, `git diff --check`, GET reale `/settings/api-keys` 200, ciclo controllato crea/elimina `CODEX_TEMP_API_KEY` con ripristino di `.env.local`.
- 2026-06-20 widget utenti impostazioni:
  - aggiunti modelli `SpecialPermission` e `UserSpecialPermission`;
  - aggiunta migration `6f708192a3b4_add_user_special_permissions.py`, applicata localmente fino a head `6f708192a3b4`;
  - corretta la validita' dei ruoli attivi: `User.active_roles` considera anche `valid_from`;
  - `/settings/users` ora mostra azioni rapide per cambio ruolo, autorizzazioni speciali, reset password ed eliminazione;
  - click sulla riga utente apre una modale dettaglio con modifica dati, eliminazione o chiusura;
  - cambio ruolo sostituisce i ruoli attivi correnti con un nuovo ruolo lifetime;
  - autorizzazioni speciali consente aggiunta di ruolo temporaneo o autorizzazione speciale con `valid_from`/`valid_to`;
  - il pulsante creazione autorizzazione speciale e' presente ma disabilitato, da definire in seguito;
  - reset password admin genera token valido 24 ore, invalida reset precedenti aperti e invia il link via email all'utente;
  - le modali utenti ripristinano il pulsante conferma su `shown.bs.modal` e `hidden.bs.modal`;
  - verifiche: `python -m py_compile models.py routes/settings.py`, `flask db current`, render template `settings/users.html` con dati reali.
- 2026-06-20 regola modali stacking/focus:
  - le modali create dentro template complessi, card, shell, pagine impostazioni, agenda o contenitori con overflow/transform/z-index devono essere spostate in `document.body` prima dell'apertura;
  - se restano dentro il contenitore originale, in questo progetto tendono ad aprirsi con backdrop attivo ma dialog non in focus/non cliccabile;
  - pattern richiesto: su `DOMContentLoaded`, per ogni modale della pagina, eseguire `document.body.appendChild(modal)` se il parent non e' gia' `document.body`;
  - dopo lo spostamento, inizializzare/ripristinare pulsanti e handler su `shown.bs.modal` e `hidden.bs.modal`;
  - questa regola va applicata preventivamente a ogni nuova modale, non come fix successivo.
  - applicato subito a `templates/settings/users.html`.
- 2026-06-20 UI widget utenti:
  - i flash nella pagina `/settings/users` sono stati riposizionati fixed sotto la navbar, con z-index alto e larghezza controllata;
  - le modali utenti usano classe `settings-user-modal` con header marrone coerente con le modali Agenda, bordo, shadow, footer separato e body scrollabile;
  - evitato l'effetto "total white" e il taglio della barra titolo nelle modali utenti;
  - verifica render template `settings/users.html` ok.
- 2026-06-20 UI impostazioni banche/circuiti/POS:
  - `templates/settings/banks.html`, `templates/settings/pos_circuits.html` e `templates/settings/pos_devices.html` sono stati uniformati allo stile del widget utenti;
  - le liste ora usano tabella compatta con click riga per aprire la modale dettaglio/modifica;
  - le azioni rapide di riga espongono modifica, toggle attivo/disattivo ed eliminazione;
  - i form di creazione sono stati spostati in modale dedicata;
  - flash e modali usano lo stesso styling corretto: header marrone, body scrollabile, footer separato e flash fixed sotto navbar;
  - tutte le modali vengono spostate in `document.body` su `DOMContentLoaded` e i pulsanti submit vengono ripristinati su `shown.bs.modal`/`hidden.bs.modal`;
  - per i circuiti carte e' stato mantenuto il picker icone in modale con layer dedicato;
  - verifica render template con dati reali ok per `settings/banks.html`, `settings/pos_circuits.html`, `settings/pos_devices.html`.
- 2026-06-20 fix creazione dispositivo POS:
  - corretto `routes/settings.py` in `/settings/pos-devices`: sui nuovi `PosDevice` viene eseguito `db.session.flush()` prima di associare i circuiti many-to-many;
  - la relazione dinamica `device.circuits` viene svuotata solo sui dispositivi esistenti, evitando errori su oggetti non ancora persistiti;
  - aggiunto `db.session.rollback()` nel blocco `except` della route per non lasciare la sessione SQLAlchemy in stato fallito;
  - verifiche: `python -m py_compile routes/settings.py` ok; POST reale di test crea un POS temporaneo con circuito associato, ritorna 302 e cleanup ok.
- 2026-06-20 UI gestione menu:
  - restyling di `templates/settings/menus.html` e `static/css/menus.css`;
  - aggiunta testata pagina con titolo, descrizione e rientro alla dashboard impostazioni;
  - card struttura menu resa coerente con il resto delle impostazioni: bordo leggero, shadow, toolbar ordinata e pulsanti con icone;
  - albero menu reso piu' leggibile con righe arrotondate, indentazione gerarchica, connettori verticali, stati inattivo/nascosto/separatore differenziati e menu azioni piu' pulito;
  - modale menu uniformata al tema impostazioni con header marrone, body scrollabile e controlli coerenti;
  - mantenuto invariato il funzionamento JS/endpoint esistente;
  - verifiche: render template `settings/menus.html` ok, `node --check static/js/menu_management.js` ok, `git diff --check` ok.
- 2026-06-20 fix menu azioni Gestione menu:
  - il dropdown di riga ora usa `dropdown-menu-end`, quindi apre verso l'interno invece di uscire dal bordo destro;
  - rimossi gli overflow clipping da `.menus-page`, `.container-fluid`, `.menu-card` e `.menu-card-body`;
  - il nodo con dropdown aperto riceve classe `menu-node-actions-open` e z-index elevato per non finire sotto gli item successivi;
  - rimossa la traslazione hover sulle righe, che creava stacking context sfavorevoli;
  - verifiche: `node --check static/js/menu_management.js` ok, `git diff --check` ok.
- 2026-06-20 semplificazione azioni Gestione menu:
  - rimosso il dropdown di riga dal widget `/settings/menus`;
  - `static/js/menu_management.js` ora genera pulsanti rapidi inline per sotto-menu, separatore, modifica, attiva/disattiva, mostra/nascondi ed elimina;
  - `static/css/menus.css` definisce dimensioni stabili per i pulsanti rapidi e layout responsive;
  - eliminata alla radice la criticita' hover/orientamento/z-index del menu "...";
  - verifiche: `node --check static/js/menu_management.js` ok, render template `settings/menus.html` ok, `git diff --check` ok.
- 2026-06-20 fix contenimento Gestione menu:
  - ripristinato clipping/scroll interno del box menu dopo la rimozione del dropdown;
  - ridotta l'indentazione delle gerarchie per evitare overflow laterale;
  - le righe menu ora possono andare a capo e i pulsanti rapidi si dispongono su piu' righe dentro il box quando lo spazio non basta;
  - verifiche: `node --check static/js/menu_management.js` ok, `git diff --check` ok.
- 2026-06-20 UI conflitti import:
  - restyling di `templates/settings/import_conflicts.html` come pagina operativa coerente con le altre impostazioni;
  - aggiunta toolbar con titolo, descrizione e ritorno alla dashboard;
  - aggiunta card stato/coda, card dato certo e confronto CSV/DB in due pannelli scrollabili;
  - barra azioni sticky con pulsanti Usa CSV, Usa DB e Salta;
  - `static/js/import_conflicts.js` ora renderizza righe campo con classi dedicate e mantiene la pill del tipo conflitto;
  - verifiche: `node --check static/js/import_conflicts.js` ok, render template `settings/import_conflicts.html` ok, `git diff --check` ok.
- 2026-06-21 logica conflitti import:
  - `/settings/next_conflict` restituisce `pending_count`, `current_position` e `duplicate_count` per mostrare avanzamento e duplicati identici;
  - `/settings/resolve_conflict` risolve automaticamente tutti i conflitti pending identici allo stesso payload del conflitto corrente;
  - `SKIP` non lascia piu' il conflitto in coda pending: lo marca `skipped` con `resolved_at`/`resolved_by`;
  - aggiunti in UI i pulsanti `Sempre CSV` e `Sempre DB`, che salvano regole di risoluzione `ALWAYS`;
  - l'import articoli consulta `ImportConflictResolution` prima di creare un nuovo conflitto `CODICE_RIASSEGNATO_O_DESC_DISCORDANTE`;
  - l'import articoli non reinserisce duplicati pending identici: se il payload e' gia' in coda, salta la creazione;
  - verifica su DB reale: primo conflitto reale espone `pending_count=2487`, `current_position=1`, `duplicate_count=156`;
  - verifica controllata: due conflitti temporanei identici risolti insieme con `duplicates_resolved=2`, regole temporanee ripulite;
  - verifiche: `python -m py_compile routes/settings.py tools/importazioni.py`, `node --check static/js/import_conflicts.js`, `git diff --check`.
- 2026-06-21 separazione widget Configurazione:
  - aggiunto widget `/settings/api-keys` per chiavi e parametri integrazioni esterne: Prestashop, Poleepo, Trello, Slack e notifiche push;
  - aggiunto widget `/settings/roles-permissions` per ruoli applicativi e soglie autorizzative;
  - dashboard impostazioni aggiornata con tile `Chiavi API` e `Ruoli e Autorizzazioni`;
  - `/settings/preferences` resta come configurazione residuale e rimanda ai widget estratti;
  - `tools/preferences.save_preferences_from_form()` ora salva solo le chiavi presenti nel form, evitando cancellazioni quando una sezione viene spostata fuori dal vecchio widget;
  - aggiunti breadcrumb client-side in `static/js/base.js`;
  - verifiche: `python -m py_compile routes/settings.py tools/preferences.py`, `node --check static/js/base.js`, render template nuovi con DB reale, POST innocue su `/settings/api-keys` e `/settings/roles-permissions` con redirect 302.
- 2026-06-21 ruoli/autorizzazioni impostazioni:
  - `/settings/roles-permissions` ora gestisce creazione, modifica ed eliminazione dei ruoli;
  - l'eliminazione di un ruolo controlla gli utenti collegati e richiede un ruolo di destinazione quando esistono assegnazioni da ricanalizzare;
  - le autorizzazioni speciali sono gestite come record `SpecialPermission` con identificatore `code`, non come soglie/pesi ruolo;
  - aggiunte creazione, modifica, attivazione/disattivazione ed eliminazione delle autorizzazioni speciali;
  - l'eliminazione di un'autorizzazione controlla `UserSpecialPermission` e richiede una destinazione quando esistono assegnazioni utente;
  - la pagina mostra conteggi utenti e conteggi funzione: i menu/funzioni attuali usano ancora soglie numeriche di peso, non FK a ruolo o permesso speciale;
  - prima delle create viene riallineata la sequence PostgreSQL del PK se risulta arretrata rispetto ai record presenti;
  - tutte le modali seguono il pattern preventivo `document.body.appendChild(modal)` e reset submit su `shown.bs.modal`/`hidden.bs.modal`;
  - verifiche: `python -m py_compile routes/settings.py`; GET reale `/settings/roles-permissions` 200; ciclo reale crea/elimina ruolo e crea/elimina autorizzazione con record temporanei e cleanup ok.
- 2026-06-21 scroll widget impostazioni:
  - aggiunto scroll interno ai box Ruoli e Autorizzazioni in `/settings/roles-permissions`, con intestazioni tabella sticky;
  - aggiunto scroll interno al corpo del form `/settings/api-keys`, lasciando visibile la barra di salvataggio;
  - verifiche: `git diff --check`; GET reali `/settings/roles-permissions` e `/settings/api-keys` entrambi 200.
- 2026-06-21 fix ruolo dev id 0:
  - il ruolo `dev` esiste nel DB con `id=0` e peso `999`;
  - corretti i controlli su `role_id`, `replacement_role_id` e `permission_id` in `routes/settings.py` usando `is not None` invece di truthy check;
  - ora il ruolo `dev` puo' essere selezionato in cambio ruolo, autorizzazioni temporanee e ricanalizzazione cancellazione ruolo;
  - verifiche: `python -m py_compile routes/settings.py`; lettura DB `Role.query.get(0)` restituisce `dev 999`.
- 2026-06-21 visibilita' ruolo dev:
  - in `/settings/roles-permissions` la tabella ruoli e' ordinata per peso decrescente, cosi' `dev` e `admin` restano in alto;
  - aumentata l'altezza utile del box scrollabile ruoli/autorizzazioni con `clamp(...)`;
  - verifica render reale: prima riga tabella ruoli `dev ID 0` peso `999`.
- 2026-06-21 fix scrollbar widget impostazioni:
  - `/settings/roles-permissions` usa classe pagina dedicata `roles-permissions-page`;
  - la `welcome-section` resta contenitiva (`height:100%`, `overflow:hidden`) per non far uscire i box dal pannello;
  - lo scroll verticale e' sul `.container-fluid` interno (`overflow-y:auto`, `padding-bottom`), cosi' le tabelle non vengono tagliate e restano dentro la welcome-section;
  - rimosso lo scroll interno dalle tabelle ruoli/autorizzazioni: resta solo `.table-responsive` per eventuale overflow orizzontale;
  - il corpo di `/settings/api-keys` mantiene invece `height: clamp(...)` e `overflow-y: scroll`, con barra salvataggio esterna;
  - verifiche: `git diff --check`; GET reale `/settings/roles-permissions` 200.
- 2026-06-21 rimozione widget Configurazione:
  - rimosso il tile `Configurazione` dalla dashboard impostazioni perche' le funzioni sono state estratte nei widget dedicati;
  - `/settings/preferences` resta come redirect informativo verso `/settings/`, senza piu' renderizzare il vecchio widget vuoto;
  - rimossa la label breadcrumb client-side `Preferenze`;
  - in `/settings/api-keys` aggiunto scroll verticale interno alle tabelle integrazioni e chiavi custom (`settings-table-scroll`);
  - verifiche: `python -m py_compile routes/settings.py tools/preferences.py`, `node --check static/js/base.js`, `git diff --check`, GET reale `/settings/` 200 senza `Configurazione`, GET reale `/settings/preferences` 302 verso `/settings/`, GET reale `/settings/api-keys` 200.
- 2026-06-21 widget Database:
  - aggiunto tile `Database` nella dashboard impostazioni e nuova route `/settings/database`;
  - il widget legge `DATABASE_URL` da `.env.local` con fallback alla config runtime, mostra tipo/host/porta/nome DB/utente/password mascherata e stringa di collegamento mascherata;
  - la modale di modifica permette di salvare tipo DB, indirizzo, porta, nome DB, nome utente e password; la stringa viene calcolata lato client per anteprima e lato server per il salvataggio;
  - il salvataggio e l'eliminazione aggiornano `.env.local`; l'app segnala che serve riavvio per applicare la connessione al motore SQLAlchemy gia' avviato;
  - le modali seguono il pattern `document.body.appendChild(modal)` e reset submit su apertura/chiusura;
  - verifiche: `python -m py_compile routes/settings.py tools/preferences.py`, `node --check static/js/base.js`, `git diff --check`, GET reale `/settings/` 200 con tile Database, GET reale `/settings/database` 200, test builder URI con password contenente `@`.
- 2026-06-21 widget Email:
  - aggiunto tile `Email` nella dashboard impostazioni e nuova route `/settings/email`;
  - il widget legge e modifica da `.env.local` le chiavi `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USE_TLS`, `MAIL_USE_SSL`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_DEFAULT_SENDER`;
  - UI tabellare coerente con gli altri widget: valori, origine `.env.local`/runtime, azioni modifica/elimina;
  - `MAIL_PASSWORD` viene mostrata solo mascherata e non viene precompilata nel DOM della modale; se il campo resta vuoto durante il salvataggio, viene mantenuto il valore esistente;
  - verifiche: `python -m py_compile routes/settings.py tools/preferences.py`, `node --check static/js/base.js`, `git diff --check`, GET reale `/settings/email` 200 con password reale assente dal markup e password mascherata presente.
- 2026-06-21 fix scroll widget Email:
  - aggiunto wrapper `settings-table-scroll` alla tabella `/settings/email`, con altezza massima e scrollbar verticale interna;
  - verifiche: `python -m py_compile routes/settings.py tools/preferences.py`, `git diff --check`, GET reale `/settings/email` 200 con wrapper scroll presente e password reale assente dal markup.
- 2026-06-21 fix encoding tile impostazioni:
  - corretti i caratteri accentati mojibake nei tile impostazioni (`Gestione menù`, `visibilità`) e in alcune flash/error message di `routes/settings.py`;
  - verifiche: `python -m py_compile routes/settings.py`, `git diff --check`, GET reale `/settings/` 200 con `Gestione menù`/`visibilità` corretti e nessun carattere `Ã` nel markup dashboard.
- 2026-06-22 scheda prodotto - bozza pubblicazione piattaforme:
  - aggiunti schema iniziale campi e mapping LDApp per pubblicazione prodotto su Prestashop e Poleepo in `routes/search.py`;
  - aggiunti endpoint `GET/POST /search/scheda_articolo/<cod_art>/publish/<platform>/draft` per generare e salvare la bozza campi piattaforma;
  - la bozza usa `ProductPlatformField` per conservare i valori articolo/piattaforma prima dell'invio remoto;
  - la scheda prodotto mostra pulsanti `Pubblica su Prestashop/Poleepo` solo se l'articolo risulta assente dalla piattaforma;
  - aggiunta modale di revisione campi con evidenza dei campi obbligatori mancanti; l'invio remoto resta volutamente non attivo finche' non validiamo mapping e payload;
  - verifiche: `python -m py_compile routes/search.py`, `node --check static/js/scheda_articolo.js`, `git diff --check`, GET reale bozza `PD02217/prestashop` 200 con 10 campi e `id_category_default` mancante, POST bozza controllato 200 con ripristino dati, render reale scheda `PD02217` 200 con pulsanti publish.
- 2026-06-22 scheda prodotto - publish Prestashop:
  - aggiunto `tools.ps_util.create_product()` per creare prodotti Prestashop via webservice XML;
  - aggiunto endpoint `POST /search/scheda_articolo/<cod_art>/publish/prestashop`;
  - il publish salva i campi correnti in bozza, valida obbligatori, invia a Prestashop e crea/aggiorna `ProductPlatformLink` con `external_id`, `external_url`, stato `present` e payload remoto;
  - la modale scheda prodotto ora include il pulsante `Pubblica su Prestashop`; Poleepo resta disabilitato per publish reale finche' non validiamo payload/API prodotto;
  - verifica non distruttiva: POST publish su `PD02217/prestashop` senza `id_category_default` torna 400 `Campi obbligatori mancanti` prima di chiamare Prestashop; render scheda 200 con bottone publish.
- 2026-06-22 scheda prodotto - select Prestashop:
  - aggiunti helper `get_category_options()` e `get_tax_rule_group_options()` in `tools/ps_util.py`;
  - nella bozza Prestashop `id_category_default` e `id_tax_rules_group` sono `select` con opzioni lette dal webservice;
  - la modale pubblicazione mostra un filtro testuale sulle select lunghe;
  - verifica reale: bozza `BB03308/prestashop` restituisce 588 categorie e 6 tax rule group; `python -m py_compile routes/search.py tools/ps_util.py`, `node --check static/js/scheda_articolo.js`, `git diff --check`.
- 2026-06-22 scheda prodotto - performance/UX bozza Prestashop:
  - aggiunta cache in memoria 30 minuti per liste Prestashop categorie/tax rule group;
  - il salvataggio bozza non ricarica piu' le opzioni remote, quindi resta locale/DB;
  - la modale chiarisce la differenza tra `Salva bozza` locale e `Pubblica` reale, e i campi lista hanno help specifico;
  - verifica reale `BB03308/prestashop`: primo GET con fetch remoto 21.82s, secondo GET da cache 0.37s, POST bozza 1.46s senza opzioni remote.
- 2026-06-22 primo publish prodotto Prestashop:
  - pubblicato articolo `BB03308` su Prestashop con bozza campi: categoria `195`, tax rule group `1`, `active=0`;
  - Prestashop ha restituito prodotto `32361`, salvato in `ProductPlatformLink(platform='prestashop', external_id='32361', status='present')`;
  - verifica render scheda `BB03308` 200: il pulsante `Pubblica su Prestashop` non viene piu' mostrato e il badge piattaforma risulta attivo.
- 2026-06-22 punto deploy / ripartenza:
  - stato pronto per deploy della prima versione di pubblicazione prodotto Prestashop da scheda articolo;
  - limiti consapevoli: lo schema campi Prestashop e' ancora minimale, le liste remote usano cache in memoria e il primo caricamento dopo restart puo' essere lento, Poleepo resta in sola bozza;
  - domani ripartire dalla documentazione Prestashop/Poleepo per completare mapping campi, creazione di categorie/caratteristiche mancanti, gestione attiva/disattiva/elimina prodotto remoto e payload prodotto Poleepo.
- 2026-06-23 scheda prodotto - primo backend publish Poleepo:
  - verificato payload reale `GET /products` Poleepo: campi presenti `id`, `active`, `type`, `sku`, `title`, `price`, `vat_rate`, `price_with_tax`, `quantity`, `main_category_id`, `images`, `provisions`, `tags`;
  - verificato `OPTIONS /products`: metodi disponibili `GET,HEAD,POST,OPTIONS`;
  - aggiunto `PoleepoConnector.create_product()` con `POST /products` e payload minimo verificato: `sku`, `title`, `price`, `vat_rate`, `quantity`, `active`, `main_category_id`;
  - la bozza Poleepo in scheda articolo usa ora `title`, `vat_rate` e `main_category_id`; il default categoria e' `8360` (`NON CATEGORIZZATO`) o `POLEEPO_DEFAULT_CATEGORY_ID` se configurato;
  - la modale pubblicazione abilita il bottone anche per Poleepo, non solo Prestashop;
  - verifiche: `python -m py_compile routes/search.py tools/shipping_connectors.py`, `node --check static/js/scheda_articolo.js`, validazione locale campi mancanti senza chiamata remota, bozza reale `PD02217/poleepo` generata senza obbligatori mancanti;
  - non e' ancora stato creato un prodotto remoto Poleepo di test: prossimo step operativo e' pubblicare un articolo controllato, verificare risposta/propagazione store e poi aggiungere attiva/disattiva/elimina.
- 2026-06-24 scheda prodotto - modifica prodotto Poleepo:
  - dopo test utente il publish Poleepo ha creato correttamente un prodotto remoto, ma la scheda non esponeva piu' azioni per modificarlo dall'app;
  - aggiunta azione `Modifica su Poleepo` per piattaforme gia' presenti e aggiornabili (`ProductPlatformLink.status != absent/error` con `external_id`);
  - aggiunto endpoint `POST /search/scheda_articolo/<cod_art>/publish/<platform>/update`, separato dal publish per evitare ricreazioni accidentali;
  - l'update remoto e' abilitato solo per Poleepo; Prestashop resta escluso finche' non viene implementato update XML completo;
  - `PoleepoConnector.update_product()` ora restituisce un formato normalizzato e gestisce anche risposte `204`;
  - create/update Poleepo filtrano entrambi il payload ai soli campi verificati: `sku`, `title`, `price`, `vat_rate`, `quantity`, `active`, `main_category_id`, piu' dimensioni/peso se presenti;
  - verifiche: `python -m py_compile routes/search.py tools/shipping_connectors.py`, `node --check static/js/scheda_articolo.js`, payload filtrato senza `description`/`barcode`, articolo reale `VB075515-23` riconosciuto come modificabile e bozza Poleepo senza obbligatori mancanti;
  - non e' ancora stato premuto `Modifica su Poleepo`: il prossimo test reale deve cambiare un dato innocuo e verificare aggiornamento remoto/propagazione.
- 2026-06-24 correzione bozza modifica Poleepo:
  - la modale `Modifica su Poleepo` ora parte dai valori realmente presenti sul prodotto remoto, letti con `GET /products/<id>`, non dai valori proposti da LDApp;
  - i valori LDApp restano visibili come suggerimento quando divergono dal remoto, ad esempio `title` mostra il valore remoto e indica il titolo LDApp completo con `descrizione_aggiuntiva`;
  - per le nuove pubblicazioni Poleepo il titolo proposto usa `descrizione + descrizione_aggiuntiva`, cosi' non si perde l'identita' del vino/prodotto;
  - la bozza mostra anche campi Poleepo in sola lettura non modificati dall'update: `id`, `type`, `price_with_tax`, `sales`, `main_category_path`, `creation_date`, `update_date`, `images`, `provisions`, `tags`;
  - il POST update usa i valori salvati dalla modale, non una rilettura remota successiva, per evitare di sovrascrivere le modifiche appena inserite;
  - verifiche su `VB075515-23`: `title` remoto letto come `VINO TREBBIANO 2023 75cl`, suggerimento LDApp `VINO TREBBIANO 2023 75cl - LE MASSERIE - TENUTA MAGNA`, priorita' dei valori salvati confermata senza chiamare il PUT remoto.
- 2026-06-24 scheda prodotto - copia immagine da altro prodotto:
  - aggiunta azione nella toolbar immagini della scheda articolo per copiare un'immagine da un altro prodotto;
  - nuova modale `Copia immagine da prodotto` con ricerca per codice, descrizione e descrizione aggiuntiva;
  - nuovo endpoint `GET /search/scheda_articolo/<cod_art>/images/copy-candidates` per cercare articoli sorgente con asset immagine moderni;
  - nuovo endpoint `POST /search/scheda_articolo/<cod_art>/images/copy` per copiare l'asset selezionato sull'articolo corrente come asset `ldapp`;
  - la copia conserva `local_path`, `remote_url`, hash, filename, mime type e metadata di provenienza (`copied_from_asset_id`, `copied_from_cod_art`, `copied_at`);
  - prima versione limitata agli asset moderni `ProductAsset`, non alle immagini legacy pure;
  - verifiche: `python -m py_compile routes/search.py tools/shipping_connectors.py`, `node --check static/js/scheda_articolo.js`, presenza DB di asset moderni copiabili con `local_path`;
  - prossimo step separato: definire `Crea prodotto da altro prodotto` per nuova annata, copiando dati/bozze/immagini in modo controllato senza creare subito remoto.
- 2026-06-24 fix copia immagine remota:
  - caso reale: immagine Poleepo copiata dal Trebbiano 2024 al 2023 ha creato asset `ldapp` con `remote_url` ma senza `local_path`, quindi la pubblicazione su Poleepo falliva con `L'immagine selezionata non ha un file locale pubblicabile`;
  - `_copy_product_asset_to_article()` ora, se la sorgente ha solo `remote_url`, scarica l'immagine in `static/images/products/ldapp` e salva `local_path`, hash, filename e mime type;
  - `_publish_product_image_to_platform()` ora ripara anche asset gia' copiati solo-remoti: prima di fallire tenta il download remoto e materializza il file locale;
  - verificato asset reale `4039` su `VB075515-23`: prima era `local_path=False`, `remote_url=https://app.poleepo.cloud/image/show/24374099.jpeg`; URL remoto scaricabile con `HTTP 200 image/jpeg`.
- 2026-06-24 fix fallback upload immagini Poleepo:
  - errore reale: dopo i tentativi multipart/json/raw, il fallback `PUT /products/<id>` con `images` passava da `update_product()`, che ora valida i campi prodotto obbligatori e bloccava con `Campi Poleepo obbligatori mancanti`;
  - separato il PUT prodotto validato dal PUT grezzo interno: `update_product()` resta vincolato ai campi prodotto, mentre il fallback immagini usa `_put_product_payload()` senza richiedere `sku/title/price/vat_rate/main_category_id`;
  - verifica: `python -m py_compile tools/shipping_connectors.py`; `update_product()` continua a bloccare payload incompleti.
- 2026-06-24 modifica Poleepo - copia valori da altro prodotto:
  - aggiunto pannello `Copia valori da altro prodotto` dentro la modale `Modifica su Poleepo`;
  - nuova API `GET /search/scheda_articolo/<cod_art>/publish/poleepo/copy-candidates` per cercare prodotti origine gia' collegati a Poleepo;
  - nuova API `GET /search/scheda_articolo/<cod_art>/publish/poleepo/copy-values` per leggere i valori remoti Poleepo dell'articolo origine;
  - i candidati origine sono ammessi solo se hanno codice articolo diverso dal target e identita' descrittiva diversa (`descrizione + descrizione_aggiuntiva`);
  - quando si copiano i valori, ogni campo editabile parte dal valore origine e mostra vicino al campo il valore letto dall'origine;
  - i valori possono essere variati prima di salvare/aggiornare;
  - corretto bug bozza su valori falsy: `quantity=0` e `active=false` non vengono piu' trasformati in stringa vuota;
  - corretto errore frontend `insertBefore`: il box del valore origine ora viene inserito solo rispetto a nodi figli diretti del wrapper campo, evitando crash su layout input/select annidati;
  - verifica reale non distruttiva tra `VB075515-24` e `VB075515-23`: origine valida, link Poleepo `11926582`, valori remoti letti e quantità/attivo preservati.
- 2026-06-25 requisito registrato - copia/clone articolo:
  - la copia immagini da altro articolo oggi permette una sola immagine; va estesa a selezione multipla con checkbox su ogni immagine sorgente e comandi `Seleziona tutte` / `Deseleziona tutte`;
  - il caso d'uso principale e' la nuova annata di un vino gia' presente: copiare tutte le immagini della vecchia annata oppure solo quelle non obsolete;
  - il clone/copia dati da altro articolo deve trasferire anche i campi interni non modificati esplicitamente, incluse immagini secondo la selezione multipla e contenuti come la scheda tecnica (`SchedeProdotti`);
  - caso reale da cui nasce il requisito: copiando dati dal Trebbiano 2024 Le Masserie al Trebbiano 2023 Le Masserie, la scheda tecnica non viene trasferita.
- 2026-06-25 implementazione locale - copia immagini/dati articolo:
  - `POST /search/scheda_articolo/<cod_art>/images/copy` ora accetta `asset_ids` multipli mantenendo compatibilita' con `asset_id` singolo;
  - la modale `Copia immagine da prodotto` mostra checkbox su ogni immagine sorgente, comandi `Seleziona tutte` / `Deseleziona tutte` per prodotto e pulsante finale `Copia selezionate`;
  - aggiunto endpoint locale `POST /search/scheda_articolo/<cod_art>/copy-local-data`;
  - nel flusso `Modifica su Poleepo` / `Copia valori da altro prodotto`, oltre a precompilare i campi remoti, LDApp copia la scheda tecnica locale (`SchedeProdotti.descrizione` e `short`) dall'articolo origine se il target non ne ha gia' una;
  - la copia scheda tecnica e' conservativa: non sovrascrive una scheda target gia' compilata senza override esplicito backend;
  - verifiche: `python -m py_compile routes/search.py`, `node --check static/js/scheda_articolo.js`, route Flask registrate per copy immagini/copy valori/copy-local-data.
- 2026-06-25 implementazione locale - label campi Poleepo:
  - `main_category_id` Poleepo non viene piu' esposto solo come input numerico quando sono disponibili descrizioni;
  - la bozza prodotto prova a costruire opzioni `ID - descrizione` dai prodotti Poleepo gia' presenti, usando `main_category_path`;
  - se la descrizione non e' disponibile, il valore resta visibile ma viene marcato come `descrizione non disponibile`, cosi' l'utente sa che non puo' validarlo con certezza;
  - aggiunto supporto a `POLEEPO_DEFAULT_CATEGORY_LABEL` per dare un nome leggibile a default numerici configurati come `59271`;
  - verifiche: `python -m py_compile routes/search.py`, `git diff --check`.
- 2026-06-25 implementazione locale - copia valori con immagini/barcode:
  - nel pannello `Copia valori da altro prodotto` i risultati origine mostrano ora anche barcode e immagini locali copiabili;
  - le immagini sono mostrate con checkbox e comandi `Seleziona tutte` / `Deseleziona tutte`, poi vengono passate a `copy-local-data` come `asset_ids`;
  - `copy-local-data` copia anche i barcode dell'origine solo se il target non ha gia' barcode, senza sovrascrivere identificativi esistenti;
  - prima iterazione: il bottone frontend era stato rinominato in `Copia valori e dati`; subito dopo e' stato separato in `Confronta valori` e `Copia dati locali` per evitare copie alla cieca;
  - verifiche: `python -m py_compile routes/search.py`, `node --check static/js/scheda_articolo.js`, `git diff --check`.
- 2026-06-25 correzione UX - confronto valori padre/figlio:
  - il flusso non copia piu' i valori piattaforma alla cieca;
  - il bottone e' diventato `Confronta valori` e mostra, accanto a ogni campo editabile del target, il valore origine e il valore corrente;
  - per ogni campo sono disponibili le azioni `Usa origine` e `Mantieni corrente`;
  - `Copia dati locali` resta un comando separato per scheda tecnica, immagini selezionate e barcode, evitando che il confronto campi faccia anche trasferimenti locali impliciti;
  - verifiche: `node --check static/js/scheda_articolo.js`, `python -m py_compile routes/search.py`, `git diff --check`.
- 2026-06-25 fix visibilita' confronto valori:
  - la modale pubblicazione ora forza sfondo bianco e testo scuro su contenuto, label e testi informativi, evitando titoli bianchi su bianco ereditati dalla pagina;
  - i box confronto padre/figlio hanno colori espliciti: arancio per valori diversi, verde per valori uguali;
  - `Confronta valori` ora conta davvero i campi confrontati: se non inserisce nessun box mostra warning invece di dire che i valori sono stati scritti;
  - dopo il confronto la UI scrolla al primo box inserito;
  - verifiche: `node --check static/js/scheda_articolo.js`, `python -m py_compile routes/search.py`, `git diff --check`.
- 2026-06-25 fix confronto non visibile:
  - oltre ai box accanto ai campi, `Confronta valori` renderizza ora anche un riepilogo confronto direttamente sotto il prodotto sorgente cliccato;
  - il riepilogo mostra per ogni campo il valore origine, il valore corrente e i pulsanti `Usa origine` / `Mantieni corrente`;
  - l'inserimento del box campo avviene subito sotto la label del campo, non piu' in posizione dipendente da input/help;
  - lo scroll viene applicato al contenitore interno `productPublicationFields`, cosi' il primo campo confrontato entra davvero nella vista;
  - verifiche: `node --check static/js/scheda_articolo.js`, `python -m py_compile routes/search.py`, `git diff --check`.
- 2026-06-26 refactor modale Poleepo comparativa:
  - `Modifica su Poleepo` ora usa una matrice dedicata: immagini in alto, ricerca prodotto padre subito sotto, tabella campi con colonne `Poleepo`, `LDApp` e `Prodotto padre`;
  - per ogni campo editabile la scelta del valore da usare passa da radio button; il valore scelto alimenta gli input hidden raccolti dal submit esistente;
  - il draft Poleepo include anche immagini remote Poleepo e immagini LDApp del prodotto corrente;
  - quando si carica un prodotto padre, la terza colonna della tabella viene popolata con i valori origine e la colonna immagini padre mostra le immagini selezionabili per la copia locale;
  - i valori vengono formattati in UI come valuta per prezzi/costi, percentuali per IVA/rate e interi per campi numerici interi;
  - verifiche: `python -m py_compile routes/search.py`, `node --check static/js/scheda_articolo.js`, `git diff --check`.
- 2026-06-26 fix modale Poleepo comparativa:
  - corretto errore su `Confronta valori` dopo ricerca prodotto padre: la riga di confronto e la riga editor sono ora gestite separatamente;
  - sotto ogni riga campo e' presente `Valore scelto e modificabile`, input/textarea editabile alimentato dal radio selezionato;
  - la modale pubblicazione e' larga `80vw`, alta `86vh`, con contenuto ridimensionabile e area principale scrollabile;
  - verifiche: `python -m py_compile routes/search.py`, `node --check static/js/scheda_articolo.js`, `git diff --check`.
- 2026-06-28 UI mobile home:
  - avviato filone smartphone friendly partendo dalla home;
  - `templates/home.html` usa classe dedicata `home-page` senza cambiare la resa desktop;
  - aggiunti override mobile `max-width: 768px` in `static/css/style.css`: navbar piu' bassa, contenuto senza tabs laterali, footer compatto, home full-width e quick action in lista touch-friendly;
  - desktop lasciato invariato salvo la classe aggiunta alla section;
  - verifiche: render GET `/` 200, presenza `home-page` nel markup, `git diff --check`.
- 2026-06-28 fix navbar mobile home:
  - da screenshot in `docs/transport` il pattern bianco della navbar mobile tagliava visivamente logo e hamburger;
  - su mobile la navbar ora usa fondo pieno senza pattern, logo ridotto/centrato e toggler 44x44 centrato;
  - i tab laterali `context-tabs` vengono nascosti su mobile per non sovrapporsi alla home;
  - verifiche: render GET `/` 200, `git diff --check`.
- 2026-06-28 fix cache mobile/PWA:
  - se un telefono vede ancora la home desktop dopo deploy, la causa piu' probabile e' cache/service worker: `style.css` era linkato senza query versionata e precacheato in `ldapp-cache-v12`;
  - `templates/base.html` ora versiona `style.css`, `context_tabs.css`, `task_status.css` e la registrazione `service-worker.js` con `app_version`;
  - service worker portato a `ldapp-cache-v13` e precache CSS aggiornato;
  - breakpoint mobile home allargato da `768px` a `820px` per coprire viewport CSS mobili piu' larghe;
  - verifiche: render GET `/` 200 con `style.css?v=...` e `service-worker.js?v=...`, `git diff --check`.
- 2026-06-28 fix mobile trigger Samsung:
  - se Galaxy/PWA continua a vedere desktop, il solo `max-width` puo' non bastare o il browser puo' servire asset con URL invariato;
  - media query home mobile estesa a `(hover: none) and (pointer: coarse)`, oltre a `max-width: 820px`;
  - asset CSS e service worker versionati con suffisso esplicito `mobile2`;
  - service worker portato a `ldapp-cache-v14`;
  - verifiche: render GET `/` 200 con `style.css?v=...-mobile2` e `service-worker.js?v=...-mobile2`, `git diff --check`.
- 2026-06-28 fix screenshot S25 home:
  - dagli screenshot in `docs/transport` il layout mobile era attivo, ma le tab contestuali laterali restavano visibili perche' `context_tabs.css` veniva caricato dopo `style.css`;
  - `context_tabs.css` ora nasconde le tab su mobile/touch con override dedicato e `style.css` usa `!important` sullo stesso fallback;
  - la barra task attivi e' stata compattata su mobile/touch per non schiacciare home e footer quando sono presenti processi in corso;
  - asset CSS e service worker versionati con suffisso `mobile3`, service worker portato a `ldapp-cache-v15`.
- 2026-06-28 fix scala visuale S25:
  - lo screenshot S25 mostra layout mobile attivo ma dimensioni visive troppo piccole, compatibili con viewport touch larga;
  - aggiunto profilo CSS dedicato `(hover: none) and (pointer: coarse) and (min-width: 821px)` che aumenta header, logo, hamburger, titoli, quick action, footer e barra task senza alterare il desktop;
  - asset CSS e service worker versionati con suffisso `mobile4`, service worker portato a `ldapp-cache-v16`.
- 2026-06-28 ritocco scala visuale S25:
  - aumentata ulteriormente la scala del profilo touch largo: header 168px, logo 88px, hamburger 76px, titoli/testi e quick action piu' grandi;
  - asset CSS e service worker versionati con suffisso `mobile5`, service worker portato a `ldapp-cache-v17`.
- 2026-06-28 ritocco mobile menu S25:
  - aumentata di circa 40% la scala del profilo touch largo rispetto al ritocco precedente: header 235px, logo 123px, hamburger 106px e quick action 157px;
  - su mobile/touch l'hamburger viene ordinato prima del logo;
  - il menu mobile non appare piu' come overlay centrale: diventa un drawer laterale sinistro e, quando aperto, sposta a destra contenuto, footer e barra task tramite classe `mobile-menu-open`;
  - `menu.js` e' versionato come gli asset CSS; suffisso asset `mobile6`, service worker `ldapp-cache-v18`.
- 2026-06-28 ritocco font menu S25:
  - il drawer mobile ora sovrascrive font e padding ereditati dalla vecchia navbar mobile: voci menu con target touch piu' alto e font piu' leggibile;
  - nel profilo touch largo S25 le voci menu usano font 2.25rem, altezza minima 96px e padding 24x28px;
  - suffisso asset `mobile7`, service worker `ldapp-cache-v19`.
- 2026-06-28 ritocco profilo drawer mobile:
  - nel drawer mobile il blocco utente/profilo viene trattato come footer: spinto in fondo, separato da bordo superiore e centrato;
  - nel profilo touch largo S25 `Ciao ...` usa font 2.25rem e foto 96x96px, proporzionati alle voci menu;
  - suffisso asset `mobile8`, service worker `ldapp-cache-v20`.
- 2026-06-28 fix interazioni drawer mobile:
  - corretto allineamento voci drawer: il primo menu sovrascrive `mx-auto`/`justify-content-center` e torna in alto a sinistra;
  - la riga profilo nel footer drawer e' cliccabile e apre il menu utente come l'icona profilo;
  - aggiunte gesture touch: swipe da bordo sinistro verso destra apre il drawer, swipe verso sinistra lo chiude quando e' aperto;
  - suffisso asset `mobile9`, service worker `ldapp-cache-v21`.
- 2026-06-28 fix menu utente e gesture drawer:
  - su mobile il menu utente nel footer drawer viene gestito manualmente per evitare doppio toggle con la delega dropdown;
  - il dropdown utente si apre verso l'alto dentro il drawer, con posizione assoluta sopra la riga profilo;
  - gesture drawer rese piu' permissive: zona di apertura fino a 120px/12% viewport e supporto sia touch events sia pointer events;
  - suffisso asset `mobile10`, service worker `ldapp-cache-v22`.
- 2026-06-28 bozza mobile informazioni prodotti:
  - ricerca prodotto per descrizione trasformata su mobile/touch in lista card touch-friendly con input, scanner, risultati e paginazione scalati anche per viewport S25 larga;
  - `search_by_description.js` aggiunge classi semantiche ai risultati senza cambiare il comportamento di selezione/apertura scheda;
  - scheda articolo ottimizzata su mobile/touch: titolo, chiudi, slot immagini, upload, carousel, metadati, piattaforme, barcode, scheda tecnica e modali principali scalati;
  - verifica: `node --check static/js/search_by_description.js`, `git diff --check`; render `/search/ricerca_x_descrizione` restituisce 302 per sessione richiesta.
- 2026-06-28 UX ricerca prodotto:
  - rimosso il pulsante `Scheda` dai risultati della ricerca per descrizione;
  - click/tap sull'intera riga/card prodotto apre direttamente la scheda quando la pagina passa `onRowClick`, mantenendo il fallback `onSelect` per altri usi del componente.
- 2026-06-28 fix paginazione/scanner ricerca prodotti:
  - `GET /search/lista_articoli` accetta `stock_only` e filtra gli articoli con giacenza prima della paginazione SQL, evitando pagine vuote o irregolari;
  - con ricerca vuota vengono mostrati gli articoli con giacenza, mentre il checkbox `Tutti i prodotti` passa `stock_only=0` e mostra tutto l'archivio;
  - la ricerca include anche `cod_art` e ordina in modo stabile per descrizione/codice;
  - `scanner.js` conserva il callback `onScan` anche dopo cambio camera, cosi' la scansione barcode continua ad aprire la scheda/ricerca prevista.
- 2026-06-28 fix barcode informazioni prodotti:
  - nella pagina informazioni articoli la scansione barcode apre direttamente la scheda se l'articolo e' univoco;
  - se il barcode corrisponde a piu' varianti/annate, viene mostrata una modale di scelta prima di aprire la scheda;
  - `scanner.js` ora emette anche eventi `input`/`change` dopo la lettura e usa il callback attivo come fallback, evitando che il valore venga solo scritto nel campo senza attivare la ricerca.
- 2026-06-28 sostituzione colore primary/info:
  - sostituite le classi Bootstrap visuali `primary` con `info` in template e JS/CSS generato dinamicamente: bottoni, outline, badge, card border/header e testi;
  - sostituiti i blu hardcoded `#0d6efd` con `#0dcaf0` dove usati come accento grafico;
  - lasciati invariati i riferimenti logici `primary` legati a dati/funzioni (`is_primary`, immagine default, variabili interne);
  - verifiche: `node --check` su tutti i JS modificati, `python -m py_compile routes/settings.py`, `git diff --check`.
- 2026-06-28 restyling login:
  - `templates/login.html` usa una card dedicata con sfondo chiaro, labels scure, input leggibili, bottone `btn-info` e link ordinati;
  - aggiunti breakpoint mobile/touch e profilo touch largo S25 per scalare titolo, campi, checkbox, bottone e link;
  - verifica render `/auth/login` 200 con `login-card` e `btn-info`, `git diff --check`.
- 2026-06-28 ritocco login/drawer anonimo:
  - la riga `Accedi` nel drawer mobile anonimo ora e' centrata e scalata come il footer profilo autenticato;
  - login card riportata sul look LDApp marrone/bianco con link chiari e hover `info`, mantenendo input leggibili e bottone `btn-info`.
- 2026-06-28 restyling registrazione:
  - `templates/register.html` usa una card coerente con login: marrone semitrasparente, testo bianco, input chiari, bottone `btn-info`;
  - layout a griglia due colonne su desktop e singola colonna su mobile/touch, con profilo S25 scalato per campi, select, bottone e link;
  - aggiunti autocomplete semanticamente corretti e link di ritorno al login;
  - verifica render `/auth/register` 200 con `register-card` e `btn-info`, `git diff --check`.
- 2026-06-28 restyling password dimenticata:
  - `templates/forgot_password.html` usa card coerente con login/registrazione: marrone semitrasparente, testo bianco, input chiaro, bottone `btn-info`;
  - aggiunti breakpoint mobile/touch e profilo touch largo S25 per titolo, testo, input, bottone e link;
  - verifica render `/auth/forgot-password` 200 con `forgot-card` e `btn-info`, `git diff --check`.
- 2026-06-29 restyling scheda articolo:
  - `templates/scheda_articolo.html` allinea la scheda articolo al look LDApp: contenitore marrone semitrasparente, card interne scure, testi bianchi e accenti `info`;
  - metadati, barcode, badge piattaforme, slot immagini, upload e scheda tecnica hanno ora superfici coerenti e leggibili;
  - rimossa una doppia graffa CSS residua a fine blocco responsive;
  - verifica render `/search/scheda_articolo/<codice>` 200 e `git diff --check`.
- 2026-06-29 fix scelta varianti da scanner:
  - nella pagina informazioni articolo la modale `barcode-choices-modal` viene forzata sopra scanner/backdrop con z-index dedicato;
  - `scanner.js` spegne e nasconde l'overlay camera prima di eseguire la callback di scansione, evitando che la scelta varianti resti in secondo piano;
  - `scanner.js` e' versionato nella pagina con suffisso `barcode-choice1`;
  - verifiche: `node --check static/js/scanner.js`, render `/search/ricerca_x_descrizione` 200 e `git diff --check`.
- 2026-06-29 fix definitivo scelta varianti scanner:
  - applicato il pattern ricorrente documentato per le modali: `barcode-choices-modal` viene spostata in `document.body` su `DOMContentLoaded`;
  - suffisso cache scanner aggiornato a `barcode-choice2`;
  - verifica render `/search/ricerca_x_descrizione` 200 con `barcode-choice2` e `appendChild(barcodeChoicesModalEl)`.
- 2026-06-29 modale scelta varianti full screen:
  - `barcode-choices-modal` usa `modal-fullscreen` invece di dialog centrato, evitando decentramenti laterali su smartphone;
  - body scrollabile, contenuto centrato con `barcode-choices-inner` e look marrone/bianco coerente con LDApp;
  - verifica render `/search/ricerca_x_descrizione` 200 con `modal-fullscreen` e `barcode-choices-inner`.
- 2026-06-29 bozza UI mobile bacheca ordini:
  - `kiosk_overview.css` aggiunge una prima bozza coerente con LDApp: shell marrone, colonne traslucide, card ordine piu' leggibili, filtri giro orizzontali e scaling mobile/touch largo;
  - `templates/kiosk_overview.html` versiona CSS/JS con suffisso `mobile-board1`, rinomina il titolo in `Bacheca ordini` e corregge il blocco script duplicato;
  - `templates/kiosk_ordini_embed.html` rende il wrapper iframe coerente con la shell mobile;
  - verifiche: render `/kiosk` e `/kiosk/board/all` 200, `kiosk_overview.js` emesso una sola volta, graffe CSS bilanciate e `git diff --check`.
- 2026-06-29 seconda bozza mobile bacheca ordini:
  - su mobile/touch la board passa da colonne orizzontali a tab per stato (`Tutti`, stati dinamici) con liste verticali; desktop resta Kanban;
  - `kiosk_overview.js` aggiunge `currentMobileStatusFilter`, generazione tab stato, contatori e filtro mobile-only tramite classe `is-mobile-status-hidden`;
  - `kiosk_overview.css` aggiunge stile tab stato e override mobile per mostrare le colonne come sezioni verticali;
  - asset board versionati a `mobile-board2`; verifiche statiche: `node --check static/js/kiosk_overview.js`, graffe CSS bilanciate, `git diff --check`. Render `/kiosk` in test client andato in timeout durante questa verifica.
- 2026-06-30 trigger contestuale menu card bacheca:
  - rimosso l'ingombro visibile del toggle menu card, che si sovrapponeva al badge consegna;
  - il menu azioni della card si apre con click destro su desktop e long press su touch/pen, riusando il dropdown Bootstrap esistente;
  - asset board versionati a `mobile-board3`; verifiche: `node --check static/js/kiosk_overview.js`, graffe CSS bilanciate e `git diff --check`.
- 2026-06-30 scala dettaglio ordine/menu bacheca:
  - aumentati font e target touch del dettaglio ordine aperto dalla card su mobile/touch;
  - corretto stile del testo ordine applicando le regole anche a `.kiosk-pre`, usata dal markup JS;
  - aumentati font, padding e larghezza del menu contestuale aperto con long press/click destro;
  - asset board versionati a `mobile-board4`; verifiche: `node --check static/js/kiosk_overview.js`, graffe CSS bilanciate e `git diff --check`.
- 2026-07-01 bozza mobile plancia ordini:
  - `templates/route_orders/board.html` aggiunge una prima ottimizzazione mobile/touch coerente con LDApp: shell marrone, controlli piu' grandi, segmenti `info` e pannelli leggibili;
  - su smartphone le tabelle della plancia diventano righe-card verticali con etichette campo, azioni touch-friendly e sezioni cliente/lista/ordini piu' scandibili;
  - modali registro/clienti rese full-screen e scalate su mobile, con profilo touch largo per viewport tipo S25;
  - verifiche: graffe CSS bilanciate, `git diff --check`; render diretto `/route-orders/board` non confermato per redirect 302 dovuto a sessione/ruolo richiesti.
- 2026-07-01 fix overflow/scroll plancia mobile:
  - le card cliente della plancia mobile sono vincolate al 100% della larghezza del pannello, con `box-sizing` coerente e wrapping dei testi lunghi;
  - lo scroll viene ripristinato sull'area card/table responsive con overflow verticale touch e overflow orizzontale nascosto.
- 2026-07-01 plancia ordini mobile compatta:
  - su mobile le righe della plancia mostrano solo cliente e stato, con colore pieno per stato operativo e apertura dettaglio full-screen al tap;
  - il dettaglio full-screen clona le sezioni complete della riga e inoltra cambi/click ai controlli originali, mantenendo le API e i gestori esistenti;
  - su desktop resta la tabella completa, ma con bordo sinistro colorato per stato in modo piu' leggero rispetto al riempimento pieno;
  - verifiche: graffe CSS bilanciate, `node --check` dello script estratto, render template Flask con `routeBoardDetailModal`, `git diff --check`.
- 2026-07-01 ritocco plancia/bacheca ordini:
  - la card mobile della plancia usa una sola barra per cliente, con fascia laterale intensa per stato e badge stato interno;
  - il riepilogo mobile e' stato spostato dentro la prima cella della tabella per evitare markup tabellare fragile e doppie righe;
  - il menu contestuale della bacheca ordini viene spostato temporaneamente nel `body` come floating menu a posizione fissa, cosi' non viene tagliato dai box stato;
  - asset bacheca versionati a `mobile-board5`; verifiche: graffe CSS bilanciate, `node --check` su plancia estratta e `kiosk_overview.js`, `git diff --check`.
- 2026-07-01 fix scroll/menu plancia-bacheca:
  - la plancia ordini ora mantiene scroll verticale sull'area attiva e sul pannello ordini da associare, evitando che testi lunghi blocchino accesso ad associazione/clienti giro;
  - il menu contestuale della bacheca chiude il dropdown gia' aperto prima di mostrare quello nuovo;
  - su mobile/touch il menu contestuale della bacheca diventa un pannello fixed in basso, con font e righe piu' grandi;
  - asset bacheca versionati a `mobile-board6`; verifiche: graffe CSS bilanciate, `node --check` su plancia estratta e `kiosk_overview.js`, `git diff --check`.
- 2026-07-01 fix iterazione scroll/menu:
  - associazione ordini da plancia: se viene scelto un cliente fuori dal giro, il cliente viene agganciato al giro e l'ordine prende sempre la route selezionata, cosi' esce dai non associati;
  - layout plancia: rimossa la compressione flex che riduceva i clienti del giro a una riga quando il pannello non associati era lungo;
  - bacheca: apertura di un nuovo menu contestuale chiude il precedente e apre subito il nuovo; CSS floating applicato anche dopo lo spostamento nel `body`;
  - drawer mobile: i submenu principali tornano nel flusso del menu con `position: static`, evitando sovrapposizioni con le voci sotto; asset globali `mobile11`, bacheca `mobile-board7`.
- 2026-07-02 ritocco menu contestuale bacheca mobile:
  - rimosso il comportamento bottom-sheet del menu contestuale su touch: il menu resta in overlay vicino alla card madre;
  - aggiunti stile LDApp, bordo `info`, freccia di aggancio alla card, ombra piu' marcata e dimensioni touch piu' grandi per S25;
  - asset bacheca versionati a `mobile-board8`; verifiche: `node --check static/js/kiosk_overview.js`, render template bacheca, `git diff --check`.
- 2026-07-02 fix comportamento menu contestuale bacheca:
  - rimosso il ritardo apertura dopo chiusura del menu precedente: un nuovo long press/click destro apre subito il menu della nuova card;
  - aggiunta chiusura esplicita con click/tap fuori dal menu e con tasto Esc;
  - forzato reset di `transform/inset` Popper quando il menu viene spostato nel `body`, e aumentata ulteriormente la scala touch S25; asset `mobile-board9`.
- 2026-07-03 prima bozza restyling rubrica:
  - `registry_book.html` mostra le anagrafiche come righe compatte: nome/metadati visibili, dettaglio espandibile al click con dati anagrafici e contatti;
  - indice alfabetico trasformato in pulsanti che scrollano il contenitore interno della rubrica, non la pagina;
  - `registry_tools.css` allinea la rubrica al look LDApp, rende l'indice a tutta altezza visibile e scala font/target touch per mobile e S25;
  - API rubrica: senza ricerca il limite sale a 2000 record, con ricerca a 120; verifica JS inline, `py_compile routes/registry.py`, render template.
- 2026-07-03 fix rubrica modale/indice:
  - la modale associa contatti viene spostata in `document.body` prima di creare l'istanza Bootstrap, evitando problemi di focus/backdrop;
  - l'indice alfabetico usa `scrollIntoView` sulla sezione lettera, rendendo lo scroll piu' affidabile nel contenitore interno; verifiche: JS inline, render template, `git diff --check`.
- 2026-07-03 fix query rubrica:
  - l'endpoint `/registry/api/registries` non forza piu' `limit=120` quando la ricerca e' vuota: usa il limite esteso della query iniziale, cosi' l'indice alfabetico puo' coprire tutte le lettere;
  - la risposta include `count` e `limited` per distinguere lista completa e risultati filtrati; verifica: `py_compile routes/registry.py`, `git diff --check`.
- 2026-07-06 policy LD Selection:
  - home: pulsante LD Selection disabilitato per utenti non autenticati/guest, abilitato da `customer` in su;
  - `/ld-selection`: customer vede Standard senza share/copia, customer_horeca e staff+ vedono Horeca, staff+ puo' condividere/copiare Standard e Horeca, admin+ anche Top;
  - versione aperta scelta automaticamente senza conferme; asset globali versionati a `mobile12`; verifiche con utenti locali customer/staff/admin e home anonima, `py_compile routes/documents.py`, `git diff --check`.
- 2026-07-06 viewer LD Selection:
  - sostituito iframe PDF con viewer interno PDF.js: canvas a pagina intera, navigazione pagina precedente/successiva, input pagina e zoom +/-;
  - il pulsante `Apri PDF` resta visibile solo da staff in su per apertura esterna nell'app associata;
  - corretti i nomi file PDF secondo case reale (`LD_Selection_Pro.pdf`, `LD_Selection_Top.pdf`); verifiche customer/staff/admin con test client.
- 2026-07-06 bozza modulo eventi:
  - aggiunto modello `Event`, migrazione `7a8b9c0d1e2f_add_events.py`, blueprint `/events` e pulsante `Eventi` in homepage visibile a tutti;
  - `/events/` mostra i prossimi eventi pubblicati; da `office` in su compare gestione con inserimento, modifica, pubblicazione/nascondimento ed eliminazione;
  - UI coerente con LDApp e scalata per mobile/S25 tramite `static/css/style.css`;
  - migrazione applicata in locale; verifiche: `py_compile`, render home, render eventi anonimo senza form, render eventi office+ con form, `git diff --check`.
- 2026-07-06 bozza ordini clienti Horeca:
  - aggiunto modulo `/customer-orders`: i clienti `customer_horeca` e staff+ vedono `Fai un ordine` in home; staff+ vede anche `Ordini Horeca`;
  - ordine cliente supporta testo, foto da camera, allegati, registrazione vocale browser e scelta consegna da opzioni configurabili;
  - aggiunti `CustomerOrderDeliveryOption`, `CustomerOrder`, `CustomerOrderRevision` e collegamento `User.customer_registry_id` verso anagrafica cliente;
  - aggiunta pagina impostazioni `/settings/customer-order-options` per opzioni consegna e associazione account-anagrafica;
  - le modifiche ordine vengono registrate come `addition` o `replacement`; lo staff vede gli ordini ricevuti in `/customer-orders/manage`;
  - migrazione `8b9c0d1e2f3a_add_customer_orders.py` applicata in locale con opzioni iniziali (`prossimo giro`, `prima possibile`, `urgente`, `data consegna`, `entro giorno`);
  - limite consapevole della bozza: gli ordini sono salvati e consultabili, ma non vengono ancora pubblicati automaticamente su Slack/plancia;
  - verifiche: `py_compile`, `flask db upgrade`, render staff di `/customer-orders/manage` e `/settings/customer-order-options`, render home staff, `git diff --check`.
- 2026-07-06 fix upload ordini Horeca:
  - aggiunto limite upload applicativo configurabile con `MAX_UPLOAD_MB` (default 64 MB) e pagina 413 dedicata per `/customer-orders`;
  - la form ordine ora mostra riepilogo allegati prima dell'invio: tipo, nome file e dimensione totale, includendo il vocale registrato;
  - i metadati allegati salvati distinguono `image`, `file` e `audio`, con `size_label` visibile nello storico cliente e nella vista staff;
  - verifica salvataggio in request context: foto, PDF e audio vengono riconosciuti e salvati come tre allegati distinti; `py_compile`, `git diff --check`.
- 2026-07-06 compressione allegati ordini Horeca:
  - le foto scattate/caricate nella pagina ordine vengono compresse lato browser: ridimensionamento max 1600px e conversione JPEG qualita' 0.72 se il risultato e' piu' leggero dell'originale;
  - i vocali usano `MediaRecorder` con codec Opus/WebM o OGG quando disponibile e bitrate audio 24 kbps;
  - il riepilogo allegati viene aggiornato dopo la compressione, cosi' il cliente vede il peso effettivamente inviato; verifica `git diff --check`.
- 2026-07-06 fix ordine Horeca solo testo:
  - corretto 500 quando `Data consegna` resta su `Nessuna preferenza`: `delivery_option_id=""` viene normalizzato a `None` prima della query su colonna integer;
  - applicata la stessa normalizzazione alle revisioni ordine;
  - verifica reale con POST solo testo: risposta 302, ordine creato e poi rimosso dal DB test; `py_compile`, `git diff --check`.
- 2026-07-06 fix 413 foto ordine Horeca:
  - la compressione foto lato browser viene ora attesa al submit: il form mostra `Preparo allegati` e invia solo dopo il ridimensionamento;
  - abbassato il profilo foto a max 1200px e JPEG qualita' 0.55 per ridurre il rischio di blocco proxy/app;
  - gli ordini ricevuti sono consultabili dallo staff in home con `Ordini Horeca` o direttamente da `/customer-orders/manage`; verifica `git diff --check`.
- 2026-07-06 allegati su modifica ordine Horeca:
  - anche le revisioni di un ordine gia' inviato ora hanno foto, file e vocale, con lo stesso riepilogo allegati del primo invio;
  - la compressione foto viene applicata a tutti gli input `photos`, incluse le modifiche ordine, e il submit attende la compressione della form corrente;
  - verifica script inline con `node --check`, `git diff --check`.
- 2026-07-06 fix submit vocale ordini Horeca:
  - corretto blocco su `Preparo allegati`: il submit non usa piu' `requestSubmit()` ricorsivo, ma attende preparazione allegati e poi invia direttamente la form;
  - se il vocale e' ancora in registrazione al submit, viene fermato e finalizzato prima dell'invio;
  - verifica script inline con `node --check`, `git diff --check`.
- 2026-07-07 home ordini Horeca:
  - il pulsante `Fai un ordine` in home e' ora visibile solo agli utenti con ruolo `customer_horeca`;
  - gli utenti aziendali mantengono `Inserisci ordine` e `Ordini Horeca`;
  - verifica render home staff: `Fai un ordine` assente, `Ordini Horeca` e `Inserisci ordine` presenti.
- 2026-07-07 utenti mobile azioni:
  - nella modale dettaglio utente sono stati aggiunti i pulsanti azione: ruolo, autorizzazioni, reset password, elimina;
  - sulla riga utente la pressione lunga touch e il click destro aprono una action sheet con le stesse azioni;
  - il tap normale continua ad aprire il dettaglio utente;
  - verifiche: script inline `node --check`, render `/settings/users` con admin/dev 200 e markup azioni presente, `git diff --check`.
- 2026-07-07 impostazioni office e split Horeca:
  - dashboard `/settings/` accessibile da `office` in su e filtra i tile per soglia: office vede Utenti, Banche, Circuiti Carte, Dispositivi POS, Email, Conflitti import, Opzioni consegna Horeca, Associazione Utente-Cliente;
  - i tile sensibili Database, Chiavi API, Ruoli e Autorizzazioni, Gestione menu restano dev/admin tecnico secondo soglie esistenti;
  - abbassate a `office+` le route operative richieste: utenti, banche, circuiti carte, dispositivi POS, email, conflitti import e ordini clienti Horeca;
  - separata `/settings/customer-order-options` dalle associazioni: ora gestisce solo le opzioni consegna;
  - aggiunta `/settings/customer-order-links` per collegare account utente ad anagrafica cliente, con layout a card responsive per smartphone;
  - verifiche: `py_compile routes/settings.py`, render office+ di `/settings/`, `/settings/customer-order-options`, `/settings/customer-order-links`, `/settings/users`, `/settings/email`, `/settings/import_conflicts`; `git diff --check`.
- 2026-07-07 locandina eventi:
  - aggiunto `Event.poster_path` e migrazione `9c0d1e2f3a4b_add_event_poster.py`;
  - i form evento supportano upload locandina JPG/PNG/WebP con salvataggio in `static/uploads/events`;
  - la locandina viene mostrata nelle card pubbliche evento e nella gestione office, dove puo' essere sostituita o rimossa;
  - migrazione applicata in locale; verifica upload test con evento creato e rimosso subito, `py_compile`, `git diff --check`.
- 2026-07-07 locandina eventi PDF:
  - le locandine evento accettano ora anche PDF (`accept="image/*,.pdf"` e validazione backend `.pdf`/`application/pdf`);
  - i PDF vengono mostrati come riquadro/link `Apri locandina PDF`, mentre le immagini restano in anteprima;
  - i PDF selezionati nei form evento vengono convertiti lato browser nella prima pagina JPEG leggera prima dell'invio, con lato massimo 1600px e qualita' 0.72;
  - portato il controllo client-side a 30 MB sul file finale per gestire locandine PDF intorno ai 20/25 MB senza 413 quando la conversione riesce;
  - la pagina 413 dedicata viene usata anche per `/events`;
  - verifica upload PDF test con evento creato e rimosso subito, `py_compile`, script inline `node --check`, `git diff --check`.
- 2026-07-07 agenda mobile prima bozza:
  - aggiunta barra mobile sticky in `templates/agenda.html` per saltare a Giorno, Totali, Movimenti e Assegni;
  - `static/css/agenda.css` ora contiene breakpoint smartphone dedicato: pagina scrollabile, colonne riordinate in flusso, KPI piu' leggibili, righe movimento con target touch piu' grandi, calendario adattato, modali agenda full-screen e menu contestuale ingrandito;
  - aggiunto cache-buster `agenda.css?...-mobile1`;
  - verifiche: render diretto `agenda.html` in Flask context, `git diff --check`.
- 2026-07-07 agenda mobile dashboard:
  - sostituita la bozza mobile a pagina lunga con dashboard compatta: barra azioni KPI/Calendario/Assegni/Fiscale-Full, testata giornata e 4 tile quadrante con soli totali;
  - i tile Incassi, Spese, Movimenti di cassa e POS aprono il rispettivo quadrante in pannello full-screen scrollabile, riusando le liste e le azioni esistenti;
  - KPI, calendario e assegni vengono spostati temporaneamente nello stesso pannello mobile e poi ripristinati alla chiusura;
  - il pulsante Fiscale/Full in barra usa il toggle vault esistente e aggiorna la label in base a `priVaultUnlocked`;
  - cache-buster agenda aggiornato a `mobile2`; verifiche: `node --check static/js/agenda.js`, render diretto `agenda.html`, `git diff --check`.
- 2026-07-07 fix switch fiscale/full agenda:
  - rimosso il pulsante Fiscale/Full dalla barra mobile: lo switch resta sul click della barra giornata `#agendaDayHeader`;
  - confermato che lo sblocco deve usare la password hardcoded `TEST123`, senza prompt, per coerenza con il meccanismo operativo esistente;
  - cache-buster agenda aggiornato a `mobile3`.
- 2026-07-08 fix agenda mobile e drawer:
  - corretto `bindAgendaMobileShell()`: i tasti KPI, Calendario e Assegni aprono ora pannelli distinti invece di ricadere sempre su calendario/assegni;
  - allineato il breakpoint agenda mobile a `(max-width: 820px), (hover: none) and (pointer: coarse)` per Samsung/PWA con viewport ampia;
  - i tile dei quattro quadranti in mobile sono ora in colonna singola;
  - ripristinato `unlockPrivateVault()` senza prompt e con password hardcoded `TEST123`;
  - migliorato il drawer mobile: scroll sul menu principale e sottomenu annidati forzati nel flusso verticale;
  - cache-buster agenda aggiornato a `mobile4`.
- 2026-07-08 affinamento agenda/drawer S25:
  - il drawer mobile non applica piu' stili inline ai dropdown: i sottomenu annidati restano nel flusso verticale sotto il padre, leggermente indentati;
  - aggiunte regole specifiche per `li.dropdown-item.dropdown` e dropdown annidati nel drawer;
  - i tile agenda mobile hanno ora larghezza contenuta nel viewport, padding coerente e colonna singola senza tagli laterali;
  - aggiunto layer touch/coarse per S25 con font e target piu' grandi;
  - cache-buster agenda aggiornato a `mobile5`.
- 2026-07-08 home/agenda S25 tuning:
  - reso esplicito lo scroll verticale di `main.app-content` su mobile/touch e rimossa l'altezza piena forzata dalla home;
  - aumentati font, pulsanti e spaziature home nel layer S25;
  - aumentato padding laterale agenda S25 a 42px per lasciare sfondo visibile e ingranditi ulteriormente tile, font e target touch;
  - cache-buster agenda aggiornato a `mobile6`.
- 2026-07-09 agenda S25 refine:
  - ingranditi titolo agenda, stato `OPEN/CLOSED`, pulsante spicci e relative icone;
  - ingrandite le icone della barra KPI/Calendario/Assegni rispetto ai pulsanti;
  - rimossa la banda bianca dei tile quadrante usando card trasparenti e header colorati pieni;
  - padding laterale S25 agenda aumentato a 54px;
  - cache-buster agenda aggiornato a `mobile7`.
- 2026-07-09 fix agenda mobile actions:
  - corretto definitivamente `bindAgendaMobileShell()`: rimossa chiamata assegni fuori ramo, ora i tre pulsanti usano una mappa esplicita azione -> pannello;
  - reso piu' robusto il click su `#agendaDayHeader` per toggle fiscale/full, ignorando solo i bottoni report interni;
  - confermato sblocco full senza prompt con password hardcoded `TEST123`.
- 2026-07-09 fix cache/sblocco agenda:
  - aggiunto cache-buster a `static/js/agenda.js` (`mobile-actions2`) per evitare codice JS stale in PWA;
  - `unlockPrivateVault()` ora segnala errore se `/api/private/unlock` risponde senza `vault.unlocked === true` o se dopo il refresh lo stato full non risulta attivo.
- 2026-07-09 fix vault locale:
  - reso il controllo vault compatibile con ambiente locale/Windows o path configurati via `PRIVATE_VAULT_MOUNT_ROOT` / `PRIVATE_VAULT_DIR`: in questi casi non dipende piu' solo da `/dev/disk/by-uuid` e `os.path.ismount`;
  - rimosso dal frontend il messaggio tecnico sul mancato mount: `unlockPrivateVault()` torna al comportamento silenzioso precedente, ma usa il backend corretto;
  - cache-buster `agenda.js` aggiornato a `mobile-actions3`.
- 2026-07-09 fix default vault Windows:
  - su Windows senza env vault esplicite, `_vault_config()` usa ora `instance/private_vault` invece del default Linux `/mnt/archive/runtime`;
  - in locale Windows `_vault_device_present()` e `_vault_mount_ready()` non bloccano piu' lo sblocco prima della creazione della directory vault;
  - verifica locale helper: `device_present=True`, `mount_ready=True`, path `instance/private_vault`.
- 2026-07-09 bozza Ordini fornitori:
  - aggiunto modulo `/supplier-orders/` accessibile da office in su (`weight >= 40`) e registrato nel menu come `Ordini fornitori`;
  - modelli `SupplierOrderGroup` e `SupplierOrderGroupItem` per creare gruppi fornitore e associare articoli, con relazione molti-a-molti tramite tabella item;
  - UI iniziale per creare/modificare gruppi, cercare articoli, aggiungerli/rimuoverli e vedere la vista acquisto con giacenze;
  - la vista acquisto espande le varianti per codice base solo su suffisso annata a 4 cifre (`19xx`/`20xx`) o codice base esplicito, evitando falsi positivi su codici tecnici con trattini;
  - migrazione `a0b1c2d3e4f5_add_supplier_orders.py` applicata in locale; verifiche: `py_compile`, `node --check`, render `/supplier-orders/` 200, API ricerca articoli 200.
- 2026-07-09 Ordini fornitori refine ricerca/groupage:
  - ricerca articoli ora usa descrizione composta `descrizione - descrizione_aggiuntiva` e cerca anche in `descrizione_aggiuntiva`;
  - vista acquisto aggregata per groupage/codice base: mostra descrizione senza annata e giacenza totale sommata sulle varianti;
  - clic sul groupage apre il dettaglio varianti con codice, descrizione completa e giacenza singola;
  - verifiche: `py_compile routes/supplier_orders.py`, `node --check static/js/supplier_orders.js`, render `/supplier-orders/` 200, API ricerca 200.
- 2026-07-10 Ordini fornitori UI semplificata:
  - pagina principale ridotta a pulsante `Definisci Gruppo` ed elenco gruppi esistenti;
  - definizione/modifica gruppo e associazione articoli spostate in modale dedicata;
  - click su un gruppo apre la modale giacenze aggregate, con dettaglio varianti espandibile;
  - aggiunta ricerca silent sull'elenco gruppi: con il riquadro gruppi selezionato, digitando lettere viene evidenziato il primo match e Invio apre il gruppo;
  - verifiche: `py_compile routes/supplier_orders.py`, `node --check static/js/supplier_orders.js`, render `/supplier-orders/` 200.
- 2026-07-10 fix modali Ordini fornitori:
  - applicato pattern ricorrente documentato: tutte le `.supplier-orders-modal` vengono spostate in `document.body` all'inizializzazione JS;
  - aggiunta classe body `supplier-orders-modal-open` e z-index dedicato per dialog/backdrop, evitando modale visibile ma non interattiva in secondo piano;
  - reset ricerca articoli e pulsanti submit su chiusura modale;
  - cache-buster asset fornitori aggiornato a `draft4`; verifiche: `node --check static/js/supplier_orders.js`, render `/supplier-orders/` 200.
- 2026-07-10 eventi multi-giorno/locandine/link pubblico:
  - gli eventi pubblicati vengono ora renderizzati come occorrenze giornaliere: un evento dal 11 al 12 luglio appare sia nell'11 sia nel 12;
  - aggiunto modello `EventPoster` e migration `b1c2d3e4f5a6_add_event_posters.py` con backfill da `events.poster_path`;
  - i form evento accettano piu' locandine, immagini o PDF convertiti lato browser, e la pagina pubblica le mostra in carosello;
  - aggiunto link pubblico `/events/public`, senza strumenti di gestione, per condivisione esterna/social;
  - corretto filtro prossimi eventi: gli eventi senza data fine restano visibili nel giorno dell'evento ma non per sempre;
  - verifiche: `py_compile`, `flask db upgrade`, render `/events/` 200, render `/events/public` 200, helper multi-giorno con 2 occorrenze.
- 2026-07-10 eventi split consultazione/gestione:
  - `/events/` mostra solo la pagina eventi pubblica; se l'utente ha ruolo office+ compare il pulsante `Gestisci eventi`;
  - aggiunta pagina `/events/manage` per inserimento/modifica eventi e consultazione del link pubblico;
  - aggiunto endpoint dedicato `POST /events/<id>/posters` e form `Scegli file` + `Carica` per aggiungere una o piu' locandine a un evento gia' salvato senza ripubblicare o risalvare i dati evento;
  - lo script locandine/carousel e conversione PDF e' condiviso in `templates/events/poster_script.html`;
  - verifiche: `py_compile`, render `/events/` 200, `/events/public` 200, `/events/manage` 200 con sessione test.
- 2026-07-10 QR app in homepage:
  - aggiunto tile `QR App` visibile a tutti in homepage;
  - il tile apre una modale con QR code per `https://ldapp.ldenoteca.it`, link cliccabile e pulsante `Copia link`;
  - la modale viene spostata in `document.body` all'avvio per evitare problemi di focus/z-index ricorrenti;
  - verifica: render home 200 e presenza markup QR anche per utente anonimo.
- 2026-07-10 fix QR app homepage:
  - sostituito QR remoto `api.qrserver.com` con asset locale `static/img/ldapp_qr.png`, evitando blocchi rete/PWA o mancato caricamento esterno;
  - aggiunto reset CSS su `.quick-action` per rendere coerente il tile `button` con i tile `a`;
  - verifiche: home punta al QR locale, nessun riferimento remoto residuo, asset `/static/img/ldapp_qr.png` servito 200 come `image/png`.
- 2026-07-10 QR app homepage dimensioni:
  - aumentata dimensione dichiarata del QR a 520px e larghezza CSS fino a 520px/92vw;
  - aggiunte regole touch/S25 per modale piu' ampia e QR fino a 760px compatibile con viewport;
  - verifica: render home con asset QR locale e nuova dimensione.
- 2026-07-10 QR app modale tema/touch:
  - modale QR uniformata al tema app con sfondo marrone scuro, testo chiaro e link azzurro info;
  - aggiunta microcopy `Inquadra il codice per aprire LDApp`;
  - ingranditi `btn-close`, pulsanti footer e font; nel layer touch/S25 i pulsanti diventano target da 96px con layout a due colonne;
  - verifica render home con contenuto modale aggiornato.
- 2026-07-10 bozza social eventi:
  - aggiunte categorie `Facebook` e `Instagram` nel tile `Chiavi API/Accounts`, con placeholder Meta App, Page ID, token, Instagram Business Account ID e flag auto-pubblicazione eventi;
  - aggiunto modello `SocialEventPost` e migration `c2d3e4f5a6b7_add_social_event_posts.py` per salvare bozze/stati dei post social eventi;
  - aggiunto servizio `tools/social_events.py` per generare periodi `Eventi della settimana` e `Questo weekend`, selezionare eventi pubblicati nel periodo e creare caption con link pubblico;
  - in `/events/manage` aggiunta sezione `Post social eventi` con generazione bozza e copia testo;
  - aggiunti task Celery `create_weekly_events_social_post_task` e `create_weekend_events_social_post_task`, schedulati lunedi' e venerdi' alle 09:00; per ora creano bozze/stato `config_missing/ready`, senza chiamate API Meta;
  - verifiche: migration applicata, `py_compile`, render `/events/manage` 200, render `/settings/api-keys` con Facebook/Instagram, POST bozza social 302 con caption contenente `/events/public` e rimozione bozza test.
- 2026-07-10 social eventi brand/media:
  - caption social aggiornata con header `LD Enoteca` e footer `LDApp: http://ldapp.ldenoteca.it`;
  - payload media aggiornato con logo aziendale `images/loghi_azienda/logo-ldenoteca-bianco.png` in posizione header;
  - `Eventi della settimana` resta formato `text_list`, mentre `Questo weekend` prepara formato `carousel` con locandine immagine degli eventi del periodo, escludendo PDF;
  - la gestione eventi mostra preview del logo, formato previsto e miniature delle locandine carousel quando la bozza contiene payload media;
  - verifiche: `py_compile tools/social_events.py`, generazione payload weekend con header/footer, formato carousel e locandine candidate; render con bozza temporanea non ripetuto per timeout DB remoto.
- 2026-07-11 anteprima social eventi:
  - in `/events/manage` ogni bozza social mostra anteprima in due colonne: card stile Facebook e card stile Instagram;
  - Facebook mostra avatar/logo LD Enoteca, caption completa e box link pubblico eventi;
  - Instagram mostra carousel quadrato se il payload e' `carousel`, altrimenti card grafica testuale con logo e periodo;
  - aggiunti stili responsive/touch per anteprime grandi e leggibili su smartphone;
  - verifiche: render `/events/manage` 200 e presenza classi anteprima Facebook/Instagram.
- 2026-07-11 anteprima social eventi refine:
  - anteprime Facebook/Instagram aggiornate con barra header nera e logo LD Enoteca grande;
  - sfondo preview portato al marrone app;
  - link app `http://ldapp.ldenoteca.it` reso elemento cliccabile nell'anteprima;
  - payload carousel weekend ora usa una sola locandina per evento anche se l'evento ne ha piu' di una;
  - slide carousel arricchite con badge data in stile calendario (mese/giorno);
  - verifiche: `py_compile tools/social_events.py`, payload weekend con una slide per evento e date calendario valorizzate.
- 2026-07-11 correzione formato post weekend:
  - caption `weekend` cambiata in `In programma questo weekend`, senza riga date e senza header testuale `LD Enoteca`;
  - rimosse dalla caption le righe `Tutti gli eventi:` e `LDApp:`;
  - footer anteprima/post impostato a `Tutti gli eventi e le info sulla nostra app nella sezione eventi` con CTA cliccabile `LDApp` verso `https://ldapp.ldenoteca.it`;
  - anche l'anteprima Facebook usa il carousel locandine per il post weekend, con fallback testuale per eventi senza locandina;
  - preview locandine ora preferisce `poster_path` locale rispetto a URL assoluti salvati nel payload, evitando immagini non caricate dopo deploy;
  - verifiche: `py_compile`, caption weekend senza righe ridondanti, payload con una slide per evento, render `/events/manage` 200.
- 2026-07-11 eliminazione bozze social:
  - aggiunta route `POST /events/social-posts/<id>/delete` protetta office+;
  - in `/events/manage` ogni bozza social ha pulsante `Elimina bozza` con conferma browser;
  - verifiche: `py_compile routes/events.py`, render `/events/manage` 200 con form delete presente.
- 2026-07-11 grafica post eventi settimana:
  - payload `Eventi della settimana` cambiato da `text_list` a `week_card`, mantenendo stessa anteprima per Facebook e Instagram;
  - card settimana con header nero/logo, sfondo marrone app, titolo `Eventi della settimana`, sottotitolo date periodo e corpo con righe evento;
  - ogni riga mostra data in stile calendario, titolo, data/luogo e miniatura locandina se presente;
  - non viene ripetuto il logo dentro la grafica, resta solo nella testata;
  - footer/CTA LDApp condiviso con le altre anteprime;
  - verifiche: `py_compile`, payload settimana `week_card` con 4 eventi/4 miniature, render anteprima con bozza temporanea e rimozione immediata.
- 2026-07-11 allineamento anteprime settimana:
  - anteprima Facebook allineata a quella Instagram: entrambe usano la stessa `events-week-card-preview`;
  - rimosso testo/caption ridondante sotto la grafica nelle anteprime;
  - rimossa sfumatura dalle aree grafiche social, sostituita da marrone pieno app;
  - date multi-giorno nei badge calendario mostrate come intervallo, es. `JUL` e `11 - 12`;
  - verifiche: `py_compile`, test calendario multi-giorno, bozza settimana temporanea con due card preview e nessuna caption visibile, poi rimossa.
- 2026-07-11 eventi/admin split e registrazione esercente:
  - gli eventi ora distinguono data obbligatoria e orario opzionale: aggiunti flag `starts_time_known` e `ends_time_known`, migration `d3e4f5a6b7c8_event_time_flags_and_role_requests.py`;
  - nei form gestione eventi l'inizio/fine sono separati in data e ora opzionale; la pagina pubblica mostra l'orario solo se indicato;
  - separata la sezione social in `/events/social-posts`, raggiungibile dal tasto `Post social` accanto a `Gestisci eventi`; `/events/manage` resta dedicata alla gestione eventi;
  - aggiunto modello `RoleActivationRequest` e checkbox `Esercente` in registrazione, che crea una richiesta pendente per ruolo `customer_horeca`;
  - verifiche: migration applicata fino a `d3e4f5a6b7c8`, `py_compile`, render `/events/`, `/auth/login`, `/auth/register`, `events/manage.html` e `events/social_posts.html`.
- 2026-07-12 contattaci:
  - aggiunto pulsante `Contattaci` nel gruppo utente della navbar/drawer, posizionato prima del menu profilo/accesso;
  - aggiunta modale globale con oggetto predefinito, email risposta modificabile/precompilata per utenti autenticati, campo `Altro` condizionale e messaggio obbligatorio;
  - aggiunta route `POST /auth/contact` che invia email a `assistenza.ldapp@ldenoteca.it`, usando `reply_to` con l'email indicata dall'utente;
  - verifiche: `py_compile routes/auth.py`, render navbar con modale, POST test con `mail.send` simulato e oggetto `altro - ...`.
- 2026-07-12 fix contattaci drawer:
  - il click su `Contattaci` chiude preventivamente il drawer mobile e rimuove `mobile-menu-open`;
  - alzato lo z-index della modale `ld-contact-modal` e del backdrop sopra i vecchi layer del drawer;
  - verifica: render navbar con trigger `#ldContactModal`.
- 2026-07-12 registrazione esercente mail:
  - quando in registrazione viene spuntato `Esercente`, oltre alla richiesta `RoleActivationRequest` viene inviata una mail a `assistenza.ldapp@ldenoteca.it`;
  - oggetto email `attivazione cliente horeca`, `reply_to` impostato sull'email dell'utente e corpo con dati anagrafici/contatto utili per rispondere ad attivazione completata;
  - label e placeholder del campo città cambiati in `Citta di residenza`;
  - verifiche: `py_compile`, render `/auth/register`, POST registrazione test con `mail.send` simulato, richiesta creata e record test ripuliti.
- 2026-07-12 ticket assistenza/admin:
  - aggiunti modelli `SupportTicket`, `SupportTicketMessage`, `SupportTicketAttachment` e migration `e4f5a6b7c8d9_add_support_tickets.py`;
  - `Contattaci` ora crea un ticket `support`, salva primo messaggio e allegati, poi invia notifica da `assistenza.ldapp@ldenoteca.it`;
  - la registrazione con `Esercente` crea anche ticket `horeca_activation` collegato a `RoleActivationRequest`;
  - aggiunte pagine impostazioni `Assistenza LDApp` (developer, peso 900) e `Attivazioni Horeca` (office+, peso 40), con dettaglio ticket, risposta email, allegati e cambio stato;
  - l'attivazione Horeca associa utente a `BusinessRegistry`, chiude ruolo `customer`, aggiunge `customer_horeca`, marca ticket/richiesta approvati e invia email al cliente;
  - aggiunto badge ruolo sotto il profilo: `visitatore` per anonimi, ruolo attivo massimo per utenti autenticati;
  - verifiche: `py_compile`, `flask db upgrade` a `e4f5a6b7c8d9`, render liste admin, POST `Contattaci` e registrazione esercente con `mail.send` simulato e cleanup dati test.
- 2026-07-12 rifiniture notifiche/menu/assistenza:
  - task-status in-app centrato nella pagina e non piu' ancorato a tutta la larghezza fuori schermo; durante drawer aperto segue lo shift senza uscire dal viewport;
  - invii email assistenza/reset uniformati tramite connessione esplicita `mail.connect()`, evitando l'errore `please run connect() first`;
  - nuova migration dati `f5a6b7c8d9e0_reorganize_customer_service_menus.py`: nasconde root `Impostazioni`, sposta i figli sotto `Strumenti`, crea root `Servizio clienti` con `Attivazioni Horeca` e `Assistenza LDApp`;
  - rimossi i tile Assistenza/Attivazioni dalla dashboard Impostazioni: ora si raggiungono dal menu;
  - logo navbar arricchito con hint visivo `Home` e title/aria-label `Torna alla home`;
  - gestione menu: modale spostata/focalizzata correttamente in apertura e drag/drop limitato al primo livello root per ridurre l'ingombro visivo dello spostamento;
  - verifiche: `py_compile`, `flask db upgrade` a `f5a6b7c8d9e0`, lettura menu DB, render navbar/menus/settings, POST Contattaci con `_send_mail` simulato e cleanup.
- 2026-07-12 fix flash e invio assistenza:
  - i flash globali `#flash-message` vengono centrati nella pagina con override `!important`, cosi' vincono anche sugli stili locali delle pagine impostazioni e non restano tagliati a sinistra;
  - `_send_mail()` reinizializza Flask-Mail con `current_app.config` prima di inviare, necessario per rispettare i parametri email aggiornati runtime da preferenze/impostazioni;
  - verifiche: `_send_mail()` con `MAIL_SUPPRESS_SEND=True` non apre connessioni SMTP; POST `/auth/contact` crea il ticket e mostra `Richiesta inviata correttamente`, poi cleanup ticket test; `py_compile routes/auth.py routes/settings.py`.
- 2026-07-12 fix mittente mail assistenza:
  - reset password usa il mittente SMTP predefinito, mentre contattaci/assistenza forzavano `assistenza.ldapp@ldenoteca.it` come `sender`;
  - aggiunto `_mail_sender()` per spedire le mail assistenza con `MAIL_DEFAULT_SENDER`/`MAIL_USERNAME`, mantenendo `assistenza.ldapp@ldenoteca.it` come destinatario o `reply_to` dove necessario;
  - verifiche: nessun `sender=ASSISTANCE_EMAIL` residuo, `py_compile`, POST `/auth/contact` con invio soppresso crea ticket e flash success.
- 2026-07-12 account mail assistenza separato:
  - introdotta configurazione SMTP dedicata `ASSISTANCE_MAIL_*` per usare `assistenza.ldapp@ldenoteca.it` come vero account mittente delle comunicazioni assistenza;
  - `MAIL_*` resta riservato alle email applicative come reset password, mentre contattaci, risposte ticket e attivazioni Horeca usano `send_assistance_mail()`;
  - pagina Email estesa con campi `ASSISTANCE_MAIL_SERVER/PORT/USE_TLS/USE_SSL/USERNAME/PASSWORD/DEFAULT_SENDER`;
  - verifiche: `py_compile`, POST `/auth/contact` con invio soppresso e account assistenza configurato crea ticket e flash success.
- 2026-07-13 account email DB-driven:
  - aggiunto modello `EmailAccount` e migration `0a1b2c3d4e5f_add_email_accounts.py`, applicata al DB;
  - password SMTP salvate cifrate con `EncryptedString`;
  - `/settings/email` mostra account codificati invece dei singoli parametri sparsi;
  - codici di sistema: `general` per reset password/notifiche applicative e `assistance` per ticket/attivazioni Horeca;
  - mantenuto fallback su `MAIL_*` e `ASSISTANCE_MAIL_*` finche' i due account non vengono salvati dal pannello;
  - aggiunta modale unica per creazione/modifica con nome, codice, server, porta, TLS/SSL, username, password, mittente e stato attivo;
  - account personalizzati eliminabili; account di sistema disattivabili ma non eliminabili;
  - servizio `send_account_mail(code, message)` disponibile per collegare nuovi account a future funzioni applicative;
  - fix modale in secondo piano: append al `body` prima dell'istanza Bootstrap, z-index dedicato per dialog/backdrop e reset submit su apertura/chiusura;
  - verifiche: `py_compile`, `git diff --check`, migrazione DB fino a `0a1b2c3d4e5f`, GET `/settings/email` 200, creazione/cifratura/rimozione account temporaneo, render account legacy e `node --check` dello script renderizzato.
- 2026-07-13 predisposizione risposte email ticket - step 1:
  - esteso `EmailAccount` con configurazione IMAP completa: server, porta, TLS/SSL, username, password cifrata, cartella e abilitazione;
  - aggiornata la modale `/settings/email` per creare/modificare nello stesso account sia SMTP sia posta in entrata;
  - aggiunto `SupportTicket.public_token` non prevedibile per il futuro accesso sicuro ai ticket anonimi; i ticket esistenti sono stati backfillati;
  - aggiunti a `SupportTicketMessage` i campi `source`, `external_message_id` univoco e `in_reply_to` per correlazione RFC e deduplica delle risposte ricevute;
  - migration `1b2c3d4e5f60_add_inbound_mail_ticket_fields.py` applicata al DB;
  - il numero ticket restera' una chiave di correlazione ma non sara' sufficiente come autorizzazione web: per le email verra' verificato anche il mittente, per il browser verra' usato il token pubblico;
  - verifiche: `py_compile`, `git diff --check`, migrazione DB fino a `1b2c3d4e5f60`, account IMAP temporaneo creato con password cifrata e rimosso, token ticket esistenti completi/univoci, `node --check` dello script Email renderizzato;
  - prossimo step: servizio IMAP periodico con parsing messaggi/allegati, correlazione ticket e deduplica.
- 2026-07-13 Help Desk e risposte email ticket - implementazione completata:
  - scelta naming: `Help Desk` e' il punto di accesso utente in navbar/drawer; `Servizio clienti` resta il menu interno dello staff per Attivazioni Horeca e Assistenza LDApp;
  - la modale Help Desk espone `Nuova richiesta` e, per autenticati, `I miei ticket` con elenco, stato e ultimo aggiornamento;
  - aggiunte route cliente `GET /auth/help-desk/tickets` e `GET/POST /auth/help-desk/ticket/<token>`;
  - il dettaglio mostra l'intera corrispondenza e consente risposte/allegati; gli allegati cliente passano da route protetta dal token invece che da URL statico diretto;
  - ticket anonimi accessibili con token sicuro ricevuto via email; se l'utente accede dal link dopo login con la stessa email, il ticket viene associato al suo account;
  - alla creazione viene inviata conferma al cliente con numero ticket e link sicuro, salvata anche nella conversazione come messaggio di sistema;
  - le risposte staff includono `Message-ID`, `[Ticket #ID]` e link alla conversazione;
  - aggiunto `tools/support_mailbox.py`: polling IMAP, parsing testo/HTML, allegati, correlazione tramite `In-Reply-To`/`References` e fallback numero ticket, controllo mittente e deduplica `Message-ID`/hash;
  - aggiunto task `config.tasks.sync_support_mailbox_task` ogni 2 minuti e pulsante `Sincronizza assistenza` in `/settings/email`;
  - una risposta cliente ricevuta riapre il ticket e viene salvata con `source='email'`;
  - verifiche: `py_compile`, `node --check static/js/menu.js`, `git diff --check`, render Help Desk anonimo, elenco autenticato 200, dettaglio token 200, risposta web 302, conferma con due messaggi e `Message-ID`, import IMAP simulato `imported=1` e seconda lettura `duplicates=1`, cleanup dati test;
  - test reale residuo: configurare e abilitare IMAP sull'account `assistance`, poi usare `Sincronizza assistenza` o attendere Celery Beat.
- 2026-07-13 fix encoding email UTF-8:
  - `send_account_mail()` passa ora a `smtplib.sendmail()` il MIME serializzato con `Message.as_bytes()` invece di `as_string()`;
  - risolto l'errore `ascii codec can't encode character` con accenti nei messaggi Help Desk/assistenza e negli altri invii centralizzati;
  - verifica con SMTP simulato: oggetto e corpo contenenti `è`, `à` e `ò` serializzati/inviati come bytes MIME UTF-8.
- 2026-07-13 bollini nuovi messaggi Help Desk:
  - aggiunti `SupportTicketMessage.read_by_user_at` e `read_by_support_at` con migration `2c3d4e5f6071_add_ticket_message_read_state.py`, applicata al DB;
  - i messaggi preesistenti sono stati marcati letti durante la migrazione per evitare notifiche storiche spurie;
  - messaggi `support` non letti alimentano il bollino utente sulla navbar Help Desk e il conteggio per singolo ticket in `I miei ticket`;
  - messaggi `user` non letti alimentano il bollino staff sulla voce DB `Assistenza LDApp` e sulle righe della lista assistenza;
  - endpoint conteggio: `/auth/help-desk/unread-count` per l'utente e `/settings/support-tickets/unread-count` per l'assistenza;
  - polling frontend ogni 60 secondi su entrambi i lati; apertura dettaglio marca letti soltanto i messaggi destinati al lato che sta visualizzando;
  - messaggi creati via web/IMAP vengono marcati letti dal mittente e lasciati non letti per il destinatario;
  - verifiche DB end-to-end: conteggi iniziali utente/assistenza `1/1`, apertura utente `0/1`, apertura staff `0`, badge presenti nel menu/lista, `node --check`, `py_compile`, `git diff --check`.
- 2026-07-13 fix modali tile utenti:
  - le modali di `/settings/users` hanno ora stacking dedicato sopra il backdrop globale dell'app;
  - i passaggi dalla scheda utente alle modali Ruolo, Autorizzazioni, Reset password ed Elimina attendono la chiusura completa della modale corrente prima di aprire la successiva;
  - append al `body`, gestione backdrop e lifecycle sono limitati alle sole modali utenti.
- 2026-07-13 pubblicazione ordini clienti Horeca:
  - `POST /customer-orders/` pubblica ora l'ordine sul canale Slack del giro associato e crea contestualmente `SlackOrder` e `RouteOrderBoardEntry`;
  - `CustomerOrder.route_board_entry_id` e `CustomerOrder.slack_order_id` vengono valorizzati e usati come guardia idempotente contro doppie pubblicazioni;
  - Slack riceve un `client_msg_id` stabile per ordine e gli allegati caricati dal cliente sono ammessi nel flusso di upload Slack;
  - i messaggi generati da bot/app vengono esclusi dal dispatcher delle automazioni Slack dopo il side-effect ordini, evitando catene ricorsive;
  - se Slack o la pubblicazione in bacheca falliscono, la transazione ordine viene annullata e il cliente riceve un errore esplicito;
  - verifica con Slack simulato e DB in rollback: un post, collegamenti bacheca/Slack presenti, seconda pubblicazione idempotente, automazioni bot non eseguite.
- 2026-07-14 badge gerarchici e gestione menu:
  - il badge di `Servizio clienti` somma ora gli elementi da gestire presenti nei figli visibili `Assistenza LDApp` e `Attivazioni Horeca`;
  - il polling staff aggiorna separatamente i conteggi assistenza/attivazioni e tutti i relativi antenati; endpoint disponibile da peso ruolo 40;
  - l'albero `/settings/menus` e' collassabile e SortableJS e' attivo su ogni livello, incluse le liste figlie vuote, consentendo di trasformare una voce principale in sotto-menu;
  - durante il drag viene mostrato un placeholder azzurro nel punto di inserimento e le liste vuote espongono una zona di rilascio esplicita;
  - la modale menu viene spostata nel `body`, usa z-index dedicato sopra il backdrop globale e ripristina pulsante/stato su `shown.bs.modal` e `hidden.bs.modal`;
  - verifiche: `py_compile`, `node --check` sui due script, `git diff --check`, GET home/menu/endpoint 200 e rendering reale del badge aggregato `activation,support`.
- 2026-07-14 stabilizzazione inserimenti Agenda incassi/assegni/clienti:
  - corretto lo stato persistente dei carrier: all'apertura di un nuovo incasso e nel caricamento in modifica `applyPriCarrierRules()` riallinea sempre i controlli al flag corrente;
  - aggiunto lock frontend `operationSaving` prima delle risoluzioni asincrone, impedendo submit concorrenti prima che il pulsante Salva venga disabilitato;
  - la scelta da suggeritore/modale conserva `registry_id` e demanda la risoluzione a un unico punto durante il salvataggio, eliminando richieste concorrenti e selezioni transitorie;
  - aggiunto modello/tabella `CashCustomerRegistryLink` e migration `3d4e5f607182_add_cash_customer_registry_links.py`, applicata al DB;
  - il resolver usa prima l'associazione persistente, crea collegamenti solo per match univoci codice/P.IVA e rifiuta esplicitamente eventuali ambiguita';
  - backfill completato: 2.002/2.002 anagrafiche clienti attive collegate, zero codici ambigui; doppia risoluzione verificata idempotente senza nuove righe;
  - `static/js/agenda.js` normalizzato in UTF-8 sostituendo i byte CP1252 invalidi preesistenti (`€`, `•`, accenti);
  - verifiche: `py_compile`, `node --check`, `git diff --check`, endpoint suggerimenti/resolve 200 e Alembic current/head `3d4e5f607182`.
- 2026-07-14 cancellazione ordini Slack non proprietari:
  - confermato il limite Slack: il bot puo' cancellare con `chat.delete` soltanto messaggi pubblicati dallo stesso bot;
  - `SlackAPI.delete_or_mark_message()` tenta prima la cancellazione reale e, se rifiutata, inserisce nel thread `Ordine eliminato dalla bacheca da <operatore>` e applica `:wastebasket:` al messaggio radice;
  - fallback condiviso dai percorsi di cancellazione Kiosk e bacheca ordini; la cancellazione locale continua e la UI informa l'operatore quando Slack e' stato soltanto contrassegnato;
  - test simulati: messaggio del bot cancellato senza marker; messaggio non eliminabile marcato con commento nel thread e reaction corretti.
  - corretto il successivo HTTP 500 nella cancellazione locale: gli eventi `SlackOrderEvent` vengono ora eliminati in cascata dall'ORM, senza tentare di impostare a `NULL` la loro chiave obbligatoria; entrambi gli endpoint eseguono rollback e restituiscono un errore esplicito se il commit locale fallisce.
  - la cancellazione Slack legge ora l'intero thread e rimuove prima le risposte/allegati pubblicati dall'app, quindi il messaggio radice; in presenza di risposte di altri autori non elimina la radice e applica invece commento e reaction, evitando allegati orfani.
- 2026-07-14 associazione attivazioni Horeca:
  - rimosso il limite statico delle prime 500 anagrafiche nelle pagine elenco e dettaglio ticket;
  - aggiunto lookup server-side sull'intero archivio clienti attivi per denominazione, ragione sociale, codice cliente e partita IVA, con selezione obbligatoria di un risultato valido;
  - verifica DB su 2.002 clienti attivi: trovato correttamente tramite codice un cliente in posizione 701, oltre il vecchio limite; verificati template, JavaScript, Python e `git diff --check`.
- 2026-07-15 revisione gestione gruppi ordini fornitori:
  - risolto il fuori fuoco delle modali: il backdrop globale e' a quota `12040`, quindi le modali fornitori vengono ora portate nel `body`, aperte tramite istanza Bootstrap esplicita e posizionate a `12110` con backdrop dedicato a `12100`;
  - resa evidente l'azione `Gestisci prodotti` e rinominata la sezione di ricerca in `Aggiungi prodotti al gruppo`, con istruzioni e validazione che obbliga a scegliere un risultato valido;
  - il `group_id` gia' presente nei redirect viene ora letto: dopo creazione/modifica/aggiunta la modale si riapre, il gruppo interessato resta espanso e il focus torna alla ricerca prodotti;
  - aggiunta gestione leggibile degli errori del lookup articoli e reset coerente dei pulsanti/risultati nei lifecycle `show/shown/hidden`;
  - verifiche: pagina autorizzata 200 con gruppo richiesto aperto, lookup reale 200/20 risultati, template compilato, `node --check`, `py_compile`, `git diff --check`.
- 2026-07-16 nuova UI gruppi ordini fornitori:
  - `Definisci Gruppo` apre una modale dedicata esclusivamente a nome/note; in creazione il comando `Crea e gestisci prodotti` salva e apre automaticamente il gestore del nuovo gruppo, mentre la stessa modale viene riusata da `Modifica` con i dati esistenti;
  - i gruppi sono esposti a righe con azioni `Consulta`, `Prodotti`, `Modifica`, `Elimina`; click/Invio/spazio sulla riga apre la consultazione per codice matrice e giacenze;
  - aggiunta cancellazione gruppo con conferma e nuova route `POST /supplier-orders/groups/<id>/delete`;
  - il gestore prodotti usa due pannelli alfabetici: catalogo filtrato a sinistra e prodotti associati a destra, selezionabili con click o spazio; disponibili aggiunta/rimozione dei selezionati e operazioni massive sui risultati visibili/intero gruppo;
  - aggiunte API `GET /supplier-orders/groups/<id>/items` e `POST /supplier-orders/groups/<id>/items/batch`; descrizioni sempre composte da `descrizione` e `descrizione_aggiuntiva`;
  - test end-to-end con gruppi temporanei: creazione 302 verso gestore, pagina 200, aggiunta batch 1, lettura 1, rimozione batch 1, lettura 0, eliminazione 302 e zero residui; verificati template, JS, Python e diff.
- 2026-07-16 fix refresh, matrici e titoli ordini fornitori:
  - alla chiusura del gestore prodotti la pagina viene ricaricata soltanto se una modifica e' stata salvata, aggiornando conteggi e modali di consultazione;
  - `_variant_root()` riconosce ora annate sia a due cifre (`-20`) sia a quattro (`-2020`); la variante piu' recente viene scelta con ordinamento cronologico del suffisso;
  - introdotto `SupplierOrderMatrixName` e migration `4e5f60718293`, applicata al DB, per salvare un titolo personalizzato per coppia gruppo/codice matrice senza modificare articoli o matrice;
  - la consultazione mostra codice matrice, numero varianti e comando di rinomina; nome vuoto rimuove l'override e ripristina la descrizione completa dell'ultima variante;
  - test reale `VR075156`: una sola matrice con 8 varianti (`-14` ... `-23`), default `VINO MONTEPULCIANO 2023 75cl - CHRONICON - ZACCAGNINI`, rinomina persistita e reset con zero override residui;
  - verificati migration, modello, route, template, JavaScript, Python e `git diff --check`.
- 2026-07-18 menu contestuale card bacheca ordini:
  - la pressione lunga touch/pen usa una soglia di movimento di 20 px invece di annullarsi a ogni minimo `pointermove`; durata 420 ms;
  - la scelta di un nuovo stato o dell'eliminazione chiude sincronicamente il dropdown prima della richiesta e del rerender;
  - il menu viene chiuso su tap/click fuori da menu e toggle, cambio focus, `Escape`, blur finestra, resize, scroll e pagina nascosta;
  - ogni rerender/refresh automatico chiude e ripristina prima il menu flottante, impedendo nodi orfani nel `body`;
  - cache asset portata a `mobile-board10`; verificati `node --check`, compilazione template e `git diff --check`.
- 2026-07-18 refresh trasparenti bacheca/Agenda e cornice card:
  - la bacheca calcola una firma dei dati renderizzati e non ricostruisce il DOM durante il polling se nulla e' cambiato;
  - se arrivano modifiche mentre un menu card e' aperto, conserva DOM/menu e differisce il rendering fino alla chiusura; le azioni sulla card chiudono il menu e applicano subito il refresh pertinente;
  - un errore temporaneo del polling non svuota piu' una bacheca gia' popolata;
  - le card hanno sfondo bianco e cornice da 3 px ottenuta dal colore precedente, resa piu' decisa tramite `color-mix`; mantenuti gli indicatori speciali di consegna;
  - `_bump_agenda_day_version()` restituisce la versione Redis incrementata e il toggle check la invia al frontend come `agenda_version`; la modifica locale viene registrata subito e non innesca il successivo refresh del polling;
  - i refresh Agenda realmente esterni preservano scroll della pagina e dei pannelli Incassi, Spese, POS e Movimenti di cassa;
  - asset aggiornati a `mobile-board11` e `mobile-actions4`; verificati JS, Python, template, bump versione simulato `42` e `git diff --check`.
- 2026-07-18 fix pressione lunga su mobile reale:
  - le hot-zone laterali della card non escludono piu' il long press; il click di cambio stato viene soppresso quando il gesto ha aperto il menu;
  - il drag HTML5 delle card resta disponibile con mouse ma viene disabilitato sui dispositivi `hover:none/pointer:coarse`, evitando il `pointercancel` del browser mobile;
  - su mobile le card usano `touch-action: pan-y`, callout e selezione testo disabilitati, mantenendo lo scroll verticale senza cedere la pressione lunga al drag nativo;
  - cache aggiornata a `mobile-board12`.
- 2026-07-18 diagnosi strumentata e fix rilascio long press mobile:
  - riprodotto in Edge mobile 390x844 tramite eventi touch CDP: il menu si apriva correttamente dopo 420 ms a `x=25, y=310`, ma il click sintetico al rilascio colpiva il menu appena sovrapposto e Bootstrap lo chiudeva subito;
  - il primo click sintetico touch/pen successivo al long press viene ora intercettato in capture, senza selezionare voci e senza raggiungere l'auto-close Bootstrap;
  - controprova automatizzata: dopo `touchEnd` il menu resta presente, visibile e aperto (`320x520`); cache aggiornata a `mobile-board13`.
- 2026-07-18 posizionamento e scroll menu card mobile:
  - il dropdown flottante viene vincolato con coordinate `fixed` alla `visualViewport`, neutralizzando gli aggiornamenti tardivi di Popper; il centro verticale del menu segue quello della card e viene limitato entro 14 px dai bordi visibili;
  - altezza massima calcolata dalla viewport dinamica, overflow verticale touch, overscroll contenuto e scorrimento inerziale rendono raggiungibili tutte le azioni;
  - il listener globale non chiude piu' il dropdown quando a scorrere e' il menu stesso, ma continua a chiuderlo per scroll esterni;
  - test reali Edge/CDP con 17 card: menu interamente nella viewport a inizio/centro/fondo pagina su 390x844 e 360x640; su 360x520 pannello `492 px`, contenuto `572 px`, overflow `auto` e `scrollTop` modificabile senza chiusura; cache `mobile-board14`.
- 2026-07-18 ruolo registrazione e logo navbar assistenza:
  - `POST /auth/register` assegna contestualmente il ruolo lifetime `customer`; se il ruolo base non e' configurato la registrazione viene fermata con errore esplicito invece di creare un utente senza autorizzazioni;
  - il brand navbar non puo' piu' restringersi nel layout flex, il logo dichiara dimensioni e priorita' di caricamento ed e' precaricato dal service worker `ldapp-cache-v23` per il fallback di rete;
  - test end-to-end con utente temporaneo: redirect login e unico ruolo `customer`, poi cleanup verificato; pagina assistenza 200 e logo PNG 200/34.470 byte.
- 2026-07-18 azioni menu card e callout mobile:
  - eliminata la finestra di 800 ms che poteva intercettare il primo tap intenzionale su una voce; il click sintetico di rilascio viene bloccato per soli 180 ms;
  - il menu completa il long press sia su `pointerup` sia su `pointercancel`, usato dai browser che tentano di aprire il context menu nativo;
  - `contextmenu` viene annullato in capture su card/menu nei dispositivi coarse/no-hover e il callout/selezione sono disabilitati anche sul pannello flottante;
  - ignorati esclusivamente i rimbalzi iniziali di focus/scroll entro 250 ms dall'apertura; `data-bs-auto-close=outside`, mentre gli handler di stato/eliminazione chiudono esplicitamente il menu;
  - test Edge touch con 24 card: sequenza `show/shown`, menu ancora visibile dopo il rilascio, voce azione individuata e sequenza di chiusura dell'handler; nessun evento DB di cambio stato prodotto dal test; cache `mobile-board15`.
- 2026-07-20 fix mobile Attivazioni Horeca, Assistenza LDApp e login:
  - Attivazioni Horeca e dettaglio ticket hanno layout mobile verticale, controlli touch e azioni a piena larghezza;
  - Assistenza LDApp trasforma la tabella ticket in schede etichettate sugli schermi stretti e rende filtri/intestazioni utilizzabili da smartphone;
  - il lookup cliente conserva `registry_id` quando viene scelto un risultato e non rilancia una ricerca sull'etichetta completa; aggiunto recupero sicuro dell'ID dall'etichetta, sempre validato dal backend;
  - la card login non si restringe e non nasconde piu' i link inferiori su viewport mobile, incluso `Crea un nuovo account`;
  - cache CSS aggiornata a `mobile14`; verificati template Jinja, login via test client, sintassi JavaScript, selezione lookup e `git diff --check`.
- 2026-07-20 revisione lista e dettaglio Assistenza LDApp:
  - la lista iniziale non usa piu' la tabella dettagliata: ogni ticket e' una scheda interamente cliccabile con barra `numero - stato - aggiornamento` e seconda riga limitata ad autore/Visitatore e oggetto;
  - dimensioni tipografiche e spaziature sono state aumentate per la lettura da smartphone;
  - il dettaglio espone `Rispondi` nell'intestazione e apre una modale con messaggio e allegati; lifecycle di pulsante, testo, handler e form viene inizializzato su `shown.bs.modal` e ripulito su `hidden.bs.modal`;
  - cambio stato mantenuto nel dettaglio con elenco di stati tradotti e pulsante `Salva stato`; lo stato `Attivato` resta disponibile soltanto per i ticket Horeca;
  - cache CSS aggiornata a `mobile15`; verificati compilazione Jinja e `git diff --check`.
- 2026-07-20 dashboard Developer e analytics prima parte:
  - aggiunti blueprint `/developer`, route `/developer/dashboard` e menu DB-driven `Developer > Dashboard`, entrambi riservati al ruolo `dev` tramite peso `999` anche lato backend;
  - la dashboard mostra visitatori unici, visite totali, registrati totali e conteggi per ciascun ruolo attivo, segnalando anche eventuali utenti senza ruolo attivo;
  - introdotto `AppVisitor`/`app_visitors` con migration `5f60718293a4`, applicata al DB; le statistiche visite decorrono dall'attivazione del sistema;
  - analytics first-party aggregati: cookie casuale persistente salvato solo come SHA-256, sessione visita di 30 minuti, nessun IP, user-agent, URL o collegamento account memorizzato, esclusione bot nota e rispetto `DNT`/`Sec-GPC`;
  - cookie `HttpOnly`, `SameSite=Lax`, `Secure` su HTTPS anche dietro `X-Forwarded-Proto`; il cookie analytics va descritto nell'informativa privacy/cookie;
  - test end-to-end: prima visita `0 -> 1`, refresh senza incremento, DNT non tracciato, dashboard renderizzata come dev, menu verificato e dati test rimossi; cache CSS `mobile16`.
- 2026-07-20 storico e spese assegni clienti:
  - la modifica anagrafica dell'assegno non puo' piu' cambiare direttamente lo stato; le transizioni passano da `POST /cassa/api/checks/<id>/events` con validazione del percorso operativo;
  - aggiunta modale `Stato e storico` con timeline, data evento, banca, spese bancarie, note e penale cliente; il lifecycle del pulsante viene inizializzato su `shown.bs.modal` e ripulito su `hidden.bs.modal`;
  - ogni transizione persiste un `CashCheckEvent`; le spese bancarie generano nella stessa transazione una vera `CashExpense` con pagamento `bank`, flag aziendale `*`, categoria `Spese bancarie assegni` e collegamento `cash_expense_id`;
  - il passaggio a `protested` calcola lato server una penale cliente del 10% del valore assegno con arrotondamento monetario `ROUND_HALF_UP`; la spesa bancaria resta distinta dalla penale;
  - percorsi supportati includono `received -> deposited -> bounced -> deposited -> protested/cashed`, oltre a spostato, anticipato e ritirato; gli stati terminali limitano le transizioni disponibili;
  - migration `60718293a4b5_add_check_event_expenses.py` applicata: aggiunto FK evento-spesa e backfill tecnico per i 27 assegni senza eventi; ora 51/51 assegni hanno almeno un evento, senza ricostruire transizioni storiche non conoscibili;
  - test end-to-end temporaneo: `received, deposited, bounced, deposited, protested`, due spese Agenda da 12,34/20,00, penale protesto 10,00 su assegno 100,00, cleanup completo; vecchio cambio stato verificato HTTP 400; Alembic current/head `60718293a4b5`;
  - asset aggiornati a `check-history1` e `mobile17`; verificati Jinja, JavaScript, Python e `git diff --check`.
- 2026-07-21 pubblicazione bozze eventi su Meta:
  - le bozze social gia' generate possono essere pubblicate separatamente su Facebook e Instagram dalla pagina `/events/social-posts`;
  - Facebook pubblica le locandine come foto non pubblicate collegate a un unico post, oppure un post con link quando non sono disponibili immagini;
  - Instagram pubblica una singola immagine o un carosello fino a 10 locandine, attendendo il completamento dei container prima di inviarli;
  - esito, ID esterno, permalink, data ed eventuale errore vengono conservati per singolo canale nel payload della bozza; un canale gia' pubblicato non viene duplicato durante un nuovo tentativo;
  - i task automatici ora effettuano realmente l'invio quando l'auto-pubblicazione e le credenziali del relativo canale sono configurate.
- 2026-07-21 mailing list:
  - implementata la voce `Strumenti > Mailing List` su `/mailing-list/`, mantenendo il peso di accesso 100;
  - gestione iscritti con consenso, stato attivo/disiscritto e token pubblico non prevedibile per la disiscrizione;
  - creazione bozze campagna con scelta dell'account SMTP configurato e invio asincrono individuale tramite Celery;
  - storico aggregato destinatari/inviati/errori e dettaglio tecnico per singola consegna, senza esporre gli indirizzi degli altri destinatari;
  - migration `b5c6d7e8f9a0_add_mailing_list.py` aggiunge iscritti, campagne, consegne e aggiorna la route del menu.
  - fix scrolling: tutto il contenuto della pagina e' ora racchiuso nel contenitore flessibile `page-scroll`, con scorrimento touch inerziale e overscroll contenuto.
- 2026-07-24 mailing list multiple e cluster clienti:
  - aggiunte liste distinte con appartenenze deduplicate; le liste di sistema `Clienti` e `Utenti APP` sono alimentate rispettivamente dalle anagrafiche TeamSystem e dagli utenti registrati;
  - i clienti sono filtrabili per coppia categoria-sottocategoria usando i codici come chiave stabile e le descrizioni importate per l'interfaccia; gli utenti sono filtrabili per ruolo attivo;
  - le campagne sono associate a una singola lista e inviano solo ai relativi membri attivi, rispettando lo stato globale di disiscrizione;
  - migration `d7e8f9a0b1c2_add_multiple_mailing_lists.py`.
- 2026-07-25 stabilizzazione invio mailing list:
  - i destinatari vengono congelati in `MailingDelivery` al salvataggio della bozza, quindi il conteggio e' disponibile prima dell'accodamento;
  - l'invio elabora consegne persistite `pending/failed`, aggiorna ogni esito singolarmente e chiude sempre la campagna in `sent/failed`;
  - le connessioni SMTP usano un timeout configurabile `MAIL_SMTP_TIMEOUT` con default 30 secondi; il task registra come fallite le consegne pendenti in caso di errore non gestito;
  - una campagna senza destinatari non viene accodata;
  - la campagna reale `Promo Spritz`, rimasta bloccata in `sending` prima della correzione, e' stata recuperata in stato `failed` ed e' nuovamente inviabile;
  - test end-to-end temporaneo verificato: snapshot di un destinatario, invio riuscito, timeout simulato, chiusura corretta degli stati e cleanup completo.
  - per la fase di test, le campagne `sent/failed` espongono `Azzera invio`: elimina gli esiti precedenti, ricrea lo snapshot dei destinatari correnti e riporta la campagna in `draft`; il reset e' bloccato durante `queued/sending`.
  - test reset verificato con consegna inviata ricreata come `pending`, conteggi/date azzerati, protezione dello stato `sending` e cleanup completo.
  - fix worker: il link di disiscrizione viene composto da `PUBLIC_BASE_URL` con fallback `https://ldapp.ldenoteca.it`, senza dipendere da un request context Flask; eliminato l'errore `Unable to build URLs outside an active request`.
  - la tabella campagne espone ora `Dettaglio errori` per destinatario, con classificazione leggibile (configurazione link, autenticazione/connessione SMTP, destinatario rifiutato o errore generico) e messaggio tecnico completo.
  - test worker fuori da request context verificato con link pubblico corretto, consegna `sent` e cleanup completo.
  - logging dedicato attivo con `get_logger("mailing_list")`: creazione/sincronizzazione liste, preparazione/reset/accodamento campagne, avvio worker, tentativi e risultati per destinatario, riepilogo e traceback finiscono sia in `mailing_list.log` sia in `main.log`;
  - `send_account_mail()` usa anche `get_logger("mail_accounts")` e registra connessione e risposta SMTP in `mail_accounts.log`/`main.log`, senza password o token;
  - il task Celery mailing usa `log_task(mailing_logger)` invece del logger generico `tasks`;
  - la UI specifica `Accettate SMTP / errori`: lo stato `sent` certifica l'accettazione da parte del server SMTP, non la consegna finale nella casella; bounce, spam e quarantena richiedono riscontri successivi;
  - test temporaneo verificato per percorso riuscito e fallimento SMTP simulato: eventi presenti in entrambi i log, traceback registrato e cleanup DB completo.
- 2026-07-27 albero filtri clienti mailing list:
  - sostituito il multiselect piatto con un albero accessibile di 6 categorie leggibili e 62 sottocategorie uniche derivate dai dati reali (`HO.RE.CA.`, `BAR`, `RISTORANTI`, ecc.);
  - ogni categoria ha checkbox padre e ramo espandibile; il padre seleziona/deseleziona tutte le figlie ed entra nello stato nativo `indeterminate` quando ne e' selezionata soltanto una parte;
  - aggiunti comandi `Seleziona tutto`/`Deseleziona tutto`, conteggio dinamico delle sottocategorie selezionate e conteggi clienti per voce;
  - i codici salvati restano le coppie compatibili `category_code|subcategory_code`; i vecchi filtri non vuoti restano validi;
  - una configurazione storica vuota continua inizialmente a rappresentare tutti i clienti e viene mostrata con tutte le checkbox selezionate; dopo il primo salvataggio `filter_mode=selected` rende esplicita anche una selezione vuota, che produce zero destinatari;
  - asset `static/js/mailing_list.js`, stili in `static/css/style.css`, cache CSS `mobile22` e JS `filters1`;
  - verificati albero DB reale, rendering autenticato, semantica config vuota/parziale, template Jinja, sintassi Python/JavaScript e `git diff --check`.
- 2026-07-28 fondazione campagne mailing evolute:
  - aggiunti i modelli `MailingTemplate`, `MailingCampaignAttachment`, `MailingCampaignSchedule` e `MailingCampaignRun`;
  - `MailingCampaign.template_id` conserva il template sorgente senza vincolare le successive modifiche della campagna;
  - gli allegati conservano metadati e percorso storage privato; la gestione fisica dei file e la UI saranno implementate nel prossimo step;
  - le pianificazioni supportano a livello dati `single`, `periodic`, `multiple` e `until`, intervalli in giorni/settimane/mesi, prossima esecuzione, pausa/completamento e contatori;
  - ogni esecuzione ha numero progressivo, origine manuale/programmata/legacy, stato, conteggi, date ed eventuale errore;
  - `MailingDelivery.run_id` collega le consegne all'esecuzione; resta temporaneamente nullable e il vecchio vincolo campagna/destinatario resta attivo finche' il motore di invio non viene convertito, mantenendo compatibile l'app attuale;
  - migration `e8f9a0b1c2d3_add_mailing_campaign_foundation.py` applicata al DB; backfill: campagna storica convertita in run `legacy` con 3 consegne collegate e zero orfane;
  - verificati upgrade, downgrade e nuovo upgrade fino a head `e8f9a0b1c2d3`; test CRUD temporaneo superato per template, campagna, allegato, schedule, run, delivery, relazioni e cascade, con cleanup completo.
- 2026-07-28 riorganizzazione pagina mailing list e gerarchia TeamSystem:
  - la pagina principale mostra soltanto le campagne attive (`draft`, `queued`, `sending`, `failed`) e i pulsanti `Liste di Invio` e `Nuova campagna`;
  - `Liste di Invio` apre una modale XL con scelta/creazione lista, sincronizzazione, filtri, aggiunta manuale e tabella destinatari; i redirect delle operazioni riaprono automaticamente la stessa modale e la lista selezionata;
  - `Nuova campagna` apre una modale XL con form di creazione e gestione di tutte le campagne, incluse quelle completate;
  - entrambe le modali vengono portate nel `body`, aperte tramite istanza Bootstrap e ripristinano esplicitamente pulsanti/testo nei lifecycle `shown.bs.modal`/`hidden.bs.modal`;
  - corretto il mapping import TeamSystem: categoria `22/23` (codice/descrizione), sottocategoria descrittiva `25`; la colonna `26` e' un parametro commerciale e non una descrizione;
  - poiche' nessun presunto codice sottocategoria e' univoco, i filtri usano la coppia affidabile `category_code + subcategory_description`; l'albero mostra 6 categorie e 62 sottocategorie associate senza collisioni;
  - riallineate nel DB 2.026 anagrafiche clienti tramite l'import corretto, senza nuovi record o contatti;
  - cache CSS `mobile23` e JS mailing `layout2`;
  - verificati parser sul CSV reale, gerarchia DB, rendering autenticato, separazione pagina/modali, redirect di riapertura, Jinja, sintassi Python/JavaScript e `git diff --check`.
## 2026-07-28 - Mailing List: modali interattive e storico campagne

- Corretto il livello delle modali Mailing List: `.mailing-management-modal` usa ora `z-index: 12050`, superiore al backdrop applicativo globale (`12040`), evitando che la modale aperta resti coperta e non interagibile.
- Aggiunto nella pagina principale il pulsante `Storico campagne`, con modale dedicata alle campagne completate (`status = sent`).
- Il controller separa ora esplicitamente `active_campaigns` e `sent_campaigns`; il parametro `modal=history` è supportato per la riapertura contestuale.
- Aggiornati i cache key di CSS (`mobile24`) e JavaScript Mailing List (`layout3`).
- Verificati sintassi JavaScript, AST Python, compilazione Jinja e whitespace della diff.
## 2026-07-28 - Gestione campagne: modifica, apertura da riga ed eliminazione

- Le campagne in stato `draft` o `failed` sono apribili facendo clic sulla riga oppure tramite l'azione `Modifica`; la modale viene popolata con lista, oggetto, account e contenuto esistenti.
- Il salvataggio della modifica ricrea lo snapshot dei destinatari sulla lista scelta, azzera i vecchi esiti e riporta la campagna in `draft`.
- Aggiunta l'azione `Elimina`; è esclusa durante gli stati `queued` e `sending` e rimuove tramite le cascade esistenti consegne, run, pianificazione e allegati collegati.
- La modale ripristina form, action, testi e pulsanti nei lifecycle Bootstrap, evitando di ereditare lo stato della campagna modificata.
- Verificati route, AST Python, Jinja, JavaScript, rendering autenticato in sola lettura e `git diff --check`.
- Verifica gerarchia clienti sul DB reale: l'export contiene direttamente associazioni ripetute o semanticamente inattese (ad esempio `FORNITORI` sotto `ALTRO` e `HO.RE.CA.`, `INGROSSO` sotto più categorie); non è stata introdotta una tassonomia inventata. Per correggere semanticamente l'albero serve la matrice categorie/sottocategorie considerata canonica.
## 2026-07-28 - Template e allegati campagne operativi

- La modale campagna espone ora la selezione del template: scegliendo un template vengono copiati oggetto e contenuto, che restano modificabili nella singola campagna; `template_id` conserva il riferimento sorgente.
- Aggiunta la modale `Template campagne` con creazione, modifica ed eliminazione logica dei template; una cancellazione non altera i contenuti già copiati nelle campagne.
- Il form campagna supporta upload multiplo di PDF, JPG/JPEG, PNG, GIF, WEBP, DOC/DOCX e XLS/XLSX, massimo 10 file e 15 MB per file.
- Gli allegati sono salvati in storage privato sotto `instance/mailing_attachments/<campaign_id>`, con nome casuale, metadati DB e controllo anti path traversal; non sono pubblicati sotto `static`.
- In modifica sono visibili gli allegati esistenti e possono essere rimossi; cancellando una campagna vengono rimossi anche i file fisici oltre ai record in cascade.
- `tools/mailing_list.py` aggiunge gli allegati reali al MIME `Message` prima di ogni invio SMTP e tratta un file mancante come errore esplicito della consegna.
- Logging dedicato `mailing_list` aggiunto per CRUD template e rimozioni allegati, nel rispetto della duplicazione su `mailing_list.log` e `main.log`.
- Test reale controllato superato: creazione template, campagna con PDF, persistenza privata, associazione `template_id`, costruzione MIME e cleanup completo senza invio SMTP. Superati anche AST Python, Jinja, sintassi JavaScript e `git diff --check`.
## 2026-07-28 - Chiusura automatica universale dei messaggi flash

- `static/js/base.js` gestisce ora tutti gli alert dentro `#flash-message` in ogni pagina basata su `base.html`.
- Timeout per leggibilità: `success/info` 5 secondi, `warning` 8 secondi, `danger` 12 secondi; la chiusura manuale resta sempre disponibile.
- Il timeout viene sospeso durante hover e focus e riprende all'uscita, evitando la scomparsa mentre l'utente sta leggendo o usando il pulsante di chiusura.
- La chiusura usa l'istanza Bootstrap `Alert`, con fallback alla rimozione DOM; cache key di `base.js` aggiornata a `flash1`.
## 2026-07-29 - Invii ciclici mailing list operativi

- La modale campagna supporta `Invio manuale`, `Invio singolo programmato`, `Invio periodico`, `Numero definito di invii` e `Invii fino a una data`.
- Le modalità cicliche richiedono data/ora iniziale e intervallo in giorni, settimane o mesi; `multiple` richiede il numero di invii, `until` la data/ora finale. Le date inserite sono interpretate in `Europe/Rome` e persistite in UTC.
- `MailingCampaignSchedule` è ora gestito dalle route di creazione/modifica; una pianificazione parte in stato `active` e può essere sospesa o riattivata dalla tabella campagne.
- Celery Beat esegue `config.tasks.dispatch_due_mailing_schedules_task` ogni minuto. Il dispatcher seleziona con lock le pianificazioni scadute, crea un `MailingCampaignRun`, congela i destinatari della singola esecuzione, calcola la prossima ricorrenza e accoda il worker.
- Ogni ciclo conserva consegne e conteggi separati tramite `run_id`; la UI mostra stato, prossima esecuzione, numero di invii accodati e dettaglio storico dei run.
- La cadenza mensile preserva il giorno quando possibile e usa l'ultimo giorno del mese negli altri casi (es. 31 gennaio -> 28/29 febbraio).
- Dopo un fermo dello scheduler viene accodato un solo invio di recupero e la ricorrenza successiva riparte dall'ora effettiva, evitando raffiche di invii arretrati; una pianificazione `until` già oltre il termine viene completata senza spedire fuori finestra.
- Migration `f9a0b1c2d3e4_enable_recurring_mailing_runs.py`: sostituisce l'unicità storica `(campaign_id, subscriber_id)` con `(run_id, subscriber_id)`. Applicata al DB, downgrade e nuovo upgrade verificati; head corrente `f9a0b1c2d3e4`.
- Test reale controllato con SMTP soppresso: due cicli della stessa campagna hanno prodotto due run `sent`, due consegne distinte allo stesso destinatario, rendering UI, pausa/riattivazione, cadenza mensile e creazione `multiple` via route. Cleanup verificato: zero record temporanei.
- Logging del dispatcher e delle esecuzioni usa `get_logger("mailing_list")`/`log_task(mailing_logger)`, quindi confluisce in `mailing_list.log` e `main.log`.
## 2026-07-29 - Analisi preliminare export situazioni contabili `EC_CLI.CSV`

- `tools.importazioni.import_estratti_conto_clienti()` oggi verifica soltanto esistenza/dimensione del file e dichiara esplicitamente che il parser non è implementato.
- Verificato direttamente l'export remoto configurato: `/dati/DISCORETE/estrazioni/export/EC_CLI.CSV`, aggiornato il 29/07/2026 alle 05:01, circa 7.094 KB.
- Il contenuto corrente non espone dati contabili interpretabili: 1.774 record da 4.094 caratteri esatti; l'intero file contiene soltanto tab, spazi, `+` e le cifre `0`, `1`, `6`, `9`. Non sono presenti lettere, separatori decimali, segni negativi, date/documenti leggibili o codici cliente variabili.
- Non è stato creato un modello/import fittizio: serve correggere l'export TeamSystem oppure ottenere il relativo tracciato colonne e un campione valido prima di definire persistenza e visualizzazione.
- Obiettivo confermato per il passo successivo: importazione idempotente delle situazioni contabili, vista comprensibile per cliente e successiva integrazione con campagne di servizio non disiscrivibili.
## 2026-07-30 - Configurazione dinamica file e tracciati importazione

- Aggiunto in `/settings` il tile amministrativo `Tracciati importazione` (peso minimo 900), collegato a `/settings/import-transfer-definitions`.
- La pagina configura i trasferimenti file-based reali: articoli, giacenze, barcode, anagrafiche clienti, anagrafiche fornitori e situazioni contabili clienti; Prestashop/Poleepo restano esclusi perché API-driven.
- Per ogni trasferimento sono selezionabili:
  - il file sorgente lasciato nella cartella export TeamSystem corrente, catalogata localmente oppure tramite `EXPORT_FOLDER_URL/lista_export`;
  - un tracciato presente in `static/tracciati/importazione`.
- La configurazione è persistita in `AppPreference` come JSON con chiave `imports.transfer_definitions`; nessuna nuova migration è necessaria. Se la preferenza o la tabella non sono disponibili, restano attivi i nomi file storici.
- `tools/import_transfer_config.py` centralizza catalogo, validazione anti path traversal, elenco file/tracciati, lettura/salvataggio e risoluzione runtime.
- Gli import di articoli, giacenze, barcode, clienti, fornitori ed estratti conto usano ora il file sorgente configurato; l'import estratti conto risolve e registra anche il tracciato associato.
- Copiato `docs/transport/tracciato_ec_cli.csv` in `static/tracciati/importazione/tracciato_ec_cli.csv`, preservando il file originale.
- Test reale controllato superato: catalogo remoto, catalogo tracciati, rendering autenticato, salvataggio e lettura runtime; l'eventuale preferenza precedente è stata ripristinata. Superati anche AST Python, Jinja, route e `git diff --check`.
- Logging dedicato tramite `get_logger("import_transfer_config")`; salvataggi ed errori di catalogazione confluiscono nel log modulo e in `main.log`.

## 2026-07-30 - Prima versione situazioni contabili clienti

- Implementato l'import reale di `EC_CLI.CSV` usando il tracciato configurabile `tracciato_ec_cli.csv`; il formato testo TeamSystem contiene record fissi da 1.703 byte e 157 campi.
- Aggiunti `CustomerAccountStatementImport` e `CustomerAccountEntry`: ogni import è uno snapshot identificato dall'hash SHA-256 del file, quindi un secondo passaggio sul medesimo export non duplica i dati.
- Ogni movimento conserva cliente, date registrazione/documento/scadenza, numero documento, descrizioni, segno Dare/Avere, importo e payload tecnico minimo.
- `ECS-CODICE` viene normalizzato numericamente per il collegamento a `BusinessRegistry.source_code`.
- Migrazione `ca1b2c3d4e5f_add_customer_account_statements.py` applicata; head DB corrente `ca1b2c3d4e5f`.
- Prima importazione reale completata: 1.788 movimenti, 186 clienti, 186 collegati e zero non collegati; Dare 676.104,36 euro, Avere 115.777,19 euro, saldo movimenti 560.327,17 euro.
- Aggiunto in `/settings` il tile `Situazioni contabili clienti`; la pagina di riepilogo offre ricerca, conteggi, Dare/Avere/Saldo e accesso al dettaglio cronologico per cliente.
- L'import può essere rilanciato dalla pagina; la route ora comunica un'importazione reale e non più una semplice verifica file.
- Lo scaduto non è ancora esposto come saldo definitivo: i campi riepilogativi dell'export risultano a zero e la prima versione evita di simulare una riconciliazione delle partite.
- Logging dell'import tramite `get_logger("importazioni")`, quindi eventi ed errori confluiscono in `importazioni.log` e `main.log`.
- Verificati parser su 157 campi/1.788 record, AST, compilazione Jinja, migrazione, idempotenza, somme contabili, rendering autenticato del riepilogo e del dettaglio, e `git diff --check`.
- Prossimo confronto: valutare leggibilità della pagina e definire la logica corretta di partite aperte/scaduto prima dell'invio automatico obbligatorio ai clienti.

## 2026-07-30 - Dashboard gerarchica credito clienti

- `Situazioni contabili clienti` è stata rimossa dalla dashboard Impostazioni e spostata sotto il menu `Amministrazione`.
- La nuova voce ha peso 40, corrispondente al ruolo `office`; migration `cb2c3d4e5f60_add_customer_credit_menu.py` applicata, head DB corrente `cb2c3d4e5f60`.
- Nuova route principale `/administration/customer-credit`; la vecchia `/settings/customer-account-statements` restituisce 404.
- Il grafico a torta naviga gerarchicamente:
  - `Credito -> Aree`: aggregazione per provincia;
  - selezione area -> zone: aggregazione per comune;
  - selezione zona -> clienti;
  - selezione cliente -> dettaglio movimenti.
- Ogni fetta SVG e ogni voce della legenda sono link reali; breadcrumb e pulsante `Indietro` riportano al livello immediatamente superiore, mentre il dettaglio cliente torna alla zona di origine.
- Province o comuni mancanti restano visibili come `Provincia non definita` e `Comune non definito`.
- Lo `scoperto` è calcolato sommando soltanto i saldi finali positivi dei singoli clienti; eventuali clienti con saldo negativo non compensano l'esposizione degli altri.
- La dashboard è responsive, include legenda scorrevole, tabella leggibile degli stessi dati e totale scoperto del livello selezionato.
- Logging dedicato tramite `get_logger("administration")`, duplicato in `administration.log` e `main.log`.
- Verificati su DB reale: menu/peso/genitore, saldi positivi, rendering autenticato dei tre livelli, drill-down AQ -> CARSOLI -> cliente, ritorno contestuale al grafico, vecchia route rimossa, AST, Jinja, JavaScript e `git diff --check`.

## 2026-07-30 - Import contabile automatico semiorario

- Celery Beat accoda `config.tasks.import_estratti_conto_clienti_task` ogni ora ai minuti `.00` e `.30`, coerentemente con la produzione dell'export TeamSystem.
- Lo scheduler usa la timezone applicativa già configurata `Europe/Rome`.
- Ogni messaggio pianificato scade dopo 25 minuti: se worker/Redis rimangono fermi non vengono processate importazioni arretrate quando è già prossimo o disponibile uno snapshot più recente.
- L'hash SHA-256 già presente mantiene l'import idempotente: se il file non è cambiato non vengono creati snapshot o movimenti duplicati.
- Restano disponibili l'import manuale dalla dashboard e il logging universale in `importazioni.log`/`main.log`.

## 2026-07-30 - Andamento mensile esposizione clienti

- La pagina principale `/administration/customer-credit` include un secondo grafico SVG con l'andamento mensile dello scoperto.
- La serie copre fino a 24 mesi e usa l'ultimo snapshot disponibile di ciascun mese; le 48 importazioni giornaliere non diventano quindi 48 punti visivi.
- Il calcolo resta coerente con la torta: per ogni snapshot vengono prima calcolati i saldi cliente e poi sommati soltanto quelli positivi.
- Il filtro storico è per area/provincia (`AQ`, `RM`, `RI`, ecc.); la precedente selezione per zona era basata su un'indicazione poi corretta.
- Un'area senza esposizione in un mese rimane nella serie con valore zero; con il solo snapshot oggi disponibile il grafico mostra correttamente un unico punto e segnala che la linea crescerà con lo storico.
- Il grafico è responsive, ha assi e griglia, tooltip nativi sui punti e scorrimento orizzontale sui dispositivi stretti.
- Superati AST, compilazione Jinja, sintassi JavaScript e `git diff --check`.
- Il test integrato read-only sul DB reale non è stato completato perché il server PostgreSQL `100.120.25.12` è andato in timeout in due tentativi consecutivi prima della prima query; non sono state eseguite scritture.
- Riorganizzazione UI successiva: `Totale scoperto` è stato spostato a destra nella fascia con snapshot, file e clienti esposti; il grafico mensile occupa ora la colonna destra precedentemente riservata al totale.
- Nei livelli Area/Zona il form del filtro storico conserva i parametri di drill-down tramite campi hidden, evitando di riportare involontariamente alla radice.

## 2026-07-30 - Dashboard Situazione Clienti e aging individuale

- Aggiunta `/administration/customer-credit/customers`: mostra soltanto clienti con saldo positivo, ordinati in modo decrescente per valore del debito.
- In alto nelle dashboard e nel dettaglio cliente sono presenti i pulsanti `Situazione Zone` e `Situazione Clienti`; lo stato attivo è distinto visivamente.
- Ogni riga cliente è interamente cliccabile e apre il relativo estratto conto; tornando indietro si rientra nella dashboard clienti oppure nella zona di origine.
- Il dettaglio cliente espone in alto:
  - KPI Dare, Avere e Saldo dovuto;
  - KPI `Giorni medi di scoperto`, ponderato sui movimenti netti;
  - grafico mensile dell'esposizione del singolo cliente, basato sull'ultimo snapshot di ciascun mese.
- Aggiunto istogramma aging con fasce `0-30`, `31-60`, `61-90`, `91-120`, `oltre 120 giorni`.
- Formula aging verificata: ogni movimento confluisce nella fascia determinata dall'età della data documento (fallback registrazione/scadenza); Dare aumenta e Avere riduce il valore netto della medesima fascia.
- La tabella cronologica dei movimenti resta disponibile sotto gli indicatori.
- Test read-only sul DB reale superato per ordinamento decrescente, uguaglianza saldo/somma aging e rendering autenticato di dashboard, storico, KPI e istogramma. Superati anche AST, Jinja, JavaScript e `git diff --check`.

## 2026-07-30 - Correzione formula aging su cliente Bottone 1950

- Audit puntuale richiesto sul cliente `0001950`: la prima implementazione FIFO/scadenza mostrava erroneamente 12.965,62 euro nella fascia 0-30 giorni.
- Composizione reale degli ultimi 30 giorni per data documento: fatture luglio 3.791,02 euro meno nota credito luglio 36,60 euro = 3.754,42 euro.
- Rimossa l'allocazione FIFO e adottato il saldo netto dei movimenti nella fascia della loro data documento; il totale delle fasce continua a coincidere esattamente con il saldo cliente.
- Risultato Bottone verificato: `0-30 = 3.754,42`, `31-60 = 5.440,25`, `61-90 = 3.734,35`, `91-120 = 4.470,24`, `oltre 120 = 13.218,96`; totale 30.618,22 euro.
- Audit su tutti i 187 codici cliente dello snapshot: zero discrepanze tra saldo, totale aging e somma delle cinque fasce.
- Cinque clienti presentano almeno una fascia netta negativa per effetto di note credito/accrediti; l'istogramma ora supporta valori sotto zero e li distingue graficamente in verde.

## 2026-07-30 - Rilevanza righe TeamSystem, audit Bar Castello 1141

- Il cliente `0001141` risultava erroneamente debitore di 655,92 euro, mentre l'e/c TeamSystem chiude a zero.
- Audit dei sei record: due fatture causale `001` in Dare; due contropartite tecniche causale `096`, Dare e `ECS-NUMRIF=00000`; due riscossioni causale `096` in Avere con riferimento valorizzato.
- Regola verificata: causale `096` + riferimento `00000` non concorre al saldo cliente, indipendentemente dal segno.
- Audit globale: 93 contropartite tecniche Dare per 53.810,52 euro e una Avere da 178,36 euro; due Dare causale 096 con riferimento valorizzato restano correttamente rilevanti.
- Aggiunti a `CustomerAccountEntry` `accounting_reason`, `accounting_reference`, `is_balance_relevant`; migration `cc3d4e5f6071_add_customer_entry_relevance.py` applicata, head DB `cc3d4e5f6071`.
- L'import valorizza i campi e completa idempotentemente i metadati mancanti su uno snapshot con hash già noto; lo snapshot 2 è stato aggiornato su tutte le 1.792 righe senza duplicazione.
- Dashboard, storico, KPI e aging usano solo righe rilevanti. L'e/c mantiene le righe tecniche con badge `riga tecnica esclusa dal saldo`.
- Test reale superato: Bar Castello saldo 0,00 e assente dai debitori; due righe tecniche visibili e marcate; Bottone 1950 invariato con 0-30 pari a 3.754,42 euro.

## 2026-07-31 - Fix azioni menu contestuale bacheca ordini

- Corretto `closeActiveCardDropdown()` in `static/js/kiosk_overview.js`: la chiusura Bootstrap azzerava `activeCardDropdown` tramite `hidden.bs.dropdown` e il codice tentava subito dopo di leggere `restore` sul riferimento ormai nullo.
- L'errore JavaScript interrompeva il click prima della chiamata a `/kiosk/api/order/<id>/set-status`, quindi le azioni `Sposta in` non producevano effetti.
- Il riferimento al dropdown viene ora conservato localmente, lo stato globale viene azzerato prima di `hide()` e il ripristino manuale resta soltanto come fallback quando non esiste un'istanza Bootstrap.
- Cache key di `kiosk_overview.js` aggiornata a `mobile-board16`.
- Verificati `node --check static/js/kiosk_overview.js` e `git diff --check`.

## 2026-08-01 - Editor manuale acquisizione assegni

- La modale `checkScanCropModal` e' stata estesa senza creare un secondo flusso di acquisizione.
- L'editor canvas permette rotazioni rapide a 90/180/270 gradi, rotazione libera tramite trascinamento, selezione con quattro linee ortogonali e selezione prospettica con quattro spigoli indipendenti.
- `POST /cassa/api/checks/scan/crop-preview` accetta anche il payload `transform` con angolo e quattro punti normalizzati; OpenCV applica rotazione, trasformazione prospettica e normalizzazione.
- Il risultato manuale e il ritaglio automatico riuscito vengono prodotti come JPEG 1402x567 px, rapporto fisico 178x72 mm a circa 200 DPI, adatto alla miniatura e alla stampa nel prospetto assegno.
- L'utente genera l'anteprima, la controlla e la conferma; il file risultante riusa il caricamento scansione gia' esistente e resta nello storage privato `instance/check_scans`.
- Asset Agenda versionati con cache key `check-editor1`.
- Verificati sintassi Python/JavaScript, trasformazione sintetica con output reale 1402x567 e `git diff --check`.
- Correzione UX successiva: aggiunto cursore di rotazione continua da -180 a +180 gradi; tutti i comandi usano `setCheckScanEditorAngle()` e segnalano esplicitamente quando la foto non ha ancora terminato il caricamento. Cache key aggiornata a `check-editor2`.
- Correzione contrasto editor: toolbar marrone con pulsanti chiari/azzurri delimitati, titoli e istruzioni scuri sul corpo chiaro, slider ad alto contrasto e azioni footer leggibili. Cache CSS aggiornata a `check-editor3`.
- Formati scansione estesi: PDF, TIFF/TIF, BMP, GIF, PNG, WebP, JPEG e gli altri formati raster riconosciuti da Pillow vengono convertiti in JPEG prima dell'editor; per documenti multipagina viene acquisita la prima pagina. Limite portato a 25 MB.
- Aggiunta dipendenza permissiva `pypdfium2==5.12.1` per il rendering PDF senza programmi esterni; test sintetici PDF/TIFF/BMP/GIF/PNG tutti normalizzati correttamente in JPEG. Cache JS aggiornata a `check-editor4`.

## 2026-08-01 - Filtro device nel quadrante POS

- Nell'intestazione del quadrante POS dell'Agenda e' disponibile una tendina `Tutti i POS` / singolo dispositivo.
- La selezione filtra immediatamente le righe e ricalcola il totale mostrato, così la quadratura puo essere eseguita terminale per terminale.
- L'API dei movimenti POS restituisce anche l'elenco dei device configurati: sono selezionabili anche quelli senza movimenti nella giornata, per i quali il totale filtrato risulta zero.
- Cambiando device viene azzerato l'eventuale filtro circuito precedente; passando a un'altra giornata una selezione non piu disponibile viene riportata automaticamente a `Tutti i POS`.
- Layout adattato anche a smartphone; asset Agenda versionati con cache key `pos-device-filter1`.
- Verificati sintassi Python/JavaScript, parsing Jinja e `git diff --check`.

## 2026-08-02 - Rendering immediato grafici credito clienti

- Diagnosticato il ritardo dei grafici: i dataset erano gia inclusi nella pagina, ma `customer_credit.js` veniva richiesto ed eseguito soltanto dopo Bootstrap CDN e tutti gli script applicativi globali; una risorsa lenta lasciava gli SVG vuoti per molto tempo.
- Il renderer dei grafici viene ora precaricato nell'`head` ed eseguito in modalita `async` appena il contenuto necessario e' presente, senza dipendere dalla catena JavaScript globale.
- Torta e andamento mensile mostrano immediatamente uno stato `Elaborazione...`; a rendering completato l'indicatore scompare, mentre dati mancanti o non validi producono un messaggio visibile invece di un riquadro vuoto.
- Asset pagina versionati con cache key `credit-fast1`.

## 2026-08-02 - Invio estratto conto e sollecito cliente

- Nella scheda situazione cliente sono disponibili in alto a destra `Invia estratto conto` e `Invia sollecito`.
- L'estratto conto usa l'account futuro `CreditManagement`; il sollecito permette email ordinaria tramite `CreditManagement` oppure PEC tramite l'account futuro `PEC`.
- Finché un account non e' configurato/attivo, la modale mostra il canale come non disponibile e impedisce l'invio.
- I destinatari sono esclusivamente recapiti email/PEC appartenenti all'anagrafica collegata; non e' possibile specificare arbitrariamente un indirizzo esterno.
- Il template include cliente, saldo corrente e movimenti rilevanti dello snapshot contabile attuale. Un sollecito e' bloccato quando il saldo non e' positivo.
- Ogni invio richiede conferma, mostra avanzamento/esito e viene registrato in `administration.log` e `main.log`; errori SMTP non espongono credenziali al client.
- WhatsApp e SMS non sono stati implementati. Test read-only del template superato su dati reali, senza invio SMTP; verificati Python, JavaScript, Jinja e `git diff --check`.

## 2026-08-03 - Anteprima e modalita test comunicazioni credito

- L'invio dalla scheda cliente e' ora un flusso esplicito a due passaggi: `Mostra anteprima` e, soltanto dopo, `Invia ora`.
- L'anteprima mostra indirizzo mittente effettivo, account SMTP, destinatario, oggetto e corpo completo; oggetto e contenuto sono modificabili prima della conferma.
- La `Modalita test` disabilita il recapito cliente e accetta un indirizzo esterno per la singola prova, senza salvarlo nell'anagrafica.
- Oggetto e log degli invii di prova vengono marcati `[TEST]`; il server ricalcola comunque lo snapshot e convalida account, canale, saldo e indirizzo prima dell'invio.
- Cambiando canale, destinatario o modalita dopo l'anteprima, questa viene invalidata e deve essere rigenerata, evitando invii con riepiloghi non aggiornati.
- Verificati Python, JavaScript, Jinja e `git diff --check`. Il test integrato read-only con gli account reali non ha raggiunto l'anteprima per una chiusura improvvisa della connessione PostgreSQL; nessun messaggio e' stato inviato.
- Correzione stacking modali: il backdrop globale dell'app (`z-index: 12040`) copriva le finestre Bootstrap standard e ne intercettava i clic. Entrambe le modali estratto conto/sollecito sono ora a `z-index: 12050` con interazione esplicita; cache CSS aggiornata a `credit-modal-stack1`.
- Verificati sul DB gli account `creditmanagement` e `pec`: entrambi attivi, con mittente e server SMTP valorizzati; nessuna credenziale e' stata esposta nel controllo.
- Correzione definitiva focus/stacking: il solo `z-index` non era sufficiente perche' le due modali restavano figlie di `page-shell`, che crea uno stacking context autonomo. `customer_credit_detail.js` sposta ora entrambe in `document.body` prima dell'inizializzazione Bootstrap, applicando il pattern obbligatorio gia documentato per tutte le modali dell'app; cache JS `credit-modal-body1`.
- Recapito a caldo: entrambe le modali includono sempre `Inserisci un indirizzo manualmente`; se l'anagrafica non restituisce email/PEC, l'opzione viene selezionata automaticamente. L'indirizzo vale solo per il singolo invio, non viene salvato e viene mostrato nell'anteprima prima della conferma.
- Il backend convalida nuovamente il recapito manuale e lo accetta anche per clienti non collegati a un'anagrafica, mantenendo invariati i controlli su account, canale e saldo. Test read-only dell'anteprima superato con destinatario manuale, mittente reale valorizzato e nessun invio SMTP. Cache JS `credit-manual-recipient1`.

## 2026-08-01 - Ottimizzazione prestazioni operative

- Eseguito un benchmark autenticato su Agenda e gestione assegni: le query assegni risultano rapide sul volume corrente (60 record, circa 6 ms), mentre il costo percepito derivava soprattutto dal ventaglio di richieste iniziali, dal polling continuo e dal download ripetuto degli asset.
- Gli asset statici versionati con `?v=` ora ricevono `Cache-Control: public, max-age=31536000, immutable`; gli altri asset statici hanno cache breve di un'ora. HTML e API restano esplicitamente `no-store` per non mostrare dati operativi obsoleti.
- Gli script globali prima privi di versione (`scheda_articolo`, `task_status`, `pwa_push`, `app_update`) usano ora `APP_VERSION`, consentendo la cache lunga con invalidazione automatica al deploy.
- Il caricamento delle preferenze runtime e' limitato a una lettura DB ogni 5 secondi per processo, con lock contro richieste concorrenti; i salvataggi dalle Impostazioni continuano ad applicare direttamente la configurazione aggiornata.
- Il polling Agenda e vault e' stato unificato in un ciclo non sovrapponibile ogni 5 secondi e non interroga il server quando la scheda browser e' nascosta.
- I riepiloghi assegni in scadenza/rientro vengono caricati in background dopo i dati principali, rendendo prima utilizzabili comandi, incassi, spese, POS e movimenti.
- Benchmark successivo: gli endpoint operativi caldi restano tra circa 21 e 73 ms; la lista di 60 assegni scende a circa 37 ms. Verificati sintassi Python/JavaScript e `git diff --check`.

## 2026-08-09 - Ripristino import anagrafiche MATRIXWS CLIFOR

- Individuata la causa delle 2.096 false nuove anagrafiche: `500001/1` restituiva clienti, fornitori e record tecnici, mentre `CFCOD` REST era privo del padding a 5 cifre usato dal precedente `exp_cli.csv`.
- Ripristino eseguito dalla baseline `exp_cli.csv` in transazione unica, dopo dry-run e backup JSON: rimossi 2.096 registry contaminati, 1.552 relativi contatti, 79 `CashCustomer` creati e 1.216 alias; ripristinate 1.969 anagrafiche preesistenti.
- Verifica finale: 2.031 registry clienti storici, nessun payload MATRIXWS contaminato, nessun codice senza padding, nessuna riga residua col timestamp della transazione errata e zero differenze sui 1.994 `CashCustomer` riconciliabili con la baseline.
- `tools/importazioni.py` filtra ora soltanto `CF-TIPO=1`, normalizza `CFCOD` a 5 cifre, deduplica prima dell'upsert e rifiuta codici ripetuti con identita' discordanti. Un guard blocca eventuali nuovi import finche' esistono record contaminati.
- Backup locale ignorato da Git: `docs/transport/matrixws_clifor_backup_20260809_232016.json`.
- Chiuso l'accesso pubblico al viewer dei log: `/logs/view` usa ora `login_required` e `role_required(999)`, coerentemente con la dashboard Developer.

## 2026-08-16 - Distribuzione automatica aggiornamenti WebAPK

- Corretto il canale di aggiornamento delle PWA Android: il link al manifest non cambia piu' a ogni release ma mantiene l'URL storico `manifest.json?v=20260522-3`, usato dagli utenti gia' installati.
- Aggiunti al manifest un `id` e uno `scope` espliciti e stabili (`/`), senza cambiare identita', start URL o nome dell'app.
- Il manifest non eredita piu' la cache annuale `immutable` degli asset versionati: viene sempre servito con `no-store/no-cache`, permettendo a Chrome di rilevare e distribuire automaticamente le modifiche al WebAPK e al Web Share Target.
- L'aggiornamento dell'integrazione nel menu Condividi resta gestito dal browser/sistema Android e puo' richiedere il normale ciclo asincrono del WebAPK; non richiede disinstallazione o reinstallazione da parte dell'utente.

## 2026-08-17 - Diagnostica Web Share Target vCard in produzione

- Verificato direttamente `https://ldapp.ldenoteca.it`: la pagina pubblica collega l'URL storico stabile `/static/manifest.json?v=20260522-3` e il server restituisce il manifest aggiornato con HTTP 200.
- Il manifest di produzione contiene `id=/`, `scope=/`, i MIME vCard e l'estensione `.vcf`; le intestazioni effettive sono `no-cache, no-store, must-revalidate, max-age=0`, quindi il deploy e la cache del server non spiegano l'assenza dal menu Condividi.
- La discriminante residua e' Android: se LDApp compare condividendo una foto ma non un contatto, il WebAPK installato conserva i vecchi filtri MIME; se non compare nemmeno per una foto, l'installazione non e' registrata come WebAPK/share target dal browser che l'ha installata.
- Test reale S25: LDApp compare per le foto ma non per i contatti, confermando un WebAPK valido rimasto con i precedenti intent filter multimediali.
- `static/manifest.json` accetta ora anche `text/*`, `application/x-vcard` e `application/octet-stream`, coprendo le varianti con cui rubriche e content provider Android possono esportare un `.vcf`.
- `theme_color` passa da `#2c3e50` a `#2c3e51` (differenza visivamente impercettibile): e' un campo che forza esplicitamente l'aggiornamento del WebAPK, cosi' la nuova APK rigenerata incorpora anche i filtri di condivisione aggiornati.
- Verificato nuovamente il server pubblico il 2026-08-17: `#2c3e51`, `text/*`, `application/x-vcard` e `application/octet-stream` sono effettivamente online; per le installazioni Chrome l'aggiornamento puo' essere richiesto manualmente dalla pagina interna `about://webapks` senza reinstallare o cancellare dati.
- Dopo reinstallazione il WebAPK espone correttamente LDApp per `.vcf`, ma la POST pubblica riceveva `302 /auth/login?next=/pwa/share`: il redirect post-login tornava in GET su un endpoint solo POST e il file condiviso andava perso.
- La ricezione vCard e' ora bifase: `/pwa/share` valida e registra anche una condivisione senza cookie, generando un token monouso casuale di cui viene conservato soltanto SHA-256; il token scade dopo 30 minuti.
- Il redirect porta a una pagina GET recuperabile. Se necessario Flask-Login conserva nel `next` anche il token; dopo l'autenticazione l'intento viene assegnato all'utente, token e scadenza vengono cancellati e l'URL viene ripulito prima dell'anteprima.
- Gli altri tipi di condivisione restano protetti dall'autenticazione; utenti autenticati con ruolo insufficiente continuano a ricevere 403. Aggiunta migrazione `f1a2b3c4d5e6` per rendere temporaneamente nullo `user_id` e memorizzare hash/scadenza del claim.
- Verificati: sintassi Python, head Alembic, SQL PostgreSQL offline, POST multipart anonima, redirect login con token preservato, claim monouso valido e rifiuto del token scaduto.
- Diagnostica successiva su produzione: la POST arrivava e creava correttamente l'intento, ma rispondeva ancora `302`. Tutti i redirect in uscita da `/pwa/share` usano ora `303 See Other`, come richiesto dal pattern ufficiale Web Share Target per trasformare senza ambiguita' la navigazione POST nella pagina GET di destinazione; aggiunto logging privo di PII su autenticazione, numero file, MIME e intent creato.
- Verifica pubblica del 2026-08-17: il deploy `v24` rispondeva effettivamente `303` e creava l'intento anonimo, ma il semplice inoltro della navigazione non risolveva il WebAPK S25. Il worker `v25` implementa quindi il flusso Web Share Target completo: legge il multipart, lo reinvia al backend con header dedicato, riceve la destinazione in JSON e restituisce esso stesso l'unico `303` ad Android. Gli errori diventano testo diagnostico visibile e il log distingue `worker=true/false`; registrazione aggiornata a `mobile13`.
- Confermato il funzionamento della condivisione vCard su S25. Corretta la pagina di associazione mobile: `.contact-import-shell` e' ora il contenitore verticale scrollabile touch, mentre il `page-shell` esterno resta vincolato all'area tra navbar e footer; aggiunto spazio di scorrimento dedicato per il footer sticky nelle due scale mobile.
- Ottimizzata l'apertura dell'import vCard: il claim viene validato, renderizzato e confermato nella stessa richiesta; il token sparisce subito dall'URL tramite `history.replaceState`, eliminando il precedente redirect e il secondo caricamento completo.
- La ricerca cliente del form usa ora `compact=1`: massimo 30 risultati, sole otto colonne necessarie, nessun caricamento di contatti/situazioni contabili e cache per query nel browser. Benchmark sul database configurato: da 10 query/~707 ms a 1 query/~106 ms per `car`, senza duplicati da join.

## 2026-08-17 - Aggiornamenti PWA trasparenti e protezione fondo cassa

- Eliminato ogni reload automatico dal controllo versione e dal cambio di controller del service worker: gli aggiornamenti vengono verificati e scaricati in background senza interrompere la pagina, i form o le modali in uso.
- Il nuovo service worker `v26` non forza piu' `skipWaiting`: resta pronto e si attiva nel normale ciclo di chiusura/riapertura dell'app, senza sostituire risorse durante un'operazione dell'utente.
- Il conteggio fondo cassa conserva in `sessionStorage`, separatamente per giornata, una bozza aggiornata a ogni modifica. Un refresh manuale ripristina quantità e totale; la bozza viene rimossa solo dopo salvataggio o eliminazione confermati dal server.
- La bozza viene scartata se nel frattempo il conteggio salvato sul server e' cambiato, evitando di sovrascrivere dati piu' recenti con valori locali obsoleti.
- Verificate sintassi JavaScript, assenza di reload/attivazioni forzate nel percorso di aggiornamento e integrita' delle patch con `git diff --check`.
- Corretto anche il refresh realtime interno dell'Agenda: il polling delle versioni resta ogni 5 secondi, ma il ridisegno dei dati viene accodato durante modali, input, touch, rotella e scorrimento e applicato una sola volta al termine dell'interazione.
- Le richieste simultanee dovute a versione Agenda e versione vault vengono consolidate nello stesso refresh; oltre allo scroll della pagina vengono preservati gli scroll interni delle tabelle responsive e delle aree modali.

## 2026-08-19 - Storico ordini unificato

- Aggiunta `/route-orders/history`, accessibile dal menu Magazzino con ruolo minimo 30, con ricerca per cliente/codice/testo, intervallo date, giro, stato, origine e stato di invio Slack.
- Lo storico unisce le righe `route_order_board_entries` della console agli ordini operativi `slack_orders`: il collegamento channel/timestamp evita duplicati e rende immediatamente visibili le righe salvate in console ma mai inviate.
- Gli ordini Slack non collegati alla console restano visibili e vengono classificati tramite l'evento di creazione come ordine diretto, `Inserisci ordine` o integrazione Slack.
- Risultati ordinati cronologicamente, paginati a 50 elementi e presentati con tabella desktop e schede mobile ad alta leggibilita; le ricerche eccessivamente ampie vengono segnalate e possono essere ristrette.
- Aggiunta migrazione `a2b3c4d5e6f8` per la voce `Storico ordini` sotto il menu reale `Magazzino`. Verificati AST Python, compilazione Jinja, singola head Alembic, `git diff --check` e risposta HTTP 200 autenticata su dati reali della settimana 10–16 agosto.
- Separato il filtro Cliente dalla ricerca nel testo: il cliente supporta suggerimenti asincroni, selezione esatta per anagrafica e ricerca libera per nome/codice; intervallo date e giro restano combinabili con gli altri filtri.
- Ogni riga desktop e scheda mobile apre un dettaglio ordine scrollabile con cliente, giro, consegna, stato, invio Slack, testo completo, allegati e cronologia disponibile.
- Verificati con sessione autenticata e database configurato lo storico filtrato e i dettagli di entrambe le origini (`console` e `slack`), tutti con risposta HTTP 200.
- Corretta l'interazione della modale dettaglio: viene riagganciata a `document.body` prima dell'inizializzazione e usa il livello applicativo `12050`, sopra il backdrop globale `12040`. Colori di intestazione, corpo, metadati, testo, cronologia e pulsante di chiusura hanno ora contrasto esplicito.

## 2026-08-19 - Agenda full sui mesi storici

- Incassi, spese e movimenti di cassa inviano ora esplicitamente al server la vista `complete` oppure `fiscal`; navigando su giugno la modalita full non dipende piu dal solo cookie di sessione rimasto in memoria.
- Il backend riallinea ogni richiesta full alla chiave vault attiva globale e apre il file PRI dell'anno selezionato, non quello dell'anno corrente.
- Se il vault non e disponibile o non e leggibile, la risposta full fallisce in modo visibile invece di restituire silenziosamente i soli movimenti fiscali e nascondere i flag `+` e `x`.
- Il polling realtime resta a 5 secondi e non e stato modificato. Verificati sintassi Python/JavaScript, integrita patch e caricamento mirato di un giugno storico.
- Corretta anche la ricerca movimenti per cliente/fornitore: il confronto continua a essere parziale e case-insensitive nelle tabelle fiscali e ora viene applicato anche a clienti e fornitori dei movimenti `+`/`x` nel vault per tutto il periodo scelto. Verificato il caso `peschiu` contro `ASS. CULT. "PESCHIU NOSTRU"`.

## 2026-08-23 - Affidabilita importazioni giacenze e monitor task

- Verificata la fonte effettiva degli import file-based: prima `EXPORT_FOLDER`, altrimenti download da `EXPORT_FOLDER_URL`; i nomi configurati restano `ARTICOLI.CSV`, `GIACENZE.CSV`, `CODBAR.CSV` ed `EC_CLI.CSV`. Le anagrafiche usano invece MATRIXWS REST `500001`.
- Individuato un disallineamento temporale: il task giacenze delle 04:10 risultava riuscito ma `GIACENZE.CSV` veniva pubblicato intorno alle 09:10. La sincronizzazione ora controlla le giacenze ogni 5 minuti e gli articoli due minuti dopo, evitando la dipendenza da un unico orario giornaliero.
- L'import giacenze ora legge e valida l'intero archivio prima di modificare il database, somma le righe ripetute per articolo/deposito e sostituisce la tabella in una sola transazione. Eliminato l'`input()` interattivo incompatibile con Celery.
- Il download remoto non materializza piu preventivamente l'intero file tramite `response.text`, conserva sul temporaneo il `Last-Modified` remoto e il parser giacenze lavora in streaming per contenere la memoria.
- Lo storico giacenze registra file, timestamp sorgente, articoli importati, totali NEG/WWW e righe aggregate; un esito positivo diventa quindi verificabile.
- Gli stati Redis senza `updated_at` vengono classificati come residui terminali, non come processi attivi; il comando del monitor rimuove errori e residui senza revocare worker reali. TTL dei nuovi stati attivi ridotto a due ore e rinnovato a ogni avanzamento.
- Giacenze e articoli usano un lock Redis di importazione: una nuova esecuzione viene ignorata se la precedente e' ancora attiva, mentre i task rimasti in coda scadono prima del ciclo successivo.
- La giacenza non viene piu riscritta integralmente: il confronto applica soltanto nuovi articoli, quantità cambiate e codici non piu presenti. Sorgenti con firma invariata vengono saltate; se il file cambia durante la lettura o lo snapshot si riduce in modo anomalo, l'import viene rinviato senza modificare il database.
- La raccolta e il confronto rimangono separati dalla provenienza dei dati: quando saranno disponibili i servizi MATRIXWS per articoli e giacenze, il lettore file potra essere sostituito mantenendo invariata la sincronizzazione incrementale.

## 2026-09-01 - Area Developer per simulazione ruoli

- Adottata la convenzione `Developer > Test > <nome_ruolo>` per tutte le future funzioni riservate a ruoli specifici: il test riusa la vista reale e non altera ruoli, membership o cliente principale del Developer.
- La migration `c0d1e2f3a5b7` aggiunge `Developer > Test > customer_horeca` e raccoglie `Situazione contabile`, `Fai un ordine` e `I miei ordini`.
- Le pagine ordini ora riconoscono esplicitamente i soli ruoli `customer_horeca` e `dev`. Il primo puo' selezionare soltanto clienti associati; il secondo dispone in alto del selettore filtrabile di tutte le anagrafiche cliente attive.
- La selezione e' rivalidata anche nelle POST: un ID cliente alterato nel browser non consente a un Horeca di operare su altre anagrafiche. Le modifiche e gli ordini creati in simulazione continuano a conservare il vero `user_id` Developer per l'audit.
- Rimosse dalla home del Developer le scorciatoie della vista cliente; restano disponibili ai veri `customer_horeca`, mentre il Developer utilizza il menu di collaudo dedicato.
- Corretto il blocco dell'upgrade precedente: le tabelle PayByLink erano gia' state create da `db.create_all`, ma Alembic risultava ancora su `a8b9c0d1e3f5`. La migration `b9c0d1e2f4a6` e' ora idempotente rispetto a questo stato, valida lo schema esistente e completa menu/revisione senza ricreare o svuotare le tabelle. Verificate entrambe le migration pendenti sul database reale in una transazione interamente annullata.

## 2026-09-01 - Stato ordini per clienti Horeca

- Aggiunta la sezione `I miei ordini` in home e la pagina `/customer-orders/status`, protetta dal ruolo `customer_horeca` e dalle associazioni cliente attive già usate dalla situazione contabile.
- Lo stato mostrato non è più il valore tecnico fermo a `published/changed`: viene letto dall'ordine operativo collegato alla bacheca e tradotto in ricevuto, preparazione, preparato, controllato, in consegna, evaso o annullato.
- Lo storico comprende ordini LDApp e ordini effettivamente registrati/inviati dall'ufficio, deduplicati per ordine Slack e channel/timestamp. Gli ordini Slack isolati sono ammessi soltanto con codice cliente esatto; nessun confronto fuzzy sul nome viene usato nella vista cliente.
- Disponibili intervallo date, selettore per utenti associati a più clienti, dettaglio dell'ordine, allegati e avanzamento visuale. Layout predisposto per desktop, touch standard e smartphone ad alta risoluzione.
- Verificati compilazione Python/Jinja, registrazione della rotta, integrità patch e query read-only sui dati configurati: 11 righe reali restituite senza duplicati e con stato valido.
