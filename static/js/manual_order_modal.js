document.addEventListener("DOMContentLoaded", () => {
  const modalElement = document.getElementById("newOrderModal");
  const form = document.getElementById("newOrderForm");
  const triggers = document.querySelectorAll("[data-manual-order-open]");
  if (!modalElement || !form || !triggers.length || !window.bootstrap) return;

  if (modalElement.parentElement !== document.body) document.body.appendChild(modalElement);
  const modal = bootstrap.Modal.getOrCreateInstance(modalElement);
  const destination = document.getElementById("newOrderDestination");
  const deliveryDate = document.getElementById("newOrderDeliveryDate");
  const destinationHelp = document.getElementById("newOrderDestinationHelp");
  const customerSearch = document.getElementById("newOrderCustomerSearch");
  const customerSelect = document.getElementById("newOrderCustomerSelect");
  const note = document.getElementById("newOrderNote");
  const listDone = document.getElementById("newOrderListDone");
  const files = document.getElementById("newOrderFiles");
  const feedback = document.getElementById("newOrderError");
  const saveButton = document.getElementById("newOrderSave");
  let searchTimer = null;
  let customerRequest = 0;

  function setFeedback(message = "", kind = "danger") {
    feedback.textContent = message;
    feedback.classList.toggle("d-none", !message);
    feedback.classList.toggle("alert-danger", kind === "danger");
    feedback.classList.toggle("alert-success", kind === "success");
  }

  async function requestJson(url, options = {}) {
    const response = await fetch(url, { credentials: "same-origin", cache: "no-store", ...options });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    return payload;
  }

  function applyDestinationDate() {
    const option = destination.selectedOptions[0];
    if (!option) return;
    deliveryDate.value = option.dataset.deliveryDate || "";
    destinationHelp.textContent = option.value === "direct"
      ? "Consegna diretta proposta per oggi; puoi modificare la data."
      : "Data proposta in base al prossimo giro; puoi modificarla.";
  }

  async function loadDestinations() {
    const payload = await requestJson("/route-orders/api/manual-order-destinations");
    destination.replaceChildren();
    const direct = new Option("Diretto", "direct");
    direct.dataset.deliveryDate = payload.today || "";
    destination.add(direct);
    (payload.destinations || []).forEach(route => {
      const option = new Option(route.name || "Giro", `route:${route.id}`);
      option.dataset.routeId = route.id;
      option.dataset.deliveryDate = route.next_delivery_date || "";
      destination.add(option);
    });
    applyDestinationDate();
  }

  async function loadCustomers(query = "") {
    const requestId = ++customerRequest;
    customerSelect.replaceChildren(new Option("Ricerca in corso...", ""));
    const payload = await requestJson(`/route-orders/api/customers?q=${encodeURIComponent(query)}`);
    if (requestId !== customerRequest) return;

    customerSelect.replaceChildren();
    const freeName = query.trim();
    customerSelect.add(new Option(
      freeName ? `Nessuna associazione — usa "${freeName}"` : "Nessuna associazione — scrivi un nome sopra",
      ""
    ));
    (payload.customers || []).forEach(customer => {
      const details = [customer.source_code ? `cod. ${customer.source_code}` : "", customer.city || ""]
        .filter(Boolean).join(" · ");
      customerSelect.add(new Option(`${customer.display || "Cliente"}${details ? ` — ${details}` : ""}`, customer.id));
    });
  }

  async function openModal(event) {
    event?.preventDefault();
    form.reset();
    clearTimeout(searchTimer);
    customerRequest += 1;
    customerSelect.replaceChildren(new Option("Caricamento clienti...", ""));
    setFeedback();
    modal.show();
    try {
      await Promise.all([loadDestinations(), loadCustomers()]);
      customerSearch.focus();
    } catch (error) {
      setFeedback(`Caricamento non riuscito: ${error.message || error}`);
    }
  }

  triggers.forEach(trigger => trigger.addEventListener("click", openModal));
  destination.addEventListener("change", applyDestinationDate);
  customerSearch.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      loadCustomers(customerSearch.value).catch(error => {
        setFeedback(`Ricerca clienti non disponibile: ${error.message || error}`);
      });
    }, 250);
  });

  form.addEventListener("submit", async event => {
    event.preventDefault();
    const selectedDestination = destination.selectedOptions[0];
    const registryId = customerSelect.value;
    const customerName = customerSearch.value.trim();
    const orderNote = note.value.trim();
    if (!selectedDestination) return setFeedback("Seleziona diretto oppure un giro.");
    if (!registryId && !customerName) return setFeedback("Seleziona un cliente oppure scrivi un nome.");
    if (!orderNote) return setFeedback("Inserisci il testo dell'ordine.");
    if (!deliveryDate.value) return setFeedback("Inserisci la data di consegna.");

    const payload = new FormData();
    if (registryId) payload.append("registry_id", registryId);
    payload.append("customer_name", customerName);
    payload.append("order_note", orderNote);
    payload.append("planned_delivery_at", deliveryDate.value);
    payload.append("list_done", listDone.checked ? "1" : "0");
    if (selectedDestination.dataset.routeId) payload.append("route_id", selectedDestination.dataset.routeId);
    Array.from(files.files || []).forEach(file => payload.append("files", file));

    saveButton.disabled = true;
    saveButton.innerHTML = '<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span> Invio...';
    setFeedback();
    try {
      await requestJson("/route-orders/api/manual-orders", { method: "POST", body: payload });
      setFeedback("Ordine inserito correttamente.", "success");
      window.setTimeout(() => modal.hide(), 650);
    } catch (error) {
      setFeedback(`Inserimento non riuscito: ${error.message || error}`);
    } finally {
      saveButton.disabled = false;
      saveButton.innerHTML = '<i class="fa-solid fa-paper-plane me-1" aria-hidden="true"></i> Inserisci ordine';
    }
  });

  modalElement.addEventListener("hidden.bs.modal", () => {
    clearTimeout(searchTimer);
    customerRequest += 1;
    setFeedback();
  });
});
