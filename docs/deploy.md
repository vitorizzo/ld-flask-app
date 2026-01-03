# LD-Flask-App — Deployment & System Services

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

La web app richiede **tre servizi distinti**, tutti gestiti tramite `systemd`.

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

### Responsabilità
- esegue task asincroni
- consuma task dal broker Redis
- non pianifica task

### Configurazione
- app: `celery_worker.celery`
- broker: Redis
- backend risultati: Redis
- pool: `solo`

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
