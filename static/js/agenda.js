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
