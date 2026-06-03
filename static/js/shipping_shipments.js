(function () {
  "use strict";

  const { accountName, api, escapeHtml, formatDateTime, statusLabel } = window.shippingCommon;
  const state = {
    shipments: [],
    accounts: [],
    selectedId: null,
  };

  const el = {
    search: document.getElementById("shippingSearch"),
    courier: document.getElementById("shippingCourierFilter"),
    lifecycle: document.getElementById("shippingLifecycleFilter"),
    status: document.getElementById("shippingStatusFilter"),
    refresh: document.getElementById("shippingRefreshBtn"),
    refreshOpen: document.getElementById("shippingRefreshOpenBtn"),
    list: document.getElementById("shipmentsList"),
    count: document.getElementById("shipmentsCount"),
    detail: document.getElementById("shipmentDetail"),
    form: document.getElementById("shipmentForm"),
    shipmentCourier: document.getElementById("shipmentCourier"),
    shipmentAccount: document.getElementById("shipmentCourierAccount"),
  };

  function summaryField(label, value) {
    if (value === null || value === undefined || value === "") return "";
    return `<div class="shipping-detail__field"><div class="shipping-detail__label">${escapeHtml(label)}</div><div>${escapeHtml(value)}</div></div>`;
  }

  function renderShipmentAccountOptions() {
    const selected = el.shipmentAccount.value;
    const courier = el.shipmentCourier.value;
    const accounts = state.accounts.filter((account) => account.courier_code === courier && account.is_enabled !== false);
    el.shipmentAccount.innerHTML = `<option value="">Automatico</option>${accounts
      .map((account) => `<option value="${account.id}">${escapeHtml(accountName(account))}</option>`)
      .join("")}`;
    if ([...el.shipmentAccount.options].some((option) => option.value === selected)) {
      el.shipmentAccount.value = selected;
    }
  }

  function renderShipments() {
    el.count.textContent = String(state.shipments.length);
    if (!state.shipments.length) {
      el.list.innerHTML = `<div class="shipping-empty">Nessuna spedizione.</div>`;
      return;
    }
    el.list.innerHTML = state.shipments
      .map(
        (shipment) => `
          <button class="shipping-item text-start ${shipment.id === state.selectedId ? "is-active" : ""}" type="button" data-shipment-id="${shipment.id}">
            <div class="shipping-item__top">
              <div>
                <div class="shipping-item__title">${escapeHtml(shipment.courier_name || shipment.courier_code)} ${escapeHtml(shipment.tracking_number)}</div>
                <div class="shipping-item__meta">${escapeHtml(shipment.customer_name || shipment.recipient_name || "Cliente non indicato")}</div>
                <div class="shipping-item__meta">${escapeHtml(formatDateTime(shipment.shipped_at) || "Data spedizione non disponibile")}</div>
                <div class="shipping-item__meta">${escapeHtml(shipment.courier_account_name || shipment.source || "")}${shipment.last_tracking_at ? ` - Agg. ${escapeHtml(formatDateTime(shipment.last_tracking_at))}` : ""}</div>
              </div>
              <span class="shipping-status">${escapeHtml(statusLabel(shipment))}</span>
            </div>
          </button>
        `
      )
      .join("");
  }

  function renderDetail(payload) {
    const shipment = payload.shipment;
    const events = payload.events || [];
    const summary = payload.tracking_summary || {};
    el.detail.innerHTML = `
      <div class="shipping-detail__title">
        <div>
          <h3>${escapeHtml(shipment.tracking_number)}</h3>
          <div class="text-muted">${escapeHtml(shipment.courier_name || shipment.courier_code)}</div>
        </div>
        <button class="btn btn-sm btn-outline-primary" type="button" data-refresh-shipment="${shipment.id}">Aggiorna tracking</button>
      </div>
      <div class="shipping-detail__grid">
        <div class="shipping-detail__field"><div class="shipping-detail__label">Stato</div><div>${escapeHtml(statusLabel(shipment))}</div></div>
        <div class="shipping-detail__field"><div class="shipping-detail__label">Cliente</div><div>${escapeHtml(shipment.customer_name || "")}</div></div>
        <div class="shipping-detail__field"><div class="shipping-detail__label">Destinatario</div><div>${escapeHtml(shipment.recipient_name || "")}</div></div>
        <div class="shipping-detail__field"><div class="shipping-detail__label">Riferimento</div><div>${escapeHtml(shipment.reference || shipment.external_order_id || "")}</div></div>
        <div class="shipping-detail__field"><div class="shipping-detail__label">Account</div><div>${escapeHtml(shipment.courier_account_name || "Automatico")}</div></div>
        <div class="shipping-detail__field"><div class="shipping-detail__label">Provenienza</div><div>${escapeHtml(shipment.source || "")}</div></div>
        ${summaryField("Data spedizione", summary.shipment_date || formatDateTime(shipment.shipped_at))}
        ${summaryField("Servizio", summary.service)}
        ${summaryField("Filiale arrivo", summary.arrival_branch)}
        ${summaryField("Colli", summary.parcels)}
        ${summaryField("Peso kg", summary.weight_kg)}
        ${summaryField("Ultimo aggiornamento", formatDateTime(shipment.last_tracking_at))}
      </div>
      ${summary.status_text ? `<div class="alert alert-light border">${escapeHtml(summary.status_text)}</div>` : ""}
      ${shipment.last_error ? `<div class="alert alert-warning">${escapeHtml(shipment.last_error)}</div>` : ""}
      <div class="fw-bold mb-2">Eventi tracking</div>
      ${
        events.length
          ? events
              .map(
                (event) => `
                  <div class="shipping-event">
                    <div class="shipping-event__time">${escapeHtml(formatDateTime(event.event_at))}</div>
                    <div>${escapeHtml(event.description || "")}</div>
                    <div class="shipping-event__meta">${escapeHtml(event.location || "")} ${escapeHtml(event.status || "")}</div>
                  </div>
                `
              )
              .join("")
          : `<div class="shipping-empty">Nessun evento tracking.</div>`
      }
    `;
  }

  async function loadAccounts() {
    const data = await api("/shipping/api/courier-accounts");
    state.accounts = data.accounts || [];
    renderShipmentAccountOptions();
  }

  async function loadShipments() {
    const params = new URLSearchParams();
    if (el.search.value.trim()) params.set("q", el.search.value.trim());
    if (el.courier.value) params.set("courier", el.courier.value);
    if (el.lifecycle.value) params.set("lifecycle", el.lifecycle.value);
    if (el.status.value) params.set("status", el.status.value);
    const data = await api(`/shipping/api/shipments?${params.toString()}`);
    state.shipments = data.shipments || [];
    renderShipments();
  }

  async function selectShipment(id) {
    state.selectedId = Number(id);
    renderShipments();
    el.detail.innerHTML = `<div class="shipping-empty">Caricamento...</div>`;
    const data = await api(`/shipping/api/shipments/${id}`);
    renderDetail(data);
  }

  let searchTimer = null;
  function scheduleLoad() {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => loadShipments().catch((err) => alert(err.message)), 250);
  }

  el.search.addEventListener("input", scheduleLoad);
  el.courier.addEventListener("change", scheduleLoad);
  el.lifecycle.addEventListener("change", scheduleLoad);
  el.status.addEventListener("change", scheduleLoad);
  el.refresh.addEventListener("click", () => loadShipments().catch((err) => alert(err.message)));
  el.refreshOpen.addEventListener("click", async () => {
    try {
      const result = await api("/shipping/api/shipments/refresh-open", { method: "POST", body: "{}" });
      await loadShipments();
      alert(`Spedizioni aggiornate: ${result.refreshed}. Cambi stato: ${result.changed}. Errori: ${(result.errors || []).length}.`);
    } catch (err) {
      alert(err.message);
    }
  });
  el.shipmentCourier.addEventListener("change", renderShipmentAccountOptions);

  el.list.addEventListener("click", (event) => {
    const item = event.target.closest("[data-shipment-id]");
    if (!item) return;
    selectShipment(item.dataset.shipmentId).catch((err) => alert(err.message));
  });

  el.detail.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-refresh-shipment]");
    if (!button) return;
    try {
      await api(`/shipping/api/shipments/${button.dataset.refreshShipment}/refresh`, { method: "POST", body: "{}" });
      await selectShipment(button.dataset.refreshShipment);
      await loadShipments();
    } catch (err) {
      alert(err.message);
      await selectShipment(button.dataset.refreshShipment).catch(() => undefined);
    }
  });

  el.form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = {
      courier_code: document.getElementById("shipmentCourier").value,
      courier_account_id: document.getElementById("shipmentCourierAccount").value || null,
      tracking_number: document.getElementById("shipmentTracking").value,
      customer_name: document.getElementById("shipmentCustomer").value,
      recipient_name: document.getElementById("shipmentRecipient").value,
      reference: document.getElementById("shipmentReference").value,
    };
    try {
      const data = await api("/shipping/api/shipments", { method: "POST", body: JSON.stringify(payload) });
      bootstrap.Modal.getOrCreateInstance(document.getElementById("shipmentModal")).hide();
      el.form.reset();
      await loadShipments();
      await selectShipment(data.shipment.id);
    } catch (err) {
      alert(err.message);
    }
  });

  loadAccounts().catch((err) => alert(err.message));
  loadShipments().catch((err) => alert(err.message));
})();
