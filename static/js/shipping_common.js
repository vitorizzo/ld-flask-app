(function () {
  "use strict";

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

  function formatDateTime(value) {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString("it-IT", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
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

  document.querySelectorAll(".shipping-modal").forEach((modal) => {
    if (modal.parentElement !== document.body) {
      document.body.appendChild(modal);
    }
  });

  window.shippingCommon = {
    accountName,
    accountTypeLabel,
    api,
    escapeHtml,
    formatDateTime,
    statusLabel,
  };
})();
