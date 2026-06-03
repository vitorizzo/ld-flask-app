(function () {
  "use strict";

  const { accountName, accountTypeLabel, api, escapeHtml } = window.shippingCommon;
  const state = { accounts: [] };

  const el = {
    form: document.getElementById("courierAccountForm"),
    list: document.getElementById("courierAccountsList"),
    count: document.getElementById("courierAccountsCount"),
  };

  function parseExtraConfig() {
    const raw = document.getElementById("courierAccountExtra").value.trim();
    if (!raw) return {};
    return JSON.parse(raw);
  }

  function resetAccountForm() {
    el.form.reset();
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
    document.getElementById("courierAccountValidFrom").value = account.valid_from || "";
    document.getElementById("courierAccountValidTo").value = account.valid_to || "";
    document.getElementById("courierAccountExtra").value = Object.keys(account.extra_config || {}).length
      ? JSON.stringify(account.extra_config, null, 2)
      : "";
    document.getElementById("courierAccountEnabled").checked = account.is_enabled !== false;
  }

  function renderAccounts() {
    el.count.textContent = String(state.accounts.length);
    if (!state.accounts.length) {
      el.list.innerHTML = `<div class="shipping-empty">Nessun account corriere configurato.</div>`;
      return;
    }
    el.list.innerHTML = state.accounts
      .map(
        (account) => `
          <button class="shipping-item text-start" type="button" data-account-id="${account.id}">
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
              <span class="shipping-tag is-muted">${escapeHtml(account.valid_from || "inizio libero")} - ${escapeHtml(account.valid_to || "fine libera")}</span>
            </div>
          </button>
        `
      )
      .join("");
  }

  async function loadAccounts() {
    const data = await api("/shipping/api/courier-accounts");
    state.accounts = data.accounts || [];
    renderAccounts();
  }

  el.list.addEventListener("click", (event) => {
    const item = event.target.closest("[data-account-id]");
    if (!item) return;
    const account = state.accounts.find((candidate) => String(candidate.id) === String(item.dataset.accountId));
    if (!account) return;
    fillAccountForm(account);
    bootstrap.Modal.getOrCreateInstance(document.getElementById("courierAccountModal")).show();
  });

  el.form.addEventListener("click", (event) => {
    if (!event.target.closest("[data-account-reset]")) return;
    resetAccountForm();
  });

  el.form.addEventListener("submit", async (event) => {
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
      valid_from: document.getElementById("courierAccountValidFrom").value || null,
      valid_to: document.getElementById("courierAccountValidTo").value || null,
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

  loadAccounts().catch((err) => {
    el.list.innerHTML = `<div class="text-danger">${escapeHtml(err.message)}</div>`;
  });
})();
