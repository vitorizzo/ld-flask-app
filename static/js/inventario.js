let lastFocusedElement = null; // fuori da qualsiasi funzione
let idMovimento = null; // fuori da qualsiasi funzione

document.addEventListener("DOMContentLoaded", () => {
    const selectInventario = document.getElementById("inventario-select");
    const btnNuovoInventario = document.getElementById("nuovo-inventario-btn");
    const contenitoreNuovo = document.getElementById("crea-inventario-container");
    const campoDataInventario = document.getElementById("data-inventario-attiva");
    const campoDepositoInventario = document.getElementById("dep-inventario-attivo");
    const hiddenInventarioId = document.getElementById("inventario-id-attivo");
    const gruppoData = document.getElementById("inventario-data-group");
    const fieldset = document.getElementById("fieldset-inserimento");

    const btnCercaBarcode = document.getElementById("btn-cerca-barcode");

    function abilitaInserimento(data, dep, id) {
        if (campoDataInventario) {
            campoDataInventario.value = data;
        }
        if (campoDepositoInventario) {
            campoDepositoInventario.value = dep;
        }
        console.log("Impostato inventario ID:", id);
        console.log("Impostato data:", data);
        console.log("Impostato dep:", dep);
        if (hiddenInventarioId) {
            hiddenInventarioId.value = id;
        }
        const hiddenDataInv = document.getElementById("data_inventario");
        if (hiddenDataInv) {
            hiddenDataInv.value = data; // non serve lo split, è già yyyy-mm-dd
        }
        const hiddenDep = document.getElementById("deposito");
        if (hiddenDep) {
            hiddenDep.value = dep;
        }
        gruppoData.style.display = "block";
        fieldset.disabled = false;

        caricaUltimiInseriti(id);
        aggiornaTabellaInventariEseguiti();

    }

    document.querySelector("#tabella-movimenti tbody")
      .addEventListener("click", async (e) => {
        const btn = e.target.closest(".btn-storico");
        if (!btn || btn.disabled) return; // ignora se non è un bottone valido

        const idMov = btn.dataset.id;

        // chiamiamo la funzione che carica e apre la modale
        await caricaEApriStorico(idMov);
      });


    document.getElementById("form-inventario").addEventListener("submit", async function (e) {
        e.preventDefault(); // blocca invio tradizionale

/*        if (fieldset.disabled) return;

        const form = e.target;
        const formData = new FormData(form);
        formData.append("submit", "1");

        fetch(form.action, {
            method: "POST",
            body: formData,
            headers: {
                "X-Requested-With": "XMLHttpRequest"
            }
        })
        .then(res => res.text())
        .then(html => {
            flashMessage("Conteggio inventario inserito!", "success");

            // Aggiorna ultimi inseriti
            const inventarioId = document.getElementById("inventario-id-attivo").value;
            caricaUltimiInseriti(inventarioId);
            aggiornaTabellaInventariEseguiti();

            // Pulisci il form
            aggiornaTabellaMovimenti(inventarioId);
            resetCampiArticoloCompleto();
        })
        .catch(err => {
            console.error("Errore durante l'inserimento:", err);
            flashMessage("Errore durante l'inserimento", "danger");
        });
    });*/

        if (fieldset.disabled) return;

        const form = e.target;
        const formData = new FormData(form);
        formData.append("submit", "1");

        try {
            // 🔄 Ottieni un nuovo token CSRF prima di inviare
            const resToken = await fetch("/inventario/get_csrf_token");
            if (!resToken.ok) throw new Error("Impossibile rigenerare CSRF");
            const dataToken = await resToken.json();

            // Aggiorna il token nel form
            formData.set("csrf_token", dataToken.csrf_token);

            // 🔼 Invia il form con il nuovo token
            const res = await fetch(form.action, {
                method: "POST",
                body: formData,
                headers: { "X-Requested-With": "XMLHttpRequest" }
            });

            if (!res.ok) throw new Error("Errore server");
            const data = await res.json(); // ⬅️ risposta JSON dal backend

            // ✅ 3️⃣ Gestione risposta
            if (data.success) {
                flashMessage("✅ Record aggiunto correttamente!", "success");
                const inventarioId = document.getElementById("inventario-id-attivo").value;
                caricaUltimiInseriti(inventarioId);
                aggiornaTabellaInventariEseguiti();
                aggiornaTabellaMovimenti(inventarioId);
                resetCampiArticoloCompleto();
            } else {
                flashMessage("❌ Problemi nell'inserimento: Record non aggiunto!", "danger");

                // Se vuoi, logga anche gli errori del form
                if (data.errors) console.warn("Errori form:", data.errors);
            }

            // 🔁 4️⃣ Rigenera di nuovo il token per la prossima chiamata
            aggiornaCSRFToken();


        } catch (err) {
            console.error("Errore durante l'inserimento:", err);
            flashMessage("Errore durante l'inserimento", "danger");
        }
    });

    selectInventario.addEventListener("change", async () => {
        const optionSelezionata = selectInventario.selectedOptions[0];
        const res = await fetch("/inventario/get_dati_inv", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ inv_id: optionSelezionata.value })
        })
        .then(res => res.json())
        .then(data => {
            if (!data.success) {
                alert("Errore nel recupero dei dati dell'inventario.");
                return;
            }
            const inv = data.inventario;
            if (inv) {
                console.log("Selezionato inventario ID:", inv.id);
                console.log("Data inventario:", inv.data_inventario);
                console.log("Deposito inventario:", inv.deposito);
                abilitaInserimento(inv.data_inventario, inv.deposito, inv.id);
            }
        });
    });


    btnNuovoInventario.addEventListener("click", () => {
        contenitoreNuovo.classList.toggle("d-none"); // mostra/nasconde la sezione
    });


    document.getElementById("crea-inventario-btn").addEventListener("click", () => {
        const data = document.getElementById("data-nuovo-inventario").value;
        const deposito = document.getElementById("dep-nuovo-inventario").value;
        console.log("Creazione nuovo inventario per data:", data, "e deposito:", deposito);
        if (!data) {
            alert("Seleziona una data valida.");
            return;
        }

        fetch("/inventario/crea", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ data_inventario: data, deposito: deposito})
        })
        .then(res => res.json())
        .then(data => {
            if (!data.success) {
                alert("Errore nella creazione dell'inventario.");
                return;
            }

            const option = document.createElement("option");
            option.value = data.id;
            option.dataset.data = data.data;
            option.dataset.deposito = data.deposito;
            option.dataset.export_inventario = data.export_inventario;
            option.dataset.fix_movements = data.fix_movements;
            option.selected = true;
            option.textContent = `Inventario del ${data.data} - deposito ${data.deposito}`;

            const firstOption = selectInventario.querySelector("option[value='']");
            if (firstOption) firstOption.remove();

            const esisteGia = [...selectInventario.options].some(o => o.value == data.id);
            if (!esisteGia) {
                selectInventario.appendChild(option);
            } else {
                option.remove();
            }

            abilitaInserimento(data.data, data.deposito, data.id);

            if (data.gia_esiste) {
                flashMessage("Inventario già esistente per la data selezionata. Riutilizzato.", "info");
            } else {
                flashMessage("Nuovo inventario creato con successo!", "success");
            }

            contenitoreNuovo.classList.add("d-none"); // nasconde la sezione
        })
        .catch(err => {
            console.error("Errore nella creazione dell'inventario:", err);
            alert("Si è verificato un errore durante la creazione del nuovo inventario.");
        });
    });


    btnCercaBarcode.addEventListener('click', () => {
        const barcode = document.getElementById('barcode').value.trim();
        if (!barcode) {
            alert("Inserisci un codice a barre.");
            return;
        }

        fetch(`/search/articoli_by_barcode_multipli?barcode=${encodeURIComponent(barcode)}`)
            .then(res => res.json())
            .then(data => {
                if (!data.success) {
                    alert(data.error || "Articolo non trovato per il barcode inserito.");
                    return;
                }

                // ✅ Se il backend dice che è un singolo articolo, popola subito
                if (data.singolo === true && data.articolo) {
                    const a = data.articolo;
                    popolaCampiArticolo({
                        cod_art: a.cod_art,
                        descrizione: `${a.descrizione} ${a.descrizione_aggiuntiva}`,
                        cpp: a.cpp,
                        ppc: a.ppc
                    });
                    return;
                }

                // ✅ Se c'è una lista di articoli (più annate), mostra modale
                if (Array.isArray(data.articoli) && data.articoli.length > 0) {
                    const elencoConvertito = data.articoli.map(a => ({
                        cod_art: a.cod_art,
                        descrizione: `${a.descrizione} ${a.descrizione_aggiuntiva}`,
                        cpp: a.cpp,
                        ppc: a.ppc
                    }));
                    mostraScelteArticoli(elencoConvertito);
                    return;
                }

                alert("Nessun articolo disponibile.");
            })
            .catch(err => {
                console.error("Errore durante la ricerca barcode:", err);
                alert("Errore nella ricerca dell'articolo tramite codice a barre.");
            });
    });


    document.getElementById("barcode").addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
            e.preventDefault();
            document.getElementById("btn-cerca-barcode").click();
        }
    });

    document.getElementById("cod_art").addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
            e.preventDefault();
            document.getElementById("btn-cerca-articolo").click();
        }
    });

    // Hook per attivare funzionalità non legate al fieldset
    const observer = new MutationObserver(() => {
        if (!fieldset.disabled) {
            abilitaPulsanti();
        }
    });
    observer.observe(fieldset, { attributes: true, attributeFilter: ['disabled'] });

    // Inizializza scanner
    initScanner("scan-button", "barcode", (decodedText) => {
        document.getElementById("btn-cerca-barcode").click();
    });


    // Inizializza ricerca per descrizione
    if (typeof initSearchByDescription === "function") {
        initSearchByDescription({
            inputId: 'inv-search-input',
            showAllCheckboxId: 'inv-search-show-all',
            listId: 'inv-search-list',
            wrapperId: 'inv-search-wrapper',
            pagination: {
                prevId: 'inv-search-prev',
                nextId: 'inv-search-next',
                infoId: 'inv-search-pageinfo',
                containerId: 'inv-search-pagination'
            },
            modalIframeId: 'product-modal-iframe',
            modalTriggerId: 'product-modal',
            showButton: true,
            onSelect: function(articolo) {
                // Codice a barre
                fetch(`/search/barcode_by_codart/${articolo.cod_art}`)
                    .then(res => res.json())
                    .then(barcodeData => {
                        document.getElementById("barcode").value = barcodeData.barcode || "";
                    });

                // Popola i campi e richiama la funzione centralizzata
                popolaCampiArticolo({
                    cod_art: articolo.cod_art,
                    descrizione: `${articolo.descrizione} ${articolo.descrizione_aggiuntiva}`,
                    cpp: articolo.cpp || 1,
                    ppc: articolo.ppc || 1
                });
            }
        });
    }

    // Matitine per modificare cpp/ppc
    ['cpp', 'ppc'].forEach(id => {
        const span = document.getElementById(id);
        const icon = span.nextElementSibling;

        [span, icon].forEach(el => {
            el.addEventListener("click", () => {
                if (fieldset.disabled) return;
                const nuovo = prompt(`Inserisci nuovo valore per ${id.toUpperCase()}:`, span.textContent);
                if (nuovo !== null && !isNaN(nuovo)) {
                    span.textContent = parseInt(nuovo);
                    document.getElementById(`hidden_${id}`).value = parseInt(nuovo);
                }
            });
        });
    });

    // Calcolo formula quantità
    calcolaBtn.addEventListener("click", function (e) {
        e.preventDefault();
        if (fieldset.disabled) return;

        const cpp = parseInt(document.getElementById("hidden_cpp").value || 1);
        const ppc = parseInt(document.getElementById("hidden_ppc").value || 1);
        const np = parseInt(document.getElementById("num_pedane").value || 0);
        const ct = parseInt(document.getElementById("num_cartoni").value || 0);
        const ps = parseInt(document.getElementById("num_pezzi_sciolti").value || 0);
        const totale = ps + ((np * cpp + ct) * ppc);

        document.getElementById("quantita_inserita").value = totale;
    });

    // Cerca per codice articolo
    btnCercaArticolo.addEventListener('click', () => {
        const cod_art = document.getElementById('cod_art').value.trim();
        if (!cod_art) {
            alert("Inserisci un codice articolo.");
            return;
        }

        fetch(`/search/dati_articolo/${cod_art}`)
            .then(response => response.json())
            .then(data => {
                if (!data.success) {
                    alert("Articolo non trovato");
                    return;
                }

                // Codice a barre
                fetch(`/search/barcode_by_codart/${data.cod_art}`)
                    .then(res => res.json())
                    .then(barcodeData => {
                        document.getElementById("barcode").value = barcodeData.barcode || "";
                    });

                // Popola dati
                document.getElementById("cod_art").value = data.cod_art;
                document.getElementById("hidden_cpp").value = data.cpp || 1;
                document.getElementById("hidden_ppc").value = data.ppc || 1;
                document.getElementById("cpp").textContent = data.cpp || 1;
                document.getElementById("ppc").textContent = data.ppc || 1;

                // Forza visibilità blocchi se presenti
                document.getElementById("fieldset-inserimento").disabled = false;
                abilitaPulsanti();
            })
            .catch(err => {
                console.error("Errore durante il recupero dell'articolo:", err);
                alert("Errore nella ricerca dell'articolo.");
            });
    });

    document.getElementById("pulisci-form").addEventListener("click", () => {
        aggiornaTabellaMovimenti(inventarioId);
        resetCampiArticoloCompleto();
    });


    // Se è già selezionato un inventario all'avvio, attivalo
    const selected = selectInventario.selectedOptions[0];
    if (selected && selected.value) {
        abilitaInserimento(selected.dataset.data, selected.dep, selected.value);
    }

    if (window.location.search.includes("inv_id=")) {
        // Reset dei campi articolo
        document.getElementById("barcode").value = "";
        document.getElementById("cod_art").value = "";
        document.getElementById("quantita_inserita").value = 0;
        document.getElementById("num_pedane").value = 0;
        document.getElementById("num_cartoni").value = 0;
        document.getElementById("num_pezzi_sciolti").value = 0;

        // Ripristina valori predefiniti per cpp/ppc
        document.getElementById("hidden_cpp").value = 1;
        document.getElementById("hidden_ppc").value = 1;
        document.getElementById("cpp").textContent = 1;
        document.getElementById("ppc").textContent = 1;

        // Svuota la ricerca descrizione
        document.getElementById("inv-search-input").value = "";
        document.getElementById("inv-search-list").innerHTML = "";
        document.getElementById("inv-search-wrapper").style.display = "none";
        document.getElementById("inv-search-pagination").style.display = "none";
    }

});

// Riabilita i pulsanti disabilitati via JS
function abilitaPulsanti() {
    scanBtn.disabled = false;
    btnCercaArticolo.disabled = false;
    calcolaBtn.disabled = false;
    matitine.forEach(el => el.classList.remove("disabled"));
}

async function caricaEApriStorico(idMov) {
  try {
    const res = await fetch(`/inventario/versioni/${idMov}`);
    if (!res.ok) throw new Error("Errore nella chiamata backend");
    const risultato = await res.json();
    const storico = risultato.righe;

    const tbody = document.querySelector("#tbody-storico-modifiche");
    tbody.innerHTML = "";

    for (const s of storico) {
      // recupera username
      const username = await usernameById(s.utente_id);
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${s.timestamp}</td>
        <td>${username}</td>
        <td class="text-end">${s.quantita_inserita}</td>
        <td class="text-end">${s.num_pedane || ''}</td>
        <td class="text-end">${s.cpp || ''}</td>
        <td class="text-end">${s.num_cartoni || ''}</td>
        <td class="text-end">${s.ppc || ''}</td>
        <td class="text-end">${s.num_pezzi_sciolti || ''}</td>
      `;
      tbody.appendChild(tr);
    };

    // Mostra la modale Bootstrap
    const modal = new bootstrap.Modal(document.getElementById("modaleStoricoModifiche"));
    const articolo = await articolo_by_idmov(idMov);
    if (articolo) {
      document.getElementById("modaleStoricoModificheLabel").textContent = `Storico modifiche - ${articolo.descrizione}`;
    }
    modal.show();

  } catch (err) {
    console.error("Errore nel caricamento storico:", err);
    alert("Impossibile caricare lo storico delle modifiche.");
  }
}

async function articolo_by_idmov(idMov) {
  try {
    const res = await fetch(`/inventario/articolo_by_idMov/${idMov}`);
    console.info("Risposta fetch:", res);
    if (res.ok) {
      const movimento = await res.json();
      console.info("articolo:", movimento);
      return movimento;
    }
  } catch (err) {
    console.error("Errore nel caricamento del movimento:", err);
    alert("Impossibile caricare il movimento specificato.");
  }
  return null; // <--- fallback
}


async function usernameById(id) {
  try {
    const res = await fetch(`/inventario/username_by_id/${id}`);
    if (res.ok) {
      const userData = await res.json();
      return userData.username || "";
    }
  } catch (err) {
    console.warn("Errore fetch username:", err);
  }
  return "";
}

const scanBtn = document.getElementById("scan-button");
const btnCercaArticolo = document.getElementById("btn-cerca-articolo");
const matitine = document.querySelectorAll(".editable, .editable + i");
const calcolaBtn = document.getElementById("calcola-formula");

function popolaCampiArticolo(articolo) {
        console.log("Articolo selezionato dalla modale:", articolo);
        const hiddenInventarioId = document.getElementById("inventario-id-attivo");
        document.getElementById("cod_art").value = articolo.cod_art;
        document.getElementById("hidden_cpp").value = articolo.cpp || 1;
        document.getElementById("hidden_ppc").value = articolo.ppc || 1;
        document.getElementById("cpp").textContent = articolo.cpp || 1;
        document.getElementById("ppc").textContent = articolo.ppc || 1;
        document.getElementById("inv-search-input").value = articolo.descrizione || "";
        document.getElementById("fieldset-inserimento").disabled = false;
        abilitaPulsanti();

        const triggerEvent = new Event("input", { bubbles: true });
        document.getElementById("inv-search-input").dispatchEvent(triggerEvent);

        setTimeout(() => {
            const item = [...document.querySelectorAll(".prodotto-item")]
                .find(el => el.dataset.cod_art === articolo.cod_art);
            if (item) {
                item.classList.add("active");
                item.scrollIntoView({ behavior: "smooth", block: "center" });
            }
        }, 500);

        fetch(`/search/immagine_articolo/${articolo.cod_art}`)
            .then(res => res.json())
            .then(data => {
                creaCaroselloImmagini(data.img_urls);
            });

        fetch(`/search/riepilogo_varianti/${articolo.cod_art}?inventario_id=${hiddenInventarioId.value}`)
            .then(res => res.json())
            .then(data => {
                const wrapper = document.getElementById("riepilogo-articolo-wrapper");
                const tbody = document.querySelector("#riepilogo-articolo-table tbody");
                tbody.innerHTML = "";

                data.varianti.forEach(row => {
                    const tr = document.createElement("tr");
                    tr.innerHTML = `
                        <td>${row.cod_art}</td>
                        <td class="text-end">${row.giacenza}</td>
                        <td class="text-end">${row.rilevata}</td>
                        <td class="text-end fw-bold ${row.differenza !== 0 ? 'text-danger' : 'text-success'}">
                            ${row.differenza}
                        </td>
                    `;
                    tbody.appendChild(tr);
                });

                wrapper.style.display = "block";
            })
            .catch(err => {
                console.warn("Errore nel caricamento riepilogo varianti:", err);
            });


    }

    btnCercaArticolo.addEventListener('click', () => {
        const cod_art = document.getElementById('cod_art').value.trim();
        if (!cod_art) {
            alert("Inserisci un codice articolo.");
            return;
        }

        fetch(`/search/dati_articolo/${cod_art}`)
            .then(response => response.json())
            .then(data => {
                if (!data.success) {
                    alert("Articolo non trovato");
                    return;
                }

                // Codice a barre
                fetch(`/search/barcode_by_codart/${data.cod_art}`)
                    .then(res => res.json())
                    .then(barcodeData => {
                        document.getElementById("barcode").value = barcodeData.barcode || "";
                    });

                const articolo = {
                    cod_art: data.cod_art,
                    descrizione: data.descrizione,
                    descrizione_aggiuntiva: data.descrizione_aggiuntiva,
                    cpp: data.cpp || 1,
                    ppc: data.ppc || 1
                };

                popolaCampiArticolo(articolo);  // usa la funzione centralizzata

                // Lancia la ricerca per selezionare l'articolo in elenco
                if (typeof initSearchByDescription === "function") {
                    const triggerEvent = new Event("input", { bubbles: true });
                    document.getElementById("inv-search-input").dispatchEvent(triggerEvent);

                    let tentativi = 0;
                    const maxTentativi = 3;
                    const attesa = 300;

                    function evidenziaArticolo() {
                        const item = [...document.querySelectorAll(".prodotto-item")]
                            .find(el => el.dataset.cod_art === data.cod_art);

                        if (item) {
                            item.classList.add("active");
                            item.scrollIntoView({ behavior: "smooth", block: "center" });
                        } else if (tentativi < maxTentativi) {
                            tentativi++;
                            setTimeout(evidenziaArticolo, attesa * tentativi);
                        }
                    }

                    setTimeout(evidenziaArticolo, attesa);
                }
            })
            .catch(err => {
                console.error("Errore durante il recupero dell'articolo:", err);
                alert("Errore nella ricerca dell'articolo.");
            });
    });


function flashMessage(messaggio, tipo = "info") {
    const div = document.createElement("div");
    div.className = `alert alert-${tipo}`;
    div.textContent = messaggio;
    document.body.prepend(div);
    setTimeout(() => div.remove(), 4000);
}


function mostraScelteArticoli(lista) {
    const listaElement = document.getElementById("lista-articoli-annate");
    listaElement.innerHTML = '';

    lista.forEach(art => {
        const li = document.createElement("li");
        li.className = "list-group-item list-group-item-action";
        li.textContent = `${art.cod_art} — ${art.descrizione}`;
        li.style.cursor = "pointer";
        li.addEventListener("click", () => {
            console.log("Articolo selezionato dalla modale:", art);
            const modal = bootstrap.Modal.getInstance(document.getElementById('annate-modal'));
            modal.hide();
            popolaCampiArticolo(art);
        });
        listaElement.appendChild(li);
    });

    const modal = new bootstrap.Modal(document.getElementById('annate-modal'));
    modal.show();
}

function caricaUltimiInseriti(inventarioId) {
    fetch(`/inventario/ultimi_inseriti/${inventarioId}`)
        .then(res => res.json())
        .then(data => {
            const wrapper = document.getElementById("ultimi-inseriti-wrapper");
            const tbody = document.getElementById("ultimi-inseriti-body");

            if (!data.success || !data.righe.length) {
                wrapper.style.display = "none";
                tbody.innerHTML = "";
                return;
            }

            tbody.innerHTML = "";
            data.righe.forEach(riga => {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td>${riga.cod_art}</td>
                    <td>${riga.descrizione}</td>
                    <td class="text-end">${riga.quantita}</td>
                `;
                tbody.appendChild(tr);
            });

            wrapper.style.display = "block";
        })
        .catch(err => {
            console.warn("Errore nel caricamento degli ultimi articoli inseriti:", err);
        });
}

function resetCampiArticoloCompleto() {
    document.getElementById("barcode").value = "";
    document.getElementById("cod_art").value = "";
    //document.getElementById("descrizione_articolo").value = "";

    document.getElementById("quantita_inserita").value = 0;
    document.getElementById("num_pedane").value = 0;
    document.getElementById("num_cartoni").value = 0;
    document.getElementById("num_pezzi_sciolti").value = 0;

    document.getElementById("hidden_cpp").value = 1;
    document.getElementById("hidden_ppc").value = 1;

    const cppSpan = document.getElementById("cpp");
    const ppcSpan = document.getElementById("ppc");
    if (cppSpan) cppSpan.textContent = 1;
    if (ppcSpan) ppcSpan.textContent = 1;

    document.getElementById("inv-search-input").value = "";
    document.getElementById("inv-search-list").innerHTML = "";
    document.getElementById("inv-search-wrapper").style.display = "none";
    document.getElementById("inv-search-pagination").style.display = "none";

    const contenitoreImmagini = document.getElementById("contenitore-immagini-articolo");
    if (contenitoreImmagini) contenitoreImmagini.innerHTML = "";

    const wrapperVarianti = document.getElementById("riepilogo-articolo-wrapper");
    if (wrapperVarianti) wrapperVarianti.style.display = "none";

    const flashEl = document.querySelector(".flash-message");
    if (flashEl) flashEl.remove();
}


function aggiornaTabellaMovimenti(inventarioId) {
    if (!inventarioId) {
        console.warn("aggiornaTabellaMovimenti: ID non definito, chiamata ignorata.");
        return;
    }

    fetch(`/inventario/righe/${inventarioId}`)
        .then(res => res.json())
        .then(data => {
            const tbody = document.querySelector("#tabella-movimenti tbody");
            tbody.innerHTML = "";

            if (!data.success) return;

            // Prepara un array di Promise per attendere il completamento di tutti i fetch
            const righePromises = data.righe.map(async (r) => {
                const tr = document.createElement("tr");
                try {
                    const res = await fetch(`/inventario/username_by_id/${r.utente_id}`);
                    const userData = await res.json();
                    const utente = userData.username || "";

                    const storicoBtnHtml = `
                      <button
                        class="btn btn-sm btn-outline-primary btn-storico"
                        data-id="${r.id}"
                        ${r.has_versions ? "" : "disabled"}
                        title="${r.has_versions ? "Vedi storico modifiche" : "Nessuno storico disponibile"}"
                      >
                        <i class="bi bi-search"></i>
                      </button>
                    `;

                    tr.innerHTML = `
                        <td>${r.cod_art}</td>
                        <td>${r.descrizione || ''}</td>
                        <td class="text-end">${r.quantita}</td>
                        <td class="text-end">${r.barcode || ''}</td>
                        <td class="text-end">${utente}</td>
                        <td class="text-center">${storicoBtnHtml}</td>
                        <td class="text-end">
                            <button class="btn btn-sm btn-info btn-modifica-movimento me-1" data-id_mov="${r.id}">Modifica</button>
                            <button class="btn btn-sm btn-danger btn-elimina-movimento" data-id_mov="${r.id}">Elimina</button>
                        </td>
                    `;

                    tbody.appendChild(tr);
                } catch (err) {
                    console.error(`Errore nel recupero utente per movimento ID ${r.id}:`, err);
                }
            });

            // Dopo che tutte le righe sono state create e inserite
            Promise.all(righePromises).then(() => {
                // Ora possiamo associare correttamente gli event listener
                document.querySelectorAll(".btn-modifica-movimento").forEach(btn => {
                    btn.addEventListener("click", e => {
                        const idMov = btn.dataset.id_mov;
                        const inventarioId = document.getElementById("modaleDettaglioInventario").dataset.inventarioId;

                        fetch(`/inventario/dati_movimento/${inventarioId}/${idMov}`)
                            .then(res => res.json())
                            .then(data => {
                                if (data.success) {
                                    const modal = bootstrap.Modal.getOrCreateInstance(document.getElementById('modaleModificaMovimentoArticolo'));
                                    const mov = data.dati_movimento;

                                    modal.show();

                                    const btnCalcola = document.getElementById("modCalcolaFormula");
                                    const btnCalcolaQuantita = document.getElementById("fcqCalcolaQuantita");
                                    btnCalcola.dataset.id_mov = idMov;
                                    btnCalcola.dataset.inventario_id = inventarioId;
                                    btnCalcolaQuantita.addEventListener("click", e => {
                                        e.preventDefault();
                                        const formCalc = document.getElementById("formCalcoloQuantita");
                                        const numPedane = parseInt(document.getElementById("fcqNumPedane").value) || 0;
                                        const cpp = parseInt(document.getElementById("fcqCPP").textContent) || 1;
                                        const numCartoni = parseInt(document.getElementById("fcqNumCartoni").value) || 0;
                                        const ppc = parseInt(document.getElementById("fcqPPC").textContent) || 1;
                                        const numPezziSciolti = parseInt(document.getElementById("fcqNumPezziSciolti").value) || 0;

                                        const quantitaInserita = (numPedane * cpp * ppc) + (numCartoni * ppc) + numPezziSciolti;
                                        document.getElementById("modQuantitaInserita").value = quantitaInserita;
                                    })
                                    btnCalcola.addEventListener("click", e => {
                                        const formCalc = document.getElementById("formCalcoloQuantita");
                                        formCalc.classList.toggle("d-none");
                                    });
                                    if (mov.num_pedane || mov.num_cartoni || mov.num_pezzi_sciolti) {
                                        const formula = `Quantità inserita (${mov.num_pedane} pedane da ${mov.cpp} cartoni + ${mov.num_cartoni} cartoni da ${mov.ppc} pezzi + ${mov.num_pezzi_sciolti} pezzi sciolti)`;
                                        document.getElementById("modQuantitaInseritaLabel").textContent = formula;
                                        document.getElementById("fcqNumPedane").value = mov.num_pedane || 0;
                                        document.getElementById("fcqCPP").textContent = mov.cpp || 1;
                                        document.getElementById("fcqNumCartoni").value = mov.num_cartoni || 0;
                                        document.getElementById("fcqPPC").textContent = mov.ppc || 1;
                                        document.getElementById("fcqNumPezziSciolti").value = mov.num_pezzi_sciolti || 0;
                                        // Matitine per modificare cpp/ppc
                                        ['fcqCPP', 'fcqPPC'].forEach(id => {
                                            const span = document.getElementById(id);
                                            const icon = span.nextElementSibling;

                                            [span, icon].forEach(el => {
                                                el.addEventListener("click", () => {
                                                    const nuovo = prompt(`Inserisci nuovo valore per ${id.toUpperCase()}:`, span.textContent);
                                                    if (nuovo !== null && !isNaN(nuovo)) {
                                                        span.textContent = parseInt(nuovo);
                                                        document.getElementById(`hidden_${id}`).value = parseInt(nuovo);
                                                    }
                                                });
                                            });
                                        });
                                    } else {
                                        document.getElementById("modQuantitaInseritaLabel").textContent = "Quantità inserita";
                                    }

                                    document.getElementById("modQuantitaInserita").value = mov.quantita_inserita;
                                    document.getElementById("modCodiceArticolo").value = mov.cod_art;
                                    document.getElementById("modDescrizioneArticolo").value = mov.descrizione || '';
                                } else {
                                    alert("Errore nel recupero dei dati del movimento.");
                                }
                            })
                            .catch(err => console.error("Errore:", err));
                    });
                });

                document.querySelectorAll(".btn-elimina-movimento").forEach(btn => {
                    btn.addEventListener("click", e => {
                        const idMov = btn.dataset.id_mov;
                        const inventarioId = document.getElementById("modaleDettaglioInventario").dataset.inventarioId;

                        if (confirm(`Vuoi eliminare il movimento selezionato?`)) {
                            fetch(`/inventario/elimina_movimento/${inventarioId}/${idMov}`, {
                                method: "DELETE"
                            })
                                .then(res => res.json())
                                .then(data => {
                                    if (data.success) {
                                        aggiornaTabellaInventarioAggregato(inventarioId);
                                        aggiornaTabellaMovimenti(inventarioId);
                                    } else {
                                        alert("Errore nell'eliminazione del movimento.");
                                    }
                                })
                                .catch(err => console.error("Errore:", err));
                        }
                    });
                });
            });

        })
        .catch(err => {
            console.error("Errore nel caricamento righe movimenti:", err);
        });
}



function aggiornaTabellaInventariEseguiti() {
    fetch("/inventario/lista_inventari")
        .then(res => res.json())
        .then(data => {
            const tbody = document.querySelector("#tabella-inventari-eseguiti tbody");
            tbody.innerHTML = "";

            data.inventari.forEach(inv => {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td>${inv.id}</td>
                    <td>${inv.data}</td>
                    <td>${inv.deposito}</td>
                    <td class="text-end">${inv.num_righe}</td>
                    <td class="text-center">${inv.export_inventario ? '<i class="bi bi-check-lg text-success" title="Esportato"></i>' : '<i class="bi bi-x-lg text-danger" title="Non esportato"></i>'}</td>
                    <td class="text-center">${inv.fix_movements ? '<i class="bi bi-check-lg text-success" title="Corretto"></i>' : '<i class="bi bi-x-lg text-danger" title="Non corretto"></i>'}</td>
                    <td>
                        <button class="btn btn-sm btn-warning btn-modifica me-1" data-id="${inv.id}" data-data="${inv.data}">Modifica</button>
                        <button class="btn btn-sm btn-danger btn-elimina" data-id="${inv.id}">Elimina</button>
                        <button class="btn btn-sm btn-info btn-importa" data-id="${inv.id}">Importa</button>
                        <button class="btn btn-sm btn-info btn-rettifica" data-id="${inv.id}">Rettifica</button>
                        <button class="btn btn-sm btn-info btn-esporta-rettifiche" data-id="${inv.id}">Esporta</button>
                    </td>
                `;

                tr.style.cursor = "pointer";
                tr.addEventListener("mouseenter", () => tr.classList.add("table-active"));
                tr.addEventListener("mouseleave", () => tr.classList.remove("table-active"));

                // Aggiungi evento per mostrare la modale (clic su riga)
                tr.addEventListener("click", (e) => {
                    // Ignora se è stato cliccato un pulsante
                    if (e.target.closest("button")) return;

                    const modale = document.getElementById("modaleDettaglioInventario");
                    modale.dataset.inventarioId = inv.id;

                    document.getElementById("modaleTitoloInventario").textContent = `Inventario #${inv.id}`;
                    document.getElementById("filtro-visualizza").value = "movimenti";
                    document.getElementById("tabella-movimenti").classList.remove("d-none");
                    document.getElementById("tabella-inventario-aggregato").classList.add("d-none");

                    aggiornaTabellaMovimenti(inv.id);

                    const bsModal = new bootstrap.Modal(modale);
                    bsModal.show();
                });

                tbody.appendChild(tr);
            });

            // 🔁 Aggiunta EventListener ai pulsanti dopo che le righe sono state aggiunte
            document.querySelectorAll(".btn-modifica").forEach(btn => {
                btn.addEventListener("click", (e) => {
                    e.stopPropagation(); // ✅ evita di aprire la modale dettaglio
                    const id = btn.dataset.id;
                    const data = btn.dataset.data;
                    apriModaleModificaData(id, data);
                });
            });

            document.querySelectorAll(".btn-elimina").forEach(btn => {
                btn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    const id = btn.dataset.id;

                    if (confirm(`Sei sicuro di voler eliminare l'inventario #${id}?. Questo comporterà la cancellazione di tutte le righe associate, Procedere?`)) {
                        fetch(`/inventario/elimina/${id}`, {
                            method: "DELETE"
                        })
                        .then(res => res.json())
                        .then(data => {
                            if (data.success) {
                                aggiornaTabellaInventariEseguiti();
                            } else {
                                alert("Errore nell'eliminazione.");
                            }
                        })
                        .catch(err => {
                            console.error("Errore durante l'eliminazione:", err);
                        });
                    }
                });
            });

            document.querySelectorAll(".btn-esporta-rettifiche").forEach(btn => {
                btn.addEventListener("click", async(e) => {
                    e.stopPropagation();
                    const id = btn.dataset.id;

                    if (confirm(`Procedo con l'esportazione delle rettifiche dell'inventario #${id}?`))
                    if (!confirm) return;
                    const response = await fetch(`/inventario/esporta_rettifiche`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ inventario_id: id })
                    });
                    if (!response.ok) {
                        alert("Errore nell'esportazione delle rettifiche.");
                        return;
                    }
                    alert("Esportazione completata!");
                });
            });

            const inputFile = document.getElementById("file-import");
            document.querySelectorAll(".btn-importa").forEach(btn => {
                btn.addEventListener("click", async(e) => {
                    e.stopPropagation();
                    const id = btn.dataset.id;

                    // 1️⃣ Check preliminare sul server
                    const checkResponse = await fetch("/inventario/check_import_esistente", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ inventario_id: id })
                    });

                    const checkData = await checkResponse.json();

                    // 2️⃣ Se esistono già dati, chiedi conferma
                    if (checkData.exists) {
                        const conferma = confirm("Esistono già dati per questo inventario.\nVuoi sovrascriverli?");
                        if (!conferma) return;
                        const response= await fetch("/inventario/pulisci_importazione", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ inventario_id: id })
                        });
                        if (!response.ok) {
                            alert("Errore nel pulire i dati esistenti.");
                        }
                        const clear_ei= await fetch("/inventario/clear_import", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ inventario_id: id })
                        });
                        if (!clear_ei) {
                            alert("Errore nel reset del flag export_inventario esistente.");
                            return
                        }
                    }

                    // 2️⃣ Recupera lista file dal server
                    const filesResponse = await fetch("/exported/lista_export");
                    const data = await filesResponse.json();

                    console.log("Files ricevuti:", data); // 👈 DEBUG

                    if (data.error) {
                        alert("Errore: " + data.error);
                        return;
                    }

                    // 3️⃣ Popola tabella nella modale
                    const tbody = document.querySelector("#tabella-file-export tbody");
                    tbody.innerHTML = "";
                    let selectedFile = null;

                    data.files.forEach(file => {
                        const tr = document.createElement("tr");
                        tr.innerHTML = `
                            <td>${file.name}</td>
                            <td class="text-end">${file.size} KB</td>
                            <td class="text-end">${file.mtime}</td>
                        `;
                        tr.addEventListener("click", () => {
                            tbody.querySelectorAll("tr").forEach(row => row.classList.remove("table-active"));
                            tr.classList.add("table-active");
                            selectedFile = file.name;
                            document.querySelector("#btnConfermaFile").disabled = false;
                        });
                        tbody.appendChild(tr);
                    });

                    // 4️⃣ Mostra modale
                    const modal = new bootstrap.Modal(document.getElementById("modalSelezioneFile"));
                    modal.show();

                    // 5️⃣ Conferma scelta
                    document.querySelector("#btnConfermaFile").onclick = async () => {
                        if (!selectedFile) return;

                        console.log("DEBUG – invio a backend:", { inventario_id: id, filename: selectedFile });

                        const importaRes = await fetch("/inventario/importa_inventario", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ inventario_id: id, filename: selectedFile })
                        });

                        console.log("Risposta importazione:", importaRes);

                        const result = await importaRes.json();
                        if (result.success) {
                            modal.hide();
                            alert("Importazione completata!");
                            const set_ei= await fetch("/inventario/set_import", {
                                method: "POST",
                                headers: { "Content-Type": "application/json" },
                                body: JSON.stringify({ inventario_id: id })
                            });
                            if (!set_ei.ok) {
                                alert("Errore nel reset del flag rettifiche esistenti.");
                                return
                            }
                            aggiornaTabellaInventariEseguiti(); // tua funzione per aggiornare la tabella
                        } else {
                            alert("Errore durante l'importazione: " + (result.error || "sconosciuto"));
                        }
                    };
                });
            });

            document.querySelectorAll(".btn-rettifica").forEach(btn => {
                btn.addEventListener("click", async(e) => {
                    e.stopPropagation();
                    const id = btn.dataset.id;

                    // 1️⃣ Check preliminare sul server
                    const checkResponse = await fetch("/inventario/check_fix_esistente", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ inventario_id: id })
                    });

                    const checkData = await checkResponse.json();

                    // 2️⃣ Se esistono già dati, chiedi conferma
                    if (checkData.exists) {
                        const conferma = confirm("Esistono già movimenti di rettifica per questo inventario.\nVuoi sovrascriverli?");
                        if (!conferma) return;
                        const response= await fetch("/inventario/pulisci_fix", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ inventario_id: id })
                        });
                        if (!response.ok) {
                            alert("Errore nel pulire le rettifiche esistenti.");
                            return
                        }
                        const clear_fm= await fetch("/inventario/clear_rettifica", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ inventario_id: id })
                        });
                        if (!clear_fm.ok) {
                            alert("Errore nel reset del flag rettifiche esistenti.");
                            return
                        }
                    }

                    const rettifica = await fetch("/inventario/rettifica", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({inventario_id: id})
                    });
                    if (!rettifica.ok) {
                        alert("Errore di rete o risposta non valida dal server.");
                        return;
                    }

                    const set_fm= await fetch("/inventario/set_rettifica", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ inventario_id: id })
                        });
                        if (!set_fm.ok) {
                            alert("Errore nel set del flag rettifiche esistenti.");
                            return
                        }

                    const data = await rettifica.json();

                    if (data.success) {
                        aggiornaTabellaInventariEseguiti();
                        flashMessage(`Rettifica completata con successo! (${data.rettifiche || 0} movimenti)`, "success");
                    } else {
                        alert(data.message || "Errore nella rettifica.");
                    }
                });
            });
        });
}


// Click su riga inventario -> apre modale
document.querySelector("#tabella-inventari-eseguiti tbody").addEventListener("click", function (e) {
    const riga = e.target.closest("tr");
    if (!riga) return;

    lastFocusedElement = this;  // memorizza l'elemento cliccato
    const inventarioId = riga.dataset.inventarioId;
    console.log(`inventarioID letto: ${inventarioId}`);

    const dataInventario = riga.dataset.data;

    document.getElementById("dettaglio-id-inventario").textContent = inventarioId;
    document.getElementById("dettaglio-data-inventario").textContent = dataInventario;
    document.getElementById("dettaglio-deposito-inventario").textContent = riga.dataset.deposito;

    // Mostra tabella movimenti di default
    document.getElementById("tabella-movimenti").classList.remove("d-none");
    document.getElementById("tabella-inventario-aggregato").classList.add("d-none");
    document.getElementById("filtro-visualizza").value = "movimenti";

    aggiornaTabellaMovimenti(inventarioId);

    const modale = new bootstrap.Modal(document.getElementById("modaleDettaglioInventario"));
    modale.show();
});

document.getElementById("filtro-visualizza").addEventListener("change", function () {
    const inventarioId = document.getElementById("modaleDettaglioInventario").dataset.inventarioId;
    console.warn(`inventarioID letto: ${inventarioId}`);
    const valore = this.value;

    if (valore === "movimenti") {
        document.getElementById("tabella-movimenti").classList.remove("d-none");
        document.getElementById("tabella-inventario-aggregato").classList.add("d-none");
        aggiornaTabellaMovimenti(inventarioId);
    } else {
        document.getElementById("tabella-movimenti").classList.add("d-none");
        document.getElementById("tabella-inventario-aggregato").classList.remove("d-none");
        aggiornaTabellaInventarioAggregato(inventarioId);
    }
});

document.getElementById('modaleDettaglioInventario').addEventListener('hidden.bs.modal', function () {
    console.log("🔁 Modale chiusa, ripristino dello stato della pagina...");

    // ✅ Sposta il focus su un elemento visibile per evitare problemi con aria-hidden
    const fallback = document.querySelector('main, body, #content, .navbar-brand'); // scegli un elemento presente
    if (fallback) fallback.focus();

    // ⏳ Attendi un attimo per garantire che la modale sia completamente rimossa
    setTimeout(() => {
        // 🔁 Rimuove forzatamente il focus residuo
        document.activeElement.blur();

        // 🔧 Rimuove classe "modal-open" dal body (se rimasta)
        document.body.classList.remove('modal-open');

        // 🧹 Rimuove overlay eventualmente rimasto
        const backdrop = document.querySelector('.modal-backdrop');
        if (backdrop) backdrop.remove();

        // ✅ Riabilita lo scroll se rimasto disattivato
        document.body.style.overflow = '';

        console.log("✅ Stato della pagina ripristinato.");
    }, 100);
});

function aggiornaTabellaInventarioAggregato(inventarioId) {
    if (!inventarioId) {
        console.warn("aggiornaTabellaInventarioAggregato: ID non definito, chiamata ignorata.");
        return;
    }

    console.log(`Chiamata a /inventario/inventario_aggregato/${inventarioId}`);

    fetch(`/inventario/inventario_aggregato/${inventarioId}`)
        .then(res => res.json())
        .then(data => {
            const tbody = document.querySelector("#tabella-inventario-aggregato tbody");
            tbody.innerHTML = "";

            console.table(data);

            data.inventario.forEach(r => {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td>${r.cod_art}</td>
                    <td>${r.descrizione}</td>
                    <td class="text-end">${r.quantita}</td>
                    <td class="text-end">
                        <button class="btn btn-sm btn-info btn-movimenti me-1" data-cod_art="${r.cod_art}">Movimenti</button>
                        <button class="btn btn-sm btn-danger btn-elimina-articolo" data-cod_art="${r.cod_art}">Elimina</button>
                    </td>
                `;
                tbody.appendChild(tr);
            });

            // ✅ Aggiungi i listener solo dopo che i pulsanti sono nel DOM
            document.querySelectorAll(".btn-movimenti").forEach(btn => {
                btn.addEventListener("click", e => {
                    const codArt = btn.dataset.cod_art;
                    const inventarioId = document.getElementById("modaleDettaglioInventario").dataset.inventarioId;

                    console.log(`codice articolo: ${codArt}`);
                    console.log(`Inventario: ${inventarioId}`);

                    fetch(`/inventario/movimenti_articolo/${inventarioId}/${codArt}`)
                        .then(res => res.json())
                        .then(data => {
                            const tbodyMov = document.getElementById("tbody-movimenti-articolo");
                            tbodyMov.innerHTML = "";

                            if (data.success) {
                                data.movimenti.forEach(m => {
                                    const tr = document.createElement("tr");
                                    tr.innerHTML = `
                                        <td>${m.data}</td>
                                        <td class="text-end">${m.descrizione}</td>
                                        <td class="text-end">${m.utente}</td>
                                        <td>${m.quantita}</td>
                                    `;
                                    tbodyMov.appendChild(tr);
                                });

                                const modal = new bootstrap.Modal(document.getElementById("modaleMovimentiArticolo"));
                                modal.show();
                            } else {
                                alert("Errore nel recupero dei movimenti.");
                            }
                        });
                });
            });
            document.querySelectorAll(".btn-elimina-articolo").forEach(btn => {
                btn.addEventListener("click", e => {
                    const codArt = btn.dataset.cod_art;
                    const inventarioId = document.getElementById("modaleDettaglioInventario").dataset.inventarioId;

                    if (confirm(`Vuoi eliminare tutti i movimenti relativi all'articolo ${codArt}?`)) {
                        fetch(`/inventario/elimina_movimenti/${inventarioId}/${codArt}`, {
                            method: "DELETE"
                        })
                        .then(res => res.json())
                        .then(data => {
                            if (data.success) {
                                console.log(`Eliminati ${data.deleted} movimenti per ${codArt}`);
                                aggiornaTabellaInventarioAggregato(inventarioId);
                                aggiornaTabellaMovimenti(inventarioId);
                            } else {
                                alert("Errore nell'eliminazione dei movimenti.");
                            }
                        })
                        .catch(err => {
                            console.error("Errore:", err);
                        });
                    }
                });
            });

        })
        .catch(err => {
            console.error("Errore nel caricamento inventario aggregato:", err);
        });
}


function mostraMovimentiPerArticolo(inventarioId, codArt) {
    fetch(`/inventario/movimenti_articolo/${inventarioId}/${codArt}`)
        .then(res => res.json())
        .then(data => {
            if (!data.success || !data.movimenti.length) {
                alert("Nessun movimento trovato per questo articolo.");
                return;
            }

            // Costruisci una modale dinamica
            let html = `
                <div class="modal fade" id="modaleMovimentiArticolo" tabindex="-1">
                  <div class="modal-dialog modal-lg">
                    <div class="modal-content">
                      <div class="modal-header">
                        <h5 class="modal-title">Movimenti per articolo ${codArt}</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                      </div>
                      <div class="modal-body">
                        <table class="table table-sm">
                          <thead>
                            <tr><th>Quantità</th><th>Note</th><th>Data inserimento</th></tr>
                          </thead>
                          <tbody>
                          ${data.movimenti.map(m => `
                            <tr>
                              <td class="text-end">${m.quantita}</td>
                              <td>${m.note || ""}</td>
                              <td>${m.data || ""}</td>
                            </tr>`).join('')}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>
                </div>`;

            document.body.insertAdjacentHTML('beforeend', html);
            const nuovaModale = new bootstrap.Modal(document.getElementById("modaleMovimentiArticolo"));
            nuovaModale.show();

            // Rimuovi la modale dopo la chiusura
            document.getElementById("modaleMovimentiArticolo").addEventListener("hidden.bs.modal", function () {
                this.remove();
            });
        });
}


async function getCsrfToken() {
    const res = await fetch('/inventario/get_csrf_token');
    const data = await res.json();
    return data.csrf_token;
}


// Mostra la modale con datepicker
function apriModaleModificaData(idInventario, dataAttuale) {
    const inputData = document.getElementById("nuovaDataInventario");
    const inputId = document.getElementById("inventarioIdPerModificaData");

    inputData.value = dataAttuale;
    inputId.value = idInventario;

    const modale = new bootstrap.Modal(document.getElementById("modaleModificaData"));
    modale.show();
}

// Al click su "Salva" nella modale
document.getElementById("salvaDataInventario").addEventListener("click", () => {
    const nuovaData = document.getElementById("nuovaDataInventario").value;
    const id = document.getElementById("inventarioIdPerModificaData").value;

    fetch(`/inventario/modifica_data/${id}`, {
        method: "POST",
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ nuova_data: nuovaData })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            console.log("Data modificata con successo");
            document.activeElement.blur();
            bootstrap.Modal.getInstance(document.getElementById("modaleModificaData")).hide();
            popolaSelectInventari(id);  // invId è l'inventario modificato
            aggiornaTabellaInventariEseguiti();  // se vuoi anche aggiornare la tabella sotto
            resetCampiArticoloCompleto();
        } else {
            alert("Errore nella modifica");
        }
    })
    .catch(err => {
        console.error("Errore:", err);
    });
});


function popolaSelectInventari(idSelezionato = null) {
    fetch("/inventario/lista_inventari")
        .then(res => res.json())
        .then(data => {
            const select = document.getElementById("inventario-select");
            select.innerHTML = `<option value="" disabled>-- Seleziona inventario --</option>`;

            data.inventari.forEach(inv => {
                const option = document.createElement("option");
                option.value = inv.id;
                option.textContent = inv.data;
                option.dataset.export_inventario = inv.export_inventario;
                option.dataset.fix_movements = inv.fix_movements;
                // Aggiungi dataset extra se serve (es. num_righe, ecc.)
                option.dataset.data = inv.data;

                if (idSelezionato && inv.id === idSelezionato) {
                    option.selected = true;
                }

                select.appendChild(option);
            });

            // Se è stato selezionato, lancia evento di change per aggiornare tutto
            if (idSelezionato) {
                select.dispatchEvent(new Event('change'));
            }
        });
}

document.getElementById("formModificaMovimento").addEventListener("submit", e => {
    e.preventDefault(); // evita refresh della pagina

    salvaMovimento();
});

function salvaMovimento() {
    const inventarioId = document.getElementById("modaleDettaglioInventario").dataset.inventarioId;
    const idMov = document.getElementById("modCalcolaFormula").dataset.id_mov;

    const payload = {
        id_mov: idMov,
        inventario_id: inventarioId,
        quantita_inserita: document.getElementById("modQuantitaInserita").value,
        num_pedane: document.getElementById("fcqNumPedane").value,
        cpp: document.getElementById("fcqCPP").textContent,  // perché è uno <span>
        num_cartoni: document.getElementById("fcqNumCartoni").value,
        ppc: document.getElementById("fcqPPC").textContent,
        num_pezzi_sciolti: document.getElementById("fcqNumPezziSciolti").value,
    };

    console.log("chiamo la route di modifica movimento con payload:", payload);
    fetch(`/inventario/modifica_dati_movimento/${inventarioId}/${idMov}`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            alert(data.message);
            // Chiudi la modale
            bootstrap.Modal.getInstance(document.getElementById('modaleModificaMovimentoArticolo')).hide();
            // Ricarica tabella movimenti se serve
            aggiornaTabellaMovimenti(inventarioId);
        } else {
            alert("Errore nel salvataggio: " + data.message);
        }
    })
    .catch(err => console.error("Errore:", err));
}
