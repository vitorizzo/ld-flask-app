NEW_CHAT_CODEX.md
Scopo

Questo file definisce le regole operative e il metodo di lavoro tra l'utente e Codex locale per il progetto LD-Flask-App.

NON contiene:

stato del progetto

decisioni tecniche specifiche

obiettivi o task

Serve esclusivamente a:

avviare nuove chat Codex in modo efficiente

evitare ripetizioni

impedire assunzioni o risposte speculative

garantire coerenza con l'architettura già implementata

Avvio di una nuova chat Codex locale

Chiedere a Codex di leggere direttamente dal repository i file di coordinamento:

- new_chat_codex.md
- project_map.md
- status.md

Non serve incollare in chat il contenuto dei file.

Solo dopo la lettura diretta dei file repository si inizia a lavorare.

Se un file richiesto non è presente o non è leggibile nel repository, Codex deve segnalarlo.

Gestione repo (fonte di verità)

Fonte di verità: ultimo commit del branch main del repo vitorizzo/ld-flask-app.

Tu mi avvisi solo quando:

hai pushato un nuovo commit, oppure

stai lavorando localmente senza push.

Quando scrivi "rileggi" significa:
-> ho pushato su main
-> devi ricaricare i file dal repo aggiornato
-> qualsiasi assunzione precedente è da considerarsi superata

REGOLE FONDAMENTALI
1. Lettura dei file

Quando l'utente dice:

"leggi /percorso/file.py"

Le uniche risposte ammesse sono:

"ho letto"

"non riesco a leggerlo perche ..."

E' vietato:

dedurre il contenuto

ricostruire per memoria

riportare codice "verosimile"

Se il file non è effettivamente leggibile dal repository locale, Codex deve dirlo.

2. Modalità REPO (vincolo anti-assunzione)

Quando l'utente introduce una nuova task tecnica, Codex deve rispondere nel seguente formato:

Fatti noti
(solo ciò che risulta dai file letti o da quanto dichiarato esplicitamente dall'utente)

File necessari da leggere (se servono)
(elenco preciso dei percorsi repository richiesti)

Soluzione coerente con l'architettura esistente
(mai roadmap generica alternativa)

Primo step operativo (uno solo)

Se mancano dati strutturali -> Codex deve chiedere i file prima di proporre soluzioni.

3. Divieto di soluzioni generiche

E' vietato:

proporre roadmap alternative senza prima verificare l'architettura esistente

re-architetturare parti già DB-driven o config-driven

ignorare pattern già implementati nel progetto

Prima di proporre modifiche, Codex deve verificare:

Esiste già nel progetto una struttura scalabile che risolve questo caso?

Se sì -> va estesa.
Se no -> si propone nuova struttura.

4. Onestà tecnica

Se Codex:

non ha letto un file

non è certo di un comportamento

sta facendo un'ipotesi

Deve dichiararlo esplicitamente.

E' vietato:

riportare codice inventato

simulare lettura di file

affermare fatti non verificati

5. Stop Assunzioni

Se l'utente scrive:

"No supposizioni"

"Solo da codice"

"Rileggi prima di rispondere"

"Stop: stai assumendo"

Codex deve:

fermarsi

tornare ai file

riformulare la risposta solo sui fatti verificati

6. Metodo di sviluppo

Esporre prima l'idea generale

Attendere conferma

Procedere step-by-step

Un solo step alla volta

Nessun refactor non richiesto

7. Gestione stato progetto

Quando l'utente scrive:

"aggiorna situazione"

Codex deve:

aggiornare status.md

aggiornare project_map.md se necessario

NON modificare new_chat_codex.md salvo richiesta esplicita

Dopo ogni intervento tecnico concluso o ogni cambio di contesto operativo rilevante, Codex deve aggiornare puntualmente:

- status.md con stato reale, verifiche e prossimo punto di ripartenza;
- project_map.md se sono cambiati architettura, moduli, route, modelli o file chiave;
- new_chat_codex.md solo se cambia il metodo operativo o se l'utente lo richiede esplicitamente.

Nota operativa modali:

- quando si implementa una nuova modale o si modifica una modale esistente, il pulsante di conferma non va affidato al solo stato iniziale del DOM;
- lo stato del pulsante di conferma, il testo e l'handler devono essere impostati all'apertura della modale (`shown.bs.modal`) e ripuliti alla chiusura (`hidden.bs.modal`);
- il default non deve ereditare uno stato disabilitato lasciato da aperture precedenti o da riuso del nodo;
- se la modale esegue un'azione critica, la conferma va resa esplicita e riassegnata ad ogni apertura.

8. Performance e gestione chat lunghe

Preferire sempre lettura diretta dei file repository

Non rigenerare codice già confermato

Non riesporre contenuti inutilmente

Ridurre output ridondanti

9. Scelta modello Codex per la sessione

Il modello della sessione Codex viene scelto dall'utente nell'ambiente/interfaccia e Codex non può cambiarlo autonomamente durante la chat.

Codex deve però valutare la task prima di iniziare e, se il modello corrente non è adeguato, deve segnalarlo all'utente prima di procedere.

Tabella operativa:

- Task ordinari di sviluppo, fix mirati, UI, route, API, template, CSS/JS: GPT-5.4 come modello consigliato.
- Task critici o ad alto rischio: GPT-5.5 consigliato.
  Esempi: formule contabili, `cash_math.py`, migrazioni DB complesse, refactor trasversali, sincronizzazione Redis, vault/USB, import massivi, modifiche che coinvolgono molte aree del progetto.
- Task leggeri di lettura, riassunto, ricerca semplice o controlli localizzati: GPT-5.4-mini può essere sufficiente.

Se il modello corrente è inferiore a quello consigliato per la task, Codex deve dirlo chiaramente e chiedere se l'utente vuole cambiare modello o procedere comunque.

Questa regola riguarda solo il modello usato da Codex durante lo sviluppo.

Le future funzioni AI interne a LD-Flask-App devono invece usare una scelta modello codificata nell'applicazione, tramite configurazione e un layer astratto tipo `AIProvider`, con modello selezionabile in base alla funzione applicativa, costi, cache, log e flag di abilitazione.

REGOLA OPERATIVA AVANZATA

Se l'utente scrive in testa al messaggio:

[MODALITÀ REPO]

Codex deve:

lavorare esclusivamente su file verificati

non proporre alternative architetturali

non usare memoria storica

non proporre roadmap generiche

limitarsi a estendere il sistema esistente

Regola d'oro

Se qualcosa non è chiaro, chiedere.
Se qualcosa non è autorizzato, fermarsi.
Se qualcosa è già deciso, non ridiscuterlo.
Se non è stato letto, non esiste.

Versione

Versione: 1.1
Stato: manifesto operativo Codex locale con aggiornamento puntuale dei file di coordinamento
Aggiornare solo previo accordo esplicito

Nota operativa 2026-06-14:
- per Agenda/Cassa la chiusura giornata passa da `POST /cassa/api/day/<day_date>/close`;
- snapshot fiscale resta nel DB, snapshot PRI/complete nel vault annuale;
- prima di ogni nuova modifica aggiornare anche `status.md` e `project_map.md`.
- audit chiusure: tabella `cash_day_audit_events` + listener SQLAlchemy; gli snapshot chiusi dal giorno toccato in avanti vengono marcati stale automaticamente.
- stato giornata: badge cliccabile in alto a destra per `open/closed`; su giornata chiusa la UI chiede se riaprire o passare a oggi prima di inserire movimenti; backend blocca i mutatori principali anche nei rami PRI.
- bootstrap home: `inject_menus` non deve rompere la pagina iniziale se il DB non e' raggiungibile; ora ritorna un menu vuoto come fallback.
- agenda crash fix: `templates/agenda.html` era stato salvato con encoding non UTF-8; Jinja generava `UnicodeDecodeError`, ora il file e' in UTF-8.
- scheda prodotto articoli: pubblicazione immagini attiva dalla LDApp verso le piattaforme presenti; Prestashop e' collegato a un upload reale, il menu disabilita i target non supportati e il drag/drop sullo slot usa lo stesso endpoint.
- chiusura report giornaliero: resa idempotente, rimosso `noload` sulla relazione `CashDay.closure` per evitare che una giornata gia' chiusa venisse trattata come priva di chiusura durante la stampa del report.
- chiusura report giornaliero: snapshot e report payload normalizzati con `_json_safe` prima del commit/salvataggio vault, per prevenire errori di serializzazione JSONB.
- stampa report giornaliero: se la giornata e' gia' chiusa il bottone usa lo snapshot salvato e non richiama piu' la chiusura.
- impostazioni applicative: le chiavi API, le soglie e i parametri operativi vanno gestiti dal pannello `/settings/preferences`; il runtime ricarica le preferenze dal DB e mantiene un fallback sui valori base di avvio.
- impostazioni applicative: la pagina `/settings/preferences` deve degradare con warning, non con 500, se `app_preferences` non e' ancora disponibile o il DB non e' allineato.
- impostazioni applicative: il template preferenze deve usare accesso esplicito ai campi dei dizionari (`section["items"]`) per evitare che Jinja risolva `dict.items` come metodo iterabile.
- impostazioni applicative: `/settings` e' la dashboard principale a tile di categoria; la prima categoria da esporre e' `Utenti`, con una pagina read-only che mostra utenti, ruoli attivi e dati anagrafici principali.
- impostazioni applicative: la dashboard deve includere anche i tile `Banche`, `Circuiti Carte` e `Dispositivi POS`, ognuno con pagina di riepilogo read-only come base per la futura gestione.
- impostazioni applicative: `Banche`, `Circuiti Carte` e `Dispositivi POS` sono gestite con form inline; il POS consente anche di associare piu' circuiti al dispositivo.
- impostazioni applicative: i circuiti carte devono mostrare icona e logo come elementi grafici, con picker icone in modale e upload logo da file con preview.
- impostazioni applicative: il picker icone dei circuiti usa Font Awesome gia' caricato nel layout; la modale deve essere portata nel `body` per non finire sotto gli stacking context della pagina.
- impostazioni applicative: il logo del circuito va preservato al salvataggio finché non viene caricato un nuovo file.
- impostazioni applicative: i dispositivi POS devono mostrare i circuiti associati come checkbox leggibili, non come multiselect con shift/click.
- impostazioni applicative: per i record nuovi il nome va validato prima di creare l'oggetto ORM, cosi' non restano insert vuoti pendenti in sessione.
- impostazioni applicative: le aree configurazione devono esporre anche azioni esplicite di disattivazione e cancellazione, ma il delete va bloccato se il record ha riferimenti storici o associazioni.
- 2026-06-18: regola operativa aggiornata: per i circuiti/dispositivi POS usare validita' temporale (`valid_from`/`valid_to`) e non bloccare la lettura dei movimenti sulle giornate chiuse; la modale icone va aperta manualmente dopo averla portata nel `body`.
- 2026-06-18 fix operativo: prima di usare `valid_from`/`valid_to` su circuiti/dispositivi POS bisogna passare da query compatibili con DB non ancora migrato; se la migrazione non e' applicata, l'app deve continuare a funzionare con i campi storici gia' presenti.
- 2026-06-18 nota operativa: per la parte POS non fare affidamento solo sulla migration; il runtime deve saper autocreare i campi di validita' mancanti e le relazioni dei dispositivi devono essere eager-loaded per non innescare query lazy su tabelle non allineate.
- 2026-06-18 nota operativa: per i circuiti POS il logo va salvato sotto `static/images/pos`; la modale icone non deve piu' dipendere da Bootstrap modal; la relazione `PosDevice.circuits` resta dinamica e non va eager-loaded.
- 2026-06-18 nota finale: la modale icone POS deve usare Bootstrap modal standard; i logo vanno salvati sotto `static/images/pos`; i circuiti dei device vanno letti con query esplicita sulla tabella di associazione, non tramite la relazione dinamica.
