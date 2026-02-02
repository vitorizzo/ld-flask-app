(function () {
  function qs(sel, root = document) { return root.querySelector(sel); }
  function qsa(sel, root = document) { return Array.from(root.querySelectorAll(sel)); }

  function applyRouteFilter(routeId) {
    const cards = qsa(".order-card");
    cards.forEach((c) => {
      const cid = c.getAttribute("data-route-id");
      const hide = (routeId !== "__all__") && (cid !== String(routeId));
      c.classList.toggle("is-hidden", hide);
    });

    // aggiorna conteggi per colonna (solo visibili)
    ["acquisito","listato","controllato","evaso"].forEach((st) => {
      const col = qs(`.kiosk-col[data-col="${st}"]`);
      const visible = qsa(`.order-card:not(.is-hidden)`, col).length;
      const counter = qs(`#count-${st}`);
      if (counter) counter.textContent = String(visible);
    });
  }

  function wireFilters() {
    qsa(".route-pill").forEach((btn) => {
      btn.addEventListener("click", () => {
        qsa(".route-pill").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        applyRouteFilter(btn.getAttribute("data-filter-route"));
      });
    });
  }

  async function openOrderModal(orderId) {
    const modalEl = qs("#orderModal");
    const titleEl = qs("#orderModalTitle");
    const bodyEl = qs("#orderModalBody");

    titleEl.textContent = `Ordine #${orderId}`;
    bodyEl.innerHTML = `<div class="text-muted">Caricamento...</div>`;

    // bootstrap modal (assumendo bootstrap già incluso da base.html)
    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    modal.show();

    try {
      const res = await fetch(`/kiosk/api/order/${orderId}`, { headers: { "Accept": "application/json" } });
      const data = await res.json();

      const notes = (data.thread_notes || []).map(n => `
        <div class="border rounded p-2 mb-2">
          <div class="small text-muted">${n.created_at || ""}</div>
          <div>${(n.text || "").replaceAll("\n","<br>")}</div>
        </div>
      `).join("");

      const children = (data.children || []).map(ch => `
        <li class="mb-1">
          <span class="badge bg-secondary me-1">${ch.label || ""}</span>
          <span>${(ch.text || "").replaceAll("\n","<br>")}</span>
          <div class="small text-muted">${ch.ts || ""}</div>
        </li>
      `).join("");

      bodyEl.innerHTML = `
        <div class="mb-2"><b>Cliente:</b> ${data.customer_display || ""}</div>
        <div class="mb-2"><b>Giro:</b> ${data.route_name || ""}</div>
        <div class="mb-2"><b>Status:</b> <span class="badge bg-dark">${data.status || ""}</span></div>
        <div class="mb-3"><b>Consegna prevista:</b> ${(data.planned_delivery_at || "").replace("T"," ")}</div>

        <div class="mb-3">
          <b>Testo ordine</b>
          <div class="border rounded p-2 mt-1" style="white-space:pre-wrap;">${data.raw_text || ""}</div>
        </div>

        <div class="mb-3">
          <b>Messaggi collegati</b>
          <ul class="mt-2">${children || "<li class='text-muted'>Nessuno</li>"}</ul>
        </div>

        <div class="mb-2">
          <b>Note / anomalie (thread)</b>
          <div class="mt-2">${notes || "<div class='text-muted'>Nessuna nota</div>"}</div>
        </div>
      `;
    } catch (e) {
      bodyEl.innerHTML = `<div class="text-danger">Errore caricamento ordine.</div>`;
    }
  }

  function wireCards() {
    qsa(".order-card").forEach((card) => {
      const id = card.getAttribute("data-order-id");
      card.addEventListener("click", () => openOrderModal(id));
      card.addEventListener("keypress", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") openOrderModal(id);
      });
    });
  }

  function wireRefresh() {
    const btn = qs("#btn-refresh");
    if (!btn) return;
    btn.addEventListener("click", () => window.location.reload());
  }

  // init
  wireFilters();
  wireCards();
  wireRefresh();
  applyRouteFilter("__all__");
})();
