# LD-Flask-App — Operations & Troubleshooting

Questo documento descrive le **operazioni quotidiane**, le **procedure di controllo**
e le **azioni di troubleshooting** per la web app **LD-Flask-App**.

È pensato per:
- gestione ordinaria
- debug rapido
- interventi in caso di errore
- supporto tecnico di secondo livello

---

## Servizi coinvolti

L’applicazione è composta da **tre servizi systemd**:

- `ld-flask-app.service` → web app (Gunicorn)
- `celery-worker.service` → esecuzione task asincroni
- `celery-beat.service` → schedulazione task periodici

Dipendenze esterne:
- `redis.service`
- database PostgreSQL

---

## Controllo stato servizi

### Stato rapido
```bash
sudo systemctl status ld-flask-app.service
sudo systemctl status celery-worker.service
sudo systemctl status celery-beat.service
sudo systemctl status redis
```

### Verifica processi attivi
```bash
ps aux | grep gunicorn
ps aux | grep celery
```

---

## Log

### Web App (Gunicorn)
```bash
sudo journalctl -u ld-flask-app.service -n 100 --no-pager
```

### Celery Worker
```bash
sudo journalctl -u celery-worker.service -n 100 --no-pager
```

### Celery Beat
```bash
sudo journalctl -u celery-beat.service -n 100 --no-pager
```

### Log in tempo reale
```bash
sudo journalctl -u celery-worker.service -f
sudo journalctl -u celery-beat.service -f
```

---

## Riavvio servizi

### Riavvio singolo
```bash
sudo systemctl restart ld-flask-app.service
sudo systemctl restart celery-worker.service
sudo systemctl restart celery-beat.service
```

### Riavvio completo stack (ordine consigliato)
```bash
sudo systemctl restart redis
sudo systemctl restart ld-flask-app.service
sudo systemctl restart celery-worker.service
sudo systemctl restart celery-beat.service
```

---

## Debug Celery (manuale)

⚠️ Da usare **solo per debug**, mai in produzione stabile.

### Avvio worker manuale
```bash
cd /home/tecno/ld-flask-app-working
./venv/bin/celery -A celery_worker.celery worker -l debug --pool=solo
```

### Avvio beat manuale
```bash
cd /home/tecno/ld-flask-app-working
./venv/bin/celery -A celery_worker.celery beat -l debug \
  --schedule=/var/lib/celery/beat/celerybeat-schedule \
  --pidfile=/var/lib/celery/beat/celerybeat.pid
```

---

## Celery Beat — Stato schedule

### File di stato
- `/var/lib/celery/beat/celerybeat-schedule`
- `/var/lib/celery/beat/celerybeat.pid`

### Controllo permessi
```bash
ls -l /var/lib/celery/beat
```

### Reset schedule (se necessario)

⚠️ Ricrea lo stato dei task pianificati.

```bash
sudo systemctl stop celery-beat.service
sudo rm /var/lib/celery/beat/celerybeat-schedule*
sudo systemctl start celery-beat.service
```

---

## Problemi comuni

### Celery non esegue task
Possibili cause:
- Redis non attivo
- Worker fermo
- Task non registrati

Verifiche:
```bash
sudo systemctl status redis
sudo systemctl status celery-worker.service
```

### Beat parte ma non pianifica
Possibili cause:
- Worker non attivo
- Schedule corrotto
- Permessi errati su `/var/lib/celery/beat`

### Errore AMQP / porta 5672
Celery sta cercando RabbitMQ invece di Redis.

Verifica che **tutti i servizi** usino:
```text
-A celery_worker.celery
```

### Moduli importati più volte
Messaggi tipo:
```text
MODULO xyz IMPORTATO
```

Normale in presenza di:
- più processi
- reload di worker/beat

Non è un errore se non causa effetti collaterali.

---

## Aggiornamento codice (deploy)

Procedura standard:
```bash
cd /home/tecno/ld-flask-app-working
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart ld-flask-app.service
sudo systemctl restart celery-worker.service
sudo systemctl restart celery-beat.service
```

---

## Regola d’oro

Se qualcosa "sembra fermo":
1. controlla Redis
2. controlla Worker
3. controlla Beat
4. infine la Web App

---

Nota finale:

Celery **non è un servizio unico**:
- Beat pianifica
- Worker esegue
- Redis coordina

Confondere i ruoli porta a debug inutili.
