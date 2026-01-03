# LD-Flask-App

LD-Flask-App è una web application basata su Flask progettata per la gestione operativa e l'automazione di processi aziendali.
L'applicazione utilizza task asincroni e pianificati per mantenere i dati sincronizzati con sistemi esterni.

Il progetto è pensato per essere **modulare**, **manutenibile** e **deployabile su server Linux** tramite servizi di sistema.

---

## Stack principale

- Flask (app factory)
- Gunicorn
- Celery
- Redis (broker + backend)
- PostgreSQL

---

## Architettura (overview)

L'applicazione è composta da componenti separati:

- **Web App**  
  Gestisce le richieste HTTP ed espone l'interfaccia tramite Gunicorn.

- **Celery Worker**  
  Esegue i task asincroni (importazioni, elaborazioni, sincronizzazioni).

- **Celery Beat**  
  Pianifica i task periodici.

I componenti comunicano tra loro tramite **Redis**.

---

## Documentazione

Per i dettagli operativi fare riferimento a:

- **Deploy e servizi di sistema**  
  → `deploy.md`

- **Operazioni, monitoraggio e troubleshooting**  
  → `operations.md`

---

## Note

Questo repository **non è monolitico**:  
web app, worker e scheduler sono servizi distinti che devono essere gestiti separatamente.
