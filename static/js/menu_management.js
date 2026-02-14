/* global Sortable, bootstrap */

if (window.__menuMgmtInitDone) {
  console.warn("menu_management.js già inizializzato: skip.");
} else {
  window.__menuMgmtInitDone = true;

  let modalSubmitting = false;
  let sortables = [];

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

  async function createMenu(payload) {
    const res = await fetch("/settings/create_menu", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(payload)
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) throw new Error("create failed");
  }

  async function updateMenuJson(payload) {
    const res = await fetch("/settings/update_menu_json", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(payload)
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) throw new Error("update failed");
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

      <li.innerHTML = `
        <div class="menu-row d-flex align-items-center gap-2 p-2 border rounded ${isActive ? "" : "menu-row-inactive"}">
          <span class="menu-handle" style="cursor:grab;">☰</span>

          <span class="menu-title ${isActive ? "" : "menu-title-inactive"}">
            ${escapeHtml(n.name)}
          </span>

          <span class="badge bg-secondary ms-auto">w:${n.weight ?? 0}</span>

          li.innerHTML = `
            <div class="d-flex align-items-center gap-2">
              <span class="menu-handle" title="Trascina per riordinare" style="cursor: grab;">☰</span>

              <span class="menu-node-title">
                ${escapeHtml(n.name)} <small class="text-muted">w:${n.weight ?? 0}</small>
              </span>

              <div class="dropdown ms-auto">
                <a class="btn btn-sm btn-outline-secondary dropdown-toggle"
                   href="#"
                   role="button"
                   data-bs-toggle="dropdown"
                   aria-expanded="false">
                  ⋮
                </a>

                <ul class="dropdown-menu">
                  <li><a class="dropdown-item" href="#" data-action="add-child" data-id="${n.id}">Aggiungi sotto-menu</a></li>
                  <li><a class="dropdown-item" href="#" data-action="edit" data-id="${n.id}">Modifica</a></li>
                  <li><a class="dropdown-item" href="#" data-action="toggle-active" data-id="${n.id}">
                    ${isActive ? "Disattiva" : "Attiva"}
                  </a></li>
                  <li><hr class="dropdown-divider"></li>
                  <li><a class="dropdown-item text-danger" href="#" data-action="delete" data-id="${n.id}">Elimina</a></li>
                </ul>
              </div>
            </div>
          `;
        </div>
      `;

      if (n.children?.length) {
        li.appendChild(renderTree(n.children));
      }

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
        handle: ".menu-handle"
      });
      sortables.push(s);
    });
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
        // Apri la stessa modale di creazione, ma con parent_id = id
        // (openModal esiste già perché viene usata per 'edit')
        openModal({ parent_id: id });
        return;
      }

      if (action === "toggle-active") {
        await apiToggleMenuActive(id);
        await renderAll();
        return;
      }

      if (action === "delete") {
        if (!confirm("Eliminare questo menu?")) return;
        await apiDeleteMenu(id, true);
        await renderAll();
        return;
      }

      if (action === "edit") {
        const data = await loadMenuData(id);
        openModal(data);
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
     INIT
  ========================= */

  document.addEventListener("DOMContentLoaded", async () => {
    const host = document.getElementById("menuTree");
    if (!host) return;

    bindActions(host);
    await renderAll();
  });
}
