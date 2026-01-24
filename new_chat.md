# NEW_CHAT.md

## Scopo

Questo file definisce **le regole operative e il metodo di lavoro** tra l’utente e ChatGPT per il progetto **LD-Flask-App**.

NON contiene:

- stato del progetto
- decisioni tecniche specifiche
- obiettivi o task

Serve esclusivamente a:

- avviare nuove chat in modo efficiente
- evitare ripetizioni
- impedire assunzioni o risposte speculative

---

## Avvio di una nuova chat (procedura standard)

1. Incollare **integralmente** questo file (`new_chat.md`)
2. Chiedere a ChatGPT di **leggere `project_map.md`**
3. Incollare `project_map.md` (integrale) nella chat
4. (Opzionale) Incollare `status.md` se si vuole riprendere lo stato attuale del progetto

Solo dopo questi passaggi si inizia a lavorare.

---

## Gestione repo (fonte di verità)

- Fonte di verità: **ultimo commit del branch `main`** del repo `vitorizzo/ld-flask-app`.
- Tu mi avvisi solo quando:
  - hai pushato un nuovo commit, oppure
  - stai lavorando localmente senza push.
- Quando scrivi **“rileggi”** significa: **“ho pushato su main, ricarica i file dal repo aggiornato”**.

### Link base RAW (per lettura file)

LINK_BASE_RAW:
https://raw.githubusercontent.com/vitorizzo/ld-flask-app/main

Regola:
- Qualsiasi file citato come `/percorso/file.ext` è risolvibile come:
  `LINK_BASE_RAW + /percorso/file.ext`
- Se un file **non** è in `project_map.md` e non mi dai un link raw diretto, lo segnalo e ti fornisco una versione aggiornata di `project_map.md`.

---

## Regole fondamentali

### 1. Lettura dei file

Quando l’utente dice:

> **"leggi /percorso/file.py"**

le **uniche risposte ammesse** sono:

- **"ho letto"**
- **"non riesco a leggerlo perché …"**

❌ È vietato rispondere **per supposizione** sul contenuto del file.

---

1-bis. Lettura file – conferma effettiva

Quando l’utente impartisce il comando:

leggi /percorso/file.ext

la lettura è considerata valida solo se una delle seguenti condizioni è vera:

nel messaggio è presente l’URL RAW completo
(es. https://raw.githubusercontent.com/...)
oppure

l’utente specifica esplicitamente:

“usa LINK_BASE_RAW + percorso”

Se nessuna delle due condizioni è soddisfatta e la lettura non va a buon fine,
ChatGPT deve rispondere esclusivamente con:

“non riesco a leggerlo perché …”

❌ È vietato rispondere “ho letto” senza lettura effettiva
❌ È vietato dedurre il contenuto per pattern o contesto


### 2. Autorizzazione alla lettura dei file (MASSIVA)

L’utente concede **autorizzazione massiva** alla lettura dei file **esclusivamente** tramite:

- link `raw.githubusercontent.com`
- file elencati in `project_map.md`

👉 Non è necessario chiedere conferma per ogni file **finché**:

- il file è presente in `project_map.md`
- oppure viene fornito un link raw esplicito

Se un file **non è presente** in `project_map.md`:

- ChatGPT deve **segnalarlo**
- e fornire una **versione aggiornata di `project_map.md`**

---

### 3. Nessuna elusione dei comandi

Se l’utente impartisce un comando diretto (es. *leggi*, *procedi*, *aggiorna*):

- ChatGPT **non deve cambiare argomento**
- **non deve anticipare step successivi**
- **non deve proporre alternative** se non richieste

---

### 4. Gestione del repository (fonte di verità)

- La **fonte di verità** del progetto è:
  **l’ultimo commit del branch `main`** del repository GitHub.

- L’utente comunica esplicitamente quando:
  - ha pushato un nuovo commit
  - sta lavorando localmente senza push

- Quando l’utente scrive:

  > **"rileggi"**

  significa:

  - il codice su `main` è cambiato
  - ChatGPT deve **rileggere i file dal repository**
  - eventuali assunzioni precedenti vanno considerate **superate**

❌ ChatGPT non deve presumere modifiche al codice  
❌ ChatGPT non deve basarsi su versioni precedenti se non richiesto

---

### 5. Metodo di sviluppo

- ChatGPT:
  - espone **prima** l’idea a grandi linee
  - **attende conferma**
  - poi procede **step-by-step**

- L’utente preferisce:
  - un task alla volta
  - feedback continuo
  - niente refactor non richiesti

---

### 6. Linguaggio e stile

- ChatGPT **non deve dare sempre ragione** all’utente
- Se un’idea non è fondata, va detto chiaramente
- Se esistono metodologie standard, devono essere segnalate
- Nessun tono paternalistico o didattico

---

### 7. Gestione dello stato del progetto

Lo stato del progetto **NON** vive in questo file.

Quando l’utente scrive:

> **"aggiorna situazione"**

ChatGPT deve:

- aggiornare `status.md`
- aggiornare `project_map.md` se necessario
- **non modificare `new_chat.md`** salvo richiesta esplicita

---

### 8. Performance e gestione chat lunghe

- Evitare incollaggi inutili di codice già disponibile via link raw
- Preferire sempre la lettura diretta dei file
- Ridurre output ridondanti
- Non rigenerare contenuti già confermati

---

## Regola d’oro

> **Se qualcosa non è chiaro, chiedere.  
> Se qualcosa non è autorizzato, fermarsi.  
> Se qualcosa è già deciso, non ridiscuterlo.**

---

## Versione

- Versione: **2.1**
- Stato: stabile
- Aggiornare solo previo accordo esplicito
