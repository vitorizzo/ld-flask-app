let currentDay = null;
let calendarInstance = null;

function escapeHtml(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function toLocalYMD(d) {
  const x = new Date(d);
  x.setMinutes(x.getMinutes() - x.getTimezoneOffset());
  return x.toISOString().slice(0, 10);
}

function fetchActiveDays(year, month) {
  const from = new Date(year, month, 1);
  const to = new Date(year, month + 1, 0);

  const fromStr = toLocalYMD(from);
  const toStr = toLocalYMD(to);


  return fetch(`/cassa/api/days/active?from=${fromStr}&to=${toStr}`)
    .then(r => r.json())
    .then(data => data.ok ? data.days.map(d => d.day_date) : []);
}

function loadDay(dateStr) {
  fetch(`/cassa/api/day?date=${dateStr}`)
    .then(r => r.json())
    .then(data => {
      if (!data.ok) return;
      currentDay = data.day.day_date;
      document.getElementById("dayDateTitle").textContent = currentDay;
      document.getElementById("dayId").textContent = data.day.id;
      document.getElementById("dayOpeningFloat").textContent = data.day.opening_float.toFixed(2);
      document.getElementById("dayStatusBadge").textContent = data.day.status.toUpperCase();
      document.getElementById("agendaLastUpdated").textContent =
        "Ultimo aggiornamento: " + new Date().toLocaleTimeString();

      loadPreview(currentDay);
      loadIncassi(currentDay);
      loadAssegniScadenza(currentDay, false);
    });
}

function _num(x) {
  const n = Number(x);
  return Number.isFinite(n) ? n : 0;
}

function _fmt2(x) {
  return _num(x).toFixed(2);
}

function loadPreview(dateStr) {
  fetch(`/cassa/api/day/${dateStr}/preview?view=fiscal`)
    .then(r => r.json())
    .then(data => {
      if (!data.ok) return;

      const t = data.totals || {};

      // Prova chiavi alternative (compatibilità) + fallback a 0
      const q = (t.q ?? t.q_versabile ?? t.Q ?? t.versabile_giornata);
      const s = (t.s ?? t.s_versabile ?? t.S ?? t.saldo_versabile);
      const ic = (t.ic ?? t.IC ?? t.incasso_calcolato);
      const df = (t.delta_fondo ?? t.deltaFondo ?? t.df);
      const dq = (t.delta_quadratura ?? t.deltaQuadratura ?? t.dq);

      document.getElementById("kpiQ").textContent = _fmt2(q);
      document.getElementById("kpiS").textContent = _fmt2(s);
      document.getElementById("kpiIC").textContent = _fmt2(ic);
      document.getElementById("kpiDeltaFondo").textContent = _fmt2(df);
      document.getElementById("kpiDeltaQuadratura").textContent = _fmt2(dq);
    })
    .catch(err => console.error("loadPreview error:", err));
}

function eur(amount) {
  const n = Number(amount || 0);
  return n.toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

function renderAssegniScadenza(items) {
  const list = document.getElementById("assegniScadenzaList");
  if (!list) return;

  list.innerHTML = "";

  if (!items || !items.length) {
    const empty = document.createElement("div");
    empty.className = "list-group-item text-muted small";
    empty.textContent = "Nessun assegno versabile (V1)";
    list.appendChild(empty);
    return;
  }

  for (const c of items) {
    const row = document.createElement("div");
    row.className = "list-group-item d-flex justify-content-between align-items-start gap-2";

    const left = document.createElement("div");
    left.className = "me-2";

    const title = document.createElement("div");
    title.className = c.is_received_today ? "fw-bold" : "fw-semibold";
    const bank = (c.bank_name || "Banca?").trim();
    const num = (c.check_number || "").trim();
    title.textContent = `${bank} • ${num}`;

    const meta = document.createElement("div");
    meta.className = "small text-muted";
    const cust = (c.customer && (c.customer.display_name || c.customer.name || c.customer.ragione_sociale))
      ? (c.customer.display_name || c.customer.name || c.customer.ragione_sociale)
      : "Cliente?";
    const due = c.due_date || "—";
    const rec = c.received_date || "—";
    meta.textContent = `Cliente: ${cust} • Scadenza: ${due} • Ricevuto: ${rec}`;

    left.appendChild(title);
    left.appendChild(meta);

    const right = document.createElement("div");
    right.className = "text-end";
    const amt = document.createElement("div");
    amt.className = c.is_overdue ? "fw-bold text-danger" : "fw-bold";
    amt.textContent = eur(c.amount);

    right.appendChild(amt);

    row.appendChild(left);
    row.appendChild(right);

    list.appendChild(row);
  }
}

async function loadIncassi(dayStr) {
  const listEl = document.getElementById("incassiList");
  if (!listEl) return;

  listEl.innerHTML = `<li class="muted">Caricamento...</li>`;

  try {
    const r = await fetch(`/cassa/api/day/${dayStr}/sales`, { credentials: "same-origin" });
    const data = await r.json();
    if (!data.ok) {
      listEl.innerHTML = `<li class="muted">Errore: ${data.error || "impossibile caricare incassi"}</li>`;
      return;
    }

    const sales = data.sales || [];
    if (!sales.length) {
      listEl.innerHTML = `<li class="muted">Nessun incasso</li>`;
      return;
    }

    // flatten payments (per ora mostriamo ogni payment come riga)
    const rows = [];
    for (const s of sales) {
      for (const p of (s.payments || [])) {
        rows.push({
          sale_id: s.id,
          created_at: p.created_at || s.created_at,
          flag: p.flag || "",
          desc: p.description || s.notes || "",
          amount: Number(p.amount || 0),
          direction: p.direction || "in",
          method: p.method || "",
          off_cash: !!p.off_cash,
        });
      }
    }

    listEl.innerHTML = rows.map(x => {
      const sign = x.direction === "out" ? "-" : "";
      const amt = `${sign}${x.amount.toFixed(2)}€`;
      const extra = [
        x.method ? x.method.toUpperCase() : null,
        x.off_cash ? "FUORI CASSA" : null,
      ].filter(Boolean).join(" · ");

      return `
        <li class="row-incasso" data-sale-id="${x.sale_id}">
          <span class="flag">${x.flag}</span>
          <span class="desc">${escapeHtml(x.desc)}</span>
          <span class="amt">${amt}</span>
          ${extra ? `<span class="meta">${extra}</span>` : ""}
        </li>
      `;
    }).join("");

    const totalEl = document.getElementById("totIncassi");
    if (totalEl) {
      const tot = rows.reduce((s, x) =>
        s + (x.direction === "out" ? -x.amount : x.amount), 0
      );
      totalEl.textContent = tot.toFixed(2).replace(".", ",");
    }

  } catch (e) {
    console.error(e);
    listEl.innerHTML = `<li class="muted">Errore di rete</li>`;
  }
}

function loadAssegniScadenza(dateStr = null, includeTodayReceived = false) {
  const ref = dateStr || currentDay || toLocalYMD(new Date());
  const qs = new URLSearchParams({
    date: ref,
    include_today_received: includeTodayReceived ? "1" : "0",
  });

  fetch(`/cassa/api/checks/due?${qs.toString()}`)
    .then(r => r.json())
    .then(data => {
      if (!data.ok) return;
      renderAssegniScadenza(data.checks || []);
    })
    .catch(() => {
      const list = document.getElementById("assegniScadenzaList");
      if (list) list.innerHTML = `<div class="list-group-item text-danger small">Errore caricamento assegni</div>`;
    });
}

document.addEventListener("DOMContentLoaded", function () {

  calendarInstance = flatpickr("#agendaCalendar", {
    inline: true,
    defaultDate: new Date(),
    onMonthChange: function(selectedDates, dateStr, instance) {
      decorateMonth(instance.currentYear, instance.currentMonth);
    },
    onChange: function(selectedDates) {
      if (selectedDates.length) {
        loadDay(toLocalYMD(selectedDates[0]));
      }
    }
  });

  decorateMonth(calendarInstance.currentYear, calendarInstance.currentMonth);

  loadDay(toLocalYMD(new Date()));
  startAssegniAutoRefresh();
});

function decorateMonth(year, month) {
  fetchActiveDays(year, month).then(activeDays => {

    document.querySelectorAll(".flatpickr-day").forEach(dayEl => {
      dayEl.classList.remove("has-movements");
    });

    activeDays.forEach(dateStr => {
      const dateObj = new Date(dateStr);
      const day = dateObj.getDate();

      document.querySelectorAll(".flatpickr-day").forEach(el => {
        if (
          el.dateObj &&
          el.dateObj.getFullYear() === year &&
          el.dateObj.getMonth() === month &&
          el.dateObj.getDate() === day
        ) {
          el.classList.add("has-movements");
        }
      });
    });
  });
}

let assegniInterval = null;

function startAssegniAutoRefresh() {
  if (assegniInterval) return;

  assegniInterval = setInterval(() => {
    if (document.visibilityState === "visible") {
      loadAssegniScadenza(currentDay, false);
    }
  }, 30000); // 30s
}

function stopAssegniAutoRefresh() {
  if (assegniInterval) {
    clearInterval(assegniInterval);
    assegniInterval = null;
  }
}

document.addEventListener("visibilitychange", function () {
  if (document.visibilityState === "visible") {
    loadAssegniScadenza(currentDay, false);
    startAssegniAutoRefresh();
  } else {
    stopAssegniAutoRefresh();
  }
});
