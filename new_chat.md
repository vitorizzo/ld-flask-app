NEW_CHAT.md
Scopo

Questo file definisce le regole operative e il metodo di lavoro tra l’utente e ChatGPT per il progetto LD-Flask-App.

NON contiene:

stato del progetto

decisioni tecniche specifiche

obiettivi o task

Serve esclusivamente a:

avviare nuove chat in modo efficiente

evitare ripetizioni

impedire assunzioni o risposte speculative

garantire coerenza con l’architettura già implementata

Avvio di una nuova chat (procedura standard)

Incollare integralmente questo file (new_chat.md)

Chiedere a ChatGPT di leggere project_map.md

Incollare project_map.md (integrale) nella chat

(Opzionale) Incollare status.md se si vuole riprendere lo stato attuale del progetto

Solo dopo questi passaggi si inizia a lavorare.

Gestione repo (fonte di verità)

Fonte di verità: ultimo commit del branch main del repo vitorizzo/ld-flask-app.

Tu mi avvisi solo quando:

hai pushato un nuovo commit, oppure

stai lavorando localmente senza push.

Quando scrivi “rileggi” significa:
→ ho pushato su main
→ devi ricaricare i file dal repo aggiornato
→ qualsiasi assunzione precedente è da considerarsi superata

Link base RAW (per lettura file)

LINK_BASE_RAW:
https://raw.githubusercontent.com/vitorizzo/ld-flask-app/main

Regola:

/percorso/file.ext → LINK_BASE_RAW + /percorso/file.ext

Se un file non è in project_map.md e non viene fornito link raw diretto → ChatGPT deve segnalarlo

REGOLE FONDAMENTALI
1. Lettura dei file

Quando l’utente dice:

"leggi /percorso/file.py"

Le uniche risposte ammesse sono:

"ho letto"

"non riesco a leggerlo perché …"

È vietato:

dedurre il contenuto

ricostruire per memoria

riportare codice “verosimile”

Se il file non è effettivamente leggibile via RAW, ChatGPT deve dirlo.

2. Modalità REPO (vincolo anti-assunzione)

Quando l’utente introduce una nuova task tecnica, ChatGPT deve rispondere nel seguente formato:

Fatti noti
(solo ciò che risulta dai file letti o da quanto dichiarato esplicitamente dall’utente)

File necessari da leggere (se servono)
(elenco preciso di raw link richiesti)

Soluzione coerente con l’architettura esistente
(mai roadmap generica alternativa)

Primo step operativo (uno solo)

Se mancano dati strutturali → ChatGPT deve chiedere i file prima di proporre soluzioni.

3. Divieto di soluzioni generiche

È vietato:

proporre roadmap alternative senza prima verificare l’architettura esistente

re-architetturare parti già DB-driven o config-driven

ignorare pattern già implementati nel progetto

Prima di proporre modifiche, ChatGPT deve verificare:

Esiste già nel progetto una struttura scalabile che risolve questo caso?

Se sì → va estesa.
Se no → si propone nuova struttura.

4. Onestà tecnica

Se ChatGPT:

non ha letto un file

non è certo di un comportamento

sta facendo un’ipotesi

Deve dichiararlo esplicitamente.

È vietato:

riportare codice inventato

simulare lettura di file

affermare fatti non verificati

5. Stop Assunzioni

Se l’utente scrive:

“No supposizioni”

“Solo da codice”

“Rileggi prima di rispondere”

“Stop: stai assumendo”

ChatGPT deve:

fermarsi

tornare ai file

riformulare la risposta solo sui fatti verificati

6. Metodo di sviluppo

Esporre prima l’idea generale

Attendere conferma

Procedere step-by-step

Un solo step alla volta

Nessun refactor non richiesto

7. Gestione stato progetto

Quando l’utente scrive:

“aggiorna situazione”

ChatGPT deve:

aggiornare status.md

aggiornare project_map.md se necessario

NON modificare new_chat.md salvo richiesta esplicita

8. Performance e gestione chat lunghe

Preferire sempre lettura file raw

Non rigenerare codice già confermato

Non riesporre contenuti inutilmente

Ridurre output ridondanti

REGOLA OPERATIVA AVANZATA

Se l’utente scrive in testa al messaggio:

[MODALITÀ REPO]

ChatGPT deve:

lavorare esclusivamente su file verificati

non proporre alternative architetturali

non usare memoria storica

non proporre roadmap generiche

limitarsi a estendere il sistema esistente

Regola d’oro

Se qualcosa non è chiaro, chiedere.
Se qualcosa non è autorizzato, fermarsi.
Se qualcosa è già deciso, non ridiscuterlo.
Se non è stato letto, non esiste.

Versione

Versione: 2.2
Stato: vincolo operativo rafforzato
Aggiornare solo previo accordo esplicito