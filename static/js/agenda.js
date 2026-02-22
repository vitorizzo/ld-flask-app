let currentDay = null;
let calendarInstance = null;

function fetchActiveDays(year, month) {
  const from = new Date(year, month, 1);
  const to = new Date(year, month + 1, 0);

  const fromStr = from.toISOString().split("T")[0];
  const toStr = to.toISOString().split("T")[0];

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
      loadAssegniScadenza();
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
    const cust = c.customer && (c.customer.name || c.customer.ragione_sociale) ? (c.customer.name || c.customer.ragione_sociale) : "Cliente?";
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

function loadAssegniScadenza() {
  fetch(`/cassa/api/checks/due`)
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
        const d = selectedDates[0].toISOString().split("T")[0];
        loadDay(d);
      }
    }
  });

  decorateMonth(calendarInstance.currentYear, calendarInstance.currentMonth);

  const todayStr = new Date().toISOString().split("T")[0];
  loadDay(todayStr);
  loadAssegniScadenza();
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
      loadAssegniScadenza();
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
    loadAssegniScadenza();
    startAssegniAutoRefresh();
  } else {
    stopAssegniAutoRefresh();
  }
});
