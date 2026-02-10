/* global Sortable, bootstrap */

let modalSubmitting = false;
let sortables = [];

/* =========================
   FETCH API
========================= */

async function fetchMenuStructure() {
  const res = await fetch("/settings/get_menu_structure", { credentials: "same-origin" });
  if (!res.ok) throw new Error("get_menu_structure failed");
  return res.json();
}

async function loadMenuData(menuId) {
  const res = await fetch(`/settings/menu/${menuId}`, { credentials: "same-origin" });
  if (!res.ok) throw new Error("menu load failed");
  return res.json();
}

async function createMenu(payload) {
  const res = await fetch("/settings/create_menu", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "create failed");
}

async function updateMenuJson(payload) {
  const res = await fetch("/settings/update_menu_json", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "update failed");
}

async function deleteMenu(menuId, cascade = false) {
  const res = await fetch(`/settings/delete_menu/${menuId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({ cascade }),
  });
  const data = await res.json();
  if (!res.ok || !data.ok) {
    const err = new Error(data.error || "delete failed");
    err.code = data.code;
    throw err;
  }
}

async function toggleMenuActive(menuId) {
  const res = await fetch(`/settings/toggle_menu_active/${menuId}`, {
    method: "POST",
    credentials: "same-origin",
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error("toggle failed");
}

/* =========================
   TREE BUILD
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

  for (const n of nodes) {
    const li = document.createElement("li");
    li.className = "menu-node";
    li.dataset.id = n.id;

    const isActive = !!n.is_active;

    li.innerHTML = `
      <div class="menu-row ${isActive ? "" : "menu-row-inactive"}">
        <span class="menu-handle">☰</span>
        <span class="menu-title ${isActive ? "" : "menu-title-inactive"}">${escapeHtml(n.name)}</span>
        <span class="badge bg-secondary ms-auto">w:${n.weight ?? 0}</span>

        <div class="dropdown">
          <button class="btn-menu-actions dropdown-toggle"
                  data-bs-toggle="dropdown"
                  type="button">⋮</button>

          <ul class="dropdown-menu">
            <li><a class="dropdown-item" data-action="add-child" data-id="${n.id}">Aggiungi sotto-menu</a></li>
            <li><a class="dropdown-item" data-action="edit" data-id="${n.id}">Modifica</a></li>
            <li><a class="dropdown-item" data-action="toggle" data-id="${n.id}">
              ${isActive ? "Disattiva" : "Attiva"}
            </a></li>
            <li><hr class="dropdown-divider"></li>
            <li><a class="dropdown-item text-danger" data-action="delete" data-id="${n.id}">Elimina</a></li>
          </ul>
        </div>
      </div>
    `;

    if (n.children.length) {
      li.appendChild(renderTree(n.children));
    }

    ul.appendChild(li);
  }

  return ul;
}

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, m =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[m])
  );
}

/* =========================
   SORTABLE
========================= */

function initSortable(root) {
  sortables.forEach(s => s.destroy());
  sortables = [];

  root.querySelectorAll("ul[data-sortable]").forEach(ul => {
    sortables.push(
      new Sortable(ul, {
        group: "menus",
        handle: ".menu-handle",
        animation: 150,
        onEnd: async () => {
          const items = collectTree(root);
          await fetch("/settings/reorder_menus", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify({ items }),
          });
        },
      })
    );
  });
}

function collectTree(root) {
  const result = [];
  const walk = (ul, parent) => {
    [...ul.children].forEach((li, i) => {
      result.push({ id: +li.dataset.id, parent_id: parent, sort_order: i });
      const sub = li.querySelector(":scope > ul");
      if (sub) walk(sub, +li.dataset.id);
    });
  };
  walk(root.querySelector(".menu-tree"), null);
  return result;
}

/* =========================
   ACTIONS
========================= */

function bindActions(root) {
  root.addEventListener("click", async e => {
    const a = e.target.closest("[data-action]");
    if (!a) return;

    const id = +a.dataset.id;
    const action = a.dataset.action;

    try {
      if (action === "add-child") openModal({ mode: "add-child", parentId: id });
      if (action === "edit") openModal({ mode: "edit", menu: await loadMenuData(id) });
      if (action === "toggle") {
        await toggleMenuActive(id);
        await renderAll();
      }
      if (action === "delete") {
        if (!confirm("Eliminare questo menu?")) return;
        try {
          await deleteMenu(id);
        } catch (err) {
          if (err.code === "HAS_CHILDREN" && confirm("Eliminare anche i sotto-menu?")) {
            await deleteMenu(id, true);
          } else return;
        }
        await renderAll();
      }
    } catch (err) {
      alert(err.message);
    }
  });
}

/* =========================
   MODAL
========================= */

function openModal({ mode, menu = {}, parentId = null }) {
  document.getElementById("mm_menu_id").value = menu.id ?? "";
  document.getElementById("mm_parent_id").value = parentId ?? menu.parent_id ?? "";
  document.getElementById("mm_name").value = menu.name ?? "";
  document.getElementById("mm_route").value = menu.route ?? "";
  document.getElementById("mm_weight").value = menu.weight ?? 0;
  document.getElementById("mm_is_active").checked = menu.is_active ?? true;

  document.getElementById("menuModalTitle").textContent =
    mode === "add-child" ? "Crea sotto-menu" :
    mode === "add-root" ? "Crea menu" : "Modifica menu";

  bootstrap.Modal.getOrCreateInstance("#menuModal").show();
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
}

document.addEventListener("DOMContentLoaded", async () => {
  const host = document.getElementById("menuTree");
  bindActions(host);
  await renderAll();
});
