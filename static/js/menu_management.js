/* global Sortable, bootstrap */

/* =========================
   FETCH
========================= */

if (window.__menuMgmtInitDone) {
  console.warn("menu_management.js già inizializzato: skip.");
}
window.__menuMgmtInitDone = true;

let modalSubmitting = false;

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
    nodes.sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0) || (a.id - b.id));
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
    li.dataset.id = String(n.id);

    const row = document.createElement("div");
    row.className = "d-flex align-items-center gap-2 p-2 border rounded menu-row";
    row.innerHTML = `
      <span class="menu-handle" title="Trascina" style="cursor:grab;">☰</span>
      <span class="menu-title">${escapeHtml(n.name ?? ("#" + n.id))}</span>
      <span class="badge bg-secondary ms-auto">w:${escapeHtml(String(n.weight ?? 0))}</span>

      <div class="dropdown">
        <button class="dropdown-toggle btn-menu-actions"
          type="button"
          data-bs-toggle="dropdown"
          aria-expanded="false"
          title="Azioni">⋮</button>
        <ul class="dropdown-menu">
          <li><a class="dropdown-item" href="#" data-action="add-child" data-id="${n.id}">Aggiungi sotto-menu</a></li>
          <li><a class="dropdown-item" href="#" data-action="edit" data-id="${n.id}">Modifica</a></li>
          <li><hr class="dropdown-divider"></li>
          <li><a class="dropdown-item text-danger" href="#" data-action="delete" data-id="${n.id}">Elimina</a></li>
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
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
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
        reorderTimer = setTimeout(async () => {
          try {
            const res = await fetch("/settings/reorder_menus", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              credentials: "same-origin",
              body: JSON.stringify({ items })
            });
            if (!res.ok) throw new Error(await res.text());
          } catch (e) {
            console.error("reorder_menus:", e);
          }
        }, 250);
      }
    });
  });
}

function collectTree(root) {
  const result = [];

  const walk = (ul, parentId) => {
    [...ul.children].forEach((li, idx) => {
      if (!li.classList.contains("menu-node")) return;
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
  const pid = (parentId ?? menu?.parent_id ?? null);
  document.getElementById("mm_parent_id").value = (pid === null) ? "" : String(pid);

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

function closeMenuModal() {
  const modalEl = document.getElementById("menuModal");
  const inst = bootstrap.Modal.getInstance(modalEl);
  if (inst) inst.hide();
}

function bindTreeActions(root) {
  if (root.__menuActionsBound) return;
  root.__menuActionsBound = true;

  root.addEventListener("click", async e => {
    const a = e.target.closest("a[data-action]");
    if (!a) return;

    e.preventDefault();
    e.stopPropagation();

    const id = Number(a.dataset.id);
    const action = a.dataset.action;

    try {
      if (action === "add-child") {
        openMenuModal({ mode: "add-child", menu: null, parentId: id });
        return;
      }

      if (action === "edit") {
        const menu = await loadMenuData(id);
        openMenuModal({ mode: "edit", menu });
        return;
      }

      if (action === "delete") {
        if (!confirm("Eliminare questo menu? (Operazione irreversibile)")) return;

        try {
          await apiDeleteMenu(id, false);
          await initMenuManager();
        } catch (err) {
          if (err.code === "HAS_CHILDREN") {
            const ok = confirm(
              "Questo menu contiene sotto-menu.\n\n" +
              "Vuoi eliminarlo CON TUTTI i sotto-menu?\n" +
              "(Operazione NON reversibile)"
            );
            if (!ok) return;

            await apiDeleteMenu(id, true);
            await initMenuManager();
          } else {
            alert(err.message || "Errore eliminazione menu");
          }
        }
      }
    } catch (err) {
      console.error("Menu action error:", err);
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
    openMenuModal({ mode: "add-root", menu: null, parentId: null });
  });
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

    const payload = {
      name: (document.getElementById("mm_name").value || "").trim(),
      route: (document.getElementById("mm_route").value || "").trim() || null,
      weight: Number(document.getElementById("mm_weight").value || 0),
      is_active: document.getElementById("mm_is_active").checked
    };

    // root => parent_id null (campo vuoto)
    payload.parent_id = parentIdRaw === "" ? null : Number(parentIdRaw);

    try {
      if (!payload.name) throw new Error("Nome obbligatorio");

      if (id) {
        await updateMenuJson({ id: Number(id), ...payload });
      } else {
        await createMenu(payload);
      }

      closeMenuModal();
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
   INIT / REFRESH
========================= */

async function renderAll() {
  const host = document.getElementById("menuTree");
  if (!host) return;

  const data = await fetchMenuStructure();
  const tree = buildTree(data);

  host.innerHTML = "";
  host.appendChild(renderTree(tree));

  initSortable(host);
  bindTreeActions(host);
}

async function initMenuManager() {
  await renderAll();
  bindRootCreateButton();
  bindModalSubmit(renderAll);
}

document.addEventListener("DOMContentLoaded", () => {
  initMenuManager().catch(console.error);
});
