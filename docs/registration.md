# Registrazione utenti

## Blocco riprodotto il 19/10/2026

La data di nascita vuota produceva “Not a valid date value.”: il DateField non aveva il validatore Optional. Il template non visualizzava questo errore, né quelli degli altri campi. Un utente poteva quindi tornare al modulo senza capire perché la registrazione non fosse avvenuta.

I riepiloghi dei log di produzione consultati non mostrano eccezioni recenti del flusso register. Le vecchie validazioni fallite non erano tracciate: non si può identificare con certezza il motivo di ogni tentativo segnalato.

## Comportamento corretto

- Nome, cognome, email, telefono, città, provincia, selezione sesso e password/conferma restano obbligatori. Data di nascita e richiesta Esercente sono facoltative.
- Errori mostrati in un riepilogo accessibile e vicino al campo, senza ripopolare le password; gli altri dati restano nel modulo. Sessione CSRF scaduta segnalata con possibilità di reinviare il token aggiornato.
- Email: rimozione spazi esterni e minuscole; controllo duplicati e login senza distinzione di maiuscole. Limite 150 caratteri coerente con User.email. Nessuna modifica agli account esistenti.
- Creazione atomica di account, ruolo customer e, se selezionata, richiesta Horeca con ticket/messaggio. L’email viene inviata dopo il commit. Un guasto email non annulla quanto salvato: la richiesta è comunque visibile allo staff; non viene attivato alcun ruolo Horeca automaticamente. La notifica email fallita viene registrata nei log; non è previsto un nuovo sistema di reinvio automatico in questa modifica.
- Errori DB gestiti con rollback e messaggio pubblico generico. Non vengono mostrate le eccezioni tecniche.
- Logging di register esplicito: nomi dei campi, motivo generico, ID account/ticket e tipo errore; niente HTML del modulo, password, token o valori personali.

## Verifica e distribuzione

14 test in tests/test_registration.py con DB isolato, template reale e invio email simulato. Nessun account o messaggio di prova creato in produzione. Non serve una migrazione: aggiornare il codice e riavviare web. Verifica visiva sul browser non completata per il limite Edge dell’ambiente.
