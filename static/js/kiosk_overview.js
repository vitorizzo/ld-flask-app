(() => {
  const API_ALL = "/kiosk/api/board/all?only_active=1&show_closed_today=1";
  const API_ORDER = (id) => `/kiosk/api/order/${id}`;

  const statusList = ["acquisito", "listato", "controllato", "evaso"];
  const statusRank = { acquisito: 0, listato: 1, controllato: 2, evaso: 3 };

  let currentRouteFilter = "__all__";
  let lastCards = []; // lista di "view cards"
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
    const pillTotal = $("#pill-total");
    if (pillTotal) pillTotal.textContent = "0";
  }

  function escapeHtml(s) {
    return String(s)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function buildSeqIndicator(seqTotal, seqOnSet) {
    if (!seqTotal || seqTotal <= 1) return "";

    const parts = [];
    parts.push(`<div class="order-seq" aria-label="Ordini del gruppo">`);
    for (let i = 1; i <= seqTotal; i += 1) {
      const on = seqOnSet.has(i);
      parts.push(`<span class="order-seq__dot ${on ? "on" : "off"}">#${i}</span>`);
    }
    parts.push(`</div>`);
    return parts.join("");
  }

  function pickPrimaryOrder(orders) {
    // sceglie il più "piccolo" per sequenza, fallback su id
    return [...orders].sort((a, b) => {
      const sa = a.group_seq ?? 1;
      const sb = b.group_seq ?? 1;
      if (sa !== sb) return sa - sb;
      return (a.id ?? 0) - (b.id ?? 0);
    })[0];
  }

  function buildCard(vm) {
    const div = document.createElement("div");
    div.className = "order-card";
    div.style.setProperty("--route-bg", vm.route_color || "#f1f3f5");
    div.dataset.routeId = String(vm.route_id || "");

    const primary = vm.primary;
    const cust = primary.customer_display || "";
    const isGroup = vm.type === "group";

    // titolo
    const title = isGroup ? `${cust} (grouped)` : `${cust}`;

    // badge blu: per gruppo mostra il totale nella card; per singolo niente
    const groupBadge = isGroup ? `<span class="badge-multi">${vm.orders.length}</span>` : ``;

    // badge giallo/rosso: somma per la card
    const notesSum = vm.orders.reduce((acc, o) => acc + (o.notes_count || 0), 0);
    const issuesSum = vm.orders.reduce((acc, o) => acc + (o.issues_count ? 1 : 0), 0);

    // indicatore #1 #2 #3
    const seqTotal = vm.seq_total || 1;
    const seqOn = new Set(vm.orders.map(o => o.group_seq || 1));
    const seqIndicator = buildSeqIndicator(seqTotal, seqOn);

    // delivery label: se ordini nella card hanno delivery diverse (non dovrebbe), metti il primary
    const deliveryLabel = primary.delivery_label || "";

    // preview: per gruppo mostriamo un preview “compatto”
    let preview = "";
    if (primary.preview) preview = primary.preview;

    div.innerHTML = `
      <div class="order-top">
        <div class="order-main">
          <div class="order-name">${escapeHtml(title)}</div>
          <div class="order-meta">
            Giro: <span class="badge-route">${escapeHtml(vm.route_name || "")}</span>
            ${deliveryLabel ? ` · <span class="order-delivery">${escapeHtml(deliveryLabel)}</span>` : ``}
          </div>
          ${seqIndicator}
        </div>
        <div class="order-badges">
          ${groupBadge}
          ${notesSum > 0 ? `<span class="badge-note">${notesSum}</span>` : ``}
          ${issuesSum > 0 ? `<span class="badge-issue">${issuesSum}</span>` : ``}
        </div>
      </div>
      ${preview ? `<div class="order-preview">${escapeHtml(preview)}</div>` : ``}
    `;

    if (isGroup) {
      div.addEventListener("click", () => openGroupModal(vm));
      div.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") openGroupModal(vm);
      });
    } else {
      div.addEventListener("click", () => openOrderModal(primary.id));
      div.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") openOrderModal(primary.id);
      });
    }

    div.tabIndex = 0;
    div.role = "button";

    return div;
  }

  async function openOrderModal(orderId) {
    const body = $("#orderModalBody");
    const title = $("#orderModalTitle");
    if (body) body.innerHTML = `<div class="text-muted">Caricamento...</div>`;
    if (title) title.textContent = `Ordine #${orderId}`;

    const modalEl = $("#orderModal");
    if (modalEl && window.bootstrap) {
      const modal = window.bootstrap.Modal.getOrCreateInstance(modalEl);
      modal.show();
    }

    try {
      const res = await fetch(API_ORDER(orderId), { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      if (title) {
        title.textContent = `${data.customer_display || "Ordine"} — ${data.route_name || ""} (${data.status || ""})`;
      }

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

  function openGroupModal(vm) {
    const body = $("#orderModalBody");
    const title = $("#orderModalTitle");
    if (body) body.innerHTML = `<div class="text-muted">Caricamento...</div>`;

    const modalEl = $("#orderModal");
    if (modalEl && window.bootstrap) {
      const modal = window.bootstrap.Modal.getOrCreateInstance(modalEl);
      modal.show();
    }

    const primary = vm.primary;
    const cust = primary.customer_display || "Gruppo";

    if (title) {
      title.textContent = `${cust} — ${vm.route_name || ""} (${vm.status || ""})`;
    }

    const seqTotal = vm.seq_total || 1;
    const seqOn = new Set(vm.orders.map(o => o.group_seq || 1));
    const seqIndicator = buildSeqIndicator(seqTotal, seqOn);

    const list = [...vm.orders].sort((a, b) => (a.group_seq ?? 1) - (b.group_seq ?? 1)).map(o => {
      const seq = o.group_seq || 1;
      const delivery = o.delivery_label || "";
      const notes = o.notes_count || 0;
      const issues = o.issues_count ? 1 : 0;
      const prev = o.preview || "";

      return `
        <div class="order-section">
          <div class="order-section__head">
            <span>Ordine #${seq}/${seqTotal}</span>
            <span>
              ${delivery ? `<span class="order-delivery">${escapeHtml(delivery)}</span>` : ``}
              <button class="btn btn-sm btn-outline-secondary ms-2" type="button" data-open-order="${o.id}">
                Apri #${seq}
              </button>
            </span>
          </div>
          <div class="order-section__body">
            ${prev ? `<div class="mb-2"><strong>Preview:</strong> ${escapeHtml(prev)}</div>` : ``}
            <div class="text-muted">
              Note: <strong>${notes}</strong> · Issues: <strong>${issues}</strong> · ID: <strong>${o.id}</strong>
            </div>
          </div>
        </div>
      `;
    }).join("");

    const routeBg = (vm.route_color || "#f1f3f5");
    const safeRoute = escapeHtml(vm.route_name || "");
    const safeStatus = escapeHtml(vm.status || "");
    const safeCust = escapeHtml(cust);

    const html = `
      <div class="order-sheet" style="--route-bg:${routeBg}">
        <div class="order-sheet__hero">
          <div class="order-sheet__hero-bar"></div>
          <div class="order-sheet__hero-body">
            <div class="order-kv">
              <div class="order-kv__k">Cliente</div><div class="order-kv__v">${safeCust} (grouped)</div>
              <div class="order-kv__k">Giro</div><div class="order-kv__v">${safeRoute}</div>
              <div class="order-kv__k">Stato</div><div class="order-kv__v">${safeStatus}</div>
              <div class="order-kv__k">Ordini</div><div class="order-kv__v">${vm.orders.length}</div>
            </div>
            ${seqIndicator}
          </div>
        </div>

        ${list}
      </div>
    `;

    if (body) body.innerHTML = html;

    // hook bottoni "Apri #n"
    if (body) {
      body.querySelectorAll("[data-open-order]").forEach(btn => {
        btn.addEventListener("click", (ev) => {
          const id = ev.currentTarget.getAttribute("data-open-order");
          if (id) openOrderModal(id);
        });
      });
    }
  }

  function applyFilterAndRender() {
    const filteredCards = (currentRouteFilter === "__all__")
      ? lastCards
      : lastCards.filter(c => String(c.route_id) === String(currentRouteFilter));

    // reset colonne
    for (const s of statusList) {
      const col = document.getElementById(`col-${s}`);
      if (!col) continue;
      col.innerHTML = "";
    }

    const counts = { acquisito: 0, listato: 0, controllato: 0, evaso: 0 };

    for (const vm of filteredCards) {
      const st = vm.status;
      if (!statusList.includes(st)) continue;
      const col = document.getElementById(`col-${st}`);
      if (!col) continue;
      col.appendChild(buildCard(vm));
      counts[st] += 1; // conta le card
    }

    for (const s of statusList) {
      const col = document.getElementById(`col-${s}`);
      if (!col) continue;
      if (col.children.length === 0) col.innerHTML = `<div class="kiosk-empty">Nessun ordine</div>`;
      const badge = document.getElementById(`count-${s}`);
      if (badge) badge.textContent = String(counts[s] || 0);
    }

    // pill totale = totale ordini (non card)
    const totalOrders = filteredCards.reduce((acc, c) => acc + (c.orders ? c.orders.length : 0), 0);
    const pillTotal = $("#pill-total");
    if (pillTotal) pillTotal.textContent = String(totalOrders);
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

            notes_count: o.note_count || 0,
            issues_count: o.has_issues ? 1 : 0,

            group_key: o.group_key || "",
            group_seq: o.group_seq || 1,
            group_size: o.group_size || 1,
            delivery_label: o.delivery_label || "",

            multi_count: o.msg_count || 0,
          });
        }
      }
    }

    // ordinamento stabile base
    out.sort((a, b) => {
      const ra = (a.route_name || "").toLowerCase();
      const rb = (b.route_name || "").toLowerCase();
      if (ra !== rb) return ra.localeCompare(rb);
      const sa = statusRank[a.status] ?? 99;
      const sb = statusRank[b.status] ?? 99;
      if (sa !== sb) return sa - sb;
      const ca = (a.customer_display || "").toLowerCase();
      const cb = (b.customer_display || "").toLowerCase();
      if (ca !== cb) return ca.localeCompare(cb);
      const ga = a.group_seq ?? 1;
      const gb = b.group_seq ?? 1;
      if (ga !== gb) return ga - gb;
      return (a.id ?? 0) - (b.id ?? 0);
    });

    return out;
  }

  function buildCardViewModels(flatOrders) {
    // B2: raggruppa per (group_key, status) se count>1
    // Serve anche una mappa seq->status per disegnare on/off coerente.
    const byGroup = new Map(); // group_key -> { seqTotal, seqToStatus, orders: [] }
    for (const o of flatOrders) {
      const gk = o.group_key || "";
      if (!byGroup.has(gk)) {
        byGroup.set(gk, {
          seqTotal: o.group_size || 1,
          seqToStatus: new Map(),
          orders: [],
        });
      }
      const g = byGroup.get(gk);
      g.orders.push(o);
      g.seqTotal = Math.max(g.seqTotal, o.group_size || 1);
      g.seqToStatus.set(o.group_seq || 1, o.status);
    }

    const cards = [];

    for (const [gk, g] of byGroup.entries()) {
      // bucket per status
      const byStatus = new Map(); // status -> [orders]
      for (const o of g.orders) {
        const st = o.status || "";
        if (!byStatus.has(st)) byStatus.set(st, []);
        byStatus.get(st).push(o);
      }

      for (const [st, arr] of byStatus.entries()) {
        const ordersSorted = [...arr].sort((a, b) => (a.group_seq ?? 1) - (b.group_seq ?? 1));
        const primary = pickPrimaryOrder(ordersSorted);

        const isGroup = ordersSorted.length > 1;
        cards.push({
          type: isGroup ? "group" : "single",
          status: st,
          group_key: gk,
          seq_total: g.seqTotal,
          orders: ordersSorted,
          primary,

          // route info (coerente nel group_key)
          route_id: primary.route_id,
          route_name: primary.route_name,
          route_color: primary.route_color,
          customer_display: primary.customer_display,
          delivery_label: primary.delivery_label,
        });
      }
    }

    // ordinamento cards
    cards.sort((a, b) => {
      const ra = (a.route_name || "").toLowerCase();
      const rb = (b.route_name || "").toLowerCase();
      if (ra !== rb) return ra.localeCompare(rb);
      const sa = statusRank[a.status] ?? 99;
      const sb = statusRank[b.status] ?? 99;
      if (sa !== sb) return sa - sb;
      const ca = (a.customer_display || "").toLowerCase();
      const cb = (b.customer_display || "").toLowerCase();
      if (ca !== cb) return ca.localeCompare(cb);
      const ga = a.primary.group_seq ?? 1;
      const gb = b.primary.group_seq ?? 1;
      return ga - gb;
    });

    return cards;
  }

  function updatePillsFromBoards(json) {
    // manteniamo i pill per-route come "numero ordini" (non card)
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

      const flat = flattenBoardsToOrders(json);
      lastCards = buildCardViewModels(flat);

      applyFilterAndRender();
    } catch (err) {
      clearColumnsKeepEmpty();
      console.error("[kiosk_overview] load error", err);
    }
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
