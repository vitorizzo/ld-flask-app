(function () {
  "use strict";

  const page = document.querySelector(".supplier-orders-page");
  if (!page || typeof bootstrap === "undefined") return;

  const modals = new Map();
  document.querySelectorAll(".supplier-orders-modal").forEach((node) => {
    if (node.parentElement !== document.body) document.body.appendChild(node);
    modals.set(`#${node.id}`, bootstrap.Modal.getOrCreateInstance(node));
    node.addEventListener("show.bs.modal", () => document.body.classList.add("supplier-orders-modal-open"));
    node.addEventListener("hidden.bs.modal", () => {
      if (!document.querySelector(".supplier-orders-modal.show")) document.body.classList.remove("supplier-orders-modal-open");
    });
  });

  const definitionModalNode = document.getElementById("supplierGroupModal");
  const definitionModal = modals.get("#supplierGroupModal");
  const definitionForm = document.getElementById("supplierGroupForm");
  const definitionTitle = definitionModalNode.querySelector(".modal-title");
  const definitionSubmit = document.getElementById("supplierGroupSubmit");
  const groupNameInput = document.getElementById("groupName");
  const groupNotesInput = document.getElementById("groupNotes");
  const groupActiveInput = definitionForm.querySelector('input[name="is_active"]');

  function openDefinition(group) {
    const editing = Boolean(group);
    definitionTitle.textContent = editing ? `Modifica gruppo: ${group.name}` : "Definisci nuovo gruppo";
    definitionForm.action = editing ? `/supplier-orders/groups/${group.id}/update` : "/supplier-orders/groups";
    groupNameInput.value = editing ? group.name : "";
    groupNotesInput.value = editing ? group.notes : "";
    groupActiveInput.value = editing ? group.active : "1";
    definitionSubmit.textContent = editing ? "Salva modifiche" : "Crea e gestisci prodotti";
    definitionSubmit.disabled = false;
    definitionModal.show();
  }

  definitionModalNode.addEventListener("shown.bs.modal", () => groupNameInput.focus());
  definitionModalNode.addEventListener("hidden.bs.modal", () => {
    definitionForm.reset();
    definitionSubmit.disabled = false;
  });
  definitionForm.addEventListener("submit", () => { definitionSubmit.disabled = true; });
  document.querySelector("[data-group-create]")?.addEventListener("click", () => openDefinition(null));
  document.querySelectorAll("[data-group-edit]").forEach((button) => button.addEventListener("click", (event) => {
    event.stopPropagation();
    openDefinition({ id: button.dataset.groupId, name: button.dataset.groupName, notes: button.dataset.groupNotes || "", active: button.dataset.groupActive || "1" });
  }));

  document.querySelectorAll("[data-delete-group-form]").forEach((form) => form.addEventListener("submit", (event) => {
    event.stopPropagation();
    if (!window.confirm(`Eliminare il gruppo “${form.dataset.groupName}” e tutte le sue associazioni prodotto?`)) event.preventDefault();
  }));

  document.querySelectorAll("[data-consult-target]").forEach((element) => {
    const open = (event) => {
      if (event.target.closest(".supplier-row-actions") && !event.target.closest("[data-consult-target]")) return;
      event.stopPropagation();
      modals.get(element.dataset.consultTarget)?.show();
    };
    element.addEventListener("click", open);
    if (element.matches("tr")) element.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); open(event); }
    });
  });

  const managerModalNode = document.getElementById("supplierProductsModal");
  const managerModal = modals.get("#supplierProductsModal");
  const managerName = document.getElementById("supplierProductsGroupName");
  const filterInput = document.getElementById("supplierCatalogFilter");
  const catalogList = document.getElementById("supplierCatalogList");
  const selectedList = document.getElementById("supplierSelectedList");
  const catalogCount = document.getElementById("supplierCatalogCount");
  const selectedCount = document.getElementById("supplierSelectedCount");
  const managerStatus = document.getElementById("supplierManagerStatus");
  let currentGroup = null;
  let catalogItems = [];
  let groupItems = [];
  let searchTimer = null;
  let searchSequence = 0;

  function sortItems(items) {
    return [...items].sort((a, b) => (a.description || a.cod_art).localeCompare(b.description || b.cod_art, "it", { sensitivity: "base" }) || a.cod_art.localeCompare(b.cod_art));
  }

  function productOption(item, selected) {
    const option = document.createElement("button");
    option.type = "button";
    option.className = `supplier-product-option${selected ? " is-selected" : ""}`;
    option.dataset.code = item.cod_art;
    option.setAttribute("role", "option");
    option.setAttribute("aria-selected", selected ? "true" : "false");
    const description = document.createElement("strong");
    description.textContent = item.description || item.cod_art;
    const code = document.createElement("span");
    code.textContent = item.cod_art;
    option.append(description, code);
    option.addEventListener("click", () => toggleOption(option));
    option.addEventListener("keydown", (event) => {
      if (event.key === " ") { event.preventDefault(); toggleOption(option); }
    });
    return option;
  }

  function toggleOption(option) {
    const selected = !option.classList.contains("is-selected");
    option.classList.toggle("is-selected", selected);
    option.setAttribute("aria-selected", selected ? "true" : "false");
  }

  function renderManager() {
    const assigned = new Set(groupItems.map((item) => item.cod_art));
    const available = sortItems(catalogItems.filter((item) => !assigned.has(item.cod_art)));
    catalogList.replaceChildren(...available.map((item) => productOption(item, false)));
    selectedList.replaceChildren(...sortItems(groupItems).map((item) => productOption(item, false)));
    if (!available.length) catalogList.innerHTML = '<div class="supplier-product-empty">Nessun prodotto disponibile per il filtro.</div>';
    if (!groupItems.length) selectedList.innerHTML = '<div class="supplier-product-empty">Nessun prodotto associato.</div>';
    catalogCount.textContent = `${available.length} risultati`;
    selectedCount.textContent = `${groupItems.length} prodotti`;
  }

  async function loadGroupItems() {
    const response = await fetch(`/supplier-orders/groups/${currentGroup.id}/items`, { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    groupItems = payload.items || [];
    renderManager();
  }

  async function searchCatalog() {
    const query = filterInput.value.trim();
    if (query.length < 2) { catalogItems = []; renderManager(); return; }
    const sequence = ++searchSequence;
    catalogList.innerHTML = '<div class="supplier-product-empty">Ricerca in corso…</div>';
    try {
      const response = await fetch(`/supplier-orders/api/articles?q=${encodeURIComponent(query)}`, { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      if (sequence !== searchSequence) return;
      catalogItems = payload.items || [];
      renderManager();
    } catch (error) {
      catalogList.innerHTML = '<div class="supplier-product-empty text-danger">Ricerca non disponibile. Riprova.</div>';
      console.error("Supplier catalog search failed", error);
    }
  }

  async function transfer(addCodes, removeCodes) {
    if (!currentGroup || (!addCodes.length && !removeCodes.length)) return;
    managerStatus.textContent = "Salvataggio…";
    try {
      const response = await fetch(`/supplier-orders/groups/${currentGroup.id}/items/batch`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ add_codes: addCodes, remove_codes: removeCodes }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      await loadGroupItems();
      managerStatus.textContent = "Modifiche salvate.";
    } catch (error) {
      managerStatus.textContent = "Salvataggio non riuscito.";
      console.error("Supplier group update failed", error);
    }
  }

  function selectedCodes(list) { return [...list.querySelectorAll(".supplier-product-option.is-selected")].map((item) => item.dataset.code); }
  function allCodes(list) { return [...list.querySelectorAll(".supplier-product-option")].map((item) => item.dataset.code); }
  document.getElementById("supplierAddSelected").addEventListener("click", () => transfer(selectedCodes(catalogList), []));
  document.getElementById("supplierAddAll").addEventListener("click", () => transfer(allCodes(catalogList), []));
  document.getElementById("supplierRemoveSelected").addEventListener("click", () => transfer([], selectedCodes(selectedList)));
  document.getElementById("supplierRemoveAll").addEventListener("click", () => transfer([], allCodes(selectedList)));
  filterInput.addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(searchCatalog, 250); });

  async function openManager(group) {
    currentGroup = group;
    managerName.textContent = group.name;
    filterInput.value = "";
    catalogItems = [];
    groupItems = [];
    managerStatus.textContent = "";
    renderManager();
    managerModal.show();
    try { await loadGroupItems(); } catch (error) { managerStatus.textContent = "Impossibile caricare i prodotti del gruppo."; console.error(error); }
  }

  managerModalNode.addEventListener("shown.bs.modal", () => filterInput.focus());
  document.querySelectorAll("[data-group-manage]").forEach((button) => button.addEventListener("click", (event) => {
    event.stopPropagation();
    openManager({ id: button.dataset.groupId, name: button.dataset.groupName });
  }));

  if (page.dataset.modalAction === "manage" && page.dataset.activeGroupId) {
    const trigger = document.querySelector(`[data-group-manage][data-group-id="${CSS.escape(page.dataset.activeGroupId)}"]`);
    if (trigger) openManager({ id: trigger.dataset.groupId, name: trigger.dataset.groupName });
  }
})();
