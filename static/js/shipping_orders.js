(function () {
  "use strict";

  const { api, escapeHtml, formatDateTime } = window.shippingCommon;

  const el = {
    importBtn: document.getElementById("poleepoImportBtn"),
    importFullBtn: document.getElementById("poleepoImportFullBtn"),
    list: document.getElementById("poleepoOrdersList"),
    count: document.getElementById("poleepoOrdersCount"),
  };

  function renderOrders(orders, total, limit) {
    el.count.textContent = total > orders.length ? `${orders.length}/${total}` : String(orders.length);
    el.list.innerHTML = orders.length
      ? orders
          .map(
            (order) => `
              <div class="shipping-item">
                <div class="shipping-item__top">
                  <div>
                    <div class="shipping-item__title">${escapeHtml(order.order_number || order.external_id)}</div>
                    <div class="shipping-item__meta">${escapeHtml(order.customer_name || order.recipient_name || "")}</div>
                    <div class="shipping-item__meta">${escapeHtml(formatDateTime(order.ordered_at) || "Data ordine non disponibile")}</div>
                  </div>
                  <span class="shipping-status">${escapeHtml(order.status)}</span>
                </div>
              </div>
            `
          )
          .join("") +
        (total > orders.length
          ? `<div class="shipping-empty">Visualizzati gli ultimi ${escapeHtml(limit)} ordini su ${escapeHtml(total)} presenti in archivio.</div>`
          : "")
      : `<div class="shipping-empty">Nessun ordine Poleepo importato.</div>`;
  }

  async function loadOrders() {
    const data = await api("/shipping/api/external-orders");
    renderOrders(data.orders || [], data.total || 0, data.limit || 200);
  }

  async function importOrders(payload) {
    const result = await api("/shipping/api/poleepo/import", { method: "POST", body: JSON.stringify(payload || {}) });
    if (result.queued) {
      alert(`Task avviato in background: ${result.task_id}. Avanzamento visibile nella barra processi.`);
      return;
    }
    await loadOrders();
    alert(`Ordini: ${result.imported} nuovi, ${result.updated} aggiornati. Spedizioni: ${result.shipments_imported || 0} nuove, ${result.shipments_updated || 0} aggiornate. Letti da Poleepo: ${result.total || 0}.`);
  }

  el.importBtn.addEventListener("click", async () => {
    try {
      await importOrders({});
    } catch (err) {
      alert(err.message);
    }
  });

  el.importFullBtn.addEventListener("click", async () => {
    if (!window.confirm("Importare lo storico completo Poleepo? L'operazione puo' richiedere piu' tempo.")) return;
    try {
      await importOrders({ force_full: true });
    } catch (err) {
      alert(err.message);
    }
  });

  loadOrders().catch((err) => {
    el.list.innerHTML = `<div class="text-danger">${escapeHtml(err.message)}</div>`;
  });
})();
