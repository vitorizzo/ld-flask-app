# PROJECT_MAP.md — v2.2

## Repository source of truth

Repo:
https://github.com/vitorizzo/ld-flask-app

Branch:
main

Fonte di verità:
ultimo commit del branch main.

---

## 🔗 LETTURA FILE — NUOVA REGOLA OPERATIVA

ChatGPT NON deve più costruire automaticamente i link RAW partendo da LINK_BASE_RAW.

Quando serve leggere un file:

ChatGPT deve fornire il percorso nel formato:

https://raw.githubusercontent.com/vitorizzo/ld-flask-app/main/percorso/file.ext

e chiedere esplicitamente:

"Incollami il link RAW di questo file"

Sarà l’utente a incollare il link completo:

https://raw.githubusercontent.com/...

Senza link RAW diretto → il file NON è leggibile.

È vietato:
- ricostruire link
- assumere contenuti
- usare memoria storica

---

## Architettura generale

- Web app: Flask
- DB: PostgreSQL
- ORM: SQLAlchemy
- Migrazioni: Alembic
- Frontend: Jinja2
- Static:
  - /static/js
  - /static/css
  - /static/images
- Logs: /logs
- Tools backend riusabili: /tools
- Blueprint: /routes
- Form: /forms

---

# MODULO AGENDA / CASSA

## Stato Architetturale

Backend matematico separato dalla UI.

Nuovo modulo:

/tools/cash_math.py

Contiene:
- Funzione calcolo preview fiscale
- Calcolo Q (versabile giornata)
- Calcolo S (saldo versabile progressivo)
- Calcolo IC (incasso calcolato)
- Delta fondo
- Delta quadratura
- Totale POS
- Assegni odierni
- Assegni postdatati

Flag supportati:
*, **, +, x, #, !

Preview attuale:
- Solo DB aziendale
- Flag + e x ignorati
- Vault non ancora integrato

Endpoint attivo:

/cassa/api/day/<date>/preview?view=fiscal

---

## Modelli coinvolti

- CashDay
- CashClosure
- CashClosurePos
- CashSale
- CashSalePayment
- CashExpense
- CashExpensePayment
- CashMove
- PosMove
- PosDevice
- PosCircuit
- CashCustomer

Relazioni stabilizzate:
NO lazy="dynamic" per evitare errori eager loading.

Approccio adottato:
Query pure + logica matematica separata.

---

## Flusso Chiusura (Progettazione attuale)

1. Calcolo live (preview)
2. Simulazione chiusura
3. Inserimento incasso consegnato
4. Verifica delta con tolleranza configurabile
5. Scrittura CashClosure
6. Scrittura CashClosurePos
7. Cambio stato CashDay → closed
8. Apertura giorno successivo con fondo iniziale

---

## Formula ufficiale stabilita

### Contanti fisici
Contanti_fisici =
Σ incassi_cash (*, **)
− Σ spese_cash (*, **)
+ ΔFondo

### Assegni
Assegni_odierni =
Σ method="check" flag='*'

Assegni_postdatati =
Σ method="check" flag='**'

### Versabile giornata (Q)
Q =
Contanti_fisici
+ Assegni_odierni
− Spese_cash

### Saldo versabile progressivo (S)
S =
S_precedente
+ Q
+ Assegni_postdatati

### Incasso calcolato (IC)
IC =
Contanti_fisici
+ Totale_corrispettivi
− Totale_POS_device
− ΔFondo

Delta quadratura:
IC − Incasso_consegnato

---

# TODO AGENDA

- UI Agenda
- Simulazione chiusura
- Integrazione Vault
- Persistenza saldo versabile progressivo
- Tolleranza configurabile

---

# Versione

Versione: 2.2  
Stato: Agenda backend matematico completato (fase DB aziendale)
