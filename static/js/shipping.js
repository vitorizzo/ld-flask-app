(function () {
  "use strict";

  const state = {
    shipments: [],
    accounts: [],
    selectedId: null,
  };

  const el = {
    search: document.getElementById("shippingSearch"),
    courier: document.getElementById("shippingCourierFilter"),
    refresh: document.getElementById("shippingRefreshBtn"),
    list: document.getElementById("shipmentsList"),
    count: document.getElementById("shipmentsCount"),
    detail: document.getElementById("shipmentDetail"),
    form: document.getElementById("shipmentForm"),
    shipmentCourier: document.getElementById("shipmentCourier"),
    shipmentAccount: document.getElementById("shipmentCourierAccount"),
    accountForm: document.getElementById("courierAccountForm"),
    accountList: document.getElementById("courierAccountsList"),
    accountCount: document.getElementById("courierAccountsCount"),
    poleepoImport: document.getElementById("poleepoImportBtn"),
    poleepoList: document.getElementById("poleepoOrdersList"),
  };

  document.querySelectorAll(".shipping-modal").forEach((modal) => {
    if (modal.parentElement !== document.body) {
      document.body.appendChild(modal);
    }
  });

  function escapeHtml(value) {
    return String(value || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  async function api(url, options) {
    const response = await fetch(url, {
      credentials: "same-origin",
      cache: "no-store",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      ...(options || {}),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok === false) throw new Error(data.error || `HTTP ${response.status}`);
    return data;
  }

  function statusLabel(shipment) {
    return shipment.status_label || shipment.status || "created";
  }

  function accountTypeLabel(type) {
    return type === "webservice" ? "Web service" : "Portale";
  }

  function accountName(account) {
    return `${(account.courier_code || "").toUpperCase()} - ${account.name || accountTypeLabel(account.account_type)}`;
  }

  function parseExtraConfig() {
    const raw = document.getElementById("courierAccountExtra").value.trim();
    if (!raw) return {};
    return JSON.parse(raw);
  }

  function resetAccountForm() {
    el.accountForm.reset();
    document.getElementById("courierAccountId").value = "";
    document.getElementById("courierAccountEnabled").checked = true;
    document.getElementById("courierAccountExtra").value = "";
  }

  function fillAccountForm(account) {
    document.getElementById("courierAccountId").value = account.id || "";
    document.getElementById("courierAccountCourier").value = account.courier_code || "brt";
    document.getElementById("courierAccountType").value = account.account_type || "portal";
    document.getElementById("courierAccountName").value = account.name || "";
    document.getElementById("courierAccountBaseUrl").value = account.base_url || "";
    document.getElementById("courierAccountUsername").value = account.username || "";
    document.getElementById("courierAccountPassword").value = "";
    document.getElementById("courierAccountExtra").value = Object.keys(account.extra_config || {}).length
      ? JSON.stringify(account.extra_config, null, 2)
      : "";
    document.getElementById("courierAccountEnabled").checked = account.is_enabled !== false;
  }

  function renderAccounts() {
    if (!el.accountList) return;
    el.accountCount.textContent = String(state.accounts.length);
    if (!state.accounts.length) {
      el.accountList.innerHTML = `<div class="shipping-empty">Nessun account corriere configurato.</div>`;
      renderShipmentAccountOptions();
      return;
    }
    el.accountList.innerHTML = state.accounts
      .map(
        (account) => `
          <div class="shipping-item" data-account-id="${account.id}">
            <div class="shipping-item__top">
              <div>
                <div class="shipping-item__title">${escapeHtml(accountName(account))}</div>
                <div class="shipping-item__meta">${escapeHtml(account.username || "Utente non indicato")}</div>
              </div>
              <span class="shipping-status">${escapeHtml(accountTypeLabel(account.account_type))}</span>
            </div>
            <div class="shipping-account__tags">
              <span class="shipping-tag ${account.is_enabled ? "is-ok" : "is-muted"}">${account.is_enabled ? "Attivo" : "Disattivo"}</span>
              <span class="shipping-tag ${account.has_password ? "is-ok" : "is-muted"}">${account.has_password ? "Password salvata" : "Password mancante"}</span>
            </div>
          </div>
        `
      )
      .join("");
    renderShipmentAccountOptions();
  }

  function renderShipmentAccountOptions() {
    if (!el.shipmentAccount || !el.shipmentCourier) return;
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
    if (!el.list) return;
    el.count.textContent = String(state.shipments.length);
    if (!state.shipments.length) {
      el.list.innerHTML = `<div class="shipping-empty">Nessuna spedizione.</div>`;
      return;
    }
    el.list.innerHTML = state.shipments
      .map(
        (shipment) => `
          <div class="shipping-item ${shipment.id === state.selectedId ? "is-active" : ""}" data-shipment-id="${shipment.id}">
            <div class="shipping-item__top">
              <div>
                <div class="shipping-item__title">${escapeHtml(shipment.courier_name || shipment.courier_code)} ${escapeHtml(shipment.tracking_number)}</div>
                <div class="shipping-item__meta">${escapeHtml(shipment.customer_name || shipment.recipient_name || "Cliente non indicato")}</div>
                <div class="shipping-item__meta">${escapeHtml(shipment.courier_account_name || shipment.source || "")}</div>
              </div>
              <span class="shipping-status">${escapeHtml(statusLabel(shipment))}</span>
            </div>
          </div>
        `
      )
      .join("");
  }

  function renderDetail(payload) {
    const shipment = payload.shipment;
    const events = payload.events || [];
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
      </div>
      ${shipment.last_error ? `<div class="alert alert-warning">${escapeHtml(shipment.last_error)}</div>` : ""}
      <div class="fw-bold mb-2">Eventi tracking</div>
      ${
        events.length
          ? events
              .map(
                (event) => `
                  <div class="shipping-event">
                    <div class="fw-bold">${escapeHtml(event.status || "")}</div>
                    <div>${escapeHtml(event.description || "")}</div>
                    <div class="text-muted">${escapeHtml(event.location || "")} ${escapeHtml(event.event_at || "")}</div>
                  </div>
                `
              )
              .join("")
          : `<div class="shipping-empty">Nessun evento tracking.</div>`
      }
    `;
  }

  async function loadShipments() {
    const params = new URLSearchParams();
    if (el.search.value.trim()) params.set("q", el.search.value.trim());
    if (el.courier.value) params.set("courier", el.courier.value);
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

  async function loadPoleepoOrders() {
    const data = await api("/shipping/api/external-orders");
    const orders = data.orders || [];
    el.poleepoList.innerHTML = orders.length
      ? orders
          .map(
            (order) => `
              <div class="shipping-item">
                <div class="shipping-item__top">
                  <div>
                    <div class="shipping-item__title">${escapeHtml(order.order_number || order.external_id)}</div>
                    <div class="shipping-item__meta">${escapeHtml(order.customer_name || order.recipient_name || "")}</div>
                  </div>
                  <span class="shipping-status">${escapeHtml(order.status)}</span>
                </div>
              </div>
            `
          )
          .join("")
      : `<div class="shipping-empty">Nessun ordine Poleepo importato.</div>`;
  }

  async function loadAccounts() {
    const data = await api("/shipping/api/courier-accounts");
    state.accounts = data.accounts || [];
    renderAccounts();
  }

  let searchTimer = null;
  function scheduleLoad() {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => loadShipments().catch((err) => alert(err.message)), 250);
  }

  el.search.addEventListener("input", scheduleLoad);
  el.courier.addEventListener("change", scheduleLoad);
  el.refresh.addEventListener("click", () => loadShipments().catch((err) => alert(err.message)));
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
  el.accountList.addEventListener("click", (event) => {
    const item = event.target.closest("[data-account-id]");
    if (!item) return;
    const account = state.accounts.find((candidate) => String(candidate.id) === String(item.dataset.accountId));
    if (!account) return;
    fillAccountForm(account);
    bootstrap.Modal.getOrCreateInstance(document.getElementById("courierAccountModal")).show();
  });
  el.accountForm.addEventListener("click", (event) => {
    if (!event.target.closest("[data-account-reset]")) return;
    resetAccountForm();
  });
  el.accountForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    let extraConfig = {};
    try {
      extraConfig = parseExtraConfig();
    } catch (err) {
      alert("Config extra JSON non valido");
      return;
    }
    const payload = {
      id: document.getElementById("courierAccountId").value || null,
      courier_code: document.getElementById("courierAccountCourier").value,
      account_type: document.getElementById("courierAccountType").value,
      name: document.getElementById("courierAccountName").value,
      base_url: document.getElementById("courierAccountBaseUrl").value,
      username: document.getElementById("courierAccountUsername").value,
      password: document.getElementById("courierAccountPassword").value,
      extra_config: extraConfig,
      is_enabled: document.getElementById("courierAccountEnabled").checked,
    };
    try {
      await api("/shipping/api/courier-accounts", { method: "POST", body: JSON.stringify(payload) });
      bootstrap.Modal.getOrCreateInstance(document.getElementById("courierAccountModal")).hide();
      resetAccountForm();
      await loadAccounts();
    } catch (err) {
      alert(err.message);
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
  el.poleepoImport.addEventListener("click", async () => {
    try {
      await api("/shipping/api/poleepo/import", { method: "POST", body: "{}" });
      await loadPoleepoOrders();
    } catch (err) {
      alert(err.message);
    }
  });

  loadAccounts().catch((err) => {
    el.accountList.innerHTML = `<div class="text-danger">${escapeHtml(err.message)}</div>`;
  });
  loadShipments().catch((err) => alert(err.message));
  loadPoleepoOrders().catch((err) => {
    el.poleepoList.innerHTML = `<div class="text-danger">${escapeHtml(err.message)}</div>`;
  });
})();
