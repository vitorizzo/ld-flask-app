/* global Sortable, bootstrap */

if (window.__menuMgmtInitDone) {
  console.warn("menu_management.js gia' inizializzato: skip.");
} else {
  window.__menuMgmtInitDone = true;

  let modalSubmitting = false;
  let sortables = [];
  let hasPendingApply = false;
  const collapsedMenuIds = new Set();

  async function fetchMenuStructure() {
    const res = await fetch("/settings/get_menu_structure", { credentials: "same-origin" });
    if (!res.ok) throw new Error("get_menu_structure failed");
    return await res.json();
  }

  async function loadMenuData(id) {
    const res = await fetch(`/settings/menu/${id}`, { credentials: "same-origin" });
    if (!res.ok) throw new Error("menu load failed");
    return await res.json();
  }

  async function apiDeleteMenu(id, cascade = false) {
    const res = await fetch(`/settings/delete_menu/${id}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ cascade })
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) {
      const err = new Error(data.error || "delete failed");
      err.code = data.code;
      throw err;
    }
  }

  async function apiToggleMenuActive(id) {
    const res = await fetch(`/settings/toggle_menu_active/${id}`, {
      method: "POST",
      credentials: "same-origin"
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) throw new Error("toggle failed");
  }

  async function apiToggleMenuVisible(id) {
    const res = await fetch(`/settings/toggle_menu_visible/${id}`, {
      method: "POST",
      credentials: "same-origin"
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) throw new Error(data.error || "toggle visible failed");
  }

  async function createMenu(payload) {
    const res = await fetch("/settings/create_menu", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(payload)
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) throw new Error(data.error || "create failed");
  }

  async function updateMenuJson(payload) {
    const res = await fetch("/settings/update_menu_json", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(payload)
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) throw new Error(data.error || "update failed");
  }

  async function apiReorderMenus(items) {
    const res = await fetch("/settings/reorder_menus", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ items })
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) throw new Error(data.error || "reorder failed");
  }

  function setPendingApply(value = true) {
    hasPendingApply = !!value;
    const btn = document.getElementById("btnApplyMenuChanges");
    if (!btn) return;
    btn.disabled = !hasPendingApply;
    btn.classList.toggle("btn-info", hasPendingApply);
    btn.classList.toggle("btn-outline-info", !hasPendingApply);
  }

  function buildTree(items) {
    const map = new Map();
    items.forEach(i => map.set(i.id, { ...i, children: [] }));

    const roots = [];
    map.forEach(node => {
      if (node.parent_id == null) roots.push(node);
      else {
        const p = map.get(node.parent_id);
        p ? p.children.push(node) : roots.push(node);
      }
    });

    const sortRec = nodes => {
      nodes.sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));
      nodes.forEach(n => sortRec(n.children));
    };
    sortRec(roots);
    return roots;
  }

  function escapeHtml(str) {
    return String(str)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;");
  }

  function renderTree(nodes) {
    const ul = document.createElement("ul");
    ul.className = "menu-tree list-unstyled ms-2";

    nodes.forEach(n => {
      const li = document.createElement("li");
      li.className = "menu-node mb-1";
      li.dataset.id = n.id;

      const isActive = !!n.is_active;
      const isVisible = (n.is_visible ?? true) === true;
      const isSeparator = (n.item_type || "link") === "separator";
      const title = isSeparator ? "Separatore" : escapeHtml(n.name ?? "");
      const route = !isSeparator && n.route ? escapeHtml(n.route) : "";
      const childCount = Array.isArray(n.children) ? n.children.length : 0;
      const isCollapsed = collapsedMenuIds.has(Number(n.id));
      const statusBadges = [
        isSeparator ? `<span class="badge text-bg-secondary">separatore</span>` : "",
        isVisible ? "" : `<span class="badge text-bg-warning">nascosto</span>`,
        isActive ? "" : `<span class="badge text-bg-secondary">non attivo</span>`
      ].filter(Boolean).join(" ");

      li.innerHTML = `
        <div class="menu-row d-flex align-items-center gap-2 ${isActive ? "" : "menu-row-inactive"} ${isVisible ? "" : "menu-row-hidden"} ${isSeparator ? "menu-row-separator" : ""}">
          <span class="menu-handle" title="Trascina per riordinare">
            <i class="fa-solid fa-grip-vertical"></i>
          </span>

          ${childCount ? `<button type="button" class="menu-collapse-btn" data-action="toggle-collapse" data-id="${n.id}" aria-expanded="${isCollapsed ? "false" : "true"}" title="${isCollapsed ? "Espandi" : "Comprimi"}"><i class="fa-solid fa-chevron-${isCollapsed ? "right" : "down"}"></i></button>` : `<span class="menu-collapse-spacer"></span>`}

          <span class="menu-node-title menu-title">
            <span class="menu-title-main">
              <i class="${isSeparator ? "fa-solid fa-grip-lines" : "fa-solid fa-link"}"></i>
              <span class="menu-title-text">${title}</span>
            </span>
            <span class="menu-meta">
              <span class="badge text-bg-light">peso ${n.weight ?? 0}</span>
              ${childCount ? `<span class="badge text-bg-light">${childCount} sotto-menu</span>` : ""}
              ${route ? `<span class="menu-route">${route}</span>` : ""}
              ${statusBadges}
            </span>
          </span>

          <div class="menu-row-actions btn-group btn-group-sm ms-auto" role="group" aria-label="Azioni menu">
            <button type="button" class="btn btn-outline-secondary" data-action="add-child" data-id="${n.id}" title="Aggiungi sotto-menu">
              <i class="fa-solid fa-plus"></i>
            </button>
            <button type="button" class="btn btn-outline-secondary" data-action="add-separator-child" data-id="${n.id}" title="Aggiungi separatore">
              <i class="fa-solid fa-grip-lines"></i>
            </button>
            <button type="button" class="btn btn-outline-info" data-action="edit" data-id="${n.id}" title="Modifica">
              <i class="fa-solid fa-pen"></i>
            </button>
            <button type="button" class="btn btn-outline-secondary" data-action="toggle-active" data-id="${n.id}" title="${isActive ? "Disattiva" : "Attiva"}">
              <i class="fa-solid fa-power-off"></i>
            </button>
            ${isActive
              ? `<button type="button" class="btn btn-outline-secondary" disabled title="Visibile fisso"><i class="fa-solid fa-eye"></i></button>`
              : `<button type="button" class="btn btn-outline-secondary" data-action="toggle-visible" data-id="${n.id}" title="${isVisible ? "Nascondi" : "Mostra"}"><i class="fa-solid ${isVisible ? "fa-eye-slash" : "fa-eye"}"></i></button>`
            }
            <button type="button" class="btn btn-outline-danger" data-action="delete" data-id="${n.id}" title="Elimina">
              <i class="fa-solid fa-trash"></i>
            </button>
          </div>
        </div>
      `;

      const childTree = renderTree(n.children || []);
      childTree.dataset.parentId = n.id;
      childTree.classList.toggle("menu-tree-collapsed", isCollapsed);
      li.appendChild(childTree);
      ul.appendChild(li);
    });

    return ul;
  }

  function destroySortables() {
    sortables.forEach(s => s.destroy());
    sortables = [];
  }

  function initSortable(root) {
    destroySortables();
    const lists = root.querySelectorAll(".menu-tree");
    lists.forEach(ul => {
      const s = new Sortable(ul, {
        group: { name: "menus", pull: true, put: true },
        animation: 150,
        handle: ".menu-handle",
        fallbackOnBody: true,
        emptyInsertThreshold: 28,
        swapThreshold: 0.65,
        ghostClass: "menu-drop-placeholder",
        chosenClass: "menu-drag-chosen",
        dragClass: "menu-dragging",
        onMove(evt) {
          return !evt.dragged.contains(evt.related);
        },
        async onEnd() {
          await persistTreeOrder(root);
        }
      });
      sortables.push(s);
    });
  }

  function getDirectMenuNodes(ul) {
    return Array.from(ul.children).filter(el => el.matches("li.menu-node"));
  }

  function collectTreeOrder(root) {
    const items = [];
    const rootUl = root.querySelector(":scope > .menu-tree");
    if (!rootUl) return items;

    function walk(ul, parentId) {
      getDirectMenuNodes(ul).forEach((li, index) => {
        const id = Number(li.dataset.id);
        if (!Number.isFinite(id)) return;
        items.push({ id, parent_id: parentId, sort_order: index + 1 });
        const childUl = li.querySelector(":scope > .menu-tree");
        if (childUl) walk(childUl, id);
      });
    }

    walk(rootUl, null);
    return items;
  }

  async function persistTreeOrder(root) {
    const items = collectTreeOrder(root);
    if (!items.length) return;
    try {
      await apiReorderMenus(items);
      setPendingApply(true);
      await renderAll();
    } catch (err) {
      console.error("REORDER:", err);
      alert(err.message || "Errore salvataggio ordine menu");
      await renderAll();
    }
  }

  function bindActions(host) {
    host.addEventListener("click", async (e) => {
      const actionEl = e.target.closest("[data-action]");
      if (!actionEl) return;
      e.preventDefault();

      const id = Number(actionEl.dataset.id);
      const action = actionEl.dataset.action;

      if (action === "toggle-collapse") {
        if (collapsedMenuIds.has(id)) collapsedMenuIds.delete(id);
        else collapsedMenuIds.add(id);
        const node = actionEl.closest(".menu-node");
        const childTree = node?.querySelector(":scope > .menu-tree");
        childTree?.classList.toggle("menu-tree-collapsed", collapsedMenuIds.has(id));
        actionEl.setAttribute("aria-expanded", collapsedMenuIds.has(id) ? "false" : "true");
        const icon = actionEl.querySelector("i");
        if (icon) icon.className = `fa-solid fa-chevron-${collapsedMenuIds.has(id) ? "right" : "down"}`;
        return;
      }

      if (action === "add-child") {
        openModal({ mode: "add-child", parentId: id });
        return;
      }

      if (action === "add-separator-child") {
        openModal({
          mode: "add-separator",
          parentId: id,
          menu: { item_type: "separator", name: "", route: null, is_active: true, is_visible: true }
        });
        return;
      }

      if (action === "toggle-active") {
        await apiToggleMenuActive(id);
        setPendingApply(true);
        await renderAll();
        return;
      }

      if (action === "toggle-visible") {
        await apiToggleMenuVisible(id);
        setPendingApply(true);
        await renderAll();
        return;
      }

      if (action === "delete") {
        if (!confirm("Eliminare questo menu?")) return;
        let deleted = false;
        try {
          await apiDeleteMenu(id, false);
          deleted = true;
        } catch (err) {
          if (err.code !== "HAS_CHILDREN") throw err;
          const cascade = confirm("Questo menu contiene sotto-menu. Eliminare anche tutti i sotto-menu?");
          if (!cascade) return;
          await apiDeleteMenu(id, true);
          deleted = true;
        } finally {
          if (deleted) setPendingApply(true);
          await renderAll();
        }
        return;
      }

      if (action === "edit") {
        const data = await loadMenuData(id);
        openModal({ mode: "edit", menu: data });
      }
    });
  }

  async function renderAll() {
    const host = document.getElementById("menuTree");
    if (!host) return;
    const data = await fetchMenuStructure();
    const tree = buildTree(data);
    host.innerHTML = "";
    host.appendChild(renderTree(tree));
    initSortable(host);
  }

  function openModal({ mode, menu, parentId }) {
    document.getElementById("mm_menu_id").value = menu?.id ?? "";
    const pid = (parentId ?? menu?.parent_id ?? null);
    document.getElementById("mm_parent_id").value = (pid === null) ? "" : String(pid);
    document.getElementById("mm_item_type").value = menu?.item_type ?? "link";
    document.getElementById("mm_name").value = menu?.name ?? "";
    document.getElementById("mm_route").value = menu?.route ?? "";
    document.getElementById("mm_weight").value = menu?.weight ?? 0;
    document.getElementById("mm_is_active").checked = (menu?.is_active ?? true) === true;
    document.getElementById("mm_is_visible").checked = (menu?.is_visible ?? true) === true;
    syncRoleSelectFromWeight(menu?.weight ?? 0);
    updateTypeFields();
    updateVisibilityFields();

    document.getElementById("menuModalTitle").textContent =
      (mode === "add-root") ? "Crea menu (root)" :
      (mode === "add-separator") ? "Crea separatore" :
      (mode === "add-child") ? "Crea sotto-menu" :
      "Modifica menu";

    bootstrap.Modal.getOrCreateInstance(document.getElementById("menuModal")).show();
  }

  function syncRoleSelectFromWeight(weight) {
    const roleSelect = document.getElementById("mm_role_weight");
    const customWrap = document.getElementById("mm_weight_custom_wrap");
    const weightInput = document.getElementById("mm_weight");
    if (!roleSelect || !customWrap || !weightInput) return;
    const value = String(Number(weight || 0));
    const hasOption = Array.from(roleSelect.options).some(opt => opt.value === value);
    roleSelect.value = hasOption ? value : "__custom__";
    customWrap.style.display = hasOption ? "none" : "";
    weightInput.value = value;
  }

  function bindRoleWeight() {
    const roleSelect = document.getElementById("mm_role_weight");
    const customWrap = document.getElementById("mm_weight_custom_wrap");
    const weightInput = document.getElementById("mm_weight");
    if (!roleSelect || !customWrap || !weightInput) return;
    roleSelect.addEventListener("change", () => {
      if (roleSelect.value === "__custom__") {
        customWrap.style.display = "";
        weightInput.focus();
        return;
      }
      customWrap.style.display = "none";
      weightInput.value = roleSelect.value || "0";
    });
  }

  function updateTypeFields() {
    const typeSelect = document.getElementById("mm_item_type");
    const routeInput = document.getElementById("mm_route");
    const nameInput = document.getElementById("mm_name");
    if (!typeSelect || !routeInput || !nameInput) return;
    const isSeparator = typeSelect.value === "separator";
    routeInput.disabled = isSeparator;
    routeInput.value = isSeparator ? "" : routeInput.value;
    nameInput.required = !isSeparator;
    nameInput.placeholder = isSeparator ? "Separatore" : "";
  }

  function bindItemType() {
    document.getElementById("mm_item_type")?.addEventListener("change", updateTypeFields);
  }

  function updateVisibilityFields() {
    const activeInput = document.getElementById("mm_is_active");
    const visibleInput = document.getElementById("mm_is_visible");
    if (!activeInput || !visibleInput) return;
    if (activeInput.checked) {
      visibleInput.checked = true;
      visibleInput.disabled = true;
      return;
    }
    visibleInput.disabled = false;
  }

  function bindVisibilityRules() {
    document.getElementById("mm_is_active")?.addEventListener("change", updateVisibilityFields);
  }

  function bindModalSubmit(refreshFn) {
    const form = document.getElementById("menuModalForm");
    if (!form) return;
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (modalSubmitting) return;
      modalSubmitting = true;
      const submitButton = document.getElementById("mm_submit");
      if (submitButton) {
        submitButton.disabled = true;
        submitButton.textContent = "Salvataggio...";
      }

      const id = (document.getElementById("mm_menu_id").value || "").trim();
      const parentIdRaw = (document.getElementById("mm_parent_id").value || "").trim();
      const itemType = document.getElementById("mm_item_type").value || "link";
      const payload = {
        name: (document.getElementById("mm_name").value || "").trim(),
        route: itemType === "separator" ? null : ((document.getElementById("mm_route").value || "").trim() || null),
        weight: Number(document.getElementById("mm_weight").value || 0),
        is_active: document.getElementById("mm_is_active").checked,
        is_visible: document.getElementById("mm_is_active").checked || document.getElementById("mm_is_visible").checked,
        item_type: itemType,
        parent_id: parentIdRaw === "" ? null : Number(parentIdRaw)
      };

      try {
        if (!payload.name && payload.item_type !== "separator") throw new Error("Nome obbligatorio");
        if (id) await updateMenuJson({ id: Number(id), ...payload });
        else await createMenu(payload);
        bootstrap.Modal.getOrCreateInstance(document.getElementById("menuModal")).hide();
        setPendingApply(true);
        await refreshFn();
      } catch (err) {
        console.error("MODAL SUBMIT:", err);
        alert(err.message || "Errore salvataggio menu");
      } finally {
        modalSubmitting = false;
        if (submitButton) {
          submitButton.disabled = false;
          submitButton.textContent = "Salva";
        }
      }
    });
  }

  document.addEventListener("DOMContentLoaded", async () => {
    const host = document.getElementById("menuTree");
    if (!host) return;

    const modalEl = document.getElementById("menuModal");
    if (modalEl && modalEl.parentElement !== document.body) {
      document.body.appendChild(modalEl);
    }
    modalEl?.addEventListener("show.bs.modal", () => {
      document.body.classList.add("settings-menu-modal-open");
    });
    modalEl?.addEventListener("shown.bs.modal", () => {
      const submit = modalEl.querySelector("#mm_submit");
      if (submit) {
        submit.disabled = false;
        submit.textContent = "Salva";
      }
      const first = modalEl.querySelector("#mm_name:not(:disabled), #mm_item_type:not(:disabled), input:not([type='hidden']):not(:disabled), select:not(:disabled)");
      first?.focus();
    });
    modalEl?.addEventListener("hidden.bs.modal", () => {
      document.body.classList.remove("settings-menu-modal-open");
      modalSubmitting = false;
      const submit = modalEl.querySelector("#mm_submit");
      if (submit) {
        submit.disabled = false;
        submit.textContent = "Salva";
      }
    });

    bindActions(host);
    bindModalSubmit(renderAll);
    bindRoleWeight();
    bindItemType();
    bindVisibilityRules();

    document.getElementById("btnAddRootMenu")?.addEventListener("click", () => {
      openModal({ mode: "add-root", parentId: null });
    });

    document.getElementById("btnAddSeparator")?.addEventListener("click", () => {
      openModal({
        mode: "add-separator",
        parentId: null,
        menu: { item_type: "separator", name: "", route: null, is_active: true, is_visible: true }
      });
    });

    document.getElementById("btnApplyMenuChanges")?.addEventListener("click", () => {
      if (!hasPendingApply) return;
      window.location.reload();
    });

    await renderAll();
    setPendingApply(false);
  });
}
