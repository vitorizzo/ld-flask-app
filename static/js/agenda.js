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

function loadPreview(dateStr) {
  fetch(`/cassa/api/day/${dateStr}/preview?view=fiscal`)
    .then(r => r.json())
    .then(data => {
      if (!data.ok) return;

      const t = data.totals;

      document.getElementById("kpiQ").textContent = t.q.toFixed(2);
      document.getElementById("kpiS").textContent = t.s.toFixed(2);
      document.getElementById("kpiIC").textContent = t.ic.toFixed(2);
      document.getElementById("kpiDeltaFondo").textContent = t.delta_fondo.toFixed(2);
      document.getElementById("kpiDeltaQuadratura").textContent = t.delta_quadratura.toFixed(2);
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
