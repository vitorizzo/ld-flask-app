(function () {
  "use strict";

  const page = document.querySelector(".supplier-orders-page");
  if (!page || typeof bootstrap === "undefined") return;
  // Read once from the rendered page; remove opening parameters before any reload.
  if(page.dataset.modalAction){const url=new URL(location.href);['modal','group_id','order_id'].forEach(key=>url.searchParams.delete(key));history.replaceState(history.state,'',url);}
  const groupFilter=document.getElementById('supplierGroupFilter');
  const groupRows=[...document.querySelectorAll('[data-group-search]')];
  const filterKey='supplier-group-filter-'+page.dataset.userId;
  try{groupFilter.value=sessionStorage.getItem(filterKey)||'';}catch{}
  function filterGroups(){
    const query=groupFilter.value.trim().toLocaleLowerCase();let count=0;
    groupRows.forEach(row=>{row.hidden=!row.dataset.groupSearch.toLocaleLowerCase().includes(query);if(!row.hidden)count++;});
    document.getElementById('supplierGroupCount').textContent=`${count} di ${groupRows.length} gruppi`;
    document.getElementById('supplierGroupEmpty').hidden=count!==0||!query;
    try{sessionStorage.setItem(filterKey,groupFilter.value);}catch{}
  }
  groupFilter.oninput=filterGroups;filterGroups();

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

  definitionModalNode.addEventListener("shown.bs.modal", () => {
    definitionSubmit.disabled = false;
    groupNameInput.focus();
  });
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
  let subgroups = [];
  let subgroupBusy = false;
  const subgroupTarget = document.getElementById("supplierSubgroupTarget");
  const subgroupName = document.getElementById("supplierSubgroupName");
  const subgroupCreate = document.getElementById("supplierSubgroupCreate");
  const subgroupAssign = document.getElementById("supplierSubgroupAssign");
  const subgroupRename = document.getElementById("supplierSubgroupRename");
  const subgroupDelete = document.getElementById("supplierSubgroupDelete");

  function updateSubgroupActions() {
    subgroupCreate.disabled = subgroupBusy;
    subgroupAssign.disabled = subgroupBusy;
    subgroupRename.disabled = subgroupBusy || !subgroupTarget.value;
    subgroupDelete.disabled = subgroupBusy || !subgroupTarget.value;
  }
  subgroupTarget.addEventListener("change", updateSubgroupActions);

  async function subgroupRequest(path, method, data) {
    if (subgroupBusy || !currentGroup) return false;
    subgroupBusy = true; updateSubgroupActions();
    managerStatus.textContent = "Salvataggio...";
    try {
      const response = await fetch(`/supplier-orders/groups/${currentGroup.id}/${path}`, {
        method, headers: {"Content-Type": "application/json", Accept: "application/json"},
        ...(data ? {body: JSON.stringify(data)} : {}),
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) throw new Error(payload.error || "Salvataggio non riuscito.");
      managerDirty = true;
      await loadGroupItems();
      managerStatus.textContent = "Modifiche salvate.";
      return true;
    } catch (error) {
      managerStatus.textContent = error.message;
      return false;
    } finally {
      subgroupBusy = false; updateSubgroupActions();
    }
  }
  subgroupCreate.addEventListener("click", async () => {
    const name = subgroupName.value.trim();
    if (!name) { managerStatus.textContent = "Inserisci il nome del sottogruppo."; subgroupName.focus(); return; }
    if (await subgroupRequest("subgroups", "POST", {name})) subgroupName.value = "";
  });
  subgroupAssign.addEventListener("click", () => {
    const codes = selectedCodes(selectedList);
    if (!codes.length) { managerStatus.textContent = "Seleziona i prodotti nella lista del gruppo."; return; }
    subgroupRequest("subgroup-assignment", "POST", {codes, subgroup_id: subgroupTarget.value ? Number(subgroupTarget.value) : null});
  });
  subgroupRename.addEventListener("click", () => {
    const row = subgroups.find(s => String(s.id) === subgroupTarget.value);
    if (!row) return;
    const name = window.prompt("Nome del sottogruppo", row.name);
    if (name !== null) subgroupRequest(`subgroups/${row.id}`, "PUT", {name});
  });
  subgroupDelete.addEventListener("click", () => {
    const row = subgroups.find(s => String(s.id) === subgroupTarget.value);
    if (row && window.confirm(`Eliminare il sottogruppo “${row.name}”? I prodotti rimangono nel gruppo, senza sottogruppo.`)) subgroupRequest(`subgroups/${row.id}`, "DELETE");
  });
  managerModalNode.addEventListener("hide.bs.modal", event => { if (subgroupBusy) event.preventDefault(); });
  let searchTimer = null;
  let searchSequence = 0;
  let managerDirty = false;

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

  const settingsNode=document.getElementById('supplierProductSettingsModal');
  const settingsModal=modals.get('#supplierProductSettingsModal');
  const settingsRows=document.getElementById('supplierSettingsRows');
  const settingsStatus=document.getElementById('supplierSettingsStatus');
  let settingsTransition=false,settingsBusy=false,settingsEditors=[];
  function settingsChanged(editor){return editor.code.value!==editor.savedCode||editor.description.value!==editor.savedDescription;}
  function renderSettings(){
    settingsRows.replaceChildren();settingsEditors=[];settingsStatus.textContent='';
    document.getElementById('supplierSettingsGroupName').textContent=currentGroup.name;
    const matrices=new Map();
    sortItems(groupItems).forEach(item=>{if(!matrices.has(item.root))matrices.set(item.root,{...item,codes:[]});matrices.get(item.root).codes.push(item.cod_art);});
    for(const item of matrices.values()){
      const row=document.createElement('tr'),descriptionCell=document.createElement('td'),internalCell=document.createElement('td'),codeCell=document.createElement('td'),actionCell=document.createElement('td');
      const name=document.createElement('strong');name.textContent=item.description||item.root;descriptionCell.append(name);
      const label=document.createElement('label');label.className='form-label small mt-2';label.textContent='Descrizione PDF (facoltativa)';
      const description=document.createElement('input');description.className='form-control';description.maxLength=200;description.value=item.order_description||'';description.setAttribute('aria-label','Descrizione PDF: '+(item.description||item.root));description.placeholder='Usa la descrizione del prodotto';
      label.append(description);descriptionCell.append(label);
      const internal=document.createElement('strong');internal.textContent=item.root;internalCell.append(internal);
      const variants=item.codes.filter(code=>code!==item.root);
      if(variants.length){const small=document.createElement('small');small.className='d-block text-muted';small.textContent='Varianti: '+variants.join(', ');internalCell.append(small);}
      const code=document.createElement('input');code.className='form-control';code.maxLength=80;code.value=item.supplier_code||'';code.placeholder='Facoltativo';code.setAttribute('aria-label','Codice fornitore: '+(item.description||item.root));codeCell.append(code);
      const save=document.createElement('button');save.className='btn btn-info';save.type='button';save.textContent='Salva';
      const status=document.createElement('small');status.className='d-block mt-2';status.setAttribute('role','status');status.setAttribute('aria-live','polite');actionCell.append(save,status);
      const editor={code,description,save,status,savedCode:code.value,savedDescription:description.value};settingsEditors.push(editor);
      save.onclick=async()=>{
        if(settingsBusy||subgroupBusy)return;
        settingsBusy=true;settingsStatus.textContent='Salvataggio…';status.textContent='';
        settingsEditors.forEach(e=>{e.save.disabled=true;e.code.disabled=true;e.description.disabled=true;});
        try{
          const ok=await subgroupRequest('product-settings','POST',{matrix_code:item.root,supplier_code:code.value,order_description:description.value});
          if(ok){code.value=code.value.trim();description.value=description.value.trim();editor.savedCode=code.value;editor.savedDescription=description.value;status.textContent='Salvato.';settingsStatus.textContent='Dati prodotto salvati.';}
          else{status.textContent='Non salvato.';settingsStatus.textContent=managerStatus.textContent||'Salvataggio non riuscito. Riprova.';}
        }finally{settingsBusy=false;settingsEditors.forEach(e=>{e.save.disabled=false;e.code.disabled=false;e.description.disabled=false;});}
      };
      row.append(descriptionCell,internalCell,codeCell,actionCell);settingsRows.append(row);
    }
    if(!settingsEditors.length){const row=document.createElement('tr'),cell=document.createElement('td');cell.colSpan=4;cell.textContent='Nessun prodotto associato al gruppo.';row.append(cell);settingsRows.append(row);}
  }
  document.getElementById('supplierProductSettingsOpen').onclick=()=>{
    if(subgroupBusy||settingsTransition||!currentGroup)return;
    renderSettings();settingsTransition=true;
    managerModalNode.addEventListener('hidden.bs.modal',()=>settingsModal.show(),{once:true});managerModal.hide();
  };
  settingsNode.addEventListener('shown.bs.modal',()=>{settingsBusy=false;settingsEditors.forEach(e=>{e.save.disabled=false;e.code.disabled=false;e.description.disabled=false;});settingsEditors[0]?.code.focus();});
  settingsNode.addEventListener('hide.bs.modal',event=>{
    if(settingsBusy){event.preventDefault();return;}
    if(settingsEditors.some(settingsChanged)&&!window.confirm('Ci sono modifiche non salvate. Tornare ai prodotti e scartarle?'))event.preventDefault();
  });
  settingsNode.addEventListener('hidden.bs.modal',()=>{
    settingsEditors.forEach(e=>{e.save.onclick=null;});settingsEditors=[];settingsRows.replaceChildren();settingsStatus.textContent='';settingsBusy=false;settingsTransition=false;managerModal.show();
  });
  function renderManager() {

    const assigned = new Set(groupItems.map((item) => item.cod_art));
    const available = sortItems(catalogItems.filter((item) => !assigned.has(item.cod_art)));
    catalogList.replaceChildren(...available.map((item) => productOption(item, false)));
    selectedList.replaceChildren();
    for (const subgroup of [...subgroups, {id: null, name: "Senza sottogruppo"}]) {
      const items = sortItems(groupItems.filter(item => (item.subgroup_id ?? null) === subgroup.id));
      if (!items.length) continue;
      if (subgroups.length) {
        const heading = document.createElement("div");
        heading.className = "supplier-subgroup-heading";
        heading.setAttribute("role", "presentation");
        heading.textContent = subgroup.name;
        selectedList.append(heading);
      }
      selectedList.append(...items.map(item => productOption(item, false)));
    }
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
    subgroups = payload.subgroups || [];
    const selected = subgroupTarget.value;
    subgroupTarget.replaceChildren(new Option("Senza sottogruppo", ""), ...subgroups.map(row => new Option(row.name, String(row.id))));
    if (subgroups.some(row => String(row.id) === selected)) subgroupTarget.value = selected;
    updateSubgroupActions();
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
      managerDirty = true;
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
    subgroups = [];
    subgroupName.value = "";
    subgroupTarget.replaceChildren(new Option("Senza sottogruppo", ""));
    updateSubgroupActions();
    managerStatus.textContent = "";
    managerDirty = false;
    renderManager();
    managerModal.show();
    try { await loadGroupItems(); } catch (error) { managerStatus.textContent = "Impossibile caricare i prodotti del gruppo."; console.error(error); }
  }

  managerModalNode.addEventListener("shown.bs.modal", () => { updateSubgroupActions(); filterInput.focus(); });
  managerModalNode.addEventListener("hidden.bs.modal", () => {
    if (managerDirty && !settingsTransition) window.location.reload();
  });
  document.querySelectorAll("[data-group-manage]").forEach((button) => button.addEventListener("click", (event) => {
    event.stopPropagation();
    openManager({ id: button.dataset.groupId, name: button.dataset.groupName });
  }));

  if (page.dataset.modalAction === "manage" && page.dataset.activeGroupId) {
    const trigger = document.querySelector(`[data-group-manage][data-group-id="${CSS.escape(page.dataset.activeGroupId)}"]`);
    if (trigger) openManager({ id: trigger.dataset.groupId, name: trigger.dataset.groupName });
  }
  if (page.dataset.modalAction === "order" && page.dataset.activeGroupId) {
    modals.get(`#supplierStockModal${page.dataset.activeGroupId}`)?.show();
  }

  document.querySelectorAll("[data-matrix-rename]").forEach((button) => button.addEventListener("click", async (event) => {
    event.preventDefault();
    event.stopPropagation();
    const proposed = window.prompt(
      `Nome del raggruppamento ${button.dataset.matrixCode}.\nLascia vuoto per ripristinare il nome dell'ultima variante.`,
      button.dataset.currentName || "",
    );
    if (proposed === null) return;
    button.disabled = true;
    try {
      const response = await fetch(`/supplier-orders/groups/${button.dataset.groupId}/matrix-name`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ matrix_code: button.dataset.matrixCode, display_name: proposed.trim() }),
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) throw new Error(payload.error || `HTTP ${response.status}`);
      const displayedName = payload.display_name || button.dataset.defaultName;
      button.closest(".supplier-matrix-heading")?.querySelector("[data-matrix-title]")?.replaceChildren(displayedName);
      button.dataset.currentName = displayedName;
    } catch (error) {
      window.alert(`Impossibile rinominare il raggruppamento: ${error.message}`);
    } finally {
      button.disabled = false;
    }
  }));
})();
