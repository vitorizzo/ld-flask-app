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
