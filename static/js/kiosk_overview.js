(function () {
  function escapeHtml(s) {
    return (s ?? "").replace(/[&<>"']/g, c => ({
      "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
    }[c]));
  }

  // filtro per giro (markup già server-side)
  document.querySelectorAll("[data-filter-route]").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("[data-filter-route]").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");

      const rid = btn.getAttribute("data-filter-route");
      document.querySelectorAll("#ordersGrid [data-route-id]").forEach(card => {
        if (rid === "__all__" || card.getAttribute("data-route-id") === rid) {
          card.style.display = "";
        } else {
          card.style.display = "none";
        }
      });
    });
  });

  // refresh “hard”
  const refreshBtn = document.getElementById("btn-refresh");
  if (refreshBtn) refreshBtn.addEventListener("click", () => location.reload());

  // click su card -> modal scheda ordine
  function bindCards() {
    document.querySelectorAll(".order-card[data-order-id]").forEach(card => {
      const orderId = card.getAttribute("data-order-id");
      const handler = () => openOrderModal(orderId);

      card.addEventListener("click", handler);
      card.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") handler();
      });
    });
  }

  async function openOrderModal(orderId) {
    try {
      const res = await fetch(`/kiosk/api/order/${orderId}`, { cache: "no-store" });
      if (!res.ok) throw new Error("HTTP " + res.status);
      const data = await res.json();

      document.getElementById("orderModalTitle").textContent =
        `${data.customer_display} — ${data.route_name}`;

      const body = document.getElementById("orderModalBody");
      body.innerHTML = `
        <div class="d-flex flex-wrap gap-2 mb-3">
          <span class="badge bg-dark">Giro: ${escapeHtml(data.route_name)}</span>
          <span class="badge bg-secondary">Status: ${escapeHtml(data.status)}</span>
          ${data.multi_count > 1 ? `<span class="badge badge-multi">Messaggi: ${data.multi_count}</span>` : ``}
          ${data.notes_count > 0 ? `<span class="badge badge-note">Note: ${data.notes_count}</span>` : ``}
          ${data.issues_count > 0 ? `<span class="badge badge-issue">Issue: ${data.issues_count}</span>` : ``}
        </div>

        ${data.raw_text ? `
          <div class="mb-3">
            <div style="font-weight:700;">Testo ordine</div>
            <pre class="p-2 rounded-2 bg-light" style="white-space: pre-wrap;">${escapeHtml(data.raw_text)}</pre>
          </div>
        ` : ``}

        ${data.children && data.children.length ? `
          <div class="mb-3">
            <div style="font-weight:700;">Ordini associati</div>
            <ul class="list-group">
              ${data.children.map(ch => `
                <li class="list-group-item">
                  <div class="d-flex justify-content-between">
                    <div><strong>${escapeHtml(ch.label)}</strong></div>
                    <div class="text-muted">${escapeHtml(ch.ts)}</div>
                  </div>
                  ${ch.text ? `<div class="mt-1"><pre class="mb-0" style="white-space: pre-wrap;">${escapeHtml(ch.text)}</pre></div>` : ``}
                </li>
              `).join("")}
            </ul>
          </div>
        ` : ``}

        ${data.thread_notes && data.thread_notes.length ? `
          <div class="mb-2">
            <div style="font-weight:700;">Note / anomalie (thread)</div>
            <ul class="list-group">
              ${data.thread_notes.map(n => `
                <li class="list-group-item">
                  <div class="text-muted">${escapeHtml(n.at)}</div>
                  <div>${escapeHtml(n.text)}</div>
                </li>
              `).join("")}
            </ul>
          </div>
        ` : ``}
      `;

      const modal = new bootstrap.Modal(document.getElementById("orderModal"));
      modal.show();

    } catch (e) {
      document.getElementById("orderModalBody").innerHTML =
        `<div class="text-danger">Errore caricamento scheda ordine: ${escapeHtml(String(e))}</div>`;
      const modal = new bootstrap.Modal(document.getElementById("orderModal"));
      modal.show();
    }
  }

  bindCards();
})();
