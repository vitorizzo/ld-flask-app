# STATUS.md

## LD-Flask-App

Aggiornato: 2026-02-18

---

# MODULO AGENDA / CASSA

## Stato attuale

Backend matematico stabile.

- Calcolo Q (versabile giornata) ✔
- Calcolo S (saldo versabile progressivo) ✔
- Calcolo IC ✔
- Delta fondo ✔
- Delta quadratura ✔
- Gestione assegni * e ** ✔
- Totale POS per device/circuit ✔
- Endpoint preview funzionante ✔

Flag + e x:
non ancora integrati nel preview fiscale.

Vault:
non ancora integrato nei calcoli.

---

## Cosa è stato fatto

- Separata logica matematica in /tools/cash_math.py
- Stabilizzato ORM rimuovendo lazy="dynamic"
- Eliminato eager loading
- Endpoint preview stabile
- Formalizzate formule ufficiali

---

## Prossimo step

Costruzione UI Agenda:

- Inserimento incassi
- Inserimento spese
- Riepilogo live
- Modal simulazione chiusura
- Inserimento incasso consegnato
- Evidenziazione delta

---

## Stato generale progetto

- Modulo Slack stabile
- Modulo Trello stabile
- Modulo Import stabile
- Modulo Automations v2 attivo
- Password reset completato
- Agenda in fase UI

---

Stato complessivo:
Struttura backend stabile.
Avvio fase UI Agenda.
