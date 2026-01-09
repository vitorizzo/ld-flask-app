# new_chat.md
Versione: 1.2  
Ultimo aggiornamento: 2026-01-09

## Istruzioni per avviare una nuova chat (per l’operatore umano)

Sequenza OBBLIGATORIA:

1) Incolla **TUTTO** il contenuto del blocco “PROMPT DI BOOTSTRAP” qui sotto come **primo messaggio** della nuova chat.
2) Secondo messaggio: leggi project_map.md https://raw.githubusercontent.com/vitorizzo/ld-flask-app/main/project_map.md
3) Terzo messaggio (**SBLOCCO TECNICO OBBLIGATORIO**):
 
Incolla **l’intero contenuto di `project_map.md`** (con tutti i link raw).
- Non fare domande.
- Non chiedere analisi.
- Serve solo a sbloccare tecnicamente la lettura dei file.

Dopo questi 3 messaggi:
- puoi dire semplicemente `leggi /routes/trello.py`
- l’assistente userà la mappa
- nessun altro link raw sarà richiesto finché resti nel perimetro della mappa

---

## PROMPT DI BOOTSTRAP (incolla questo come primo messaggio)

Stiamo lavorando su una web app Flask reale in produzione chiamata “ld-flask-app”.
Repository GitHub (pubblico): https://github.com/vitorizzo/ld-flask-app
Branch di riferimento: main (sempre l’ultimo commit pushato, salvo mie indicazioni).

OBIETTIVO CORRENTE DELLA SESSIONE
- Ripristinare e migliorare (solo quando richiesto) la parte relativa ai webhook e alle automazioni Trello.
- In parallelo, assicurare che l’app factory (create_app) non lasci l’app monca e che non ci siano inizializzazioni duplicate (Gunicorn/Celery).

REGOLE FONDAMENTALI (OBBLIGATORIE)
1) NON dare nulla per scontato.
2) NON proporre refactoring, riscritture o “migliorie” se prima non ti chiedo esplicitamente di farlo.
3) Prima di suggerire QUALSIASI modifica:
   - devi chiedermi di mostrarti i file necessari (o di aggiungerli alla mappa)
   - devi leggerli
   - devi spiegarmi cosa fanno ORA e cosa NON fanno (o cosa si è rotto)
4) Ogni intervento deve essere:
   - incrementale
   - reversibile
   - giustificato tecnicamente
5) UN SOLO step per messaggio:
   - Tu mi chiedi una sola azione (un comando o un singolo file)
   - Io la eseguo / te lo fornisco
   - Ti riporto l’output
   - Solo dopo si va avanti
6) Se dico qualcosa senza fondamento o propongo una strategia non ottimale rispetto a metodologie note, devi dirmelo chiaramente e proporti di spiegarmelo “nel dettaglio” solo se te lo chiedo.

CONTESTO TECNICO (STATO ATTUALE)
- Stack: Flask, Gunicorn, Celery worker + beat, Redis, PostgreSQL, SQLAlchemy.
- Migrazione in corso:
  app.py monolitico → pattern app factory (create_app)
- Durante la migrazione:
  - molto codice è stato rimosso da app.py
  - solo una parte è stata reinserita in create_app()
  - alcune integrazioni non sono più inizializzate correttamente
- Stato confermato:
  - Celery (worker+beat) funziona
  - Redis funziona
  - systemd è corretto
  - la web app è “monca” (non tutto viene inizializzato come prima)

ENTRYPOINT (IMPORTANTE)
- app.py chiama solo create_app()
- create_app() sta in tools/app_factory.py
- Gunicorn avvia direttamente l’app con ld-flask-app.service

LETTURA FILE (VINCOLI E METODO)
- Non usare github.com/.../blob/... perché spesso il contenuto è caricato via JS e non è leggibile.
- Usare SOLO raw.githubusercontent.com
- Esiste un file di mappatura nella root: project_map.md

REGOLE DI MAPPATURA
- Prima fase di ogni chat: devi chiedermi di farti leggere la mappa.
- Quando ti dico “leggi project_map.md”, devi caricare la mappa (percorso_logico → link_raw).
- Dopo che hai caricato la mappa:
  - se ti dico “leggi /routes/trello.py” tu apri il link raw corrispondente dalla mappa
  - NON leggere file non presenti nella mappa
  - se ti serve un file non in mappa: me lo chiedi (un solo step), e io decido se aggiungerlo alla mappa

GESTIONE REPO
- Fonte di verità: ultimo commit del branch main.
- Io ti avviso solo quando:
  - ho pushato un nuovo commit
  - oppure sto lavorando localmente senza push
- Quando dico “rileggi”, significa: “ho pushato su main, ricarica i file dal repo aggiornato”.

PRIMO STEP OBBLIGATORIO
Dimmi ESATTAMENTE:
- quali file vuoi leggere per primi
- in che ordine
- e perché
e fermati lì (nessuna analisi oltre questo finché non ti autorizzo).
