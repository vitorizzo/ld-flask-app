// =====================
// KIOSK SHARED STATE
// =====================
window.kioskState = {
  statusMeta: [],
  statusList: [],
  statusRank: {},
  currentRouteFilter: "__all__",
  lastCards: [],
};

(() => {
  const API_ALL = "/kiosk/api/board/all?only_active=1&show_closed_today=1";
  const API_ORDER = (id) => `/kiosk/api/order/${id}`;
  const API_REPARSE_DELIVERIES = "/kiosk/api/orders/reparse-deliveries";
  const API_STATUSES = "/kiosk/api/statuses";

  let refreshTimer = null;

  // Drag context (single dragged card at a time)
  let dragCtx = {
    el: null,
    fromColBody: null,
    fromStatus: null,
    payload: null, // { orderIds:[], fromStatus:"..." }
    isDragging: false,
  };

  function $(sel) {
    return document.querySelector(sel);
  }
  function $all(sel) {
    return Array.from(document.querySelectorAll(sel));
  }

  function escapeHtml(s) {
    return String(s)
      .replaceAll("&", "&")
      .replaceAll("<", "<")
      .replaceAll(">", ">")
      .replaceAll('"', '"')
      .replaceAll("'", "'");
  }

  function setNowText() {
    const el = $("#ui-now");
    if (!el) return;
    const d = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    el.textContent = `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ${pad(
      d.getHours()
    )}:${pad(d.getMinutes())}`;
  }

  function getPrevNextStatus(code) {
    const meta = kioskState.statusMeta || [];
    const idx = meta.findIndex((s) => String(s.code) === String(code));
    const prev = idx > 0 ? meta[idx - 1] : null;
    const next = idx >= 0 && idx < meta.length - 1 ? meta[idx + 1] : null;
    return { prev, next, idx };
  }

  function renderColumnsFromStatuses() {
    const wrap = document.querySelector(".kiosk-cols");
    if (!wrap) return;

    wrap.innerHTML = "";

    kioskState.statusMeta.forEach((st) => {
      const col = document.createElement("div");
      col.className = "kiosk-col";
      col.dataset.status = st.code;

      col.innerHTML = `
        <div class="kiosk-col__head">
          <div class="kiosk-col__title">${escapeHtml(st.label || st.code)}</div>
          <div class="kiosk-col__count"><span data-count>0</span></div>
        </div>
        <div class="kiosk-col__body" aria-label="drop-zone-${escapeHtml(st.code)}">
          <div class="kiosk-empty">Nessun ordine</div>
        </div>
      `;

      wrap.appendChild(col);
    });

    enableDnDForColumns();
  }

  async function loadStatuses() {
    try {
      const res = await fetch(API_STATUSES, { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const data = await res.json();
      const meta = Array.isArray(data) ? data : [];

      meta.sort((a, b) => (a.order_index ?? 1e9) - (b.order_index ?? 1e9));

      kioskState.statusMeta = meta;
      kioskState.statusList = meta.map((s) => s.code);
      kioskState.statusRank = {};
      meta.forEach((s, i) => {
        kioskState.statusRank[s.code] = i;
      });

      renderColumnsFromStatuses();
    } catch (e) {
      console.error("[kiosk_overview] loadStatuses error", e);
      const wrap = document.querySelector(".kiosk-cols");
      if (wrap) wrap.innerHTML = `<div class="alert alert-danger">Errore caricamento stati</div>`;
      return;
    }
  }

  function statusOptionsFor(currentCode) {
    const meta = kioskState.statusMeta;
    if (!Array.isArray(meta) || !meta.length) return [];
    return meta.filter((s) => s.code !== currentCode);
  }

  async function setOrderStatus(orderId, targetCode) {
    const res = await fetch(`/kiosk/api/order/${orderId}/set-status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: targetCode }),
      cache: "no-store",
    });

    const json = await res.json().catch(() => ({}));
    if (!res.ok || !json.ok) {
      const msg = json.error ? `${json.error}` : `HTTP ${res.status}`;
      throw new Error(msg);
    }
    return json;
  }

  async function setManyOrdersStatus(orderIds, targetCode) {
    for (const id of orderIds) {
      await setOrderStatus(id, targetCode);
    }
  }

  function buildSeqIndicator(seqTotal, seqOnSet) {
    if (!seqTotal || seqTotal <= 1) return "";
    const parts = [];
    parts.push(`<div class="order-seq">`);
    for (let i = 1; i <= seqTotal; i += 1) {
      const on = seqOnSet.has(i);
      parts.push(`<span class="seq-dot ${on ? "on" : ""}">#${i}</span>`);
    }
    parts.push(`</div>`);
    return parts.join("");
  }

  function pickPrimaryOrder(orders) {
    return [...orders].sort((a, b) => {
      const sa = a.group_seq ?? 1;
      const sb = b.group_seq ?? 1;
      if (sa !== sb) return sa - sb;
      return (a.id ?? 0) - (b.id ?? 0);
    })[0];
  }

  function recountColumnsFromDOM() {
    const filter = kioskState.currentRouteFilter || "__all__";
    const visibleCards =
      filter === "__all__"
        ? $all(".kiosk-col__body .order-card")
        : $all(`.kiosk-col__body .order-card[data-route-id="${filter}"]`);

    document.querySelectorAll(".kiosk-col").forEach((col) => {
      const body = col.querySelector(".kiosk-col__body");
      const cards = body ? Array.from(body.querySelectorAll(".order-card")) : [];

      const badge = col.querySelector("[data-count]");
      if (badge) badge.textContent = String(cards.length);

      if (body) {
        const empty = body.querySelector(".kiosk-empty");
        if (cards.length === 0) {
          if (!empty) {
            const d = document.createElement("div");
            d.className = "kiosk-empty";
            d.textContent = "Nessun ordine";
            body.appendChild(d);
          }
        } else {
          if (empty) empty.remove();
        }
      }
    });

    const pillTotal = document.getElementById("pill-total");
    if (pillTotal) {
      const count = filter === "__all__" ? $all(".kiosk-col__body .order-card").length : visibleCards.length;
      pillTotal.textContent = String(count);
    }
  }

  function enableDnDForColumns() {
    document.querySelectorAll(".kiosk-col").forEach((col) => {
      const body = col.querySelector(".kiosk-col__body");
      if (!body) return;

      body.addEventListener("dragover", (ev) => {
        if (!dragCtx.isDragging) return;
        ev.preventDefault();
        body.classList.add("is-over");
      });

      body.addEventListener("dragleave", () => {
        body.classList.remove("is-over");
      });

      body.addEventListener("drop", async (ev) => {
        if (!dragCtx.isDragging) return;
        ev.preventDefault();
        body.classList.remove("is-over");

        const targetStatus = col.dataset.status;
        const payload = dragCtx.payload;

        if (!payload || !targetStatus) return;
        if (payload.fromStatus === targetStatus) return;

        const dragged = dragCtx.el;
        if (!dragged) return;

        const prevParent = dragCtx.fromColBody;

        try {
          body.appendChild(dragged);
          recountColumnsFromDOM();

          dragged.classList.add("is-busy");
          await setManyOrdersStatus(payload.orderIds, targetStatus);

          await loadAndRender();
        } catch (e) {
          console.error("[kiosk_overview] dnd move error", e);

          if (prevParent && dragged) prevParent.appendChild(dragged);
          recountColumnsFromDOM();

          alert(`Errore spostamento: ${String(e.message || e)}`);
        } finally {
          if (dragged) dragged.classList.remove("is-busy");
        }
      });
    });
  }

  function buildCard(vm) {
    const div = document.createElement("div");
    div.className = "order-card";
    div.style.setProperty("--route-bg", vm.route_color || "#f1f3f5");
    div.dataset.routeId = String(vm.route_id || "");
    div.setAttribute("data-route-id", String(vm.route_id || ""));

    const primary = vm.primary;
    const cust = primary.customer_display || "";
    const isGroup = vm.type === "group";
    const title = isGroup ? `${cust} (grouped)` : `${cust}`;
    const groupBadge = isGroup ? `${vm.orders.length}` : ``;

    const notesSum = vm.orders.reduce((acc, o) => acc + (o.notes_count || 0), 0);
    const issuesSum = vm.orders.reduce((acc, o) => acc + (o.issues_count ? 1 : 0), 0);
    const attachmentsSum = vm.orders.reduce((acc, o) => acc + (o.attachment_count || 0), 0);

    const seqTotal = vm.seq_total || 1;
    const seqOn = new Set(vm.orders.map((o) => o.group_seq || 1));
    const seqIndicator = buildSeqIndicator(seqTotal, seqOn);

    const deliveryLabel = primary.delivery_label || "";
    const preview = primary.preview || "";
    const deliveryFromMessage = vm.orders.some((o) => o.delivery_from_message);
    const deliveryBadge = deliveryLabel
      ? `<span class="order-delivery-badge ${deliveryFromMessage ? "is-from-message" : ""}" title="${
          deliveryFromMessage ? "Consegna indicata nel messaggio Slack" : "Consegna stimata dal giro"
        }">${escapeHtml(deliveryLabel)}</span>`
      : "";

    const { prev, next } = getPrevNextStatus(vm.status);

    const moveOpts = statusOptionsFor(vm.status);
    const moveMenuHtml = moveOpts.length
      ? `
        <div class="order-actions dropdown">
          <button class="btn btn-sm btn-dark dropdown-toggle" type="button" data-bs-toggle="dropdown" aria-expanded="false">⋯</button>
          <ul class="dropdown-menu">
            <li class="dropdown-header">Sposta in</li>
            ${moveOpts
              .map(
                (s) =>
                  `<li><a class="dropdown-item" href="#" data-move-to="${escapeHtml(s.code)}">${escapeHtml(
                    s.label
                  )}</a></li>`
              )
              .join("")}
          </ul>
        </div>
      `
      : ``;

    // Hot-zones laterali
    const edgeLeft = `
      <button type="button" class="kiosk-edge kiosk-edge--left" data-step="prev" ${
        prev ? "" : "disabled"
      } aria-label="retrocedi">
        <span class="kiosk-edge__arrow">←</span>
      </button>
    `;
    const edgeRight = `
      <button type="button" class="kiosk-edge kiosk-edge--right" data-step="next" ${
        next ? "" : "disabled"
      } aria-label="promuovi">
        <span class="kiosk-edge__arrow">→</span>
      </button>
    `;

    div.innerHTML = `
      ${edgeLeft}
      ${edgeRight}

      <div class="order-topbar d-flex align-items-center justify-content-end" style="gap:8px; position: relative; z-index: 30;">
        ${deliveryBadge}
        ${moveMenuHtml}
      </div>

      <div class="order-title">${escapeHtml(title)}</div>
      <div class="order-meta">Giro: ${escapeHtml(vm.route_name || "")}${deliveryLabel ? ` · ${escapeHtml(deliveryLabel)}` : ``}</div>
      ${seqIndicator}
      <div class="order-badges">
        ${groupBadge ? `<span class="badge bg-secondary">${escapeHtml(groupBadge)}</span>` : ``}
        ${notesSum > 0 ? `<span class="badge bg-info">${notesSum}</span>` : ``}
        ${attachmentsSum > 0 ? `<span class="badge bg-warning text-dark">Foto ${attachmentsSum}</span>` : ``}
        ${issuesSum > 0 ? `<span class="badge bg-danger">${issuesSum}</span>` : ``}
      </div>
      ${preview ? `<div class="order-preview">${escapeHtml(preview)}</div>` : ``}
    `;

    const openFn = () => {
      if (isGroup) openGroupModal(vm);
      else openOrderModal(primary.id);
    };

    div.addEventListener("click", (ev) => {
      if (dragCtx.isDragging) return;
      if (ev.target.closest(".order-actions")) return;
      if (ev.target.closest(".kiosk-edge")) return; // edge gestisce click
      openFn();
    });

    // Menu “…”: spostamento diretto a qualunque status
    div.querySelectorAll("[data-move-to]").forEach((btn) => {
      btn.addEventListener("click", async (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        const target = ev.currentTarget.getAttribute("data-move-to");
        if (!target) return;

        const ids = isGroup ? vm.orders.map((o) => o.id) : [primary.id];

        div.classList.add("is-busy");
        try {
          await setManyOrdersStatus(ids, target);
          await loadAndRender();
        } catch (e) {
          console.error("[kiosk_overview] move error", e);
          alert(`Errore spostamento: ${String(e.message || e)}`);
        } finally {
          div.classList.remove("is-busy");
        }
      });
    });

    // Stepper edges ← →
    div.querySelectorAll("[data-step]").forEach((btn) => {
      btn.addEventListener("click", async (ev) => {
        ev.preventDefault();
        ev.stopPropagation();

        const dir = ev.currentTarget.getAttribute("data-step");
        const current = vm.status;

        const { prev: p, next: n } = getPrevNextStatus(current);
        const target = dir === "prev" ? (p ? p.code : null) : (n ? n.code : null);
        if (!target) return;

        const ids = isGroup ? vm.orders.map((o) => o.id) : [primary.id];

        div.classList.add("is-busy");
        try {
          await setManyOrdersStatus(ids, target);
          await loadAndRender();
        } catch (e) {
          console.error("[kiosk_overview] edge step error", e);
          alert(`Errore cambio stato: ${String(e.message || e)}`);
        } finally {
          div.classList.remove("is-busy");
        }
      });
    });

    // Dropdown stacking helper
    const ddToggle = div.querySelector('[data-bs-toggle="dropdown"]');
    if (ddToggle) {
      ddToggle.addEventListener("shown.bs.dropdown", () => {
        div.classList.add("menu-open");
      });
      ddToggle.addEventListener("hidden.bs.dropdown", () => {
        div.classList.remove("menu-open");
      });
    }

    // ---------------------
    // Drag & Drop: CARD
    // ---------------------
    const orderIds = isGroup ? vm.orders.map((o) => o.id) : [primary.id];
    div.dataset.orderIds = JSON.stringify(orderIds);
    div.dataset.fromStatus = String(vm.status || "");

    div.draggable = true;

    div.addEventListener("dragstart", (ev) => {
      if (ev.target && ev.target.closest && ev.target.closest(".order-actions")) {
        ev.preventDefault();
        return;
      }
      if (ev.target && ev.target.closest && ev.target.closest(".kiosk-edge")) {
        ev.preventDefault();
        return;
      }

      dragCtx.isDragging = true;
      dragCtx.el = div;
      dragCtx.fromStatus = String(vm.status || "");

      const fromCol = div.closest(".kiosk-col");
      const fromBody = fromCol ? fromCol.querySelector(".kiosk-col__body") : null;
      dragCtx.fromColBody = fromBody;

      dragCtx.payload = {
        orderIds,
        fromStatus: dragCtx.fromStatus,
      };

      try {
        ev.dataTransfer.setData("application/json", JSON.stringify(dragCtx.payload));
      } catch (e) {
        ev.dataTransfer.setData("text/plain", JSON.stringify(dragCtx.payload));
      }

      ev.dataTransfer.effectAllowed = "move";
      div.classList.add("is-dragging");
    });

    div.addEventListener("dragend", () => {
      div.classList.remove("is-dragging");
      dragCtx.isDragging = false;
      dragCtx.el = null;
      dragCtx.fromColBody = null;
      dragCtx.fromStatus = null;
      dragCtx.payload = null;
      document.querySelectorAll(".kiosk-col__body.is-over").forEach((b) => b.classList.remove("is-over"));
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

    const modalEl = $("#orderModal");
    if (modalEl && window.bootstrap) {
      const modal = window.bootstrap.Modal.getOrCreateInstance(modalEl);
      modal.show();
    }

    try {
      const res = await fetch(API_ORDER(orderId), { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      if (title) title.textContent = `${data.customer_display || "Ordine"} — ${data.route_name || ""} (${data.status || ""})`;

      const safeTitle = escapeHtml(data.customer_display || "Ordine");
      const safeRoute = escapeHtml(data.route_name || "");
      const safeStatus = escapeHtml(data.status || "");
      const deliveryText = data.planned_delivery_at
        ? new Date(data.planned_delivery_at).toLocaleString("it-IT", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
          })
        : "";
      const deliveryHint = data.delivery_hint || "";

      const parts = [];
      parts.push(`
        <div class="row g-2">
          <div class="col-12"><div class="fw-bold">Cliente</div><div>${safeTitle}</div></div>
          <div class="col-12"><div class="fw-bold">Giro</div><div>${safeRoute}</div></div>
          <div class="col-12"><div class="fw-bold">Stato</div><div>${safeStatus}</div></div>
          ${
            deliveryText
              ? `<div class="col-12"><div class="fw-bold">Consegna prevista</div><div>${escapeHtml(deliveryText)}${
                  deliveryHint ? ` <span class="badge bg-warning text-dark">da messaggio</span>` : ``
                }</div></div>`
              : ``
          }
          <div class="col-12"><div class="fw-bold">Testo</div><pre class="kiosk-pre">${escapeHtml(data.raw_text || "")}</pre></div>
        </div>
      `);

      if (Array.isArray(data.attachments) && data.attachments.length) {
        parts.push(`
          <hr/>
          <div class="fw-bold">Allegati</div>
          <div class="kiosk-attachments">
            ${data.attachments
              .map((a) => {
                const titleText = escapeHtml(a.title || a.name || "Allegato");
                if (a.is_image) {
                  return `
                    <a class="kiosk-attachment kiosk-attachment--image" href="${escapeHtml(a.url || "#")}" target="_blank" rel="noopener">
                      <img src="${escapeHtml(a.thumb_url || a.url || "")}" alt="${titleText}" loading="lazy">
                      <span>${titleText}</span>
                    </a>
                  `;
                }
                return `
                  <a class="kiosk-attachment" href="${escapeHtml(a.url || "#")}" target="_blank" rel="noopener">
                    <span>${titleText}</span>
                  </a>
                `;
              })
              .join("")}
          </div>
        `);
      }

      if (Array.isArray(data.children) && data.children.length) {
        parts.push(`
          <hr/>
          <div class="fw-bold">Messaggi</div>
          <ul class="mb-0">
            ${data.children.map((c) => `<li><span class="text-muted">${escapeHtml(c.label)}</span> — ${escapeHtml(c.text || "")}</li>`).join("")}
          </ul>
        `);
      }

      if (Array.isArray(data.thread_notes) && data.thread_notes.length) {
        parts.push(`
          <hr/>
          <div class="fw-bold">Note</div>
          <ul class="mb-0">
            ${data.thread_notes.map((n) => `<li>${escapeHtml(n.text || "")}</li>`).join("")}
          </ul>
        `);
      }

      if (body) body.innerHTML = parts.join("");
    } catch (err) {
      if (body) body.innerHTML = `<div class="alert alert-danger">Errore caricamento ordine: ${escapeHtml(String(err))}</div>`;
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

    if (title) title.textContent = `${cust} — ${vm.route_name || ""} (${vm.status || ""})`;

    const seqTotal = vm.seq_total || 1;
    const seqOn = new Set(vm.orders.map((o) => o.group_seq || 1));
    const seqIndicator = buildSeqIndicator(seqTotal, seqOn);

    const list = [...vm.orders]
      .sort((a, b) => (a.group_seq ?? 1) - (b.group_seq ?? 1))
      .map((o) => {
        const seq = o.group_seq || 1;
        const delivery = o.delivery_label || "";
        const notes = o.notes_count || 0;
        const issues = o.issues_count ? 1 : 0;
        const prev = o.preview || "";

        return `
          <div class="kiosk-group-item" style="margin-bottom:10px;">
            <div class="fw-bold">Ordine #${seq}/${seqTotal} ${delivery ? `· ${escapeHtml(delivery)}` : ``}</div>
            ${prev ? `<div class="text-muted">Preview: ${escapeHtml(prev)}</div>` : ``}
            <div class="small">Note: ${notes} · Issues: ${issues} · ID: ${o.id}</div>
            <button class="btn btn-sm btn-primary mt-1" data-open-order="${o.id}">Apri</button>
          </div>
        `;
      })
      .join("");

    const safeRoute = escapeHtml(vm.route_name || "");
    const safeStatus = escapeHtml(vm.status || "");
    const safeCust = escapeHtml(cust);

    const html = `
      <div class="row g-2">
        <div class="col-12"><div class="fw-bold">Cliente</div><div>${safeCust} (grouped)</div></div>
        <div class="col-12"><div class="fw-bold">Giro</div><div>${safeRoute}</div></div>
        <div class="col-12"><div class="fw-bold">Stato</div><div>${safeStatus}</div></div>
        <div class="col-12"><div class="fw-bold">Ordini</div><div>${vm.orders.length}</div></div>
        <div class="col-12"><div class="fw-bold">Sequenza</div>${seqIndicator}</div></div>
        <hr/>
        <div class="col-12"><div class="fw-bold">Dettagli</div>${list}</div>
      </div>
    `;

    if (body) body.innerHTML = html;

    if (body) {
      body.querySelectorAll("[data-open-order]").forEach((btn) => {
        btn.addEventListener("click", (ev) => {
          const id = ev.currentTarget.getAttribute("data-open-order");
          if (id) openOrderModal(id);
        });
      });
    }
  }

  function applyFilterAndRender() {
    const filter = kioskState.currentRouteFilter || "__all__";
    const cards = Array.isArray(kioskState.lastCards) ? kioskState.lastCards : [];
    const filtered = filter === "__all__" ? cards : cards.filter((c) => String(c.route_id) === String(filter));

    document.querySelectorAll(".kiosk-col").forEach((col) => {
      const body = col.querySelector(".kiosk-col__body");
      if (body) body.innerHTML = "";
      const badge = col.querySelector("[data-count]");
      if (badge) badge.textContent = "0";
    });

    const counts = {};
    for (const vm of filtered) {
      const body = document.querySelector(`.kiosk-col[data-status="${vm.status}"] .kiosk-col__body`);
      if (!body) continue;
      body.appendChild(buildCard(vm));
      counts[vm.status] = (counts[vm.status] || 0) + 1;
    }

    document.querySelectorAll(".kiosk-col").forEach((col) => {
      const status = col.dataset.status;
      const body = col.querySelector(".kiosk-col__body");
      const badge = col.querySelector("[data-count]");

      if (body && body.children.length === 0) body.innerHTML = `<div class="kiosk-empty">Nessun ordine</div>`;
      if (badge) badge.textContent = String(counts[status] || 0);
    });

    const pillTotal = document.getElementById("pill-total");
    if (pillTotal) pillTotal.textContent = String(filtered.length);
  }

  function hookFilters() {
    const container = $("#routeFilters");
    if (!container) return;

    container.addEventListener("click", (ev) => {
      const btn = ev.target.closest(".route-pill");
      if (!btn) return;
      const route = btn.getAttribute("data-filter-route");
      kioskState.currentRouteFilter = route || "__all__";
      $all(".route-pill").forEach((b) => b.classList.remove("active"));
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
            customer_key: o.customer_key || "",
            preview: (o.raw_text || "").trim().split("\n")[0].slice(0, 140),
            notes_count: o.note_count || 0,
            issues_count: o.has_issues ? 1 : 0,
            attachment_count: o.attachment_count || 0,
            delivery_from_message: Boolean(o.delivery_from_message),
            group_key: o.group_key || "",
            group_seq: o.group_seq || 1,
            group_size: o.group_size || 1,
            delivery_label: o.delivery_label || "",
            raw_text: o.raw_text || "",
          });
        }
      }
    }

    out.sort((a, b) => {
      const ra = (a.route_name || "").toLowerCase();
      const rb = (b.route_name || "").toLowerCase();
      if (ra !== rb) return ra.localeCompare(rb);

      const sa = kioskState.statusRank[a.status] ?? 99;
      const sb = kioskState.statusRank[b.status] ?? 99;
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
    const byGroup = new Map();
    for (const o of flatOrders) {
      const gk = o.group_key || "";
      if (!byGroup.has(gk)) byGroup.set(gk, { seqTotal: o.group_size || 1, orders: [] });
      const g = byGroup.get(gk);
      g.orders.push(o);
      g.seqTotal = Math.max(g.seqTotal, o.group_size || 1);
    }

    const cards = [];
    for (const [gk, g] of byGroup.entries()) {
      const byStatus = new Map();
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
          route_id: primary.route_id,
          route_name: primary.route_name,
          route_color: primary.route_color,
          customer_display: primary.customer_display,
        });
      }
    }

    cards.sort((a, b) => {
      const ra = (a.route_name || "").toLowerCase();
      const rb = (b.route_name || "").toLowerCase();
      if (ra !== rb) return ra.localeCompare(rb);

      const sa = kioskState.statusRank[a.status] ?? 99;
      const sb = kioskState.statusRank[b.status] ?? 99;
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
      kioskState.lastCards = buildCardViewModels(flat);
      applyFilterAndRender();
      recountColumnsFromDOM();
    } catch (err) {
      console.error("[kiosk_overview] load error", err);
      document.querySelectorAll(".kiosk-col__body").forEach((body) => {
        body.innerHTML = `<div class="kiosk-empty">Nessun ordine</div>`;
      });
      document.querySelectorAll(".kiosk-col [data-count]").forEach((b) => (b.textContent = "0"));
    }
  }

  async function reparseDeliveries() {
    const btn = $("#btn-reparse-deliveries");
    const oldText = btn ? btn.textContent : "";
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Riprogrammo...";
    }

    try {
      const res = await fetch(API_REPARSE_DELIVERIES, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        cache: "no-store",
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok || !json.ok) {
        throw new Error(json.error || `HTTP ${res.status}`);
      }

      await loadAndRender();
      const changed = Number(json.changed || 0);
      if (btn) btn.textContent = changed ? `Riprogrammate: ${changed}` : "Nessuna modifica";
      window.setTimeout(() => {
        if (btn) btn.textContent = oldText || "Riprogramma";
      }, 2500);
    } catch (err) {
      console.error("[kiosk_overview] reparseDeliveries error", err);
      alert(`Errore riprogrammazione: ${String(err.message || err)}`);
      if (btn) btn.textContent = oldText || "Riprogramma";
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function start() {
    hookFilters();

    const btn = $("#btn-refresh");
    if (btn) btn.addEventListener("click", loadAndRender);

    const reparseBtn = $("#btn-reparse-deliveries");
    if (reparseBtn) reparseBtn.addEventListener("click", reparseDeliveries);

    await loadStatuses();
    await loadAndRender();

    if (refreshTimer) clearInterval(refreshTimer);
    refreshTimer = setInterval(loadAndRender, 10000);
  }

  document.addEventListener("DOMContentLoaded", () => {
    start();
  });
})();
