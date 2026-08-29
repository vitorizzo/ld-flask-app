(function () {
  "use strict";

  const page = document.querySelector(".payment-links-page");
  const modalNode = document.getElementById("paymentLinkModal");
  if (!page || !modalNode) return;

  // Le modali dentro app-shell ereditano uno stacking context che le rende inattive.
  document.body.appendChild(modalNode);
  const modal = bootstrap.Modal.getOrCreateInstance(modalNode);
  const form = document.getElementById("paymentLinkForm");
  const coreFields = document.getElementById("paymentLinkCoreFields");
  const amount = document.getElementById("paymentLinkAmount");
  const description = document.getElementById("paymentLinkDescription");
  const existingId = document.getElementById("paymentLinkExistingId");
  const emailFields = document.getElementById("paymentLinkEmailFields");
  const searchFields = document.getElementById("paymentLinkSearchFields");
  const recipientName = document.getElementById("paymentLinkRecipientName");
  const recipientEmail = document.getElementById("paymentLinkRecipientEmail");
  const recipientSearch = document.getElementById("paymentLinkRecipientSearch");
  const recipientResults = document.getElementById("paymentLinkRecipientResults");
  const recipientId = document.getElementById("paymentLinkRecipientId");
  const recipientContactId = document.getElementById("paymentLinkRecipientContactId");
  const recipientSelected = document.getElementById("paymentLinkRecipientSelected");
  const alertNode = document.getElementById("paymentLinkModalAlert");
  const resultNode = document.getElementById("paymentLinkResult");
  const resultUrl = document.getElementById("paymentLinkResultUrl");
  const resultSummary = document.getElementById("paymentLinkResultSummary");
  const deliveryStatus = document.getElementById("paymentLinkDeliveryStatus");
  const submitButton = document.getElementById("generatePaymentLinkButton");
  const submitLabel = submitButton.querySelector(".button-label");
  const spinner = submitButton.querySelector(".spinner-border");
  const modalTitle = document.getElementById("paymentLinkModalLabel");
  let searchTimer = null;
  let searchController = null;
  let selectedRecipient = null;

  function recipientType() {
    return form.querySelector('input[name="paymentLinkRecipientType"]:checked').value;
  }

  function showAlert(message, type) {
    alertNode.className = `alert alert-${type || "danger"}`;
    alertNode.textContent = message;
  }

  function clearAlert() {
    alertNode.className = "alert d-none";
    alertNode.textContent = "";
  }

  function setBusy(busy) {
    submitButton.disabled = busy;
    spinner.classList.toggle("d-none", !busy);
  }

  function clearRecipientSelection() {
    selectedRecipient = null;
    recipientId.value = "";
    recipientContactId.value = "";
    recipientSelected.classList.add("d-none");
    recipientSelected.innerHTML = "";
  }

  function updateRecipientFields() {
    const type = recipientType();
    emailFields.classList.toggle("d-none", type !== "email");
    searchFields.classList.toggle("d-none", type !== "user" && type !== "customer");
    recipientResults.innerHTML = "";
    recipientSearch.value = "";
    clearRecipientSelection();
    if (existingId.value && type === "none") {
      form.querySelector('input[name="paymentLinkRecipientType"][value="email"]').checked = true;
      return updateRecipientFields();
    }
  }

  function resetModal() {
    form.reset();
    existingId.value = "";
    coreFields.classList.remove("d-none");
    amount.disabled = false;
    description.disabled = false;
    modalTitle.textContent = "Genera link di pagamento";
    submitLabel.textContent = "Genera link";
    submitButton.classList.remove("d-none");
    resultNode.classList.add("d-none");
    resultUrl.value = "";
    deliveryStatus.textContent = "";
    clearAlert();
    updateRecipientFields();
  }

  document.getElementById("newPaymentLinkButton")?.addEventListener("click", resetModal);
  form.querySelectorAll('input[name="paymentLinkRecipientType"]').forEach(input => input.addEventListener("change", updateRecipientFields));

  function escapeHtml(value) {
    const node = document.createElement("div");
    node.textContent = String(value || "");
    return node.innerHTML;
  }

  function selectRecipient(item, contact) {
    selectedRecipient = item;
    recipientId.value = item.id;
    recipientContactId.value = contact?.id || "";
    const email = contact?.email || item.email || "";
    recipientSelected.innerHTML = `<strong>${escapeHtml(item.label)}</strong><span>${escapeHtml(email)}</span><button type="button" class="btn-close" aria-label="Rimuovi"></button>`;
    recipientSelected.classList.remove("d-none");
    recipientSelected.querySelector("button").addEventListener("click", clearRecipientSelection);
    recipientResults.innerHTML = "";
    recipientSearch.value = "";
  }

  function renderResults(items, type) {
    recipientResults.innerHTML = "";
    if (!items.length) {
      recipientResults.innerHTML = '<div class="recipient-empty">Nessun destinatario con email trovato.</div>';
      return;
    }
    items.forEach(item => {
      if (type === "customer") {
        item.contacts.forEach(contact => {
          const button = document.createElement("button");
          button.type = "button";
          button.className = "recipient-result";
          button.innerHTML = `<strong>${escapeHtml(item.label)}</strong><span>Cod. ${escapeHtml(item.code)} · ${escapeHtml(contact.label)}: ${escapeHtml(contact.email)}</span>`;
          button.addEventListener("click", () => selectRecipient(item, contact));
          recipientResults.appendChild(button);
        });
      } else {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "recipient-result";
        button.innerHTML = `<strong>${escapeHtml(item.label)}</strong><span>${escapeHtml(item.email)}</span>`;
        button.addEventListener("click", () => selectRecipient(item));
        recipientResults.appendChild(button);
      }
    });
  }

  recipientSearch.addEventListener("input", function () {
    clearTimeout(searchTimer);
    if (searchController) searchController.abort();
    const query = recipientSearch.value.trim();
    if (query.length < 2) {
      recipientResults.innerHTML = "";
      return;
    }
    searchTimer = setTimeout(async () => {
      searchController = new AbortController();
      const type = recipientType();
      recipientResults.innerHTML = '<div class="recipient-empty"><span class="spinner-border spinner-border-sm me-2"></span>Ricerca…</div>';
      try {
        const url = new URL(page.dataset.searchUrl, window.location.origin);
        url.searchParams.set("type", type);
        url.searchParams.set("q", query);
        const response = await fetch(url, {headers: {Accept: "application/json"}, signal: searchController.signal});
        const data = await response.json();
        if (!response.ok || !data.ok) throw new Error(data.error || "Ricerca non riuscita.");
        renderResults(data.items || [], type);
      } catch (error) {
        if (error.name !== "AbortError") recipientResults.innerHTML = `<div class="recipient-empty text-danger">${escapeHtml(error.message)}</div>`;
      }
    }, 280);
  });

  function requestPayload() {
    const type = recipientType();
    const payload = {recipient_type: type};
    if (!existingId.value) {
      payload.amount = amount.value;
      payload.description = description.value.trim();
    }
    if (type === "email") {
      payload.recipient_name = recipientName.value.trim();
      payload.recipient_email = recipientEmail.value.trim();
    } else if (type === "user" || type === "customer") {
      payload.recipient_id = recipientId.value;
      payload.recipient_contact_id = recipientContactId.value || undefined;
    }
    return payload;
  }

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    clearAlert();
    if (!existingId.value && (!amount.value.trim() || !description.value.trim())) {
      showAlert("Inserisci importo e descrizione.", "warning");
      return;
    }
    const type = recipientType();
    if (type === "email" && !recipientEmail.value.trim()) {
      showAlert("Inserisci l'indirizzo email del destinatario.", "warning");
      return;
    }
    if ((type === "user" || type === "customer") && !recipientId.value) {
      showAlert("Cerca e seleziona un destinatario.", "warning");
      return;
    }
    setBusy(true);
    try {
      const endpoint = existingId.value ? `/administration/payment-links/${existingId.value}/send` : page.dataset.createUrl;
      const response = await fetch(endpoint, {
        method: "POST",
        headers: {"Content-Type": "application/json", Accept: "application/json"},
        body: JSON.stringify(requestPayload()),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || "Operazione non riuscita.");
      if (existingId.value) {
        showAlert(`Invio accodato per ${data.delivery.email}.`, "success");
        submitButton.classList.add("d-none");
      } else {
        resultUrl.value = data.item.url;
        resultSummary.textContent = `${data.item.description} · ${Number(data.item.amount).toLocaleString("it-IT", {style: "currency", currency: "EUR"})}`;
        deliveryStatus.textContent = data.item.delivery ? `Invio email accodato per ${data.item.delivery.email}.` : "Il link è pronto per essere copiato e condiviso.";
        form.classList.add("d-none");
        resultNode.classList.remove("d-none");
        submitButton.classList.add("d-none");
      }
    } catch (error) {
      showAlert(error.message, "danger");
    } finally {
      setBusy(false);
    }
  });

  async function copyText(text, button) {
    try {
      await navigator.clipboard.writeText(text);
    } catch (_) {
      const helper = document.createElement("textarea");
      helper.value = text;
      helper.style.position = "fixed";
      helper.style.opacity = "0";
      document.body.appendChild(helper);
      helper.select();
      document.execCommand("copy");
      helper.remove();
    }
    const original = button.innerHTML;
    button.innerHTML = '<i class="fa-solid fa-check me-1"></i>Copiato';
    setTimeout(() => { button.innerHTML = original; }, 1800);
  }

  document.getElementById("copyGeneratedPaymentLink").addEventListener("click", event => copyText(resultUrl.value, event.currentTarget));
  document.querySelectorAll(".copy-payment-link").forEach(button => button.addEventListener("click", () => copyText(button.dataset.url, button)));
  document.querySelectorAll(".send-payment-link").forEach(button => button.addEventListener("click", function () {
    resetModal();
    existingId.value = button.dataset.id;
    coreFields.classList.add("d-none");
    modalTitle.textContent = "Invia link di pagamento";
    submitLabel.textContent = "Accoda invio";
    form.querySelector('input[name="paymentLinkRecipientType"][value="email"]').checked = true;
    updateRecipientFields();
    description.value = button.dataset.description || "";
    amount.value = button.dataset.amount || "";
    modal.show();
  }));

  modalNode.addEventListener("hidden.bs.modal", function () {
    form.classList.remove("d-none");
    resetModal();
  });
})();
