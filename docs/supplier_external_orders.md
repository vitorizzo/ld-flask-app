# Bacheca e ordini fornitori esterni

Le schede manuali e gli ordini esterni consentono titolo, testo **Ordine** facoltativo, riferimento, note generali e **Note da trasmettere** separate. Le note sono memorizzate senza invio automatico. Gli ordini generati conservano editor prodotti e PDF; gli esterni si modificano dalla bacheca.

Da ogni gruppo, **Allega ordine** apre una modale con titolo precompilato e colonna obbligatoria. Il fornitore della Rubrica è facoltativo. Il salvataggio mostra il collegamento alla nuova scheda, senza richiedere quantità o prodotti. Il filtro gruppi cerca subito nome e note senza distinzione fra maiuscole e minuscole, mostra conteggi e conserva la ricerca nella stessa scheda browser anche dopo il ricaricamento.

## Pagamento e allegati

Contrassegno e termine di pagamento sono indipendenti. Con contrassegno occorre un termine; con **Altro** occorre una spiegazione. Termini: A vista, Fine mese, 30/60/90 giorni, Altro. La data pagamento è facoltativa e non viene calcolata.

Allegati: PDF, JPEG, PNG, WebP, DOC/DOCX, XLS/XLSX. Massimo 10 allegati, 10 MiB ciascuno, 50 MiB complessivi per scheda. Il PDF generato dall'app resta separato. Per sostituire un file, rimuoverlo e aggiungere il nuovo prima di salvare: in caso di errore restano disponibili dati e allegati precedenti. Download con gli stessi permessi della bacheca (peso >=40), `Content-Disposition: attachment`, `Cache-Control: private, no-store`; nessuna cache PWA per l'area fornitori.

## API

- Le API JSON esistenti restano compatibili. POST `/supplier-orders/api/board/cards` e PUT `/supplier-orders/api/board/cards/<id>` accettano anche multipart: campo `data` con oggetto JSON e file multipli nel campo `files`.
- Nuovi campi: `order_text`, `transmission_notes`, `cash_on_delivery` (booleano), `payment_terms` (`sight`, `month_end`, `30`, `60`, `90`, `other` oppure vuoto), `payment_terms_other`, `payment_date` (ISO oppure vuoto).
- `remove_attachment_ids` indica i file da rimuovere nella stessa transazione. PUT multipart e modifiche JSON ai nuovi campi richiedono `revision` uguale a `order_revision`; conflitto HTTP 409. Le vecchie modifiche JSON conservano il comportamento precedente, con controllo revisione quando fornita.
- POST `/supplier-orders/groups/<id>/external-orders`: stessi dati, `client_key` obbligatoria (16–64 caratteri alfanumerici/trattino). Retry con la stessa chiave restituisce la scheda già creata; chiave appartenente a un altro gruppo/tipo: 409. Risposta con `card`, `replayed`, `board_url`.
- `card.order_kind`: `manual`, `generated`, `external`; `card.attachments` contiene solo metadati e URL, nessun contenuto binario.
- GET `/supplier-orders/api/board/cards/<id>/attachments/<attachment_id>`: scaricamento autenticato; 404 se il file non appartiene alla scheda.

## Deploy

Produzione da aggiornare successivamente:

1. `git pull --ff-only origin main`.
2. `venv/bin/python -m pip install -r requirements.txt` (nuova dipendenza `olefile==0.47`).
3. `venv/bin/flask --app app db upgrade`. Nuova head `v7e8f9a0b1c2`, successiva a `u6d7e8f9a0b1`.
4. Riavviare il servizio web secondo la procedura del server.

La migrazione preserva schede, ordini e PDF esistenti, inizializza contrassegno e indicatore esterno a false e aggiunge campi vuoti; è compatibile con tabelle già create da `create_all`. Gli allegati hanno contenuto binario differito nel database. Il limite HTTP deve consentire 50 MiB più il multipart: il default applicativo `MAX_UPLOAD_MB=64` è sufficiente; allineare eventuali limiti del proxy.

Verifiche: `venv/Scripts/python.exe -m unittest discover -s tests -p "test_supplier*.py"` e `node tests/test_activity_service_worker.mjs`. I controlli browser locali usano template e script reali con API simulate e ricaricamento HTTP a 320/1440 px.
