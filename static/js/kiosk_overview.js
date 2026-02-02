// static/js/kiosk_overview.js

(function () {
  const REFRESH_MS = 10_000;

  const boardEl = document.getElementById("kioskBoard");
  const btnRefresh = document.getElementById("btn-refresh");

  const colMap = {
    acquisito: document.getElementById("col-acquisito"),
    listato: document.getElementById("col-listato"),
    controllato: document.getElementById("col-controllato"),
    evaso: document.getElementById("col-evaso"),
  };

  function ensureEmpty(colEl) {
    if (!colEl) return;
    if (!colEl.querySelector(".kiosk-empty")) {
      const d = document.createElement("div");
      d.className = "kiosk-empty";
      d.textContent = "Nessun ordine";
      colEl.appendChild(d);
    }
  }

  function clearColumns() {
    Object.values(colMap).forEach((colEl) => {
      if (!colEl) return;
      colEl.innerHTML = "";
      ensureEmpty(colEl);
    });
  }

  function removeEmpty(colEl) {
    const empty = colEl.querySelector(".kiosk-empty");
    if (empty) empty.remove();
  }

  function getActiveRouteFilter() {
    return boardEl?.dataset?.activeRoute || "__all__";
  }

  function setActiveRouteFilter(routeId) {
    if (!boardEl) return;
    boardEl.dataset.activeRoute = String(routeId);
  }

  function normalizeOverviewPayload(data) {
    // Ritorna: { orders: [ {id, status, route_id, route_name, route_color, customer_display, raw_text, ...} ] }
    const out = { orders: [] };

    if (!data || typeof data !== "object") return out;

    // Caso A: overview già “flat”
    if (Array.isArray(data.orders)) {
      out.orders = data.orders;
      return out;
    }

    // Caso B: board singola: { route, groups:{acquisito:[], ...} }
    if (data.groups && typeof data.groups === "object") {
      const route = data.route || {};
      Object.entries(data.groups).forEach(([status, arr]) => {
        (arr || []).forEach((o) => {
          out.orders.push({
            ...o,
            status,
            route_id: o.route_id ?? route.id,
            route_name: o.route_name ?? route.name,
            route_color: o.route_color ?? route.color,
          });
        });
      });
      return out;
    }

    // Caso C: overview come lista board: { boards: [ {route, groups}, ... ] }
    if (Array.isArray(data.boards)) {
      data.boards.forEach((b) => {
        const route = b.route || {};
        const groups = b.groups || {};
        Object.entries(groups).forEach(([status, arr]) => {
          (arr || []).forEach((o) => {
            out.orders.push({
              ...o,
              status,
              route_id: o.route_id ?? route.id,
              route_name: o.route_name ?? route.name,
              route_color: o.route_color ?? route.color,
            });
          });
        });
      });
      return out;
    }

    return out;
  }

  function makeBadge(text, cls) {
    const s = document.createElement("span");
    s.className = `badge ${cls}`;
    s.textContent = text;
    return s;
  }

  function createOrderCard(order) {
    const card = document.createElement("div");
    card.className = "order-card";
    card.tabIndex = 0;
    card.dataset.routeId = String(order.route_id ?? "");
    card.dataset.orderId = String(order.id ?? "");

    // Colore di giro
    const routeColor = order.route_color || "#e9ecef";
    card.style.setProperty("--route-bg", routeColor);

    const top = document.createElement("div");
    top.className = "order-top";

    const main = document.createElement("div");
    main.className = "order-main";

    const name = document.createElement("div");
    name.className = "order-name";
    name.textContent = order.customer_display || order.customer || "(senza nome)";
    main.appendChild(name);

    const meta = document.createElement("div");
    meta.className = "order-meta";
    meta.appendChild(document.createTextNode("Giro: "));
    meta.appendChild(makeBadge(order.route_name || "-", "bg-dark"));
    meta.appendChild(document.createTextNode(" · Status: "));
    meta.appendChild(makeBadge(order.status || "-", "bg-secondary"));
    main.appendChild(meta);

    const badges = document.createElement("div");
    badges.className = "order-badges";

    // multi_count: nel tuo JSON è "multi_count" o "msg_count"
    const multiCount = Number(order.multi_count ?? order.msg_count ?? 1);
    const notesCount = Number(order.notes_count ?? order.note_count ?? 0);
    const issuesCount = Number(order.issues_count ?? order.has_issues ? 1 : 0);

    if (multiCount > 1) badges.appendChild(makeBadge(`+${multiCount - 1}`, "badge-multi"));
    if (notesCount > 0) badges.appendChild(makeBadge(String(notesCount), "badge-note"));
    if (issuesCount > 0) badges.appendChild(makeBadge(String(issuesCount), "badge-issue"));

    top.appendChild(main);
    top.appendChild(badges);

    card.appendChild(top);

    // preview: se non c’è, usa raw_text (accorciato)
    const previewText = (order.preview || order.raw_text || "").trim();
    if (previewText) {
      const prev = document.createElement("div");
      prev.className = "order-preview";
      prev.textContent = previewText.length > 120 ? previewText.slice(0, 120) + "…" : previewText;
      card.appendChild(prev);
    }

    // TODO: click -> modal scheda ordine (lo agganciamo dopo che vedi le card)
    return card;
  }

  function renderOrders(orders) {
    clearColumns();

    const activeRoute = getActiveRouteFilter();

    orders.forEach((o) => {
      const status = (o.status || "").toLowerCase();
      const colEl = colMap[status];
      if (!colEl) return;

      const routeId = String(o.route_id ?? "");
      if (activeRoute !== "__all__" && routeId !== String(activeRoute)) return;

      removeEmpty(colEl);
      colEl.appendChild(createOrderCard(o));
    });

    // Se una colonna resta vuota, il placeholder rimane
    Object.values(colMap).forEach(ensureEmpty);
  }

  async function fetchAndRender() {
    try {
      // usa l’endpoint overview: se nel tuo backend è diverso, dimmelo e lo allineo
      const res = await fetch("/kiosk/api/board/all?only_active=1", { cache: "no-store" });
      const data = await res.json();
      const norm = normalizeOverviewPayload(data);
      renderOrders(norm.orders || []);
    } catch (e) {
      console.error("kiosk_overview: fetch failed", e);
      clearColumns();
    }
  }

  function bindRouteFilters() {
    document.querySelectorAll("[data-filter-route]").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll("[data-filter-route]").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        setActiveRouteFilter(btn.dataset.filterRoute || "__all__");
        fetchAndRender();
      });
    });
  }

  // init
  bindRouteFilters();
  if (btnRefresh) btnRefresh.addEventListener("click", fetchAndRender);
  fetchAndRender();
  setInterval(fetchAndRender, REFRESH_MS);
})();
