# STATUS.md — v1.2
Data aggiornamento: 2026-02-23

---

## 🔄 Stato generale progetto

Applicazione stabile in produzione.
Gunicorn + Nginx funzionanti.
Migrazioni database allineate.
Nessun errore bloccante in avvio applicazione.

---

## 🧾 Modulo Cassa / Agenda — Stato attuale

### ✅ Completato

- Implementata tabella:
  - `cash_deposits`
  - `cash_deposit_checks`

- Collegamento versamenti ↔ assegni tramite tabella ponte.
- Campo `deposit_type`:
  - `versamento_incasso`
  - `versamento_intermedio`

- Endpoint:
  - `/cassa/api/checks/due`
  - `/cassa/api/day/<date>/preview`

- Logica cutoff bancabile:
  - `next_banking_day(ref_date)`
  - `due_date <= cutoff_bancabile`

- KPI calcolati lato backend con:
  - Q (versabile giornata)
  - S (progressivo)
  - IC
  - delta fondo
  - delta quadratura
  - versamenti intermedi e totali

- Agenda.js integrato con:
  - preview giornata
  - elenco assegni versabili
  - auto refresh 30s

- Deploy produzione OK.
- Nessun 502.
- Gunicorn attivo.
- Nginx attivo.

---

## 🧠 Logica Q / S formalizzata

Esempi validati manualmente:

Q = incassi_cash_odierni + assegni_versabili_odierni

S = S_precedente
    - totale_versato_oggi
    + Q_odierno
    + assegni_postdatati_odierni

Totale titolare = contenuto reale cassetto fine giornata.

Distinzione chiara tra:
- incasso_consegnato
- totale_versato_oggi

---

## 🚧 Prossimo Step Operativo

Popolamento dati reali per validazione formule:

1. Inserimento CashDay
2. Inserimento CashCheck
3. Inserimento CashDeposit
4. Simulazione sequenza multi-giorno
5. Verifica coerenza Q / S

---

## ⚠️ Nota Migrazioni

aggRisolto problema constraint duplicato:
- `pos_device_circuits`
- PK coerente con modello

Al momento schema stabile.