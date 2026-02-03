(() => {
  const API_ALL = "/kiosk/api/board/all?only_active=1&show_closed_today=1";
  const API_ORDER = (id) => `/kiosk/api/order/${id}`;

  const statusList = ["acquisito", "listato", "controllato", "evaso"];
  let currentRouteFilter = "__all__";
  let lastOrders = []; // flat list
  let refreshTimer = null;

  function $(sel) { return document.querySelector(sel); }
  function $all(sel) { return Array.from(document.querySelectorAll(sel)); }

  function setNowText() {
    const el = $("#ui-now");
    if (!el) return;
    const d = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    el.textContent = `${pad(d.getDate())}/${pad(d.getMonth()+1)}/${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  function clearColumnsKeepEmpty() {
    for (const s of statusList) {
      const col = document.getElementById(`col-${s}`);
      if (!col) continue;
      col.innerHTML = `<div class="kiosk-empty">Nessun ordine</div>`;
      const count = document.getElementById(`count-${s}`);
      if (count) count.textContent = "0";
    }
  }

  function buildCard(o) {
    const div = document.createElement("div");
    div.className = "order-card";
    div.style.setProperty("--route-bg", o.route_color || "#f1f3f5");
    div.dataset.routeId = String(o.route_id || "");
    div.dataset.orderId = String(o.id);

    const multiExtra = (o.multi_count && o.multi_count > 1) ? (o.multi_count - 1) : 0;

    div.innerHTML = `
      <div class="order-top">
        <div class="order-main">
          <div class="order-name">${escapeHtml(o.customer_display || o.customer || "")}</div>
          <div class="order-meta">
            Giro: <span class="badge-route">${escapeHtml(o.route_name || "")}</span>
          </div>
        </div>
        <div class="order-badges">
          ${multiExtra > 0 ? `<span class="badge-multi">+${multiExtra}</span>` : ``}
          ${(o.notes_count || 0) > 0 ? `<span class="badge-note">${o.notes_count}</span>` : ``}
          ${(o.issues_count || 0) > 0 ? `<span class="badge-issue">${o.issues_count}</span>` : ``}
        </div>
      </div>
      ${o.preview ? `<div class="order-preview">${escapeHtml(o.preview)}</div>` : ``}
    `;

    div.addEventListener("click", () => openOrderModal(o.id));
    div.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" || ev.key === " ") openOrderModal(o.id);
    });
    div.tabIndex = 0;
    div.role = "button";

    return div;
  }

  async function openOrderModal(orderId) {
    const body = $("#orderModalBody");
    const title = $("#orderModalTitle");
    if (body) body.innerHTML = `<div class="text-muted">Caricamento...</div>`;
    if (title) title.textContent = `Ordine #${orderId}`;

    // bootstrap modal
    const modalEl = $("#orderModal");
    let modal = null;
    if (modalEl && window.bootstrap) {
      modal = window.bootstrap.Modal.getOrCreateInstance(modalEl);
      modal.show();
    }

    try {
      const res = await fetch(API_ORDER(orderId), { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      if (title) {
        title.textContent = `${data.customer_display || "Ordine"} — ${data.route_name || ""} (${data.status || ""})`;
      }

      const parts = [];
      const routeBg = (data.route_color || "#f1f3f5");
      const safeTitle = escapeHtml(data.customer_display || "Ordine");
      const safeRoute = escapeHtml(data.route_name || "");
      const safeStatus = escapeHtml(data.status || "");

      const parts = [];
      parts.push(`
        <div class="order-sheet" style="--route-bg:${routeBg}">
          <div class="order-sheet__hero">
            <div class="order-sheet__hero-bar"></div>
            <div class="order-sheet__hero-body">
              <div class="order-kv">
                <div class="order-kv__k">Cliente</div><div class="order-kv__v">${safeTitle}</div>
                <div class="order-kv__k">Giro</div><div class="order-kv__v">${safeRoute}</div>
                <div class="order-kv__k">Stato</div><div class="order-kv__v">${safeStatus}</div>
              </div>
            </div>
          </div>

          <div class="order-section">
            <div class="order-section__head">Testo</div>
            <div class="order-section__body">
              <pre class="order-pre">${escapeHtml(data.raw_text || "")}</pre>
            </div>
          </div>
      `);

      if (Array.isArray(data.children) && data.children.length) {
        parts.push(`
          <div class="order-section">
            <div class="order-section__head">Messaggi</div>
            <div class="order-section__body">
              <ul class="order-list">
                ${data.children.map(c =>
                  `<li><strong>${escapeHtml(c.label)}</strong> — ${escapeHtml(c.text || "")}</li>`
                ).join("")}
              </ul>
            </div>
          </div>
        `);
      }

      if (Array.isArray(data.thread_notes) && data.thread_notes.length) {
        parts.push(`
          <div class="order-section">
            <div class="order-section__head">Note</div>
            <div class="order-section__body">
              <ul class="order-list">
                ${data.thread_notes.map(n =>
                  `<li>${escapeHtml(n.text || "")}</li>`
                ).join("")}
              </ul>
            </div>
          </div>
        `);
      }

      parts.push(`</div>`); // chiude order-sheet
      if (body) body.innerHTML = parts.join("");
    } catch (err) {
      if (body) body.innerHTML = `<div class="text-danger">Errore caricamento ordine: ${escapeHtml(String(err))}</div>`;
    }
  }

  function applyFilterAndRender() {
    const filtered = (currentRouteFilter === "__all__")
      ? lastOrders
      : lastOrders.filter(o => String(o.route_id) === String(currentRouteFilter));

    // reset colonne (sempre visibili)
    for (const s of statusList) {
      const col = document.getElementById(`col-${s}`);
      if (!col) continue;
      col.innerHTML = ""; // poi gestiamo empty
    }

    const counts = { acquisito: 0, listato: 0, controllato: 0, evaso: 0 };

    for (const o of filtered) {
      const st = o.status;
      if (!statusList.includes(st)) continue;
      const col = document.getElementById(`col-${st}`);
      if (!col) continue;
      col.appendChild(buildCard(o));
      counts[st] += 1;
    }

    for (const s of statusList) {
      const col = document.getElementById(`col-${s}`);
      if (!col) continue;
      if (col.children.length === 0) {
        col.innerHTML = `<div class="kiosk-empty">Nessun ordine</div>`;
      }
      const badge = document.getElementById(`count-${s}`);
      if (badge) badge.textContent = String(counts[s] || 0);
    }

    // aggiorna pill totale
    const total = filtered.length;
    const pillTotal = $("#pill-total");
    if (pillTotal) pillTotal.textContent = String(total);
  }

  function hookFilters() {
    const container = $("#routeFilters");
    if (!container) return;

    container.addEventListener("click", (ev) => {
      const btn = ev.target.closest(".route-pill");
      if (!btn) return;

      const route = btn.getAttribute("data-filter-route");
      currentRouteFilter = route || "__all__";

      $all(".route-pill").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");

      applyFilterAndRender();
    });
  }

  function flattenBoardsToOrders(json) {
    const boards = Array.isArray(json.boards) ? json.boards : [];
    const out = [];

    for (const b of boards) {
      const route = b.route || {};
      const routeId = route.id;
      const routeName = route.name || "";
      const routeColor = route.color || "#f1f3f5";
      const groups = b.groups || {};

      for (const st of Object.keys(groups)) {
        const arr = Array.isArray(groups[st]) ? groups[st] : [];
        for (const o of arr) {
          out.push({
            id: o.id,
            status: o.status || st,
            route_id: routeId,
            route_name: routeName,
            route_color: routeColor,
            customer_display: o.customer || "",
            preview: (o.raw_text || "").trim().split("\n")[0].slice(0, 140),
            multi_count: o.msg_count || 0,
            notes_count: o.note_count || 0,
            issues_count: o.has_issues ? 1 : 0,
          });
        }
      }
    }

    // ordinamento consistente: route, status, customer
    const rank = { acquisito: 0, listato: 1, controllato: 2, evaso: 3 };
    out.sort((a, b) => {
      const ra = (a.route_name || "").toLowerCase();
      const rb = (b.route_name || "").toLowerCase();
      if (ra !== rb) return ra.localeCompare(rb);
      const sa = rank[a.status] ?? 99;
      const sb = rank[b.status] ?? 99;
      if (sa !== sb) return sa - sb;
      const ca = (a.customer_display || "").toLowerCase();
      const cb = (b.customer_display || "").toLowerCase();
      return ca.localeCompare(cb);
    });

    return out;
  }

  function updatePillsFromBoards(json) {
    const boards = Array.isArray(json.boards) ? json.boards : [];
    const totalsByRoute = new Map();
    let total = 0;

    for (const b of boards) {
      const route = b.route || {};
      const routeId = route.id;
      let count = 0;
      const groups = b.groups || {};
      for (const st of Object.keys(groups)) {
        const arr = Array.isArray(groups[st]) ? groups[st] : [];
        count += arr.length;
      }
      totalsByRoute.set(String(routeId), count);
      total += count;
    }

    const pillTotal = $("#pill-total");
    if (pillTotal) pillTotal.textContent = String(total);

    totalsByRoute.forEach((count, routeId) => {
      const pill = document.getElementById(`pill-route-${routeId}`);
      if (pill) pill.textContent = String(count);
    });
  }

  async function loadAndRender() {
    setNowText();

    try {
      const res = await fetch(API_ALL, { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();

      updatePillsFromBoards(json);
      lastOrders = flattenBoardsToOrders(json);
      applyFilterAndRender();
    } catch (err) {
      clearColumnsKeepEmpty();
      console.error("[kiosk_overview] load error", err);
    }
  }

  function escapeHtml(s) {
    return String(s)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function start() {
    hookFilters();

    const btn = $("#btn-refresh");
    if (btn) btn.addEventListener("click", loadAndRender);

    loadAndRender();

    if (refreshTimer) clearInterval(refreshTimer);
    refreshTimer = setInterval(loadAndRender, 10000);
  }

  document.addEventListener("DOMContentLoaded", start);
})();
