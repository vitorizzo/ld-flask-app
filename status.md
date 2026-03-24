# STATUS.md — v1.4
Data aggiornamento: 2026-03-24

---

## 🔄 Stato generale progetto

Applicazione stabile in produzione.
Gunicorn + Nginx funzionanti.
Migrazioni database allineate.
Nessun errore bloccante in avvio applicazione.

---

## 🧾 Modulo Cassa / Agenda — Stato attuale

### ✅ Completato backend

- Endpoint giornata attivo:
  - `/cassa/api/day`
  - `/cassa/api/day/<date>/preview`
  - `/cassa/api/days/active`

- Endpoint CRUD / lettura attivi per:
  - incassi
  - spese
  - movimenti di cassa
  - POS
  - e-commerce
  - conteggio fondo cassa
  - versamenti
  - assegni versabili
  - saldo spicci

- Calcolo centralizzato in `tools/cash_math.py` aggiornato con:
  - `versabile_giornata`
  - `versabile_residuo`
  - `saldo_versabile`
  - `saldo_attuale`
  - `assegni_in_pancia`
  - `massimo_contanti_incasso`
  - `debito_contanti_incasso`

- Implementata distinzione logica tra:
  - `versamento_incasso`
  - `versamento_intermedio`

- Implementata eliminazione versamenti tramite endpoint:
  - `DELETE /cassa/api/deposits/<deposit_id>`

- L’eliminazione dei versamenti:
  - rimuove correttamente il record dal DB
  - ripristina lo stato assegni collegati quando presenti
  - non è pensata per gestire casi storici complessi come richiamo / ripresentazione, che saranno trattati nella futura gestione assegni

---

## 🖥️ Frontend Agenda — Stato attuale

### ✅ Completato frontend

- Pagina agenda funzionante con:
  - calendario laterale
  - caricamento giornata
  - quadranti:
    - incassi
    - spese
    - movimenti cassa
    - POS
  - KPI in alto
  - modali operative

- Modale conteggio fondo funzionante:
  - caricamento
  - salvataggio
  - eliminazione

- Modale e-commerce funzionante:
  - inserimento
  - eliminazione
  - aggiornamento KPI

- Modale versamenti funzionante:
  - caricamento assegni disponibili
  - caricamento storico versamenti
  - inserimento versamento
  - eliminazione versamento
  - refresh coerente senza hard refresh

### ✅ Logica frontend versamenti

- In modalità `versamento_incasso`:
  - la UI mostra il massimo contanti consigliato basato su `massimo_contanti_incasso`
  - se superato, il campo contanti viene evidenziato in rosso
  - il superamento resta consentito come warning, non come blocco

- In modalità `versamento_intermedio`:
  - la UI mostra il massimo contanti consigliato basato su:
    - `versabile_residuo`
    - meno assegni odierni ancora in pancia
  - se superato, il campo contanti viene evidenziato in rosso
  - la logica è distinta da quella del versamento incasso

- Dopo inserimento o cancellazione versamenti:
  - lista assegni disponibili aggiornata
  - storico versamenti aggiornato
  - KPI aggiornati
  - warning contanti aggiornato

### ✅ KPI

- KPI “Incasso” rinominato concettualmente in **Totale di Giornata**
- Calcolo `incasso_calcolato` corretto:
  - usa `delta_fondo` solo se esistono sia fondo iniziale sia fondo finale
  - in mancanza di dati completi, continua a mostrare un valore indicativo
- Badge stato presenti per:
  - `corrispettivi`
  - `fondo cassa`
- Se i dati non sono completi:
  - badge rossi bordo trasparente
  - valore KPI mostrato come indicativo con stile attenuato

---

## ⚠️ Limiti noti / comportamento voluto

- La gestione eventi assegni è ancora parziale per i vecchi assegni di test creati prima della modellazione completa della storia eventi.
- La cancellazione del versamento è intesa come correzione di un errore di inserimento, non come annullamento logico di eventi bancari reali.
- Richiami, ripresentazioni, insoluti, protesti e casi analoghi saranno gestiti in una fase successiva dedicata alla **storia assegni**.
- I KPI sono ora coerenti dopo refresh applicativo lato frontend; il problema precedente era dovuto a refresh parziale del JS, non al ricalcolo backend.

---

## 🎯 Prossimo obiettivo

Prossimo task: sistemazione del KPI **Quadratura**.

Obiettivi previsti del prossimo task:
- definire con precisione la formula finale della quadratura
- distinguere chiaramente dati certi vs dati indicativi
- verificare il rapporto tra:
  - incasso consegnato
  - incasso calcolato / totale giornata
  - fondo iniziale / finale
  - corrispettivi
- sistemare eventuali badge / stati visivi coerenti con quelli già introdotti nel KPI Totale di Giornata

---