# Visibilità e assegnazioni delle attività

La visibilità ordinaria è l'unione di tre assegnazioni esplicite:

- **Utente**: attività indirizzata al proprio utente, anche se cambia ruolo.
- **Ruolo**: attività indirizzata a uno dei propri ruoli attivi. Il solo peso uguale o superiore non concede accesso a un ruolo diverso.
- **Peso**: attività con `target_min_weight` non vuoto, visibile quando il peso massimo dei propri ruoli attivi è maggiore o uguale alla soglia.

Admin (peso 900) e Dev (peso 1000) vedono tutte le attività, con utenti, ruoli e soglia indicati nell'elenco, nel dettaglio e nel riepilogo Home. La vista completa usa la soglia privilegiata 900 del progetto. Il permesso dell'ufficio (peso ≥40) di creare e gestire le attività non concede visibilità globale, né rende visibili quelle create dall'utente ma assegnate soltanto ad altri.

Lo stesso filtro server protegge elenco, conteggi, riepilogo Home, dettaglio, azioni, caricamento e download/rimozione delle foto. Un'attività non visibile restituisce 404 anche tramite collegamento diretto. I ruoli scaduti non partecipano alla verifica del ruolo o del peso. Le attività già indirizzate a un singolo utente mantengono la destinazione; non occorre ricrearle.

Nella modale Nuova attività, **Assegna per peso minimo** è facoltativo e separato dai ruoli esatti e dagli utenti. Le tre scelte possono essere combinate e producono una sola attività condivisa. Il filtro **Parti da un ruolo** serve soltanto a cercare utenti, senza assegnare automaticamente il ruolo o il peso.

## API e migrazione

POST `/activities/api` accetta `target_min_weight` (intero da 30 a 1000, oppure `null`/omesso). Può essere l'unico destinatario. I retry con la stessa `client_key` devono conservare anche questa soglia. GET elenco e riepilogo restituiscono `sees_all`; ogni attività restituisce `target_min_weight` insieme a `roles` e `users`. GET `/activities/api/assignees` restituisce anche il peso dei ruoli.

Nuova migrazione `w8f9a0b1c2d3`, dopo `v7e8f9a0b1c2`: aggiunge `OperationalActivity.target_min_weight` nullable, preserva le assegnazioni esistenti e supporta `create_all`.

Produzione da aggiornare con `git pull --ff-only origin main`, `venv/bin/flask --app app db upgrade` e riavvio del servizio web. Se non è ancora installato il precedente aggiornamento fornitori, installare anche `requirements.txt` prima della migrazione.

Verifiche: 18 test attività (utenti privati, ufficio non assegnato, ruoli esatti, soglie, ruoli scaduti, Admin/Dev, conteggi/Home, dettaglio/azioni/foto, retry e migrazione), oltre ai controlli browser desktop/mobile.
