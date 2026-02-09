/* global Sortable, bootstrap */

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

/* =========================
   TREE BUILD
========================= */

function buildTree(items) {
  const map = new Map();
  items.forEach(i => map.set(i.id, { ...i, children: [] }));

  const roots = [];
  map.forEach(node => {
    if (node.parent_id == null) {
      roots.push(node);
    } else {
      const parent = map.get(node.parent_id);
      parent ? parent.children.push(node) : roots.push(node);
    }
  });

  const sortRec = nodes => {
    nodes.sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));
    nodes.forEach(n => sortRec(n.children));
  };
  sortRec(roots);

  return roots;
}

/* =========================
   RENDER
========================= */

function renderTree(nodes) {
  const ul = document.createElement("ul");
  ul.className = "menu-tree list-unstyled ms-2";
  ul.dataset.sortable = "1";

  nodes.forEach(n => {
    const li = document.createElement("li");
    li.className = "menu-node mb-1";
    li.dataset.id = n.id;

    const row = document.createElement("div");
    row.className = "d-flex align-items-center gap-2 p-2 border rounded";
    row.innerHTML = `
      <span class="menu-handle" style="cursor:grab;">☰</span>
      <span class="menu-title">${escapeHtml(n.name ?? ("#" + n.id))}</span>
      <span class="badge bg-secondary ms-auto">w:${n.weight ?? 0}</span>

      <div class="dropdown">
        <button class="dropdown-toggle btn-menu-actions"
        type="button"
        data-bs-toggle="dropdown"
        aria-expanded="false">⋮</button>
        <ul class="dropdown-menu">
          <li><a class="dropdown-item" href="#" data-action="add-child" data-id="${n.id}">Aggiungi sotto-menu</a></li>
          <li><a class="dropdown-item" href="#" data-action="edit" data-id="${n.id}">Modifica</a></li>
        </ul>
      </div>
    `;
    li.appendChild(row);

    if (n.children && n.children.length) {
      li.appendChild(renderTree(n.children));
    }

    ul.appendChild(li);
  });

  return ul;
}

function escapeHtml(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

/* =========================
   SORTABLE
========================= */

let reorderTimer = null;

function initSortable(root) {
  root.querySelectorAll("ul[data-sortable]").forEach(ul => {
    new Sortable(ul, {
      group: "menus",
      animation: 150,
      handle: ".menu-handle",
      onEnd() {
        const items = collectTree(root);
        console.log("Tree changed:", items);

        clearTimeout(reorderTimer);
        reorderTimer = setTimeout(() => {
          fetch("/settings/reorder_menus", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify({ items })
          }).catch(console.error);
        }, 250);
      }
    });
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

  const rootUl = root.querySelector("ul.menu-tree");
  if (rootUl) walk(rootUl, null);

  return result;
}

/* =========================
   MODALE
========================= */

function openMenuModal({ mode, menu, parentId }) {
  document.getElementById("mm_menu_id").value = menu?.id ?? "";
  document.getElementById("mm_parent_id").value = (parentId ?? menu?.parent_id ?? "") === null ? "" : (parentId ?? menu?.parent_id ?? "");
  document.getElementById("mm_name").value = menu?.name ?? "";
  document.getElementById("mm_route").value = menu?.route ?? "";
  document.getElementById("mm_weight").value = menu?.weight ?? 0;
  document.getElementById("mm_is_active").checked = (menu?.is_active ?? true) === true;

  document.getElementById("menuModalTitle").textContent =
    (mode === "add-root") ? "Crea menu (root)" :
    (mode === "add-child") ? "Crea sotto-menu" :
    "Modifica menu";

  bootstrap.Modal.getOrCreateInstance(document.getElementById("menuModal")).show();
}

function bindTreeActions(root) {
  root.addEventListener("click", async e => {
    const a = e.target.closest("a[data-action]");
    if (!a) return;
    e.preventDefault();

    const id = Number(a.dataset.id);
    const action = a.dataset.action;

    if (action === "add-child") {
      openMenuModal({ mode: "add-child", menu: null, parentId: id });
      return;
    }

    if (action === "edit") {
      const menu = await loadMenuData(id);
      openMenuModal({ mode: "edit", menu });
    }
  });
}

/* =========================
   ROOT BUTTON
========================= */

function bindRootCreateButton() {
  const btn = document.getElementById("btnAddRootMenu");
  if (!btn) return;

  btn.addEventListener("click", () => {
    // parent_id null => campo hidden vuoto
    openMenuModal({ mode: "add-root", menu: null, parentId: null });
  });
}

/* =========================
   BOOTSTRAP
========================= */

async function initMenuManager() {
  const host = document.getElementById("menuTree");
  if (!host) return;

  const data = await fetchMenuStructure();
  const tree = buildTree(data);

  host.innerHTML = "";
  host.appendChild(renderTree(tree));

  initSortable(host);
  bindTreeActions(host);
  bindRootCreateButton();
}

document.addEventListener("DOMContentLoaded", initMenuManager);
