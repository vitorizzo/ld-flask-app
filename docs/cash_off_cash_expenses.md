# Spese fuori cassa nel versabile

Una spesa in contanti aziendale (flag * o **) deve diminuire il versabile anche quando è stata anticipata fuori cassa. Il flag fuori cassa incide esclusivamente sull’uscita fisica dal cassetto.

Esempio verificato in sola lettura il 16/10/2026: la spesa fuori cassa di 86,40 € del 15/10 riduce il versabile giornaliero da 497,35 € a 410,95 €, senza cambiare il cassetto. Nessun dato di produzione è stato modificato.

## Implementazione

- tools/cash_math.py: calculate_closure_pure sottrae spese_fuori_cassa dal versabile, lasciando invariata la formula fisica.
- routes/cassa.py: stessa correzione nel calcolo SQL rapido; il progressivo comprende le spese contanti aziendali indipendentemente da off_cash.
- Il dettaglio versabile include la spesa come voce negativa esplicitamente fuori cassa.
- Snapshot utilizzabili come base: versione almeno 3 e marcatore off_cash_versabile_calculation_version=1 nei totali del payload. Il marcatore distingue la formula dalla revisione progressiva dello snapshot. Senza una base aggiornata il saldo viene aggregato dai movimenti.
- Preview di giornate chiuse e report archiviati non riutilizzano totali con la vecchia formula. Il report ricostruisce la preview senza modificare l’archivio del vault. La normale rigenerazione degli snapshot già stale resta nel flusso applicativo esistente.

## Verifica e attivazione

18 test Python (tests/test_cash_intermediate_deposits.py e tests/test_cash_off_cash_expenses.py) e 8 casi Node di tests/test_cash_report.mjs passati. Confronto dei due calcoli (Python e SQL), dettaglio e progressivo, depositi, centesimi e snapshot inclusi.

Non serve una migrazione. Aggiornare codice e riavviare web. Nessuna correzione manuale ai movimenti o riapertura della giornata richiesta per rivedere la preview corretta.
