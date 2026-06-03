(function () {
  "use strict";

  const { api, escapeHtml, formatDateTime } = window.shippingCommon;

  const el = {
    importBtn: document.getElementById("poleepoImportBtn"),
    syncShipments: document.getElementById("poleepoSyncShipmentsBtn"),
    list: document.getElementById("poleepoOrdersList"),
    count: document.getElementById("poleepoOrdersCount"),
  };

  function renderOrders(orders) {
    el.count.textContent = String(orders.length);
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
          .join("")
      : `<div class="shipping-empty">Nessun ordine Poleepo importato.</div>`;
  }

  async function loadOrders() {
    const data = await api("/shipping/api/external-orders");
    renderOrders(data.orders || []);
  }

  el.importBtn.addEventListener("click", async () => {
    try {
      const result = await api("/shipping/api/poleepo/import", { method: "POST", body: "{}" });
      await loadOrders();
      alert(`Ordini: ${result.imported} nuovi, ${result.updated} aggiornati. Spedizioni: ${result.shipments_imported || 0} nuove, ${result.shipments_updated || 0} aggiornate.`);
    } catch (err) {
      alert(err.message);
    }
  });

  el.syncShipments.addEventListener("click", async () => {
    try {
      const result = await api("/shipping/api/poleepo/sync-shipments", { method: "POST", body: JSON.stringify({ limit: 100 }) });
      alert(`Spedizioni Poleepo: ${result.imported} nuove, ${result.updated} aggiornate. Errori: ${(result.errors || []).length}.`);
    } catch (err) {
      alert(err.message);
    }
  });

  loadOrders().catch((err) => {
    el.list.innerHTML = `<div class="text-danger">${escapeHtml(err.message)}</div>`;
  });
})();
