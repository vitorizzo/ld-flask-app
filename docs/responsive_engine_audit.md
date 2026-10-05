# Consolidamento responsive — 2026-10-05

## Motore responsive unico per viewport CSS (2026-10-05)

- Le misure reali S25 distinguono sito desktop (viewport 980, scala visuale .367) da mobile (viewport 360, scala visuale 1). Disattivato sito desktop, anche Chrome/PWA mostrano il problema: il vecchio moltiplicatore 2.3 applicato al modello era la causa delle dimensioni gigantesche.
- `static/js/responsive_profile.js`, sincrono prima dei CSS, e' l'unico proprietario della scala: viewport CSS <=360: .92; <=390: 1; <=430: 1.08; <=820: 1.12; oltre: 1. Modalita' mobile per viewport <=820 oppure pointer coarse. Nessuna decisione per user-agent, modello, Client Hints o DPR. Resize aggiorna root/body; zoom visuale e altezza tastiera non aggiungono compensazioni.
- `responsive_profile.css` caricato dopo i CSS pagina definisce il contratto comune di `.ld-page-standard`, `.ld-action-grid`, controlli e modali, oltre alla shell mobile. Rimossi bootstrap duplicato, override alta densita'/bassa risoluzione e dimensioni Home duplicate; Home legacy esclusa dalle classi migrate. Kiosk conserva i propri ingombri shell e il fallback mobile delle modali.
- Diagnostica Developer disponibile e include `mode`; aggiornate cache key degli asset modificati. Le sezioni precedenti sui profili per modello sono storiche e superate da questa policy.
- Verifica: 64 combinazioni viewport/DPR/puntatore con lifecycle e resize; diagnostica copia/refresh/fallback; Edge headless con CSS reali a 320/360/390/412/430/768/980/1440 px, font e dimensioni attese senza overflow orizzontale pagina. A 360 px azione 58.875 px, font 14.72 px, navbar 79.109 px, font modale 16.56 px. Verifica fisica sui quattro telefoni ancora da effettuare dopo deploy manuale.

## Causa e limite delle verifiche

Il DPR 3 misura il rapporto pixel fisici/CSS e non richiede un font tre volte piu' grande. Il report Samsung mostrava font Home 41.4 px, titolo 92 px e azione alta 820.78 px a viewport 360. Il report Chrome desktop spiegava invece i caratteri piccoli: pagina da 980 pixel rimpicciolita sullo schermo da 360. Il successivo riscontro utente ha confermato che Chrome mobile e PWA avevano lo stesso ingrandimento di Samsung Browser.

Il contratto ora usa le fasce standard gia' esistenti, centralizzate in un solo script, senza compensare la modalita' sito desktop. Proporzioni coerenti riguardano i componenti migrati; disposizione e wrapping dipendono dallo spazio disponibile. Le altre pagine mantengono i loro CSS legacy fino alla migrazione.

I test browser usano fixture con i CSS reali e i token standard: verificano la cascata e la geometria, non sostituiscono Safari iOS, Samsung Browser o la PWA sui dispositivi fisici. La diagnostica resta accessibile da Developer > Diagnostica responsive per il confronto dopo deploy. Le misure si copiano localmente e non vengono salvate nei log di produzione.
