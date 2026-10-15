# Destinatari esito e allegati attività

Nella creazione manuale sono obbligatori sia gli incaricati sia i destinatari dell’esito. I due gruppi sono indipendenti e supportano l’unione di utenti espliciti, ruoli esatti attivi e peso minimo (30–1000). La ricerca utenti, il filtro per ruolo e le selezioni multiple sono gli stessi nei due gruppi. Un destinatario dell’esito non acquisisce il diritto di prendere in carico, modificare o riaprire il lavoro.

Alla conclusione, al Non necessario dei lotti o all’annullamento, il server fotografa i destinatari in ActivityResultNotice nella stessa transazione dell’evento. Un utente presente in più criteri riceve un solo avviso. L’esito contiene stato e nota dell’evento; il dettaglio consente la consultazione degli allegati. Utenti espliciti restano destinatari anche cambiando ruolo; i ruoli/soglie sono risolti sulle appartenenze attive alla conclusione. Non viene aggiunto implicitamente il creatore.

Esiti ricevuti in Attività e Home elenca gli avvisi non letti; Segna letto è personale e non revoca la consultazione dell’attività conclusa. Il dettaglio è accessibile anche dalla push. Alla riapertura gli avvisi del ciclo precedente sono esclusi dall’inbox e non concedono accesso alla nuova lavorazione; la nuova conclusione produce un nuovo avviso. Le attività precedenti e quelle automatiche da arrivo conservano la propria configurazione: nessun destinatario esito viene inventato retroattivamente.

## File

La creazione accetta allegati delle istruzioni. Il dettaglio di un’attività aperta permette di aggiungere file/foto di lavorazione e dell’esito, anche per attività diverse dai lotti. Sono ammessi PDF, DOC/DOCX, XLS/XLSX, JPEG/PNG/WebP con controllo del contenuto: massimo 10 file e 50 MB per fase/ciclo, 10 MB per file. I file sono binari differiti nel DB, mai esposti in static. Il download richiede autorizzazione sull’attività, usa Content-Disposition attachment, nosniff e private/no-store. Backup DB include questi file; le foto lotti già esistenti continuano a richiedere anche il backup di instance/activity_photos.

Gli allegati delle istruzioni e dei cicli precedenti sono conservati. Si possono rimuovere solo quelli della lavorazione corrente aperta, rispettando incarico e revisione. Una foto aggiunta come allegato di lavorazione soddisfa anche l’evidenza fotografica richiesta per completare i lotti; una foto delle sole istruzioni non la soddisfa.

Creazione multipart: campo data JSON con result_recipients={role_ids:[],user_ids:[],target_min_weight:null}, oltre ai campi incaricati esistenti, e campo files ripetuto. Header X-Requested-With: XMLHttpRequest obbligatorio per multipart. La stessa client_key richiede gli stessi destinatari e file (nome/contenuto), evitando duplicazione su retry. Creazione JSON senza file resta disponibile ma richiede destinatari esito espliciti.

API aggiunte: GET /activities/api/results, POST /activities/api/results/<id>/read, POST /activities/api/<id>/attachments, GET/DELETE /activities/api/attachments/<id>. Le mutazioni continuano a usare esclusivamente la visibilità degli incaricati, anche se le letture includono gli esiti ricevuti.

## Push e deploy

config.tasks.dispatch_activity_results_task usa la coda notifiche esistente e il logger activities (file dedicato e main.log). L’azione tenta l’accodamento dopo il commit; il dispatcher periodico ogni minuto recupera avvisi persistenti non inviati. La nuova voce è configurabile nel pannello Task Celery. Senza VAPID gli esiti restano disponibili nell’app e le push rimangono in attesa; senza subscription attive non viene inviato nulla. Gli invii già completati non vengono ripetuti normalmente; un crash durante la consegna o una consegna parziale può comportare un retry, con tag stabile della notifica.

Dopo backup e pull: applicare flask --app app db upgrade (nuova head x9a0b1c2d3e4), quindi riavviare web, tutti i worker e Beat secondo docs/deploy.md. Nessuna nuova dipendenza. Verificare push reali su un dispositivo con notifiche abilitate. Non sono stati modificati produzione o destinatari reali durante lo sviluppo.

Verifiche: test_activity_results.py (privacy, ruoli/soglie, cicli, allegati/retry, push simulate, errore broker e migrazione preservante/create_all/offline/downgrade); test_activity_create.mjs (selettori, filtri, multipart, retry e lifecycle). Il collaudo visivo Edge non è stato completato: l’eseguibile termina senza output DOM. Verificare layout e interazioni sui dispositivi dopo deploy.


## Archivio, modifiche e sottoattività (2026-10-15)

La testata Attività espone Attività completate e Attività aperte. L’archivio riusa la stessa pagina con stato completed e comprende anche Non necessario; le attività annullate restano disponibili dal filtro. In presenza di sottoattività viene mantenuto il contesto dell’albero: il filtro seleziona gli alberi pertinenti e ciascuna pagina contiene fino a30 alberi interi. I rami completati rimangono fissati davanti a quelli ancora aperti, con indicatore di pin. Una sottoattività autorizzata resta consultabile anche se la principale non è visibile; nessun dato del genitore nascosto viene esposto.

Modifica attività nella scheda riusa la modale e i selettori esistenti per Titolo, Descrizione, Incaricati e Destinatari esito. È riservata a ufficio/supervisori con accesso operativo all’attività o alla sua principale. Ricevere soltanto un esito non abilita la modifica. Salvataggi con revisione superata vengono respinti; una modifica effettiva registra prima/dopo leggibili nello storico. Se l’attività è già conclusa, si crea un nuovo avviso in-app/push sia per i destinatari del ciclo già avvisati sia per quelli aggiornati. Lo stato rimane concluso; un salvataggio senza variazioni non produce eventi o avvisi.

Crea sottoattività nella scheda è disponibile agli incaricati operativi autorizzati durante la lavorazione, compreso Staff: si indicano titolo/istruzioni, incaricati e destinatari con gli stessi criteri. Il form propone i file e le foto della principale come checkbox di condivisione esplicita. Gli allegati selezionati vengono copiati come istruzioni private della figlia; le copie sopravvivono alla rimozione dell’originale e non concedono accesso ad altri allegati o all’intera principale. Il limite complessivo include nuove aggiunte e file condivisi. Il server controlla appartenenza dei file, permessi, revisione principale, retry e massimo otto livelli. Il legame padre non è modificabile dall’editor, impedendo cicli o spostamenti impliciti.

La principale non può essere completata/Non necessario finché ogni figlia diretta non è completed o not_required; la regola si applica ricorsivamente poiché ciascuna figlia controlla le proprie dipendenze. Una figlia annullata richiede risoluzione esplicita (riapertura e completamento), non sblocca automaticamente il lavoro. Non si possono aggiungere figlie a una principale chiusa né riaprire una figlia sotto una principale chiusa: riaprire prima la principale. Le operazioni concorrenti sono serializzate bloccando la radice dell’albero. Questo vincolo riguarda il workflow Attività; non interviene sulle funzioni di emissione documenti esterne al modulo.

Gli incaricati della principale possono seguire i rami discendenti; gli incaricati delle figlie non acquisiscono visibilità verso l’alto. Ufficio operativo sulla principale può anche gestire le figlie; chi riceve soltanto l’esito mantiene accesso in sola lettura. La conclusione di una figlia avvisa automaticamente anche gli incaricati della principale, oltre ai destinatari esito scelti.

Migrazione y0b1c2d3e4f5 aggiunge parent_id auto-referenziato con indice e FK RESTRICT, senza cambiare le attività precedenti. API PUT /activities/api/<id> per modifica; creazione POST /activities/api estesa con parent_id, parent_revision, share_attachment_ids, share_photo_ids. GET /api/assignees permette la selezione per una sottoattività quando il richiedente è incaricato della principale. Nuovi campi API: parent_id, parent_visible, children, blocked_children, can_edit, can_create_child.

Deploy: backup, pull, flask --app app db upgrade fino a y0b1c2d3e4f5 e riavvio web/tutti i worker/Beat. Test dedicati in test_activity_tree.py e test_activity_tree.mjs; test_activity_create.mjs esteso a precompilazione/modifica/sottoattività. Restano da verificare layout sui dispositivi e push reali dopo deploy; nessuna operazione su dati o notifiche di produzione durante lo sviluppo.


## 2026-10-15 — Albero Home, badge Attività e rami collassabili

- Home carica fino a cinque famiglie complete, con principale e sottoattività autorizzate, incluse le completate pinnate. Il limite non taglia i rami.
- Titoli dei nodi con figli sono pulsanti accessibili (aria-expanded): aprono/chiudono il ramo in Home e nell’area Attività. Stato conservato durante polling e aggiornamenti della pagina corrente.
- Menu Attività: badge iniziale lato server e aggiornamento ogni 30 secondi, anche per operativi; somma attività aperte visibili e avvisi di esito non letti della lavorazione corrente. Mantiene gli altri conteggi nei menu antenati.
- Endpoint GET /activities/api/badge autenticato, senza modifiche schema. Asset attività6 / menu support2.
- Verifica: 41 test Python (13 albero + 28 attività/esiti), quattro suite Node (albero/collasso, badge/aggregazione, creazione, service worker), sintassi JS/Python, Jinja incluso navbar, head Alembic unico e logging dedicato/aggregato: OK. QA visiva browser resta da eseguire per il limite Edge già documentato.
- Nessun deploy effettuato. Per queste sole modifiche aggiornare codice e riavviare web; resta necessaria la migrazione y0b1c2d3e4f5 se non ancora applicata per le implementazioni precedenti.


## 2026-10-15 — Notifiche per tutti gli eventi delle attività

- Ogni evento crea avvisi transazionali per incaricati e destinatari dell’esito: creazione, presa in carico/rilascio, completamento/non necessario, annullamento/riapertura, modifica, sottoattività e allegati/foto aggiunti o rimossi. Stessi criteri utente/ruolo esatto/peso minimo, ruoli attivi e deduplicazione per evento/utente. Le sottoattività avvisano anche gli incaricati della principale.
- I cambi destinatari notificano vecchio e nuovo insieme di utenti. Retry idempotenti, no-op, errori e rollback non generano avvisi duplicati o orfani.
- Push accodate dopo risposta riuscita e commit; recupero periodico già esistente in caso di broker/VAPID indisponibili. Testo specifico per evento con autore e nota/esito, senza derivare l’azione dallo stato corrente.
- Home e Attività mostrano “Notifiche attività”; badge include tutti gli avvisi non letti. Restano consultabili e inviabili anche gli avvisi di cicli precedenti. La ricevuta dà lettura del ciclo corrente, senza nuovi permessi di modifica; un destinatario rimosso non accede ai cicli successivi. Link e URL push rispettano questa visibilità.
- Nessun backfill degli eventi storici privi di avviso, nessuna nuova migrazione. Asset attività7. Al deploy riavviare web e worker notifiche; mantenere Beat attivo per recupero periodico. Le migrazioni precedenti fino a y0b1c2d3e4f5 restano necessarie se ancora da applicare. Nessun deploy eseguito da questa sessione.
- Verifica: 48 test Python (28 attività/esiti, 13 albero, 7 nuovi eventi), 5 suite Node (creazione, albero/collasso, badge, notifiche UI, service worker), sintassi, Jinja, head Alembic unico e logging dedicato/aggregato: OK. QA visiva e push su dispositivo reale non eseguite; limite Edge già documentato.


## 2026-10-15 — Modale tabellare codici fornitore

- In Gestisci prodotti, “Definisci codice fornitore / descrizione” apre una modale dedicata al posto della fisarmonica con selezione a tendina.
- Tabella: descrizione prodotto (con descrizione PDF facoltativa), codice interno/matrice con elenco varianti, codice fornitore facoltativo e Salva per riga. Una riga per matrice, coerente con la condivisione dei dati tra varianti. Salvataggio tramite endpoint product-settings esistente, senza modifiche backend/schema.
- Passaggio fra modali serializzato dopo hidden.bs.modal, entrambe montate nel body; ritorno al gruppo corrente senza reload intermedio. Handler e pulsanti ripristinati alla riapertura, chiusura bloccata durante salvataggio e conferma per scartare modifiche reali non salvate. Il salvataggio di una riga conserva gli altri campi modificati.
- Tabella con scorrimento orizzontale su schermi piccoli, colori e dimensioni del tema condiviso; asset settings2.
- Verifica: suite Node dedicata (raggruppamento varianti, codice vuoto, salvataggio, errori, modifiche pendenti, chiusura/riapertura), 7 test Python workflow ordini, sintassi JS, Jinja/ID univoco e git diff --check: OK. Verifica visiva nel browser non eseguita per il limite Edge già documentato.
- Nessuna migrazione o deploy eseguito. Aggiornare codice e riavviare web per attivare questa modifica.
