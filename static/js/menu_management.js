/* global Sortable, bootstrap */

if (window.__menuMgmtInitDone) {
  console.warn("menu_management.js già inizializzato: skip.");
} else {
  window.__menuMgmtInitDone = true;

  let modalSubmitting = false;
  let sortables = [];
  let hasPendingApply = false;

  /* =========================
     API
  ========================= */

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
    btn.classList.toggle("btn-primary", hasPendingApply);
    btn.classList.toggle("btn-outline-primary", !hasPendingApply);
  }

  /* =========================
     TREE
  ========================= */

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
      const statusBadges = [
        isSeparator ? `<span class="badge text-bg-secondary">separatore</span>` : "",
        isVisible ? "" : `<span class="badge text-bg-warning">nascosto</span>`,
        isActive ? "" : `<span class="badge text-bg-secondary">non attivo</span>`
      ].filter(Boolean).join(" ");

      li.innerHTML = `
        <div class="menu-row d-flex align-items-center gap-2 ${isActive ? "" : "menu-row-inactive"} ${isVisible ? "" : "menu-row-hidden"} ${isSeparator ? "menu-row-separator" : ""}">
          <span class="menu-handle" title="Trascina per riordinare" style="cursor: grab;">
            ⠿
          </span>

          <span class="menu-node-title menu-title">
            ${title} <small class="text-muted">w:${n.weight ?? 0}</small> ${statusBadges}
          </span>

          <div class="dropdown ms-auto">
            <a class="btn btn-sm btn-outline-secondary dropdown-toggle btn-menu-actions"
               href="#"
               role="button"
               data-bs-toggle="dropdown"
               aria-expanded="false">⋮</a>

            <ul class="dropdown-menu">
              <li><a class="dropdown-item" href="#" data-action="add-child" data-id="${n.id}">Aggiungi sotto-menu</a></li>
              <li><a class="dropdown-item" href="#" data-action="add-separator-child" data-id="${n.id}">Aggiungi separatore</a></li>
              <li><a class="dropdown-item" href="#" data-action="edit" data-id="${n.id}">Modifica</a></li>
              <li><a class="dropdown-item" href="#" data-action="toggle-active" data-id="${n.id}">
                ${((n.is_active ?? n.active ?? true) ? "Disattiva" : "Attiva")}
              </a></li>
              <li>
                ${isActive
                  ? `<span class="dropdown-item disabled">Visibile fisso</span>`
                  : `<a class="dropdown-item" href="#" data-action="toggle-visible" data-id="${n.id}">
                      ${isVisible ? "Nascondi" : "Mostra"}
                    </a>`
                }
              </li>
              <li><hr class="dropdown-divider"></li>
              <li><a class="dropdown-item text-danger" href="#" data-action="delete" data-id="${n.id}">Elimina</a></li>
            </ul>
          </div>
        </div>
      `;


      li.appendChild(renderTree(n.children || []));

      ul.appendChild(li);
    });

    return ul;
  }

  /* =========================
     SORTABLE
  ========================= */

  function destroySortables() {
    sortables.forEach(s => s.destroy());
    sortables = [];
  }

  function initSortable(root) {
    destroySortables();

    root.querySelectorAll(".menu-tree").forEach(ul => {
      const s = new Sortable(ul, {
        group: "menus",
        animation: 150,
        handle: ".menu-handle",
        fallbackOnBody: true,
        swapThreshold: 0.65,
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

        items.push({
          id,
          parent_id: parentId,
          sort_order: index + 1
        });

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

  /* =========================
     ACTIONS (delegation)
  ========================= */

  function bindActions(host) {
    host.addEventListener("click", async (e) => {
      const a = e.target.closest("a[data-action]");
      if (!a) return;

      e.preventDefault();

      const id = Number(a.dataset.id);
      const action = a.dataset.action;

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
        return;
      }
    });
  }

  /* =========================
     RENDER
  ========================= */

  async function renderAll() {
    const host = document.getElementById("menuTree");
    if (!host) return;

    const data = await fetchMenuStructure();
    const tree = buildTree(data);

    host.innerHTML = "";
    host.appendChild(renderTree(tree));

    initSortable(host);
  }

  /* =========================
     MODALE
  ========================= */

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

  function closeMenuModal() {
    const modalEl = document.getElementById("menuModal");
    const inst = bootstrap.Modal.getInstance(modalEl);
    if (inst) inst.hide();
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

  /* =========================
     MODAL SUBMIT
  ========================= */

  function bindModalSubmit(refreshFn) {
    const form = document.getElementById("menuModalForm");
    if (!form) return;

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      e.stopPropagation();

      if (modalSubmitting) return;
      modalSubmitting = true;

      const id = (document.getElementById("mm_menu_id").value || "").trim();
      const parentIdRaw = (document.getElementById("mm_parent_id").value || "").trim();
      const itemType = document.getElementById("mm_item_type").value || "link";

      const payload = {
        name: (document.getElementById("mm_name").value || "").trim(),
        route: itemType === "separator" ? null : ((document.getElementById("mm_route").value || "").trim() || null),
        weight: Number(document.getElementById("mm_weight").value || 0),
        is_active: document.getElementById("mm_is_active").checked,
        is_visible: document.getElementById("mm_is_active").checked || document.getElementById("mm_is_visible").checked,
        item_type: itemType
      };

      // root => parent_id null (campo vuoto)
      payload.parent_id = parentIdRaw === "" ? null : Number(parentIdRaw);

      try {
        if (!payload.name && payload.item_type !== "separator") throw new Error("Nome obbligatorio");

        if (id) {
          await updateMenuJson({ id: Number(id), ...payload });
        } else {
          await createMenu(payload);
        }

        bootstrap.Modal.getOrCreateInstance(document.getElementById("menuModal")).hide();
        setPendingApply(true);
        await refreshFn();
      } catch (err) {
        console.error("MODAL SUBMIT:", err);
        // in futuro: toast/alert in modale
        alert(err.message || "Errore salvataggio menu");
       } finally {
         modalSubmitting = false;
      }
     });
  }


  /* =========================
     INIT
  ========================= */

  document.addEventListener("DOMContentLoaded", async () => {
    const host = document.getElementById("menuTree");
    if (!host) return;

    const modalEl = document.getElementById("menuModal");
    if (modalEl && modalEl.parentElement !== document.body) {
      document.body.appendChild(modalEl);
    }

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
