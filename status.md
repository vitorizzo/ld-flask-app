🔄 STATUS UPDATE — Menu Manager Dinamico
✅ Stato attuale: STABILE E FUNZIONANTE

Il modulo Gestione Menu Dinamici è ora considerato stabile dopo refactoring completo di:

menu_management.js

menu.css

gestione dropdown Bootstrap

rimozione hack z-index conflittuali

eliminazione stacking context indesiderati

gestione stato attivo/disattivo senza uso di opacity su container

sistemazione hover + click dropdown

pulizia doppie inizializzazioni JS

Funzionalità verificate

Creazione menu root

Creazione sotto-menu

Modifica menu

Toggle attivo/disattivo

Eliminazione con gestione cascade figli

Drag & drop con persistenza ordinamento

Scroll preservation dopo refresh

Dropdown stabile sopra altri nodi

Modal con gestione weight tramite ruolo o valore custom

Nessun conflitto con style.css globale

Il modulo è ora coerente con Bootstrap senza override pericolosi.

🧠 TODO FUTURI — Menu Manager (Miglioramenti)
UX / Interazione

Evidenziare nodo selezionato

Animazione più elegante apertura dropdown

Indicatore visivo durante drag

Eventuale rimozione hover-open e lasciare solo click (valutare UX definitiva)

Logica gerarchica

Impedire attivazione figlio se parent è disattivato

Disattivare automaticamente figli quando parent viene disattivato

Validazione duplicati route

Validazione duplicati name sotto stesso parent

Ruoli / Weight

Modalità “Simula utente con peso X”

Evidenziare menu non visibili per determinato weight

Associare direttamente ruoli anziché solo peso numerico

Robustezza

Toast al posto di alert()

Logging lato backend su modifiche struttura

Protezione race condition in reorder

📒 MODULO AGENDA — Stato Architetturale
Stato: IN PROGETTAZIONE AVANZATA (Architettura definita)
🎯 Obiettivo

Implementare un sistema Agenda giornaliera per:

Registrazione incassi

Registrazione spese

Movimenti di cassa

Movimenti POS

Calcolo versabile

Chiusura giornaliera

Con separazione strutturale tra dati fiscali (AZ) e dati personali/non fiscali (PRI).

🧠 Architettura Definitiva
1️⃣ Doppia sorgente dati
🔹 AZ (Aziendale / Fiscale)

Database PostgreSQL aziendale

Contiene solo movimenti fiscali documentabili

🔹 PRI (Privato / Non fiscale)

File JSON cifrato

Struttura identica ai modelli aziendali

Memorizzato su chiavetta USB

Separato fisicamente dal database aziendale

📦 Struttura Vault Privato

Percorso montato sul server:

/mnt/vault/
    2026.enc
    2027.enc
    ...


Un file cifrato per anno

Contiene movimenti completi (sales, expenses, cash_moves, pos_moves, closures)

Struttura JSON identica ai modelli SQLAlchemy

🔐 Modalità operative
Modalità Fiscale

Usa solo dati AZ

Vault non caricato

Totali coerenti con contabilità aziendale

Modalità Completa

Usa AZ + PRI

Richiede sblocco vault

Serve per quadratura reale di cassa

🔓 Sblocco Vault

Solo utenti autorizzati (ruolo adeguato)

Password separata dal login

Caricamento in RAM

Non persistito in sessione client

TTL lungo (es. giornata lavorativa)

Richiusura automatica su logout/scadenza sessione

🧮 Comportamento calcoli
Quadratura serale

Sempre effettuata in modalità completa.

Controllo fiscale

Può essere effettuato in modalità fiscale.
Non devono risultare movimenti personali.

⚠️ Requisiti di sicurezza

PRI mai scritto in chiaro su disco

Scrittura atomica del file cifrato

fsync prima di considerare salvato

Se chiavetta assente → sistema lavora solo AZ

Nessun errore esplicito che suggerisca occultamento

🗂 Flag Movimenti (Definiti)
Fiscali

*, **, #, !

Non fiscali

+, x

+ modificabile in fiscale in futuro

x definitivamente non fiscale

📌 Decisioni Architetturali Bloccate

Vault annuale

JSON cifrato (no SQLite)

Caricamento all’avvio modalità completa

Nessun lazy loading

Nessun salvataggio decriptato su disco

📍 Prossimo Step

Implementazione API:

GET /cassa/api/private/status

POST /cassa/api/private/unlock

POST /cassa/api/private/lock

Senza ancora integrare i dati nei calcoli.