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

      li.innerHTML = `
        <div class="menu-row d-flex align-items-center gap-2 p-2 border rounded ${isActive ? "" : "menu-row-inactive"}">
          <span class="menu-handle" style="cursor:grab;">☰</span>

          <span class="menu-title ${isActive ? "" : "menu-title-inactive"}">
            ${escapeHtml(n.name)}
          </span>

          <span class="badge bg-secondary ms-auto">w:${n.weight ?? 0}</span>

          <div class="dropdown">
            <button class="btn-menu-actions dropdown-toggle"
                    data-bs-toggle="dropdown">
              ⋮
            </button>

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

      if (action === "toggle-active") {
        await apiToggleMenuActive(id);
        await renderAll();
      }

      if (action === "delete") {
        if (!confirm("Eliminare questo menu?")) return;
        await apiDeleteMenu(id, true);
        await renderAll();
      }

      if (action === "edit") {
        const data = await loadMenuData(id);
        openModal(data);
      }

      if (action === "add-child") {
        openModal(null, id);
      }
    });
  }

  /* =========================
     MODAL
  ========================= */

  function openModal(data = null, parentId = null) {
    const modal = document.getElementById("menuModal");
    const form = document.getElementById("menuModalForm");
    const titleEl = document.getElementById("menuModalTitle");
    const menuIdInput = document.getElementById("mm_menu_id");
    const parentIdInput = document.getElementById("mm_parent_id");
    const nameInput = document.getElementById("mm_name");
    const routeInput = document.getElementById("mm_route");
    const roleWeightSelect = document.getElementById("mm_role_weight");
    const weightCustomWrap = document.getElementById("mm_weight_custom_wrap");
    const weightInput = document.getElementById("mm_weight");
    const isActiveCheck = document.getElementById("mm_is_active");

    if (data) {
      titleEl.textContent = "Modifica menu";
      menuIdInput.value = data.id || "";
      parentIdInput.value = data.parent_id || "";
      nameInput.value = data.name || "";
      routeInput.value = data.route || "";
      roleWeightSelect.value = data.weight ?? "";
      weightInput.value = data.weight ?? 0;
      isActiveCheck.checked = !!data.is_active;
    } else {
      titleEl.textContent = "Nuovo menu";
      menuIdInput.value = "";
      parentIdInput.value = parentId || "";
      nameInput.value = "";
      routeInput.value = "";
      roleWeightSelect.value = "";
      weightInput.value = 0;
      isActiveCheck.checked = true;
    }

    weightCustomWrap.style.display = "none";

    const bsModal = new bootstrap.Modal(modal);
    bsModal.show();
  }

  /* =========================
     INIT
  ========================= */

  document.addEventListener("DOMContentLoaded", async () => {
    const host = document.getElementById("menuTree");
    if (!host) return;

    bindActions(host);
    await renderAll();

    // Gestore form modale
    const form = document.getElementById("menuModalForm");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();

      if (modalSubmitting) return;
      modalSubmitting = true;

      try {
        const menuId = document.getElementById("mm_menu_id").value;
        const parentId = document.getElementById("mm_parent_id").value || null;
        const name = document.getElementById("mm_name").value;
        const route = document.getElementById("mm_route").value || null;
        const roleWeightSelect = document.getElementById("mm_role_weight");
        const weightInput = document.getElementById("mm_weight");
        const isActive = document.getElementById("mm_is_active").checked;

        let weight = 0;
        if (roleWeightSelect.value === "__custom__") {
          weight = parseInt(weightInput.value, 10) || 0;
        } else if (roleWeightSelect.value) {
          weight = parseInt(roleWeightSelect.value, 10) || 0;
        }

        const payload = {
          name,
          route,
          weight,
          is_active: isActive,
          parent_id: parentId ? parseInt(parentId, 10) : null
        };

        if (menuId) {
          payload.id = parseInt(menuId, 10);
          await updateMenuJson(payload);
        } else {
          await createMenu(payload);
        }

        bootstrap.Modal.getInstance(document.getElementById("menuModal")).hide();
        form.reset();
        await renderAll();
      } catch (err) {
        alert("Errore: " + (err.message || "Unknown error"));
      } finally {
        modalSubmitting = false;
      }
    });

    // Gestore pulsante "Nuovo menu (root)"
    const btnAddRootMenu = document.getElementById("btnAddRootMenu");
    if (btnAddRootMenu) {
      btnAddRootMenu.addEventListener("click", () => {
        openModal(null, null);
      });
    }

    // Gestore cambio ruolo (per mostrare/nascondere input personalizzato)
    const roleWeightSelect = document.getElementById("mm_role_weight");
    if (roleWeightSelect) {
      roleWeightSelect.addEventListener("change", (e) => {
        const wrap = document.getElementById("mm_weight_custom_wrap");
        wrap.style.display = e.target.value === "__custom__" ? "block" : "none";
      });
    }
  });
}
