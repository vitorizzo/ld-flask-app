(function () {
  "use strict";

  const root = document.querySelector("[data-order-id]");
  if (!root) return;

  const orderId = root.dataset.orderId;
  const extra = document.querySelector("[data-detail-extra]");
  const statusLabel = document.querySelector("[data-current-status]");

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

  function renderDetails(data) {
    if (!extra) return;
    const events = []
      .concat(Array.isArray(data.children) ? data.children : [])
      .concat(Array.isArray(data.thread_notes) ? data.thread_notes.map((note) => ({ ...note, label: "nota", ts: note.at })) : []);
    const attachments = Array.isArray(data.attachments) ? data.attachments : [];

    const eventHtml = events.length
      ? `<div class="order-detail__events">${events
          .map(
            (event) => `
              <div class="order-detail__event">
                <div class="order-detail__event-label">${escapeHtml(event.label || "")}</div>
                <div>${escapeHtml(event.text || "")}</div>
              </div>
            `
          )
          .join("")}</div>`
      : `<div class="text-muted">Nessun dettaglio aggiuntivo.</div>`;

    const attachmentHtml = attachments.length
      ? `
        <div class="order-detail__panel-title mt-3">Allegati</div>
        <div class="order-detail__attachments">
          ${attachments
            .map((attachment) => {
              const title = escapeHtml(attachment.title || attachment.name || "Allegato");
              const url = escapeHtml(attachment.url || "#");
              const thumb = escapeHtml(attachment.thumb_url || attachment.url || "");
              const image = attachment.is_image && thumb ? `<img src="${thumb}" alt="${title}" loading="lazy">` : `<i class="fa-solid fa-paperclip"></i>`;
              return `<a class="order-detail__attachment" href="${url}" target="_blank" rel="noopener">${image}<span>${title}</span></a>`;
            })
            .join("")}
        </div>
      `
      : "";

    extra.innerHTML = `<div class="order-detail__panel-title">Dettagli</div>${eventHtml}${attachmentHtml}`;
  }

  async function loadDetails() {
    const data = await api(`/kiosk/api/order/${orderId}`);
    renderDetails(data);
  }

  async function setStatus(status) {
    const buttons = Array.from(document.querySelectorAll("[data-status]"));
    buttons.forEach((button) => {
      button.disabled = true;
    });
    try {
      await api(`/kiosk/api/order/${orderId}/set-status`, {
        method: "POST",
        body: JSON.stringify({ status }),
      });
      buttons.forEach((button) => {
        button.classList.toggle("is-active", button.dataset.status === status);
      });
      if (statusLabel) statusLabel.textContent = status;
    } catch (err) {
      alert(err.message || "Errore cambio stato");
    } finally {
      buttons.forEach((button) => {
        button.disabled = false;
      });
    }
  }

  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-status]");
    if (!button || button.classList.contains("is-active")) return;
    setStatus(button.dataset.status);
  });

  loadDetails().catch((err) => {
    if (extra) extra.innerHTML = `<div class="text-danger">Errore caricamento dettagli: ${escapeHtml(err.message || err)}</div>`;
  });
})();
