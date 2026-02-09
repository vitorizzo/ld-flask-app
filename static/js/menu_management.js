/* global Sortable */

async function fetchMenuStructure() {
  const res = await fetch("/settings/get_menu_structure", { credentials: "same-origin" });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`get_menu_structure failed: ${res.status} ${txt.slice(0, 120)}`);
  }
  return await res.json();
}

async function loadMenuData(menuId) {
  const res = await fetch(`/settings/menu/${menuId}`, { credentials: "same-origin" });
  if (!res.ok) throw new Error(`menu/${menuId} failed: ${res.status}`);
  return await res.json();
}

function buildTree(items) {
  const byId = new Map();
  items.forEach(i => byId.set(i.id, { ...i, children: [] }));

  const roots = [];
  byId.forEach(node => {
    if (node.parent_id == null) {
      roots.push(node);
    } else {
      const parent = byId.get(node.parent_id);
      if (parent) parent.children.push(node);
      else roots.push(node); // orfani -> root
    }
  });

  function sortRec(nodes) {
    nodes.sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0) || a.id - b.id);
    nodes.forEach(n => sortRec(n.children));
  }
  sortRec(roots);

  return roots;
}

function renderTree(nodes) {
  const ul = document.createElement("ul");
  ul.className = "menu-tree list-unstyled ms-2";
  ul.dataset.sortable = "1";

  nodes.forEach(n => {
    const li = document.createElement("li");
    li.className = "menu-node mb-1";
    li.dataset.id = String(n.id);

    const row = document.createElement("div");
    row.className = "d-flex align-items-center gap-2 p-2 border rounded";
    row.innerHTML = `
      <span class="menu-handle" style="cursor:grab;">☰</span>
      <span class="menu-title">${escapeHtml(n.name ?? ("#" + n.id))}</span>
      <span class="badge bg-secondary ms-auto">w:${n.weight ?? 0}</span>
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

let reorderTimer = null;
function postReorderDebounced(items) {
  if (reorderTimer) clearTimeout(reorderTimer);
  reorderTimer = setTimeout(() => {
    fetch("/settings/reorder_menus", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ items })
    })
      .then(async (r) => {
        if (!r.ok) throw new Error(await r.text());
        return r.json();
      })
      .then((data) => {
        if (!data.ok) throw new Error(data.error || "reorder failed");
      })
      .catch(err => console.error("reorder_menus:", err));
  }, 300);
}

function initNestedSortable(rootEl) {
  const lists = rootEl.querySelectorAll('ul[data-sortable="1"]');
  lists.forEach(ul => {
    new Sortable(ul, {
      group: "menus",
      animation: 150,
      handle: ".menu-handle",
      fallbackOnBody: true,
      swapThreshold: 0.65,
      onEnd: () => {
        const items = collectTree(rootEl);
        console.log("Tree changed:", items);
        postReorderDebounced(items);

        fetch("/settings/reorder_menus", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify({ items })
        }).then(async (r) => {
          if (!r.ok) throw new Error(await r.text());
          return r.json();
        }).then((data) => {
          if (!data.ok) throw new Error(data.error || "reorder failed");
          // opzionale: ricarica per riallineare con DB
          // renderAndBindTree();
        }).catch(err => console.error("reorder_menus:", err));
      }
    });
  });
}

function collectTree(rootEl) {
  const result = [];

  function walk(ul, parentId) {
    const children = Array.from(ul.children).filter(el => el.matches("li.menu-node"));
    children.forEach((li, idx) => {
      const id = parseInt(li.dataset.id, 10);
      result.push({ id, parent_id: parentId, sort_order: idx });

      const childUl = li.querySelector(":scope > ul");
      if (childUl) walk(childUl, id);
    });
  }

  const rootUl = rootEl.querySelector("ul.menu-tree");
  if (rootUl) walk(rootUl, null);
  return result;
}

async function renderAndBindTree() {
  const host = document.getElementById("menuTree");
  if (!host) return;

  const items = await fetchMenuStructure();
  const roots = buildTree(items);

  host.innerHTML = "";
  host.appendChild(renderTree(roots));

  initNestedSortable(host);

  // Click su riga: carica nel form
  host.addEventListener("click", async (ev) => {
    const node = ev.target.closest("li.menu-node");
    if (!node) return;
    const id = parseInt(node.dataset.id, 10);

    try {
      const data = await loadMenuData(id);
      fillFormFromMenu(data);
    } catch (e) {
      console.error(e);
    }
  }, { once: true }); // lo reimposto a ogni render (vedi sotto)
}

function fillFormFromMenu(data) {
  const form = document.querySelector("form");
  if (!form) return;

  // campo hidden se presente
  const menuIdEl = form.elements["menu_id"];
  if (menuIdEl) menuIdEl.value = data.id ?? "";

  Object.entries(data).forEach(([key, value]) => {
    const el = form.elements[key];
    if (!el) return;
    el.value = value == null ? "" : value;
  });
}

function setupCancelButton() {
  const btn = document.getElementById("cancelButton");
  if (!btn) return;
  btn.addEventListener("click", () => {
    const form = document.querySelector("form");
    if (form) form.reset();
  });
}

function setupFormSubmission() {
  const form = document.querySelector("form");
  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();

    try {
      const formData = new FormData(form);
      const res = await fetch("/settings/update_menu", {
        method: "POST",
        body: formData,
        credentials: "same-origin"
      });

      const data = await res.json();
      if (!data.success) throw new Error(data.error || "update_menu failed");

      // ricarica tree (così riflette name/route/parent/weight/sort_order aggiornati)
      await renderAndBindTree();
    } catch (err) {
      console.error("Errore update_menu:", err);
    }
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  if (typeof Sortable !== "function") {
    console.error("SortableJS non disponibile (script CDN non caricato)");
    return;
  }

  setupCancelButton();
  setupFormSubmission();

  try {
    await renderAndBindTree();
  } catch (e) {
    console.error(e);
  }
});
