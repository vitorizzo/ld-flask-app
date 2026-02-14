let CASH_DAY = null;

function euro(v) {
  const n = Number(v || 0);
  return n.toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

function renderDayHeader(day) {
  const el = document.getElementById("day-header");
  if (!el) return;

  const badge = day.status === "closed"
    ? `<span class="badge bg-secondary">CHIUSA</span>`
    : `<span class="badge bg-success">APERTA</span>`;

  el.innerHTML = `
    <div class="d-flex align-items-center justify-content-between flex-wrap gap-2">
      <div>
        <div class="h4 mb-0">Agenda Cassa — ${day.day_date}</div>
        <div class="text-muted">Fondo cassa iniziale: <strong>${euro(day.opening_float)}</strong></div>
      </div>
      <div>${badge}</div>
    </div>
  `;
}

async function loadOrCreateDay() {
  const res = await fetch("/cassa/api/day", { headers: { "Accept": "application/json" } });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  if (!data.ok) throw new Error(data.error || "Errore API");
  CASH_DAY = data.day;
  renderDayHeader(CASH_DAY);
  console.log("CASH_DAY:", CASH_DAY);
}

document.addEventListener("DOMContentLoaded", async () => {
  try {
    await loadOrCreateDay();
  } catch (err) {
    console.error("Errore inizializzazione agenda:", err);
  }
});
