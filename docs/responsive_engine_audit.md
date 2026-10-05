# Audit motore responsive — 2026-10-05

## Evidenze dal codice

- `templates/base.html`: decide il profilo nel bootstrap inline prima dei CSS. `static/js/base.js` ripete la decisione e la raffina con Client Hints. La policy corrente riconosce S25 e A16 per modello e assegna rispettivamente 2.3/.92; gli altri dispositivi restano standard. Il riconoscimento reale sui telefoni non e' stato misurato.
- `static/css/style.css`: definisce componenti nuovi in testa, Home legacy nel blocco mobile (circa 3059), nuove regole responsive da circa 3460, neutralizzazioni specifiche Home da circa 3496, fasce viewport da circa 3530 e override high-density in coda. Le classi nuove non sono ancora un confine completo dalla cascata legacy.
- `static/css/home.css`: ridefinisce padding e min-height della Home dopo `style.css`. Il risultato dipende da specificita' e `!important` oltre che dai token.
- `static/css/responsive_profile.css`: arriva dopo `extra_css` e impone le dimensioni finali a shell/pagine/azioni/controlli/modali soltanto per high-density. Standard e low-resolution non ricevono lo stesso contratto finale.
- `static/css/ld_modal.css`: scala il font mobile, ma padding e min-height mobile restano non moltiplicati; il foglio finale li moltiplica soltanto per high-density. Contiene inoltre fallback DPR <= 2.75 e classe low-resolution che sovrascrivono il font mobile.

## Misure necessarie prima di cambiare il criterio

La Home Developer con `/?responsive_debug=1` legge localmente viewport CSS/layout/visuale, zoom visualViewport, screen/DPR, input, Client Hints, profilo e scale inline/calcolate. Misura navbar/logo/hamburger/footer/pagina/griglia/azione/icona e include i token del tema per distinguere differenze di configurazione da differenze del browser. Il rapporto non viene inviato al server o persistito; la copia e' esplicita. Nessun token, cookie o dato account e' incluso.

Raccogliere nello stesso contesto d'uso (browser/PWA, orientamento verticale, zoom normale) S25, iPhone 16 Plus, Motorola G15 e Android low resolution. L'attuale 3/4 funzionante e' il riferimento dichiarato dall'utente, non una verifica locale sui dispositivi.

## Contratto per il consolidamento successivo

1. Un solo proprietario della scelta della scala; niente blacklist/whitelist per modello come criterio definitivo.
2. Il criterio deriva dalle misure reali: DPR non e' una misura dello spazio CSS disponibile. Non introdurre una nuova soglia ipotetica prima del confronto.
3. Le classi migrate `.ld-page-standard`, `.ld-action-grid` e `.ld-modal` ricevono un contratto comune finale per desktop/touch; font, padding, gap, icone e touch target derivano una sola volta dalla scala.
4. Disposizione, wrapping e scorrimento sono regole strutturali separate dalla scala.
5. Rimuovere/escludere le vecchie dimensioni sui componenti migrati; lasciare funzionante il legacy sulle pagine non migrate. Nessuna migrazione globale delle pagine in questo intervento.
6. Riprodurre le misure raccolte in fixture browser e confrontare tutti i profili, incluse Home, drawer e modali, prima del nuovo deploy.

## Stato

Audit e raccolta misure predisposti. Nessuna modifica al criterio/alle dimensioni in questa fase, per non alterare i tre dispositivi corretti prima di conoscere la differenza effettiva dell'S25. Il consolidamento e la correzione restano da eseguire dopo la raccolta.
