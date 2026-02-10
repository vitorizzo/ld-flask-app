/* global Sortable, bootstrap */

if (window.__menuMgmtInitDone) {
  console.warn("menu_management.js già inizializzato: skip.");
}
window.__menuMgmtInitDone = true;

/* =========================
   STATE
========================= */

let modalSubmitting = false;
let sortables = [];

/* =========================
   FETCH
========================= */

async function fetchMenuStructure() {
  const res = await fetch("/settings/get_menu_structure", { credentials: "same-origin" });
  if (!res.ok) throw new Error("get_menu_structure failed");
  return await res.json();
}

async function loadMenuData(menuId) {
  const res = await fetch(`/settings/menu/${menuId}`, { credentials: "same-origin" });
  if (!res.ok) throw new Error(`menu/${menuId} failed`);
  return await res.json();
}

async function apiDeleteMenu(menuId, cascade = false) {
  const res = await fetch(`/settings/delete_menu/${menuId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({ cascade })
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.ok) {
    const err = new Error(data.error || "delete_menu failed");
    err.code = data.code;
    throw err;
  }
  return data;
}

async function apiToggleMenuActive(menuId) {
  const res = await fetch(`/settings/toggle_menu_active/${menuId}`, {
    method: "POST",
    credentials: "same-origin"
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.ok) throw new Error(data.error || "toggle_menu_active failed");
  return data;
}

async function createMenu(payload) {
  const res = await fetch("/settings/create_menu", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify(payload)
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.ok) throw new Error(data.error || "create_menu failed");
  return data;
}

async function updateMenuJson(payload) {
  const res = await fetch("/settings/update_menu_json", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify(payload)
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.ok) throw new Error(data.error || "update_menu_json failed");
  return data;
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
    else map.get(node.parent_id)?.children.push(node);
  });

  const sortRec = nodes => {
    nodes.sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0) || a.id - b.id);
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

/* =========================
   RENDER
========================= */

function renderTree(nodes) {
  const ul = document.createElement("ul");
  ul.className = "menu-tree list-unstyled ms-2";
  ul.dataset.sortable = "1";

  nodes.forEach(n => {
    const isActive = n.is_active === true || n.is_active === 1;

    const li = document.createElement("li");
    li.className = "menu-node mb-1";
    li.dataset.id = n.id;

    const row = document.createElement("div");
    row.className = `menu-row d-flex align-items-center gap-2 p-2 border rounded ${!isActive ? "menu-row-inactive" : ""}`;

    row.innerHTML = `
      <span class="menu-handle" style="cursor:grab;">☰</span>
      <span class="menu-title ${!isActive ? "menu-title-inactive" : ""}">
        ${escapeHtml(n.name)}
      </span>
      <span class="badge bg-secondary ms-auto">w:${n.weight ?? 0}</span>
      <span class="badge ${isActive ? "badge-active" : "badge-inactive"} ms-2">
        ${isActive ? "ATTIVO" : "OFF"}
      </span>

      <div class="dropdown">
        <button class="btn-menu-actions dropdown-toggle"
          data-bs-toggle="dropdown"
          type="button">⋮</button>

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
    `;

    li.appendChild(row);

    if (n.children?.length) li.appendChild(renderTree(n.children));
    ul.appendChild(li);
  });

  return ul;
}

/* =========================
   SORTABLE
========================= */

function initSortable(root) {
  sortables.forEach(s => s.destroy());
  sortables = [];

  root.querySelectorAll("ul[data-sortable]").forEach(ul => {
    sortables.push(new Sortable(ul, {
      group: "menus",
      animation: 150,
      handle: ".menu-handle",
      onEnd: async () => {
        const items = collectTree(root);
        await fetch("/settings/reorder_menus", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify({ items })
        });
      }
    }));
  });
}

function collectTree(root) {
  const result = [];
  const walk = (ul, parentId) => {
    [...ul.children].forEach((li, idx) => {
      const id = Number(li.dataset.id);
      result.push({ id, parent_id: parentId, sort_order: idx });
      const child = li.querySelector(":scope > ul");
      if (child) walk(child, id);
    });
  };
  walk(root.querySelector("ul.menu-tree"), null);
  return result;
}

/* =========================
   ACTIONS
========================= */

function bindActions(root) {
  root.addEventListener("click", async e => {
    const a = e.target.closest("a[data-action]");
    if (!a) return;

    e.preventDefault();

    const id = Number(a.dataset.id);
    const action = a.dataset.action;

    if (action === "add-child") openMenuModal({ mode: "add-child", parentId: id });
    if (action === "edit") openMenuModal({ mode: "edit", menu: await loadMenuData(id) });

    if (action === "toggle-active") {
      await apiToggleMenuActive(id);
      await renderAll();
    }

    if (action === "delete") {
      if (!confirm("Eliminare questo menu?")) return;
      try {
        await apiDeleteMenu(id);
      } catch (err) {
        if (err.code === "HAS_CHILDREN") {
          if (!confirm("Contiene sotto-menu. Eliminare tutto?")) return;
          await apiDeleteMenu(id, true);
        }
      }
      await renderAll();
    }
  });
}

/* =========================
   DROPDOWN STACKING (FIX)
========================= */

function bindDropdownStacking(root) {
  root.addEventListener("shown.bs.dropdown", e => {
    const li = e.target.closest(".menu-node");
    if (li) li.classList.add("dropdown-open");
  });

  root.addEventListener("hidden.bs.dropdown", e => {
    const li = e.target.closest(".menu-node");
    if (li) li.classList.remove("dropdown-open");
  });
}

/* =========================
   INIT
========================= */

async function renderAll() {
  const host = document.getElementById("menuTree");
  const data = await fetchMenuStructure();
  host.innerHTML = "";
  host.appendChild(renderTree(buildTree(data)));

  initSortable(host);
  bindActions(host);
  bindDropdownStacking(host);
}

document.addEventListener("DOMContentLoaded", renderAll);
