# LD-Flask-App — Deployment & System Services

## Attività manuali (2026-10-14)

La creazione manuale richiede la migrazione `u6d7e8f9a0b1` (dopo `t5c6d7e8f9a0`).
Dopo il pull eseguire `venv/bin/flask --app app db upgrade` e riavviare il web.
La migrazione aggiunge descrizione, chiave richiesta univoca e destinatari utenti;
preserva le attività e gli arrivi precedenti. Non richiede modifiche Celery.
Gli utenti ufficio/supervisori (peso >=40) trovano `Attività > Nuova attività`:
ruoli interi, utenti individuali o utenti scelti filtrando per ruolo, anche combinati.
L'attività rimane unica e condivisa; gli utenti espliciti restano assegnati anche
se successivamente cambiano ruolo. Le assegnazioni per ruolo seguono i ruoli attivi.

## Area Attività (2026-10-14)

La prima versione dell'area richiede la migrazione `t5c6d7e8f9a0`, successiva
a `s4b5c6d7e8f9`. Dopo il pull, prima del normale riavvio web:

```bash
venv/bin/flask --app app db upgrade
```

La migrazione aggiunge cinque tabelle e la voce menu Attività. Non sono richiesti
pacchetti nuovi: le foto usano Pillow già presente. Il servizio web deve poter
scrivere nella directory `activity_photos` sotto `Flask.instance_path`, creata
al primo upload. **Includere questa directory e il database nei backup**:
le foto sono file privati, i loro metadati e le autorizzazioni sono nel DB.

Aggiornare anche la PWA: service worker v29 mantiene attività e foto fuori
dalla cache offline. Dopo il deploy verificare dal browser/PWA il nuovo menu,
il riepilogo Home e il caricamento di una foto. Gli altri servizi si riavviano
secondo la procedura ordinaria; questa versione non aggiunge task Celery.

Primo uso: `Attività > Ruoli destinatari`, poi aprire una scheda fornitore e
scegliere `Merce arrivata · crea attività`. Il ruolo Staff viene proposto solo
se esiste; in assenza occorre scegliere i ruoli operativi. Solo la conferma
dell'arrivo effettivo genera la checklist, non la creazione dell'ordine.
Ogni arrivo successivo/parziale è separato; ripetere la medesima richiesta
con la stessa chiave non genera duplicati.

Gli utenti vedono le attività dei ruoli attivi; l'ufficio (peso almeno40)
supervisiona e configura. Riapertura/annullamento richiedono motivazione.
Le foto dei cicli precedenti restano nello storico e non chiudono una nuova
lavorazione. La prima fase offre attività persistenti nell'app; push,
promemoria e ulteriori sorgenti evento sono il collegamento successivo.

## Bacheca fornitori: migrazione sezioni (2026-10-13)

Il deploy delle sezioni configurabili richiede la migrazione `r3a4b5c6d7e8`
(successiva a `q2f3a4b5c6d7`) e, per i colori dei badge, la successiva
`s4b5c6d7e8f9`. Dopo il pull, prima di riavviare la web app,
dalla directory del progetto in produzione:

```bash
venv/bin/flask --app app db upgrade
```

La migrazione aggiunge `supplier_board_sections` e
`supplier_board_card_sections`, con indici/vincoli e le undici sezioni iniziali.
La migrazione dei colori aggiunge tre colonne nullable: le sezioni esistenti
continuano a usare il tema finche' non si scelgono colori personalizzati.
Riconosce anche le tabelle eventualmente precreate dagli import tramite
`db.create_all`. Non richiede pacchetti nuovi. Il riavvio web ricarica modelli,
route e asset; le modifiche successive alle sezioni dalla bacheca sono immediate
e non richiedono altre migrazioni o riavvii.

L'eliminazione dal configuratore cancella una definizione e i relativi testi
anche nelle schede archiviate: la UI mostra il numero di schede coinvolte e
chiede conferma. Note generali, righe d'ordine e PDF esistenti vengono conservati.

Questo documento descrive come è deployata la web app **LD-Flask-App** in produzione
e quali servizi di sistema sono necessari per il suo funzionamento.

È pensato per:
- manutenzione futura
- migrazione su nuovo server
- onboarding di un altro tecnico

---

## Stack

- Flask (app factory)
- Gunicorn + systemd
- Celery
- Redis (broker + backend)
- PostgreSQL

---

## Servizi systemd

La web app usa Web, Celery Beat e worker gestiti da `systemd`. Dopo l'attivazione
delle code per contesto i worker diventano quattro, per un totale di sei servizi
applicativi. Prima dell'attivazione resta compatibile con il worker unico.

I servizi **non si avviano a vicenda automaticamente** e devono essere gestiti esplicitamente.

---

## 1. Web App (Gunicorn)

### Service
- `ld-flask-app.service`

### Responsabilità
- espone l’app Flask tramite Gunicorn
- gestisce le richieste HTTP
- non esegue task asincroni
- non avvia Celery

### Note operative
- porta 5000 in produzione
- porta 5001 per test manuali

### Comandi
```bash
sudo systemctl start ld-flask-app.service
sudo systemctl stop ld-flask-app.service
sudo systemctl restart ld-flask-app.service
sudo systemctl status ld-flask-app.service
```

---

## 2. Celery Worker

### Service
- `celery-worker.service`
- `celery-context@gestionale.service`
- `celery-context@notifiche.service`
- `celery-context@spedizioni.service`

### Responsabilità
- esegue task asincroni
- consuma task dal broker Redis
- non pianifica task

### Configurazione
- app: `celery_worker.celery`
- broker: Redis
- backend risultati: Redis
- pool: `solo`
- un processo per contesto, prefetch 1 e hostname distinto
- `celery-worker` consuma `celery` (background); le tre istanze consumano
  rispettivamente `ld_gestionale`, `ld_notifiche`, `ld_spedizioni`

### Comandi
```bash
sudo systemctl start celery-worker.service
sudo systemctl stop celery-worker.service
sudo systemctl restart celery-worker.service
sudo systemctl status celery-worker.service
```

---

## 3. Celery Beat (Scheduler)

### Service
- `celery-beat.service`

### Responsabilità
- pianifica task periodici
- non esegue task
- richiede almeno un worker attivo

### Persistenza stato
Per evitare problemi di permessi e garantire idempotenza:

- schedule DB: `/var/lib/celery/beat/celerybeat-schedule`
- PID file: `/var/lib/celery/beat/celerybeat.pid`

La directory `/var/lib/celery/beat` deve esistere ed essere scrivibile
dall’utente che esegue il servizio.

### Comandi
```bash
sudo systemctl start celery-beat.service
sudo systemctl stop celery-beat.service
sudo systemctl restart celery-beat.service
sudo systemctl status celery-beat.service
```

---

## Ordine di avvio consigliato

1. Redis
2. PostgreSQL
3. ld-flask-app
4. celery-worker
5. celery-beat

---

## Nota finale

L’architettura è intenzionalmente separata:

- web app → HTTP
- worker → esecuzione task
- beat → schedulazione
- redis → coordinamento

Questa separazione è parte integrante dell’architettura dell’applicazione.

## Attivazione delle code per contesto (2026-10-13)

Il codice instrada le task con `tools/celery_contexts.py`. Il flag
`CELERY_CONTEXT_QUEUES_ENABLED` ha default false: finche' non sono pronti i
worker dedicati, i producer continuano a usare la coda `celery`, evitando code
senza consumer. La deduplicazione e le metriche funzionano anche in modalita'
seriale dopo il riavvio dei processi aggiornati.

Dopo il deploy del codice, dalla directory di produzione:

```bash
cd /home/tecno/ld-flask-app-working
sudo bash deploy/install_celery_contexts.sh
```

Lo script controlla la sintassi prima di fermare servizi, salva unit ed ambiente
in `.codex_tmp/celery-contexts-<data UTC>`, ferma Beat/web e attende la chiusura
normale delle task in corso. Installa i template systemd, abilita il solo flag
delle code in `.env.local`, avvia i quattro worker e controlla PID e code tramite
`tools/check_celery_workers.py`. Infine riavvia web e Beat. Richiede privilegi
sudo per i servizi; nessuna nuova dipendenza runtime o migration. La pausa
`MATRIX_FILE_IMPORTS_PAUSED` e le impostazioni nel DB non vengono modificate.

Un errore nell'attivazione avvia il ripiego seriale con un worker che consuma
tutte e quattro le code, cosi' anche i messaggi gia' inviati alle code nuove
restano processabili. Il drop-in di ripiego e' sotto `/run/systemd/system`;
un successivo avvio dello script lo sposta nel backup. Le task legacy ricevute
dalla coda sbagliata vengono trasferite alla destinazione corretta, conservando
identita' e callback e senza completare prematuramente il risultato.

Per i deploy successivi riavviare anche le tre istanze:

```bash
sudo systemctl restart celery-context@gestionale.service celery-context@notifiche.service celery-context@spedizioni.service
```

Mantenere un solo Beat e un solo worker per ogni contesto. I worker solo
serializzano il loro contesto mentre i quattro processi lavorano in parallelo.
La coda gestionale ha anche un lock Redis condiviso, con lease rinnovata ogni
15 secondi e scadenza 180 secondi, per la protezione nelle transizioni.

Le task import e periodiche prenotano atomicamente l'occorrenza prima della
pubblicazione. Gli alias barcode/giacenze condividono la prenotazione; notifiche
relative a pratiche diverse e campagne distinte non vengono deduplicate per
nome. Errore di pubblicazione libera la prenotazione. Le scadenze broker e di
prenotazione coincidono; senza una scadenza esplicita, la validita' in coda e'
30 minuti dalla pubblicazione (o dall'ETA). Reaper Beat e revoca del consumer
contano una scadenza una sola volta. Le lease inattive indicano crash o perdita
del rinnovo, non una prova esclusiva di crash del processo; non sostituiscono
l'idempotenza delle operazioni applicative.

Il pannello Developer mostra coda, stato operativo, skip queued/running/expired,
percentuale e durate nelle ultime 24 ore, errori e totali cumulativi. Pausa e
task annullate sono separate dai duplicati. La percentuale e' skip / (avvii +
skip registrati nelle 24h); le occorrenze ancora in attesa non sono valutate.
Azzera totali mantiene storico 24h e ultima durata, e non modifica lo scheduler.
Le statistiche sono in Redis, con finestra eventi limitata e contatori cumulativi;
la loro conservazione tra riavvii Redis dipende dalla persistenza del servizio.
