window.initSearchByDescription = function (config) {
  const input = document.getElementById(config.inputId);
  const checkbox = document.getElementById(config.showAllCheckboxId);
  const list = document.getElementById(config.listId);
  const wrapper = document.getElementById(config.wrapperId);
  const prevBtn = document.getElementById(config.pagination.prevId);
  const nextBtn = document.getElementById(config.pagination.nextId);
  const pageInfo = document.getElementById(config.pagination.infoId);
  const paginationContainer = document.getElementById(config.pagination.containerId);
  const modalIframe = document.getElementById(config.modalIframeId);
  const modalId = config.modalTriggerId;

  let currentPage = 1;
  const perPage = 10;

  function caricaProdotti(query = "", page = 1) {
    const showAll = checkbox ? checkbox.checked : false;
    const stockOnly = showAll ? "0" : "1";

    fetch(`/search/lista_articoli?filter=${encodeURIComponent(query)}&page=${page}&per_page=${perPage}&stock_only=${stockOnly}`)
      .then(res => res.json())
      .then(data => {
        list.innerHTML = "";
        const trovati = data.prodotti || [];

        if (trovati.length === 0) {
          list.innerHTML = `<li class="list-group-item text-muted text-center">Nessun prodotto trovato</li>`;
        } else {
          trovati.forEach(prodotto => {
            const li = document.createElement("li");
            li.className = "list-group-item d-flex justify-content-between align-items-center prodotto-item search-product-result";
            li.dataset.cod_art = prodotto.cod_art;

            const descr = `
              <div class="search-product-result__text">
                <div class="fw-bold search-product-result__title">${prodotto.descrizione}</div>
                <small class="text-muted search-product-result__subtitle">${prodotto.descrizione_aggiuntiva || ""}</small>
              </div>
            `;

            const cod_art = `<span class="badge bg-primary search-product-result__code">${prodotto.cod_art}</span>`;

            li.innerHTML = `<div class="d-flex justify-content-between w-100 align-items-center search-product-result__row">
                              ${descr}
                              <div class="d-flex align-items-center search-product-result__actions">
                                ${cod_art}
                              </div>
                            </div>`;

            // 👉 Salva tutti i dati necessari per onSelect
            li.dataset.descrizione = prodotto.descrizione;
            li.dataset.descrizioneAggiuntiva = prodotto.descrizione_aggiuntiva;
            li.dataset.cpp = prodotto.ppc;
            li.dataset.ppc = prodotto.cpp;

            list.appendChild(li);
          });
        }

        wrapper.style.display = "block";
        paginationContainer.style.display = "flex";
        pageInfo.textContent = `Pagina ${data.pagina_corrente} di ${data.pagine_totali}`;
        prevBtn.disabled = data.pagina_corrente === 1;
        nextBtn.disabled = data.pagina_corrente >= data.pagine_totali;

        currentPage = data.pagina_corrente;
      });
  }

  input.addEventListener("input", () => {
    currentPage = 1;
    caricaProdotti(input.value, currentPage);
  });

  if (checkbox) {
    checkbox.addEventListener("change", () => {
      currentPage = 1;
      caricaProdotti(input.value, currentPage);
    });
  }

  prevBtn.addEventListener("click", () => {
    if (currentPage > 1) {
      caricaProdotti(input.value, currentPage - 1);
    }
  });

  nextBtn.addEventListener("click", () => {
    caricaProdotti(input.value, currentPage + 1);
  });

  list.addEventListener("click", (e) => {
    const btn = e.target.closest(".apri-scheda");
    const item = e.target.closest(".prodotto-item");

    if (btn) {
      const cod_art = btn.dataset.cod_art;
      if (typeof config.onRowClick === "function") {
        config.onRowClick({ cod_art });
      } else if (modalIframe && modalId) {
        modalIframe.src = `/search/scheda_articolo/${cod_art}`;
        const modal = new bootstrap.Modal(document.getElementById(modalId));
        modal.show();
      }
    } else if (item && !btn) {
      const articolo = {
        cod_art: item.dataset.cod_art,
        descrizione: item.dataset.descrizione,
        descrizione_aggiuntiva: item.dataset.descrizioneAggiuntiva,
        cpp: parseInt(item.dataset.cpp || 1),
        ppc: parseInt(item.dataset.ppc || 1)
      };

      if (typeof config.onRowClick === "function") {
        config.onRowClick(articolo);
        return;
      }

      // Evidenzia selezione
      list.querySelectorAll(".prodotto-item").forEach(el => el.classList.remove("active"));
      item.classList.add("active");

      if (typeof config.onSelect === "function") {
        config.onSelect(articolo);
      }
    }
  });

  caricaProdotti();
};
