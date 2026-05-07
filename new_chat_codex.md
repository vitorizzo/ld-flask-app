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

8. Performance e gestione chat lunghe

Preferire sempre lettura diretta dei file repository

Non rigenerare codice già confermato

Non riesporre contenuti inutilmente

Ridurre output ridondanti

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

Versione: 1.0
Stato: manifesto operativo Codex locale
Aggiornare solo previo accordo esplicito
