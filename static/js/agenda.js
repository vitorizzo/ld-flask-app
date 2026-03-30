let currentDay = null;
let calendarInstance = null;
let lastPaymentMode = "cash";
let currentPreviewTotals = {};

/* =========================
   UTILS BASE
========================= */

function setText(id, value) {
  const el = document.getElementById(id);
  if (!el) return false;
  el.textContent = value;
  return true;
}

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

function _num(x) {
  const n = Number(x);
  return Number.isFinite(n) ? n : 0;
}

function _fmt2(x) {
  return _num(x).toFixed(2);
}

function eur(amount) {
  const n = Number(amount || 0);
  return n.toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

function parseEuroToNumber(raw) {
  if (raw == null) return 0;
  const s = String(raw).trim()
    .replace(/\./g, "")
    .replace(",", ".")
    .replace(/[^\d.-]/g, "");
  const n = Number(s);
  return Number.isFinite(n) ? n : 0;
}

function formatEuro2(n) {
  const x = Number(n);
  const safe = Number.isFinite(x) ? x : 0;
  return safe.toLocaleString("it-IT", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
}

function isNonEmpty(value) {
  return String(value || "").trim().length > 0;
}

function setBadgeState(id, ok) {
  const el = document.getElementById(id);
  if (!el) return;

  if (ok) {
    el.className = "badge rounded-pill text-bg-success";
  } else {
    el.className = "badge rounded-pill border border-danger text-danger bg-transparent";
  }
}

function setIndicativeState(id, isIndicative) {
  const el = document.getElementById(id);
  if (!el) return;

  el.classList.toggle("kpi-num-indicative", !!isIndicative);
}

function updateQuadraturaLeds(delta) {
  const leds = {
    redLeft: document.getElementById("ledQuadraturaRedLeft"),
    yellowLeft: document.getElementById("ledQuadraturaYellowLeft"),
    green: document.getElementById("ledQuadraturaGreen"),
    yellowRight: document.getElementById("ledQuadraturaYellowRight"),
    redRight: document.getElementById("ledQuadraturaRedRight"),
  };

  Object.values(leds).forEach(el => {
    if (!el) return;
    el.classList.remove("on");
  });

  if (delta === null || delta === undefined) return;

  const d = Number(delta);

  if (Math.abs(d) <= 2) {
    leds.green?.classList.add("on");
    return;
  }

  if (d > 2 && d <= 10) {
    leds.yellowRight?.classList.add("on");
    return;
  }

  if (d < -2 && d >= -10) {
    leds.yellowLeft?.classList.add("on");
    return;
  }

  if (d > 10) {
    leds.redRight?.classList.add("on");
    return;
  }

  if (d < -10) {
    leds.redLeft?.classList.add("on");
    return;
  }
}

/* =========================
   API HELPERS
========================= */

function fetchActiveDays(year, month) {
  const from = new Date(year, month, 1);
  const to = new Date(year, month + 1, 0);

  const fromStr = toLocalYMD(from);
  const toStr = toLocalYMD(to);

  return fetch(`/cassa/api/days/active?from=${fromStr}&to=${toStr}`)
    .then(r => r.json())
    .then(data => data.ok ? data.days.map(d => d.day_date) : []);
}

async function fetchCustomerSuggest(q) {
  const url = `/cassa/api/customers/suggest?q=${encodeURIComponent(q)}`;
  const r = await fetch(url, {
    credentials: "same-origin",
    headers: { "Accept": "application/json" }
  });
  const data = await r.json();
  if (!data.ok) return [];
  return data.customers || [];
}

/* =========================
   OWNER TAKE MODAL REFS
========================= */

const ownerTakeModalEl = document.getElementById("ownerTakeModal");
const ownerTakeTypeSelect = document.getElementById("ownerTakeType");
const ownerTakeCashAmountInput = document.getElementById("ownerTakeCashAmount");
const ownerTakeNoteInput = document.getElementById("ownerTakeNote");
const ownerTakeChecksHint = document.getElementById("ownerTakeChecksHint");
const ownerTakeChecksTableBody = document.getElementById("ownerTakeChecksTableBody");
const ownerTakeTableBody = document.getElementById("ownerTakeTableBody");
const ownerTakeTotalAmountEl = document.getElementById("ownerTakeTotalAmount");
const ownerTakeAddBtn = document.getElementById("ownerTakeAddBtn");

let ownerTakeModal = null;
let editingOwnerTakeId = null;

/* =========================
   OWNER TAKES
========================= */

function resetOwnerTakeForm() {
  editingOwnerTakeId = null;

  if (ownerTakeTypeSelect) ownerTakeTypeSelect.value = "serale";
  if (ownerTakeCashAmountInput) ownerTakeCashAmountInput.value = "0,00";
  if (ownerTakeNoteInput) ownerTakeNoteInput.value = "";

  const addBtn = document.getElementById("ownerTakeAddBtn");
  if (addBtn) addBtn.textContent = "Salva prelievo";

  if (ownerTakeChecksTableBody) {
    ownerTakeChecksTableBody.querySelectorAll(".owner-take-check-select").forEach(el => {
      el.checked = false;
    });
  }

  updateOwnerTakeTotal();
}

function startEditOwnerTake(row) {
  editingOwnerTakeId = row.id;

  if (ownerTakeTypeSelect) ownerTakeTypeSelect.value = row.take_type || "serale";
  if (ownerTakeCashAmountInput) ownerTakeCashAmountInput.value = formatEuro2(row.cash_amount || 0);
  if (ownerTakeNoteInput) ownerTakeNoteInput.value = row.notes || "";

  const selectedIds = new Set((row.checks || []).map(x => Number(x.id)));

  if (ownerTakeChecksTableBody) {
    ownerTakeChecksTableBody.querySelectorAll(".owner-take-check-select").forEach(el => {
      el.checked = selectedIds.has(Number(el.value));
    });
  }

  const addBtn = document.getElementById("ownerTakeAddBtn");
  if (addBtn) addBtn.textContent = "Salva modifica";

  updateOwnerTakeTotal();
  ownerTakeCashAmountInput?.focus();
  ownerTakeCashAmountInput?.select?.();
}

function updateOwnerTakeTotal() {
  const cash = parseEuroToNumber(ownerTakeCashAmountInput?.value || "0");

  const checksTotal = Array.from(
    ownerTakeChecksTableBody?.querySelectorAll(".owner-take-check-select:checked") || []
  ).reduce((sum, el) => {
    return sum + Number(el.dataset.amount || 0);
  }, 0);

  const total = cash + checksTotal;

  if (ownerTakeTotalAmountEl) {
    ownerTakeTotalAmountEl.textContent = `€ ${formatEuro2(total)}`;
  }

  if (ownerTakeChecksHint) {
    ownerTakeChecksHint.textContent =
      `Assegni selezionati: ${formatEuro2(checksTotal)} • Totale prelievo: ${formatEuro2(total)}`;
  }
}

async function loadOwnerTakeAvailableChecks(dayStr) {
  if (!ownerTakeChecksTableBody) return;

  ownerTakeChecksTableBody.innerHTML = `
    <tr>
      <td colspan="7" class="text-center text-muted">Caricamento...</td>
    </tr>
  `;

  try {
    const r = await fetch(`/cassa/api/day/${dayStr}/owner-take-available-checks`, {
      credentials: "same-origin",
      headers: { "Accept": "application/json" }
    });

    const data = await r.json();

    if (!r.ok || !data.ok) {
      ownerTakeChecksTableBody.innerHTML = `
        <tr>
          <td colspan="7" class="text-center text-danger">
            ${escapeHtml(data.error || "Errore caricamento assegni")}
          </td>
        </tr>
      `;
      updateOwnerTakeTotal();
      return;
    }

    const checks = data.checks || [];

    if (!checks.length) {
      ownerTakeChecksTableBody.innerHTML = `
        <tr>
          <td colspan="7" class="text-center text-muted">Nessun assegno disponibile</td>
        </tr>
      `;
      updateOwnerTakeTotal();
      return;
    }

    ownerTakeChecksTableBody.innerHTML = checks.map(c => `
      <tr data-check-id="${c.id}">
        <td>
          <input
            type="checkbox"
            class="form-check-input owner-take-check-select"
            value="${c.id}"
            data-amount="${Number(c.amount || 0)}">
        </td>
        <td>${escapeHtml(c.bank_name || "")}</td>
        <td>${escapeHtml(c.check_number || "")}</td>
        <td>${escapeHtml(c.customer_display_name || "")}</td>
        <td>${escapeHtml(c.received_date || "")}</td>
        <td>${escapeHtml(c.due_date || "")}</td>
        <td class="text-end">${formatEuro2(c.amount || 0)}</td>
      </tr>
    `).join("");

    updateOwnerTakeTotal();

  } catch (err) {
    console.error("loadOwnerTakeAvailableChecks error:", err);
    ownerTakeChecksTableBody.innerHTML = `
      <tr>
        <td colspan="7" class="text-center text-danger">Errore di rete</td>
      </tr>
    `;
    updateOwnerTakeTotal();
  }
}

async function loadOwnerTakes(dayStr) {
  if (!ownerTakeTableBody) return;

  ownerTakeTableBody.innerHTML = `
    <tr>
      <td colspan="7" class="text-center text-muted">Caricamento...</td>
    </tr>
  `;

  try {
    const r = await fetch(`/cassa/api/day/${dayStr}/owner-takes`, {
      credentials: "same-origin",
      headers: { "Accept": "application/json" }
    });

    const data = await r.json();

    if (!r.ok || !data.ok) {
      ownerTakeTableBody.innerHTML = `
        <tr>
          <td colspan="7" class="text-center text-danger">
            ${escapeHtml(data.error || "Errore caricamento prelievi")}
          </td>
        </tr>
      `;
      return;
    }

    const rows = data.owner_takes || [];

    if (!rows.length) {
      ownerTakeTableBody.innerHTML = `
        <tr>
          <td colspan="7" class="text-center text-muted">Nessun prelievo</td>
        </tr>
      `;
      return;
    }

    ownerTakeTableBody.innerHTML = rows.map(row => `
      <tr data-owner-take-id="${row.id}">
        <td>${row.created_at ? new Date(row.created_at).toLocaleString() : ""}</td>
        <td>${row.take_type === "serale" ? "Prelievo serale" : "Prelievo parziale"}</td>
        <td class="text-end">${formatEuro2(row.cash_amount || 0)}</td>
        <td class="text-end">${formatEuro2(row.check_amount || 0)}</td>
        <td class="text-end fw-semibold">${formatEuro2(row.total_amount || 0)}</td>
        <td>${escapeHtml(row.notes || "")}</td>
        <td class="text-end">
          <button
            type="button"
            class="btn btn-sm btn-outline-secondary btn-owner-take-edit"
            data-row='${escapeHtml(JSON.stringify(row))}'>
            Modifica
          </button>
          <button
            type="button"
            class="btn btn-sm btn-outline-danger btn-owner-take-delete"
            data-id="${row.id}">
            Elimina
          </button>
        </td>
      </tr>
    `).join("");

  } catch (err) {
    console.error("loadOwnerTakes error:", err);
    ownerTakeTableBody.innerHTML = `
      <tr>
        <td colspan="7" class="text-center text-danger">Errore di rete</td>
      </tr>
    `;
  }
}

async function openOwnerTakeModal() {
  if (!currentDay) {
    alert("Nessuna giornata selezionata.");
    return;
  }

  resetOwnerTakeForm();
  await loadOwnerTakeAvailableChecks(currentDay);
  await loadOwnerTakes(currentDay);
  updateOwnerTakeTotal();

  if (!ownerTakeModal) {
    alert("Modale cassetto non disponibile.");
    return;
  }

  ownerTakeModal.show();
}

async function saveOwnerTake() {
  if (!currentDay) {
    alert("Nessuna giornata selezionata.");
    return;
  }

  const take_type = (ownerTakeTypeSelect?.value || "serale").trim();
  const cash_amount = parseEuroToNumber(ownerTakeCashAmountInput?.value || "0");
  const notes = (ownerTakeNoteInput?.value || "").trim() || null;

  const check_ids = Array.from(
    ownerTakeChecksTableBody?.querySelectorAll(".owner-take-check-select:checked") || []
  ).map(el => Number(el.value)).filter(Number.isFinite);

  if (cash_amount <= 0 && check_ids.length === 0) {
    alert("Inserisci almeno contanti o seleziona almeno un assegno.");
    return;
  }

  const isEdit = !!editingOwnerTakeId;
  const url = isEdit
    ? `/cassa/api/owner-takes/${editingOwnerTakeId}`
    : `/cassa/api/day/${currentDay}/owner-takes`;

  const method = isEdit ? "PUT" : "POST";

  try {
    if (ownerTakeAddBtn) ownerTakeAddBtn.disabled = true;

    const r = await fetch(url, {
      method,
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/json"
      },
      credentials: "same-origin",
      body: JSON.stringify({
        take_type,
        cash_amount,
        notes,
        check_ids
      })
    });

    const data = await r.json();

    if (!r.ok || !data.ok) {
      alert(data.error || "Errore salvataggio prelievo");
      return;
    }

    resetOwnerTakeForm();
    await loadOwnerTakeAvailableChecks(currentDay);
    await loadOwnerTakes(currentDay);
    updateOwnerTakeTotal();
    await loadPreview(currentDay);

  } catch (err) {
    console.error("saveOwnerTake error:", err);
    alert("Errore di rete durante il salvataggio del prelievo.");
  } finally {
    if (ownerTakeAddBtn) ownerTakeAddBtn.disabled = false;
  }
}

async function deleteOwnerTake(ownerTakeId) {
  if (!ownerTakeId) return;

  const confirmed = window.confirm("Vuoi eliminare questo prelievo?");
  if (!confirmed) return;

  try {
    const r = await fetch(`/cassa/api/owner-takes/${ownerTakeId}`, {
      method: "DELETE",
      headers: { "Accept": "application/json" },
      credentials: "same-origin"
    });

    const data = await r.json();

    if (!r.ok || !data.ok) {
      alert(data.error || "Errore eliminazione prelievo");
      return;
    }

    if (editingOwnerTakeId && Number(editingOwnerTakeId) === Number(ownerTakeId)) {
      resetOwnerTakeForm();
    }

    await loadOwnerTakeAvailableChecks(currentDay);
    await loadOwnerTakes(currentDay);
    updateOwnerTakeTotal();
    await loadPreview(currentDay);

  } catch (err) {
    console.error("deleteOwnerTake error:", err);
    alert("Errore di rete durante l'eliminazione del prelievo.");
  }
}

/* =========================
   DRAWER COUNT MODAL REFS
========================= */

const drawerModalEl = document.getElementById("drawerCountModal");
const drawerRowsEl = document.getElementById("drawerCountRows");
const drawerTotalEl = document.getElementById("drawerGrandTotal");
const drawerSaveBtn = document.getElementById("drawerSaveBtn");
const drawerDeleteBtn = document.getElementById("drawerDeleteBtn");

let drawerModal = null;

/* =========================
   ECOMMERCE MODAL REFS
========================= */

const ecommerceModalEl = document.getElementById("ecommerceModal");
const ecoTableBody = document.getElementById("ecoTableBody");
const ecoAddBtn = document.getElementById("ecoAddBtn");
const ecoAmountInput = document.getElementById("ecoAmount");
const ecoDescriptionInput = document.getElementById("ecoDescription");

let ecommerceModal = null;

/* =========================
   DEPOSIT MODAL REFS
========================= */

const depositModalEl = document.getElementById("depositModal");
const depositTypeSelect = document.getElementById("depositType");
const depositDateInput = document.getElementById("depositDate");
const depositCashAmountInput = document.getElementById("depositCashAmount");
const depositTotalAmountInput = document.getElementById("depositTotalAmount");
const depositNoteInput = document.getElementById("depositNote");
const depositChecksHint = document.getElementById("depositChecksHint");
const depositChecksTableBody = document.getElementById("depositChecksTableBody");
const depositTableBody = document.getElementById("depositTableBody");
const depositAddBtn = document.getElementById("depositAddBtn");
const depositBankSelect = document.getElementById("depositBank");

let depositModal = null;
let editingDepositId = null;

/* =========================
   DAY / PREVIEW
========================= */

function loadDay(dateStr) {
  fetch(`/cassa/api/day?date=${dateStr}`)
    .then(r => r.json())
    .then(data => {
      if (!data.ok) return;

      currentDay = data.day.day_date;

      setText("dayDateTitle", currentDay);
      setText("dayId", data.day.id);
      setText("dayOpeningFloat", Number(data.day.opening_float || 0).toFixed(2));
      setText("dayStatusBadge", String(data.day.status || "—").toUpperCase());
      setText("agendaLastUpdated", "Ultimo aggiornamento: " + new Date().toLocaleTimeString());

      loadPreview(currentDay);
      loadIncassi(currentDay);
      loadSpese(currentDay);
      loadPosMoves(currentDay);
      loadCashMoves(currentDay);
      loadCoinsBalance(currentDay);
      loadAssegniScadenza(currentDay, false);

      document.getElementById("btnNewIncasso")?.removeAttribute("disabled");
      document.getElementById("btnNewSpesa")?.removeAttribute("disabled");
      document.getElementById("btnNewMovimento")?.removeAttribute("disabled");
      document.getElementById("btnNewPos")?.removeAttribute("disabled");
    });
}

async function loadPreview(dateStr) {
  try {
    const r = await fetch(`/cassa/api/day/${dateStr}/preview?view=fiscal`, {
      credentials: "same-origin",
      headers: { "Accept": "application/json" },
      cache: "no-store"
    });

    const data = await r.json();
    if (!data.ok) return;

    const t = data.totals || {};
    currentPreviewTotals = t;

    const q = (t.q ?? t.q_versabile ?? t.Q ?? t.versabile_residuo);
    const s = (t.s ?? t.s_versabile ?? t.S ?? t.saldo_versabile);
    const ic = (t.ic ?? t.IC ?? t.incasso_calcolato);
    const df = (t.delta_fondo ?? t.deltaFondo ?? t.df);
    const dq = (t.delta_quadratura ?? t.deltaQuadratura ?? t.dq);
    const fondoInit = (t.fondo_iniziale ?? t.opening_float ?? t.fondoIniziale);
    const fondoFin = (t.fondo_finale ?? t.fondoFinale);
    const sPrev = (t.saldo_versabile_precedente ?? t.saldo_versabile_init ?? t.saldoVersabilePrecedente);
    const totEcommerce = Number(t.totale_ecommerce || 0);
    const totVers = (t.totale_versato_oggi ?? t.totale_versamenti ?? t.totVersamenti);
    const cor = (t.total_corrispettivi ?? t.corrispettivi ?? t.corrispettivi_totali);
    const consegnato = (t.incasso_consegnato ?? t.incassoConsegnato);
    const hasCorrispettivi = !!t.has_corrispettivi;
    const hasFondoIniziale = !!t.has_fondo_iniziale;
    const hasFondoFinale = !!t.has_fondo_finale;
    const totaleGiornataIsPartial = !!t.totale_giornata_is_partial;
    const hasQuadratura = hasCorrispettivi && hasFondoIniziale && hasFondoFinale;

    setText("kpiSaldoVersabileInit", _fmt2(sPrev));
    setText("kpiSaldoVersabileNew", _fmt2(s));
    setText("kpiVersabileGiornata", _fmt2(q));

    setText("kpiFondoIniziale", _fmt2(fondoInit));
    setText("kpiFondoFinale", _fmt2(fondoFin));

    setText("kpiIC", _fmt2(ic));

    setBadgeState("badgeCorrispettiviState", hasCorrispettivi);
    setBadgeState("badgeFondoState", hasFondoIniziale && hasFondoFinale);
    setIndicativeState("kpiIC", totaleGiornataIsPartial);

    setText("kpiDeltaFondo", _fmt2(df));

    const dqEl = document.getElementById("kpiDeltaQuadratura");

    if (!hasQuadratura) {
      if (dqEl) dqEl.textContent = "--";
      updateQuadraturaLeds(null);
    } else {
      if (dqEl) dqEl.textContent = _fmt2(dq);
      updateQuadraturaLeds(Number(dq));
    }

    setText("kpiTotEcommerce", _fmt2(totEcommerce));
    setText("kpiTotVersamenti", _fmt2(totVers));
    setText("kpiCorrispettivi", _fmt2(cor));
    setText("kpiIncassoConsegnato", _fmt2(consegnato));

    updateDepositCashUi();
  } catch (err) {
    console.error("loadPreview error:", err);
  }
}

async function refreshAgendaData() {
  if (!currentDay) return;

  await loadPreview(currentDay);
  await Promise.all([
    loadIncassi(currentDay),
    loadSpese(currentDay),
    loadPosMoves(currentDay),
    loadCashMoves(currentDay),
    loadCoinsBalance(currentDay)
  ]);

  loadAssegniScadenza(currentDay, false);
}

/* =========================
   DRAWER COUNT
========================= */

async function openDrawerCountModal() {
  if (!currentDay) {
    alert("Nessuna giornata selezionata.");
    return;
  }

  try {
    const res = await fetch(`/cassa/api/day/${currentDay}/drawer-count`, {
      credentials: "same-origin",
      headers: { "Accept": "application/json" }
    });

    const data = await res.json();

    if (!data.ok) {
      alert(data.error || "Errore caricamento conteggio fondo");
      return;
    }

    renderDrawerRows(data.drawer_count?.lines || []);

    if (!drawerModal) {
      alert("Modale conteggio fondo non disponibile.");
      return;
    }

    drawerModal.show();
  } catch (err) {
    console.error("openDrawerCountModal error:", err);
    alert("Errore di rete durante il caricamento del conteggio fondo.");
  }
}

function renderDrawerRows(lines) {
  if (!drawerRowsEl) return;

  drawerRowsEl.innerHTML = "";

  lines.forEach(line => {
    const tr = document.createElement("tr");

    tr.innerHTML = `
      <td>€ ${escapeHtml(String(line.denomination))}</td>
      <td>
        <input
          type="number"
          min="0"
          step="1"
          class="form-control form-control-sm drawer-qty"
          data-denom="${escapeHtml(String(line.denomination))}"
          value="${Number(line.quantity || 0)}"
        >
      </td>
      <td class="drawer-line-total">
        ${eur(parseEuroToNumber(line.line_total || 0))}
      </td>
    `;

    drawerRowsEl.appendChild(tr);
  });

  updateDrawerTotals();
}

function updateDrawerTotals() {
  if (!drawerRowsEl || !drawerTotalEl) return;

  let grand = 0;

  drawerRowsEl.querySelectorAll("tr").forEach(row => {
    const qtyInput = row.querySelector(".drawer-qty");
    if (!qtyInput) return;

    const denom = Number(qtyInput.dataset.denom || 0);
    const qty = Number(qtyInput.value || 0);
    const total = denom * qty;

    const totalCell = row.querySelector(".drawer-line-total");
    if (totalCell) {
      totalCell.innerText = eur(total);
    }

    grand += total;
  });

  drawerTotalEl.innerText = eur(grand);
}

async function saveDrawerCount() {
  if (!currentDay) {
    alert("Nessuna giornata selezionata.");
    return;
  }

  if (!drawerRowsEl) {
    alert("Tabella conteggio fondo non disponibile.");
    return;
  }

  const lines = [];

  drawerRowsEl.querySelectorAll("tr").forEach(row => {
    const qtyInput = row.querySelector(".drawer-qty");
    if (!qtyInput) return;

    lines.push({
      denomination: qtyInput.dataset.denom,
      quantity: Number(qtyInput.value || 0)
    });
  });

  try {
    const res = await fetch(`/cassa/api/day/${currentDay}/drawer-count`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ lines })
    });

    const data = await res.json();

    if (!data.ok) {
      alert(data.error || "Errore salvataggio fondo cassa");
      return;
    }

    if (drawerModal) {
      drawerModal.hide();
    }

    await refreshAgendaData();
  } catch (err) {
    console.error("saveDrawerCount error:", err);
    alert("Errore di rete durante il salvataggio del fondo cassa.");
  }
}

async function deleteDrawerCount() {
  if (!currentDay) {
    alert("Nessuna giornata selezionata.");
    return;
  }

  const confirmed = window.confirm(
    "Vuoi eliminare completamente il conteggio del fondo cassa di questa giornata?"
  );

  if (!confirmed) return;

  try {
    const res = await fetch(`/cassa/api/day/${currentDay}/drawer-count`, {
      method: "DELETE",
      headers: { "Accept": "application/json" },
      credentials: "same-origin"
    });

    const data = await res.json();

    if (!data.ok) {
      alert(data.error || "Errore eliminazione fondo cassa");
      return;
    }

    if (drawerModal) {
      drawerModal.hide();
    }

    await refreshAgendaData();
  } catch (err) {
    console.error("deleteDrawerCount error:", err);
    alert("Errore di rete durante l'eliminazione del fondo cassa.");
  }
}

/* =========================
   ASSEGNI
========================= */

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
      if (list) {
        list.innerHTML = `<div class="list-group-item text-danger small">Errore caricamento assegni</div>`;
      }
    });
}

/* =========================
   RENDER LISTE GIORNATA
========================= */

async function loadCoinsBalance(dayStr) {
  const el = document.getElementById("coinsVaultBalance");
  if (!el) return;

  el.textContent = "—";

  try {
    const r = await fetch(`/cassa/api/coins/balance?date=${encodeURIComponent(dayStr)}`, {
      credentials: "same-origin"
    });
    const data = await r.json();
    if (!data.ok) {
      el.textContent = "—";
      return;
    }
    el.textContent = _fmt2(data.coins_vault_balance).replace(".", ",");
  } catch (e) {
    console.error("loadCoinsBalance error:", e);
    el.textContent = "—";
  }
}

async function loadCashMoves(dayStr) {
  const listEl = document.getElementById("movCassaList");
  const totalEl = document.getElementById("totMovCassa");
  if (!listEl) return;

  listEl.innerHTML = `<div class="list-group-item text-muted small">Caricamento...</div>`;
  if (totalEl) totalEl.textContent = "0,00";

  try {
    const r = await fetch(`/cassa/api/day/${dayStr}/cash_moves`, { credentials: "same-origin" });
    const data = await r.json();

    if (!data.ok) {
      listEl.innerHTML = `<div class="list-group-item text-muted small">Errore: ${data.error || "impossibile caricare movimenti"}</div>`;
      return;
    }

    const moves = data.cash_moves || [];
    if (!moves.length) {
      listEl.innerHTML = `<div class="list-group-item text-muted small">Nessun movimento</div>`;
      return;
    }

    const tot = moves.reduce((s, m) => s + Number(m.amount || 0), 0);
    if (totalEl) totalEl.textContent = tot.toFixed(2).replace(".", ",");

    listEl.innerHTML = moves.map(m => {
      const a = Number(m.amount || 0);
      const isOut = a < 0;
      const who = (m.performed_by || "").trim();
      const notes = (m.notes || "").trim();
      const kind = (m.kind || "").trim();

      const desc = [who, notes].filter(Boolean).join(" • ") || "Movimento";
      const amt = (isOut ? "-" : "") + Math.abs(a).toFixed(2) + "€";
      const colorClass = isOut ? "text-danger" : "text-primary";

      const badges = [];
      if (kind === "spicci") badges.push(`<span class="badge badge-soft badge-coins">SPICCI</span>`);

      return `
        <div class="list-group-item table-row" data-cash-move-id="${m.id}">
          <div class="col-desc">
            <span class="flag"></span>
            <span class="desc">${escapeHtml(desc)}</span>
          </div>
          <div class="col-badges">${badges.join("")}</div>
          <div class="col-amt ${colorClass}">${amt}</div>
        </div>
      `;
    }).join("");

  } catch (e) {
    console.error("loadCashMoves error:", e);
    listEl.innerHTML = `<div class="list-group-item text-muted small">Errore di rete</div>`;
  }
}

async function loadEcommerce(dayStr) {
  if (!ecoTableBody) return;

  ecoTableBody.innerHTML = `
    <tr>
      <td colspan="3" class="text-center text-muted">Caricamento...</td>
    </tr>
  `;

  try {
    const r = await fetch(`/cassa/api/day/${dayStr}/ecommerce`, {
      credentials: "same-origin"
    });

    const data = await r.json();

    if (!data.ok) {
      ecoTableBody.innerHTML = `
        <tr>
          <td colspan="3" class="text-center text-danger">
            ${escapeHtml(data.error || "Errore caricamento movimenti e-commerce")}
          </td>
        </tr>
      `;
      return;
    }

    const rows = data.ecommerce || [];

    if (!rows.length) {
      ecoTableBody.innerHTML = `
        <tr>
          <td colspan="3" class="text-center text-muted">Nessun movimento</td>
        </tr>
      `;
      return;
    }

    ecoTableBody.innerHTML = rows.map(row => `
      <tr data-ecommerce-id="${row.id}">
        <td>${escapeHtml(row.description || "")}</td>
        <td class="text-end">${formatEuro2(row.amount || 0)}</td>
        <td class="text-end">
          <button type="button" class="btn btn-outline-danger btn-sm btn-eco-delete" data-id="${row.id}">
            Elimina
          </button>
        </td>
      </tr>
    `).join("");
  } catch (err) {
    console.error("loadEcommerce error:", err);
    ecoTableBody.innerHTML = `
      <tr>
        <td colspan="3" class="text-center text-danger">Errore di rete</td>
      </tr>
    `;
  }
}

async function openEcommerceModal() {
  if (!currentDay) {
    alert("Nessuna giornata selezionata.");
    return;
  }

  await loadEcommerce(currentDay);

  if (!ecommerceModal) {
    alert("Modale e-commerce non disponibile.");
    return;
  }

  ecommerceModal.show();
}

async function loadIncassi(dayStr) {
  const listEl = document.getElementById("incassiList");
  const totalEl = document.getElementById("totIncassi");
  if (!listEl) return;

  listEl.innerHTML = `<li class="muted">Caricamento...</li>`;

  try {
    const r = await fetch(`/cassa/api/day/${dayStr}/sales`, { credentials: "same-origin" });
    const data = await r.json();

    if (!data.ok) {
      listEl.innerHTML = `<li class="muted">Errore: ${data.error || "impossibile caricare incassi"}</li>`;
      if (totalEl) totalEl.textContent = "0,00";
      return;
    }

    const sales = data.sales || [];
    if (!sales.length) {
      listEl.innerHTML = `<li class="muted">Nessun incasso</li>`;
      if (totalEl) totalEl.textContent = "0,00";
      return;
    }

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

      const badges = [];
      if (x.method === "pos") badges.push(`<span class="badge badge-soft badge-pos">POS</span>`);
      if (x.method === "bank") badges.push(`<span class="badge badge-soft badge-bank">BANCA</span>`);
      if (x.method === "check") badges.push(`<span class="badge badge-soft badge-bank">ASSEGNO</span>`);
      if (x.off_cash) badges.push(`<span class="badge badge-soft badge-offcash">FUORI CASSA</span>`);

      return `
        <div class="list-group-item table-row" data-sale-id="${x.sale_id}">
          <div class="col-desc">
            <span class="flag">${escapeHtml(x.flag || "")}</span>
            <span class="desc">${escapeHtml(x.desc)}</span>
          </div>
          <div class="col-badges">${badges.join("")}</div>
          <div class="col-amt">${amt}</div>
        </div>
      `;
    }).join("");

    if (totalEl) {
      const tot = rows.reduce((s, x) => s + (x.direction === "out" ? -x.amount : x.amount), 0);
      totalEl.textContent = tot.toFixed(2).replace(".", ",");
    }

  } catch (e) {
    console.error(e);
    listEl.innerHTML = `<li class="muted">Errore di rete</li>`;
  }
}

async function loadSpese(dayStr) {
  const listEl = document.getElementById("speseList");
  const totalEl = document.getElementById("totSpese");
  if (!listEl) return;

  listEl.innerHTML = `<div class="list-group-item text-muted small">Caricamento...</div>`;

  try {
    const r = await fetch(`/cassa/api/day/${dayStr}/expenses`, { credentials: "same-origin" });
    const data = await r.json();

    if (!data.ok) {
      listEl.innerHTML = `<div class="list-group-item text-muted small">Errore: ${data.error || "impossibile caricare spese"}</div>`;
      return;
    }

    const expenses = data.expenses || [];
    if (!expenses.length) {
      listEl.innerHTML = `<div class="list-group-item text-muted small">Nessuna spesa</div>`;
      if (totalEl) totalEl.textContent = "0,00";
      return;
    }

    const rows = [];
    for (const e of expenses) {
      for (const p of (e.payments || [])) {
        rows.push({
          expense_id: e.id,
          created_at: p.created_at || e.created_at,
          flag: p.flag || "",
          desc: p.description || e.notes || "",
          amount: Number(p.amount || 0),
          direction: p.direction || "out",
          method: p.method || "",
          off_cash: !!p.off_cash,
        });
      }
    }

    if (totalEl) {
      const tot = rows.reduce((s, x) => s + (x.direction === "out" ? x.amount : -x.amount), 0);
      totalEl.textContent = tot.toFixed(2).replace(".", ",");
    }

    listEl.innerHTML = rows.map(x => {
      const amt = `${x.amount.toFixed(2)}€`;

      const badges = [];
      if (x.method === "pos") badges.push(`<span class="badge badge-soft badge-pos">POS</span>`);
      if (x.method === "bank") badges.push(`<span class="badge badge-soft badge-bank">BANCA</span>`);
      if (x.method === "check") badges.push(`<span class="badge badge-soft badge-bank">ASSEGNO</span>`);
      if (x.off_cash) badges.push(`<span class="badge badge-soft badge-offcash">FUORI CASSA</span>`);

      return `
        <div class="list-group-item table-row" data-expense-id="${x.expense_id}">
          <div class="col-desc">
            <span class="flag">${escapeHtml(x.flag || "")}</span>
            <span class="desc">${escapeHtml(x.desc)}</span>
          </div>
          <div class="col-badges">${badges.join("")}</div>
          <div class="col-amt">${amt}</div>
        </div>
      `;
    }).join("");

  } catch (e) {
    console.error(e);
    listEl.innerHTML = `<div class="list-group-item text-muted small">Errore di rete</div>`;
  }
}

async function loadPosMoves(dayStr) {
  const listEl = document.getElementById("posList");
  const totalEl = document.getElementById("totPos");
  if (!listEl) return;

  listEl.innerHTML = `<div class="list-group-item text-muted small">Caricamento...</div>`;
  if (totalEl) totalEl.textContent = "0,00";

  try {
    const r = await fetch(`/cassa/api/day/${dayStr}/pos_moves`, { credentials: "same-origin" });
    const data = await r.json();

    if (!data.ok) {
      listEl.innerHTML = `<div class="list-group-item text-muted small">Errore: ${data.error || "impossibile caricare POS"}</div>`;
      return;
    }

    const moves = data.pos_moves || [];
    if (!moves.length) {
      listEl.innerHTML = `<div class="list-group-item text-muted small">Nessun POS</div>`;
      return;
    }

    const tot = moves.reduce((s, m) => {
      const a = Number(m.amount || 0);
      return s + (m.direction === "in" ? a : -a);
    }, 0);
    if (totalEl) totalEl.textContent = tot.toFixed(2).replace(".", ",");

    listEl.innerHTML = moves.map(m => {
      const sign = m.direction === "out" ? "-" : "";
      const amt = `${sign}${Number(m.amount || 0).toFixed(2)}€`;
      const devName = m.pos_device_name || `POS ${m.pos_device_id}`;

      const circuitLabel = m.pos_circuit_name || "Circuito";
      const logoPath = m.pos_circuit_logo_path;

      const logoImg = logoPath
        ? `<img class="pos-logo" src="/static/${escapeHtml(logoPath)}" alt="${escapeHtml(circuitLabel)}"
                onerror="this.dataset.err='1';this.style.display='none';this.insertAdjacentHTML('afterend','<span class=&quot;pos-logo-fallback&quot;>${escapeHtml(circuitLabel)}</span>');">`
        : "";

      const iconFallback = (!logoPath && m.pos_circuit_icon)
        ? `<i class="${escapeHtml(m.pos_circuit_icon)}"></i><span class="pos-logo-fallback">${escapeHtml(circuitLabel)}</span>`
        : `<span class="pos-logo-fallback">${escapeHtml(circuitLabel)}</span>`;

      const badgeInner = logoPath ? logoImg : iconFallback;
      const badge = `<span class="badge badge-soft badge-icon">${badgeInner}</span>`;
      const desc = m.doc_ref ? escapeHtml(m.doc_ref) : devName;

      return `
        <div class="list-group-item table-row" data-pos-move-id="${m.id}">
          <div class="col-desc">
            <span class="flag"></span>
            <span class="desc">${desc}</span>
          </div>
          <div class="col-badges">${badge}</div>
          <div class="col-amt">${amt}</div>
        </div>
      `;
    }).join("");

  } catch (e) {
    console.error(e);
    listEl.innerHTML = `<div class="list-group-item text-muted small">Errore di rete</div>`;
  }
}

/* =========================
   CALENDARIO / AUTOREFRESH
========================= */

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
  }, 30000);
}

function stopAssegniAutoRefresh() {
  if (assegniInterval) {
    clearInterval(assegniInterval);
    assegniInterval = null;
  }
}

/* =========================
   DEPOSIT UI HELPERS
========================= */

function updateDepositCashUi() {
  if (!depositCashAmountInput || !depositTypeSelect || !depositChecksHint) return;

  const mode = depositTypeSelect.value || "versamento_incasso";
  const cashValue = parseEuroToNumber(depositCashAmountInput.value || "0");

  depositCashAmountInput.classList.remove("is-invalid");
  depositCashAmountInput.removeAttribute("title");

  const versabileResiduo = Number(currentPreviewTotals.versabile_residuo || 0);
  const maxIncassoStorico = Number(currentPreviewTotals.massimo_contanti_incasso || 0);
  const debitoContanti = Number(currentPreviewTotals.debito_contanti_incasso || 0);

  const visibleChecksTotal = Array.from(
    depositChecksTableBody?.querySelectorAll(".deposit-check-select") || []
  ).reduce((sum, el) => {
    return sum + Number(el.dataset.amount || 0);
  }, 0);

  if (mode === "versamento_intermedio") {
    let maxContantiIntermedio = versabileResiduo - visibleChecksTotal;
    if (!Number.isFinite(maxContantiIntermedio)) {
      maxContantiIntermedio = 0;
    }

    let hint = "Assegni ricevuti oggi";
    hint += ` • Residuo versabile: ${formatEuro2(versabileResiduo)}`;
    hint += ` • Assegni odierni in pancia: ${formatEuro2(visibleChecksTotal)}`;
    hint += ` • Contanti consigliati max: ${formatEuro2(maxContantiIntermedio)}`;

    depositChecksHint.textContent = hint;

    if (cashValue > maxContantiIntermedio) {
      depositCashAmountInput.classList.add("is-invalid");
      depositCashAmountInput.title =
        `Contanti oltre soglia consigliata. Max consigliato: ${formatEuro2(maxContantiIntermedio)}`;
    }

    return;
  }

  let hint = "Assegni ricevuti nei giorni precedenti o spostati";

  if (Number.isFinite(maxIncassoStorico)) {
    hint += ` • Contanti consigliati max: ${formatEuro2(maxIncassoStorico)}`;
  }

  if (debitoContanti > 0) {
    hint += ` • Eccedenza da recuperare: ${formatEuro2(debitoContanti)}`;
  }

  depositChecksHint.textContent = hint;

  if (cashValue > maxIncassoStorico) {
    depositCashAmountInput.classList.add("is-invalid");
    depositCashAmountInput.title =
      `Contanti oltre soglia consigliata. Max consigliato: ${formatEuro2(maxIncassoStorico)}`;
  }
}

function updateDepositTotal() {
  const cash = parseEuroToNumber(depositCashAmountInput?.value || "0");

  const checksTotal = Array.from(
    depositChecksTableBody?.querySelectorAll(".deposit-check-select:checked") || []
  ).reduce((sum, el) => {
    return sum + Number(el.dataset.amount || 0);
  }, 0);

  const total = cash + checksTotal;

  if (depositTotalAmountInput) {
    depositTotalAmountInput.value = formatEuro2(total);
  }
}

function resetDepositForm() {
  editingDepositId = null;

  if (depositTypeSelect) depositTypeSelect.value = "versamento_incasso";
  if (depositDateInput) depositDateInput.value = currentDay || "";
  if (depositCashAmountInput) depositCashAmountInput.value = "0,00";
  if (depositNoteInput) depositNoteInput.value = "";
  if (depositTotalAmountInput) depositTotalAmountInput.value = "0,00";
  if (depositBankSelect) depositBankSelect.value = "";

  if (depositChecksTableBody) {
    depositChecksTableBody.querySelectorAll(".deposit-check-select").forEach(el => {
      el.checked = false;
    });
  }

  if (depositAddBtn) depositAddBtn.textContent = "Salva versamento";

  updateDepositTotal();
  updateDepositCashUi();
}

/* =========================
   INIT
========================= */

document.addEventListener("DOMContentLoaded", function () {
  calendarInstance = flatpickr("#agendaCalendar", {
    inline: true,
    defaultDate: new Date(),
    onMonthChange: function (selectedDates, dateStr, instance) {
      decorateMonth(instance.currentYear, instance.currentMonth);
    },
    onChange: function (selectedDates) {
      if (selectedDates.length) {
        loadDay(toLocalYMD(selectedDates[0]));
      }
    }
  });

  const kpiEcommerceBox = document.getElementById("kpiEcommerceBox");
  if (kpiEcommerceBox) {
    kpiEcommerceBox.addEventListener("click", () => {
      openEcommerceModal();
    });
  }

  decorateMonth(calendarInstance.currentYear, calendarInstance.currentMonth);
  loadDay(toLocalYMD(new Date()));
  startAssegniAutoRefresh();

  if (ownerTakeModalEl) {
    ownerTakeModal = new bootstrap.Modal(ownerTakeModalEl);
  }

  normalizeCurrencyInput(ownerTakeCashAmountInput);

  document.getElementById("kpiCassettoBox")?.addEventListener("click", async () => {
    await openOwnerTakeModal();
  });

  ownerTakeCashAmountInput?.addEventListener("input", () => {
    updateOwnerTakeTotal();
  });

  ownerTakeChecksTableBody?.addEventListener("change", (e) => {
    if (e.target.closest(".owner-take-check-select")) {
      updateOwnerTakeTotal();
    }
  });

  ownerTakeAddBtn?.addEventListener("click", async () => {
    await saveOwnerTake();
  });

  ownerTakeTableBody?.addEventListener("click", async (e) => {
    const editBtn = e.target.closest(".btn-owner-take-edit");
    if (editBtn) {
      try {
        const row = JSON.parse(editBtn.dataset.row || "{}");
        startEditOwnerTake(row);
      } catch (err) {
        console.error("ownerTake edit parse error:", err);
        alert("Errore nel caricamento del prelievo da modificare.");
      }
      return;
    }

    const deleteBtn = e.target.closest(".btn-owner-take-delete");
    if (deleteBtn) {
      const ownerTakeId = deleteBtn.dataset.id;
      await deleteOwnerTake(ownerTakeId);
    }
  });

  const opModalEl = document.getElementById("opModal");
  const opModal = opModalEl ? new bootstrap.Modal(opModalEl) : null;

  const opAmountInput = document.getElementById("opAmount");
  const saveBtn = document.getElementById("opSaveBtn");
  const paymentWarning = document.getElementById("paymentWarning");

  const posDeviceSelect = document.getElementById("posDeviceSelect");
  const posCircuitSelect = document.getElementById("posCircuitSelect");
  const bankSelect = document.getElementById("bankSelect");

  const paymentPanels = {
    cash: document.getElementById("paymentSingleCashPanel"),
    pos: document.getElementById("paymentSinglePosPanel"),
    bank: document.getElementById("paymentSingleBankPanel"),
    check: document.getElementById("paymentSingleCheckPanel"),
    multi: document.getElementById("paymentMultiPanel"),
  };

  const multiPaymentsList = document.getElementById("multiPaymentsList");
  const multiPaymentRowTemplate = document.getElementById("multiPaymentRowTemplate");
  const btnAddPaymentRow = document.getElementById("btnAddPaymentRow");

  if (drawerModalEl) {
    drawerModal = new bootstrap.Modal(drawerModalEl);
  }

  if (ecommerceModalEl) {
    ecommerceModal = new bootstrap.Modal(ecommerceModalEl);
  }

  if (depositModalEl) {
    depositModal = new bootstrap.Modal(depositModalEl);
  }

  (function initModalStack3D() {
    const BASE_MODAL_Z = 1055;
    const BASE_BACKDROP_Z = 1050;
    const STEP = 20;

    function restack() {
      const modals = Array.from(document.querySelectorAll(".modal.show"));
      modals.forEach((m, i) => {
        m.style.zIndex = String(BASE_MODAL_Z + i * STEP);
      });

      const backdrops = Array.from(document.querySelectorAll(".modal-backdrop"));
      backdrops.forEach((bd, i) => {
        bd.style.zIndex = String(BASE_BACKDROP_Z + i * STEP);
      });

      modals.forEach((m, i) => {
        const isTop = (i === modals.length - 1);
        m.classList.toggle("modal-underlay", !isTop);
        m.classList.toggle("modal-top", isTop);
      });
    }

    document.addEventListener("shown.bs.modal", restack);
    document.addEventListener("hidden.bs.modal", () => requestAnimationFrame(restack));
    document.addEventListener("show.bs.modal", () => setTimeout(restack, 0));
  })();

  const OP_FLAGS = ["*", "**", "#", "!", "+", "x"];

  (function initFlagDropdown() {
    const input = document.getElementById("opFlag");
    const btn = document.getElementById("opFlagBtn");
    const menu = document.getElementById("opFlagMenu");
    if (!input || !btn || !menu) return;

    const dd = bootstrap.Dropdown.getOrCreateInstance(btn, { autoClose: true });

    function buildMenu(filterText = "") {
      const f = (filterText || "").trim().toLowerCase();
      const items = OP_FLAGS.filter(v => v.toLowerCase().includes(f));

      menu.innerHTML = "";

      if (!items.length) {
        const li = document.createElement("li");
        li.innerHTML = `<span class="dropdown-item-text text-muted">Nessun match</span>`;
        menu.appendChild(li);
        return;
      }

      for (const v of items) {
        const li = document.createElement("li");
        li.innerHTML = `<button type="button" class="dropdown-item" data-flag="${v}">${v}</button>`;
        menu.appendChild(li);
      }
    }

    btn.addEventListener("click", () => buildMenu(""));

    input.addEventListener("focus", () => {
      buildMenu(input.value);
      dd.show();
    });

    input.addEventListener("input", () => {
      buildMenu(input.value);
      dd.show();
    });

    menu.addEventListener("click", (e) => {
      const el = e.target.closest("[data-flag]");
      if (!el) return;
      input.value = el.getAttribute("data-flag") || "";
      dd.hide();
      input.dispatchEvent(new Event("change"));
    });

    if (!input.value) input.value = "*";
    buildMenu("");
  })();

  function getPaymentMode() {
    const checked = document.querySelector('input[name="paymentMode"]:checked');
    return checked?.value || "cash";
  }

  function setPaymentMode(mode) {
    const target = document.querySelector(`input[name="paymentMode"][value="${mode}"]`);
    if (target) target.checked = true;

    Object.entries(paymentPanels).forEach(([key, panel]) => {
      if (!panel) return;
      panel.classList.toggle("d-none", key !== mode);
    });

    if (mode === "pos") {
      loadPosDevices().catch(err => console.error("loadPosDevices setPaymentMode:", err));
    } else if (mode === "bank") {
      loadBanks().catch(err => console.error("loadBanks setPaymentMode:", err));
    } else if (mode === "multi") {
      if (!multiPaymentsList?.children.length) {
        addMultiPaymentRow();
      }
    }

    lastPaymentMode = mode;
  }

  function getOpAmount() {
    return parseEuroToNumber(opAmountInput?.value || "0");
  }

  function clearPaymentWarning() {
    paymentWarning?.classList.add("d-none");
    if (saveBtn) saveBtn.disabled = false;
  }

  function showPaymentWarning(message = "La somma dei pagamenti non coincide con il totale dell'operazione.") {
    if (paymentWarning) {
      paymentWarning.textContent = message;
      paymentWarning.classList.remove("d-none");
    }
    if (saveBtn) saveBtn.disabled = true;
  }

  function clearSingleCarrierFields() {
    const ids = [
      "cashAmount",
      "posAmount",
      "bankAmount",
      "checkAmount",
      "checkBankName",
      "checkBankABI",
      "checkBankCAB",
      "checkNumber",
      "checkDueDate"
    ];

    ids.forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      el.value = "";
    });

    if (posCircuitSelect) {
      posCircuitSelect.innerHTML = `<option value="">Seleziona...</option>`;
      posCircuitSelect.disabled = true;
    }
  }

  function resetMultiPayments() {
    if (multiPaymentsList) multiPaymentsList.innerHTML = "";
  }

  function refreshSingleAmountFields() {
    const total = formatEuro2(getOpAmount());
    const mode = getPaymentMode();

    const cashAmount = document.getElementById("cashAmount");
    const posAmount = document.getElementById("posAmount");
    const bankAmount = document.getElementById("bankAmount");
    const checkAmount = document.getElementById("checkAmount");

    if (mode === "cash" && cashAmount) cashAmount.value = total;
    if (mode === "pos" && posAmount) posAmount.value = total;
    if (mode === "bank" && bankAmount) bankAmount.value = total;
    if (mode === "check" && checkAmount) checkAmount.value = total;
  }

  function getMultiPaymentsTotal() {
    const rows = Array.from(multiPaymentsList?.querySelectorAll(".multi-payment-row") || []);
    return rows.reduce((sum, row) => {
      const amount = parseEuroToNumber(row.querySelector(".multi-amount")?.value || "0");
      return sum + amount;
    }, 0);
  }

  function syncOpAmountFromMultiRows() {
    if (getPaymentMode() !== "multi") return;
    const total = getMultiPaymentsTotal();
    if (opAmountInput) {
      opAmountInput.value = formatEuro2(total);
    }
  }

  function updatePaymentState() {
    const mode = getPaymentMode();

    if (mode === "multi") {
      syncOpAmountFromMultiRows();

      const opAmount = getOpAmount();
      const totalPayments = getMultiPaymentsTotal();

      if (opAmount <= 0 && totalPayments <= 0) {
        showPaymentWarning("Inserisci almeno un pagamento con importo maggiore di zero.");
        return;
      }

      if (Math.abs(totalPayments - opAmount) > 0.009) {
        showPaymentWarning();
        return;
      }

      clearPaymentWarning();
      return;
    }

    const opAmount = getOpAmount();

    if (opAmount <= 0) {
      showPaymentWarning("Inserisci un importo operazione maggiore di zero.");
      return;
    }

    let totalPayments = 0;

    if (mode === "cash") {
      totalPayments = parseEuroToNumber(document.getElementById("cashAmount")?.value || "0");
    } else if (mode === "pos") {
      totalPayments = parseEuroToNumber(document.getElementById("posAmount")?.value || "0");
    } else if (mode === "bank") {
      totalPayments = parseEuroToNumber(document.getElementById("bankAmount")?.value || "0");
    } else if (mode === "check") {
      totalPayments = parseEuroToNumber(document.getElementById("checkAmount")?.value || "0");
    }

    if (Math.abs(totalPayments - opAmount) > 0.009) {
      showPaymentWarning();
      return;
    }

    clearPaymentWarning();
  }

  function normalizeCurrencyInput(input) {
    if (!input) return;
    input.addEventListener("blur", () => {
      input.value = formatEuro2(parseEuroToNumber(input.value));
      updatePaymentState();
    });
    input.addEventListener("input", () => {
      updatePaymentState();
    });
  }

  async function loadPosCircuits(deviceId, circuitSelect = posCircuitSelect) {
    if (!circuitSelect) return;

    circuitSelect.innerHTML = `<option value="">Seleziona...</option>`;
    circuitSelect.disabled = true;

    if (!deviceId) return;

    try {
      const r = await fetch(`/cassa/api/pos/devices/${deviceId}/circuits`, {
        credentials: "same-origin",
        headers: { "Accept": "application/json" }
      });

      const data = await r.json();
      if (!data.ok) return;

      (data.circuits || []).forEach(c => {
        const opt = document.createElement("option");
        opt.value = String(c.id);
        opt.textContent = c.name;
        circuitSelect.appendChild(opt);
      });

      circuitSelect.disabled = false;
    } catch (err) {
      console.error("loadPosCircuits error:", err);
    }
  }

  async function fetchPosDevicesRaw() {
    const r = await fetch("/cassa/api/pos/devices", {
      credentials: "same-origin",
      headers: { "Accept": "application/json" }
    });
    const data = await r.json();
    if (!data.ok) return [];
    return data.devices || [];
  }

  async function loadPosDevices(selectEl = posDeviceSelect, autoLoadCircuits = true, linkedCircuitSelect = posCircuitSelect) {
    if (!selectEl) return;

    selectEl.innerHTML = `<option value="">Seleziona...</option>`;
    if (linkedCircuitSelect) {
      linkedCircuitSelect.innerHTML = `<option value="">Seleziona...</option>`;
      linkedCircuitSelect.disabled = true;
    }

    try {
      const devices = await fetchPosDevicesRaw();
      let defaultId = "";

      devices.forEach(d => {
        const opt = document.createElement("option");
        opt.value = String(d.id);
        opt.textContent = d.name;
        selectEl.appendChild(opt);

        if (d.is_default) defaultId = String(d.id);
      });

      if (defaultId) {
        selectEl.value = defaultId;
        if (autoLoadCircuits && linkedCircuitSelect) {
          await loadPosCircuits(defaultId, linkedCircuitSelect);
        }
      }
    } catch (err) {
      console.error("loadPosDevices error:", err);
    }
  }

  async function fetchBanksRaw() {
    const r = await fetch("/cassa/api/banks", {
      credentials: "same-origin",
      headers: { "Accept": "application/json" }
    });
    const data = await r.json();
    if (!data.ok) return [];
    return data.banks || [];
  }

  async function loadBanks() {
    try {
      const res = await fetch("/cassa/api/banks", { credentials: "same-origin" });
      const data = await res.json();

      if (!data.ok) return;

      const depositBankSelect = document.getElementById("depositBank");
      depositBankSelect.innerHTML = '<option value="">Seleziona...</option>';

      let defaultBankId = null;

      data.banks.forEach(b => {
        const opt = document.createElement("option");
        opt.value = b.id;
        opt.textContent = b.name;

        if (b.is_default) {
          defaultBankId = b.id;
        }

        depositBankSelect.appendChild(opt);
      });

      // 👉 applico il default DOPO aver creato tutte le option
      if (defaultBankId) {
        depositBankSelect.value = String(defaultBankId);
      }

    } catch (err) {
      console.error("Errore caricamento banche:", err);
    }
  }

  async function loadDepositBanks(selectedBankId = null) {
    if (!depositBankSelect) return;

    depositBankSelect.innerHTML = `<option value="">Seleziona...</option>`;

    try {
      const banks = await fetchBanksRaw();
      let defaultId = null;

      banks.forEach(b => {
        const opt = document.createElement("option");
        opt.value = String(b.id);
        opt.textContent = b.name;
        depositBankSelect.appendChild(opt);

        if (b.is_default) {
          defaultId = String(b.id);
        }
      });

      const finalValue = selectedBankId != null && String(selectedBankId).trim() !== ""
        ? String(selectedBankId)
        : defaultId;

      if (finalValue) {
        depositBankSelect.value = finalValue;
      }

      console.log("depositBank options:", banks);
      console.log("depositBank selected:", depositBankSelect.value);

    } catch (err) {
      console.error("loadDepositBanks error:", err);
    }
  }

  function updateMultiRowFields(row) {
    const method = row.querySelector(".multi-method")?.value || "cash";

    row.querySelectorAll(".multi-pos-fields").forEach(el => {
      el.classList.toggle("d-none", method !== "pos");
    });

    row.querySelectorAll(".multi-bank-fields").forEach(el => {
      el.classList.toggle("d-none", method !== "bank");
    });

    row.querySelectorAll(".multi-check-fields").forEach(el => {
      el.classList.toggle("d-none", method !== "check");
    });
  }

  function multiRowsHaveData() {
    const rows = Array.from(multiPaymentsList?.querySelectorAll(".multi-payment-row") || []);
    if (!rows.length) return false;

    return rows.some(row => {
      const amount = parseEuroToNumber(row.querySelector(".multi-amount")?.value || "0");
      const method = row.querySelector(".multi-method")?.value || "cash";

      if (amount > 0) return true;

      if (method === "pos") {
        return !!(row.querySelector(".multi-pos-device")?.value || row.querySelector(".multi-pos-circuit")?.value);
      }

      if (method === "bank") {
        return !!row.querySelector(".multi-bank-select")?.value;
      }

      if (method === "check") {
        return [
          row.querySelector(".multi-check-bank-name")?.value,
          row.querySelector(".multi-check-bank-abi")?.value,
          row.querySelector(".multi-check-bank-cab")?.value,
          row.querySelector(".multi-check-number")?.value,
          row.querySelector(".multi-check-due-date")?.value,
        ].some(v => String(v || "").trim() !== "");
      }

      return false;
    });
  }

  async function addMultiPaymentRow(initialMethod = "cash") {
    if (!multiPaymentsList || !multiPaymentRowTemplate) return;

    const fragment = multiPaymentRowTemplate.content.cloneNode(true);
    const row = fragment.querySelector(".multi-payment-row");

    const methodSelect = row.querySelector(".multi-method");
    const amountInput = row.querySelector(".multi-amount");
    const removeBtn = row.querySelector(".btn-remove-payment-row");
    const rowPosDevice = row.querySelector(".multi-pos-device");
    const rowPosCircuit = row.querySelector(".multi-pos-circuit");
    const rowBankSelect = row.querySelector(".multi-bank-select");

    if (methodSelect) methodSelect.value = initialMethod;

    normalizeCurrencyInput(amountInput);

    methodSelect?.addEventListener("change", async () => {
      updateMultiRowFields(row);

      const method = methodSelect.value;

      if (method === "pos") {
        await loadPosDevices(rowPosDevice, true, rowPosCircuit);
      } else if (method === "bank") {
        await loadBanks(rowBankSelect);
      } else {
        if (rowPosDevice) rowPosDevice.innerHTML = `<option value="">Seleziona...</option>`;
        if (rowPosCircuit) {
          rowPosCircuit.innerHTML = `<option value="">Seleziona...</option>`;
          rowPosCircuit.disabled = true;
        }
        if (rowBankSelect) rowBankSelect.innerHTML = `<option value="">Seleziona...</option>`;
      }

      updatePaymentState();
    });

    rowPosDevice?.addEventListener("change", async (e) => {
      await loadPosCircuits(e.target.value, rowPosCircuit);
      updatePaymentState();
    });

    removeBtn?.addEventListener("click", () => {
      row.remove();
      updatePaymentState();
    });

    multiPaymentsList.appendChild(row);
    updateMultiRowFields(row);

    if (initialMethod === "pos") {
      await loadPosDevices(rowPosDevice, true, rowPosCircuit);
    } else if (initialMethod === "bank") {
      await loadBanks(rowBankSelect);
    }

    updatePaymentState();
  }

  function openOpModal(type) {
    if (!opModal) return;

    setText("opModalTitle", type === "sale" ? "Nuovo incasso" : "Nuova spesa");

    const opType = document.getElementById("opType");
    const opDesc = document.getElementById("opDesc");
    const opFlag = document.getElementById("opFlag");
    const opCustomerId = document.getElementById("opCustomerId");
    const opCustomer = document.getElementById("opCustomer");
    const opOffCash = document.getElementById("opOffCash");
    const opOffCashWho = document.getElementById("opOffCashWho");
    const opOffCashBox = document.getElementById("opOffCashBox");

    if (opType) opType.value = type;
    if (opAmountInput) opAmountInput.value = "0,00";
    if (opDesc) opDesc.value = "";
    if (opFlag) opFlag.value = "*";
    if (opCustomerId) opCustomerId.value = "";
    if (opCustomer) opCustomer.value = "";
    if (opOffCash) opOffCash.checked = false;
    if (opOffCashWho) opOffCashWho.value = "";
    if (opOffCashBox) opOffCashBox.classList.add("d-none");

    clearSingleCarrierFields();
    resetMultiPayments();
    setPaymentMode("cash");
    refreshSingleAmountFields();
    clearPaymentWarning();

    opModal.show();
  }

  async function ensureSelectedCustomer() {
    const opCustomerInput = document.getElementById("opCustomer");
    const opCustomerIdInput = document.getElementById("opCustomerId");

    if (!opCustomerInput || !opCustomerIdInput) {
      return { ok: true, customer_id: null };
    }

    const currentId = String(opCustomerIdInput.value || "").trim();
    if (currentId) {
      return { ok: true, customer_id: Number(currentId) };
    }

    const rawText = String(opCustomerInput.value || "").trim();
    if (!rawText) {
      return { ok: true, customer_id: null };
    }

    const items = await fetchCustomerSuggest(rawText);
    const exact = items.find(x => String(x.display || "").trim() === rawText);

    if (!exact) {
      return {
        ok: false,
        error: "Cliente non selezionato correttamente. Sceglilo dalla lista o dalla ricerca avanzata."
      };
    }

    opCustomerIdInput.value = String(exact.id);
    opCustomerInput.value = exact.display || rawText;

    return { ok: true, customer_id: Number(exact.id) };
  }

  async function loadAvailableDepositChecks(dayStr) {
    if (!depositChecksTableBody || !depositTypeSelect) return;

    depositChecksTableBody.innerHTML = `
      <tr>
        <td colspan="7" class="text-center text-muted">Caricamento...</td>
      </tr>
    `;

    try {
      const r = await fetch(`/cassa/api/day/${dayStr}/deposit-available-checks`, {
        credentials: "same-origin",
        headers: { "Accept": "application/json" }
      });

      const data = await r.json();

      if (!data.ok) {
        depositChecksTableBody.innerHTML = `
          <tr>
            <td colspan="7" class="text-center text-danger">
              ${escapeHtml(data.error || "Errore caricamento assegni")}
            </td>
          </tr>
        `;
        return;
      }

      const mode = depositTypeSelect.value || "versamento_incasso";
      const checks = mode === "versamento_intermedio"
        ? (data.intermedio || [])
        : (data.incasso || []);

      if (!checks.length) {
        depositChecksTableBody.innerHTML = `
          <tr>
            <td colspan="7" class="text-center text-muted">Nessun assegno disponibile</td>
          </tr>
        `;
        updateDepositCashUi();
        return;
      }

      depositChecksTableBody.innerHTML = checks.map(c => `
        <tr data-check-id="${c.id}">
          <td>
            <input type="checkbox" class="form-check-input deposit-check-select" value="${c.id}" data-amount="${Number(c.amount || 0)}">
          </td>
          <td>${escapeHtml(c.bank_name || "")}</td>
          <td>${escapeHtml(c.check_number || "")}</td>
          <td>${escapeHtml(c.customer_display_name || "")}</td>
          <td>${escapeHtml(c.received_date || "")}</td>
          <td>${escapeHtml(c.due_date || "")}</td>
          <td class="text-end">${formatEuro2(c.amount || 0)}</td>
        </tr>
      `).join("");

      updateDepositCashUi();
    } catch (err) {
      console.error("loadAvailableDepositChecks error:", err);
      depositChecksTableBody.innerHTML = `
        <tr>
          <td colspan="7" class="text-center text-danger">Errore di rete</td>
        </tr>
      `;
      updateDepositCashUi();
    }
  }

  async function loadDeposits(dayStr) {
    if (!depositTableBody) return;

    depositTableBody.innerHTML = `
      <tr>
        <td colspan="8" class="text-center text-muted">Caricamento...</td>
      </tr>
    `;

    try {
      const r = await fetch(`/cassa/api/day/${dayStr}/deposits`, {
        credentials: "same-origin",
        headers: { "Accept": "application/json" }
      });

      const data = await r.json();

      if (!data.ok) {
        depositTableBody.innerHTML = `
          <tr>
            <td colspan="8" class="text-center text-danger">
              ${escapeHtml(data.error || "Errore caricamento versamenti")}
            </td>
          </tr>
        `;
        return;
      }

      const rows = data.deposits || [];

      if (!rows.length) {
        depositTableBody.innerHTML = `
          <tr>
            <td colspan="8" class="text-center text-muted">Nessun versamento</td>
          </tr>
        `;
        return;
      }

      depositTableBody.innerHTML = rows.map(row => `
        <tr data-deposit-id="${row.id}">
          <td>${escapeHtml(row.deposit_date || "")}</td>
          <td>${escapeHtml(row.deposit_type || "")}</td>
          <td>${escapeHtml(row.bank_name || "-")}</td>
          <td class="text-end">${formatEuro2(row.cash_amount || 0)}</td>
          <td class="text-end">${formatEuro2(row.checks_total || 0)}</td>
          <td class="text-end fw-semibold">${formatEuro2(row.total_amount || 0)}</td>
          <td>${escapeHtml(row.note || "")}</td>
          <td class="text-end">
            <button
              type="button"
              class="btn btn-outline-primary me-1 btn-sm btn-edit-deposit"
              data-id="${row.id}">
              Modifica
            </button>
            <button
              type="button"
              class="btn btn-outline-danger btn-sm btn-deposit-delete"
              data-id="${row.id}">
              Elimina
            </button>
          </td>
        </tr>
      `).join("");
    } catch (err) {
      console.error("loadDeposits error:", err);
      depositTableBody.innerHTML = `
        <tr>
          <td colspan="8" class="text-center text-danger">Errore di rete</td>
        </tr>
      `;
    }
  }

  async function openDepositModal() {
    if (!currentDay) {
      alert("Nessuna giornata selezionata.");
      return;
    }

    resetDepositForm();

    await loadDepositBanks();
    await loadAvailableDepositChecks(currentDay);
    await loadDeposits(currentDay);

    updateDepositTotal();
    updateDepositCashUi();

    if (!depositModal) {
      alert("Modale versamenti non disponibile.");
      return;
    }

    depositModal.show();
  }

  async function saveDeposit() {
    if (!currentDay) {
      alert("Nessuna giornata selezionata.");
      return;
    }

    const depositType = depositTypeSelect?.value || "";
    const cashAmount = parseEuroToNumber(depositCashAmountInput?.value || "0");
    const note = (depositNoteInput?.value || "").trim() || null;
    const bankId = Number(depositBankSelect?.value || 0);

    const checkIds = Array.from(
      depositChecksTableBody?.querySelectorAll(".deposit-check-select:checked") || []
    ).map(el => Number(el.value)).filter(Number.isFinite);

    if (!depositType) {
      alert("Seleziona un tipo di versamento.");
      return;
    }

    if (!bankId) {
      alert("Seleziona la banca del versamento.");
      return;
    }

    if (cashAmount <= 0 && checkIds.length === 0) {
      alert("Inserisci almeno contanti o seleziona almeno un assegno.");
      return;
    }

    const isEdit = !!editingDepositId;
    const url = isEdit
      ? `/cassa/api/deposits/${editingDepositId}`
      : `/cassa/api/day/${currentDay}/deposits`;

    const method = isEdit ? "PUT" : "POST";

    try {
      if (depositAddBtn) depositAddBtn.disabled = true;

      const r = await fetch(url, {
        method,
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json"
        },
        credentials: "same-origin",
        body: JSON.stringify({
          deposit_type: depositType,
          cash_amount: cashAmount,
          note,
          check_ids: checkIds,
          bank_id: bankId
        })
      });

      const data = await r.json();

      if (!r.ok || !data.ok) {
        alert(data.error || "Errore salvataggio versamento");
        return;
      }

      await loadDepositBanks();
      resetDepositForm();
      await loadAvailableDepositChecks(currentDay);
      await loadDeposits(currentDay);
      await loadPreview(currentDay);
      updateDepositTotal();
      updateDepositCashUi();

    } catch (err) {
      console.error("saveDeposit error:", err);
      alert("Errore di rete");
    } finally {
      if (depositAddBtn) depositAddBtn.disabled = false;
    }
  }

  let receiptModalInstance = null;
  let editingReceiptClosureId = null;

  function getReceiptModal() {
    const el = document.getElementById("receiptModal");
    if (!el) return null;
    if (!receiptModalInstance) {
      receiptModalInstance = new bootstrap.Modal(el);
    }
    return receiptModalInstance;
  }

  function resetReceiptForm() {
    const amountInput = document.getElementById("rc_amount");
    const typeSelect = document.getElementById("rc_type");
    const descriptionInput = document.getElementById("rc_description");
    const addBtn = document.getElementById("btnAddReceipt");

    editingReceiptClosureId = null;

    if (amountInput) amountInput.value = "0,00";
    if (typeSelect) typeSelect.value = "fine_giornata";
    if (descriptionInput) descriptionInput.value = "";
    if (addBtn) addBtn.textContent = "Aggiungi";
  }

  function startEditReceiptClosure(row) {
    const amountInput = document.getElementById("rc_amount");
    const typeSelect = document.getElementById("rc_type");
    const descriptionInput = document.getElementById("rc_description");
    const addBtn = document.getElementById("btnAddReceipt");

    editingReceiptClosureId = row.id;

    if (amountInput) amountInput.value = formatEuro2(row.amount || 0);
    if (typeSelect) typeSelect.value = row.closure_type || "fine_giornata";
    if (descriptionInput) descriptionInput.value = row.description || "";
    if (addBtn) addBtn.textContent = "Salva";

    amountInput?.focus();
    amountInput?.select?.();
  }

  async function loadReceiptClosures() {
    const tbody = document.getElementById("rc_table");
    if (!tbody || !currentDay) return;

    tbody.innerHTML = `<tr><td colspan="4" class="text-muted">Caricamento...</td></tr>`;

    try {
      const res = await fetch(`/cassa/api/day/${currentDay}/receipt-closures`);
      const rows = await res.json();

      if (!Array.isArray(rows) || rows.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4" class="text-muted">Nessun corrispettivo inserito</td></tr>`;
        return;
      }

      tbody.innerHTML = rows.map(row => `
        <tr data-id="${row.id}">
          <td>${row.created_at ? new Date(row.created_at).toLocaleString() : ""}</td>
          <td>${row.closure_type === "fine_giornata" ? "Fine giornata" : "Intermedia"}</td>
          <td>${Number(row.amount).toFixed(2)} €</td>
          <td class="text-end">
            <button
              type="button"
              class="btn btn-sm btn-outline-secondary btn-receipt-edit"
              data-row='${escapeHtml(JSON.stringify(row))}'>
              Modifica
            </button>
            <button
              type="button"
              class="btn btn-sm btn-outline-danger btn-receipt-delete"
              data-id="${row.id}">
              Elimina
            </button>
          </td>
        </tr>
      `).join("");
    } catch (err) {
      console.error("Errore loadReceiptClosures:", err);
      tbody.innerHTML = `<tr><td colspan="4" class="text-danger">Errore nel caricamento</td></tr>`;
    }
  }

  async function openReceiptModal() {
    resetReceiptForm();
    await loadReceiptClosures();
    const modal = getReceiptModal();
    if (modal) modal.show();
  }

  async function getBaseOperationData() {
    const opType = document.getElementById("opType")?.value || "sale";
    const flag = (document.getElementById("opFlag")?.value || "*").trim();
    const description = (document.getElementById("opDesc")?.value || "").trim();
    const customerLabel = (document.getElementById("opCustomer")?.value || "").trim();
    const offCash = !!document.getElementById("opOffCash")?.checked;
    const offCashWho = (document.getElementById("opOffCashWho")?.value || "").trim();

    const ensuredCustomer = await ensureSelectedCustomer();
    if (!ensuredCustomer.ok) {
      return ensuredCustomer;
    }

    return {
      ok: true,
      opType,
      flag,
      description,
      customer_id: ensuredCustomer.customer_id,
      customer_label: customerLabel || null,
      off_cash: offCash,
      off_cash_who: offCashWho || null,
      amount: getOpAmount(),
    };
  }

  function buildSinglePaymentPayload(base) {
    const mode = getPaymentMode();
    const amount = base.amount;

    if (amount <= 0) {
      return { ok: false, error: "Importo operazione non valido." };
    }

    if (!base.description) {
      return { ok: false, error: "Inserisci una descrizione." };
    }

    if (mode === "cash") {
      return {
        ok: true,
        payload: {
          description: base.description,
          flag: base.flag,
          customer_id: base.customer_id,
          customer_label: base.customer_label,
          off_cash: base.off_cash,
          off_cash_who: base.off_cash_who,
          payments: [
            {
              method: "cash",
              amount: amount
            }
          ]
        }
      };
    }

    if (mode === "pos") {
      const pos_device_id = Number(posDeviceSelect?.value || 0);
      const pos_circuit_id = Number(posCircuitSelect?.value || 0);

      if (!pos_device_id || !pos_circuit_id) {
        return { ok: false, error: "Seleziona dispositivo e circuito POS." };
      }

      return {
        ok: true,
        payload: {
          description: base.description,
          flag: base.flag,
          customer_id: base.customer_id,
          customer_label: base.customer_label,
          off_cash: base.off_cash,
          off_cash_who: base.off_cash_who,
          payments: [
            {
              method: "pos",
              amount: amount,
              pos_device_id,
              pos_circuit_id
            }
          ]
        }
      };
    }

    if (mode === "bank") {
      const bank_id = Number(bankSelect?.value || 0);
      if (!bank_id) {
        return { ok: false, error: "Seleziona una banca." };
      }

      return {
        ok: true,
        payload: {
          description: base.description,
          flag: base.flag,
          customer_id: base.customer_id,
          customer_label: base.customer_label,
          off_cash: base.off_cash,
          off_cash_who: base.off_cash_who,
          payments: [
            {
              method: "bank",
              amount: amount,
              bank_id
            }
          ]
        }
      };
    }

    if (mode === "check") {
      const bank_name = (document.getElementById("checkBankName")?.value || "").trim();
      const abi = (document.getElementById("checkBankABI")?.value || "").trim();
      const cab = (document.getElementById("checkBankCAB")?.value || "").trim();
      const check_number = (document.getElementById("checkNumber")?.value || "").trim();
      const due_date = (document.getElementById("checkDueDate")?.value || "").trim();

      if (!base.customer_id) {
        return { ok: false, error: "Per un assegno devi selezionare un cliente." };
      }

      if (!bank_name || !abi || !cab || !check_number || !due_date) {
        return { ok: false, error: "Completa tutti i dati dell’assegno." };
      }

      return {
        ok: true,
        payload: {
          description: base.description,
          flag: base.flag,
          customer_id: base.customer_id,
          customer_label: base.customer_label,
          off_cash: base.off_cash,
          off_cash_who: base.off_cash_who,
          payments: [
            {
              method: "check",
              amount: amount,
              bank_name,
              abi,
              cab,
              check_number,
              due_date
            }
          ]
        }
      };
    }

    return { ok: false, error: "Modalità pagamento non valida." };
  }

  function buildMultiPaymentPayload(base) {
    const rows = Array.from(multiPaymentsList?.querySelectorAll(".multi-payment-row") || []);
    let effectiveAmount = base.amount;

    if (effectiveAmount <= 0) {
      effectiveAmount = getMultiPaymentsTotal();
    }

    if (!rows.length) {
      return { ok: false, error: "Aggiungi almeno una riga pagamento." };
    }

    if (effectiveAmount <= 0) {
      return { ok: false, error: "Importo operazione non valido." };
    }

    if (!base.description) {
      return { ok: false, error: "Inserisci una descrizione." };
    }

    const payments = [];

    for (const row of rows) {
      const method = row.querySelector(".multi-method")?.value || "cash";
      const amount = parseEuroToNumber(row.querySelector(".multi-amount")?.value || "0");

      if (amount <= 0) {
        return { ok: false, error: "Ogni riga pagamento deve avere un importo maggiore di zero." };
      }

      if (method === "cash") {
        payments.push({
          method: "cash",
          amount
        });
        continue;
      }

      if (method === "pos") {
        const pos_device_id = Number(row.querySelector(".multi-pos-device")?.value || 0);
        const pos_circuit_id = Number(row.querySelector(".multi-pos-circuit")?.value || 0);

        if (!pos_device_id || !pos_circuit_id) {
          return { ok: false, error: "Ogni riga POS deve avere dispositivo e circuito." };
        }

        payments.push({
          method: "pos",
          amount,
          pos_device_id,
          pos_circuit_id
        });
        continue;
      }

      if (method === "bank") {
        const bank_id = Number(row.querySelector(".multi-bank-select")?.value || 0);
        if (!bank_id) {
          return { ok: false, error: "Ogni riga banca deve avere una banca selezionata." };
        }

        payments.push({
          method: "bank",
          amount,
          bank_id
        });
        continue;
      }

      if (method === "check") {
        if (!base.customer_id) {
          return { ok: false, error: "Per gli assegni devi selezionare un cliente." };
        }

        const bank_name = (row.querySelector(".multi-check-bank-name")?.value || "").trim();
        const abi = (row.querySelector(".multi-check-bank-abi")?.value || "").trim();
        const cab = (row.querySelector(".multi-check-bank-cab")?.value || "").trim();
        const check_number = (row.querySelector(".multi-check-number")?.value || "").trim();
        const due_date = (row.querySelector(".multi-check-due-date")?.value || "").trim();

        if (!bank_name || !abi || !cab || !check_number || !due_date) {
          return { ok: false, error: "Completa tutti i dati per ogni assegno." };
        }

        payments.push({
          method: "check",
          amount,
          bank_name,
          abi,
          cab,
          check_number,
          due_date
        });
        continue;
      }

      return { ok: false, error: "Tipo pagamento non valido in una delle righe." };
    }

    const totalPayments = payments.reduce((sum, p) => sum + Number(p.amount || 0), 0);
    if (Math.abs(totalPayments - effectiveAmount) > 0.009) {
      return { ok: false, error: "La somma dei pagamenti non coincide con il totale dell’operazione." };
    }

    return {
      ok: true,
      payload: {
        description: base.description,
        flag: base.flag,
        customer_id: base.customer_id,
        customer_label: base.customer_label,
        off_cash: base.off_cash,
        off_cash_who: base.off_cash_who,
        payments
      }
    };
  }

  async function buildOperationPayload() {
    const base = await getBaseOperationData();
    if (!base.ok) {
      return base;
    }

    const mode = getPaymentMode();

    if (mode === "multi") {
      return buildMultiPaymentPayload(base);
    }
    return buildSinglePaymentPayload(base);
  }

  async function saveReceiptClosure() {
    if (!currentDay) {
      alert("Nessuna giornata selezionata.");
      return;
    }

    const amountInput = document.getElementById("rc_amount");
    const typeSelect = document.getElementById("rc_type");
    const descriptionInput = document.getElementById("rc_description");
    const addBtn = document.getElementById("btnAddReceipt");

    const amount = parseEuroToNumber(amountInput?.value || "0");
    const closure_type = (typeSelect?.value || "fine_giornata").trim();
    const description = (descriptionInput?.value || "").trim();

    if (amount <= 0) {
      alert("Inserisci un importo valido.");
      return;
    }

    const isEdit = !!editingReceiptClosureId;
    const url = isEdit
      ? `/cassa/api/receipt-closures/${editingReceiptClosureId}`
      : `/cassa/api/day/${currentDay}/receipt-closures`;

    const method = isEdit ? "PUT" : "POST";

    try {
      if (addBtn) addBtn.disabled = true;

      const r = await fetch(url, {
        method,
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json"
        },
        credentials: "same-origin",
        body: JSON.stringify({
          amount,
          closure_type,
          description
        })
      });

      const data = await r.json();

      const ok = isEdit ? data.ok : data.success;
      if (!r.ok || !ok) {
        alert(data.error || "Errore salvataggio corrispettivo");
        return;
      }

      resetReceiptForm();
      await loadReceiptClosures();
      await loadPreview(currentDay);

    } catch (err) {
      console.error("saveReceiptClosure error:", err);
      alert("Errore di rete durante il salvataggio del corrispettivo.");
    } finally {
      if (addBtn) addBtn.disabled = false;
    }
  }

  async function deleteReceiptClosure(receiptClosureId) {
    if (!receiptClosureId) return;

    const confirmed = window.confirm("Vuoi eliminare questo corrispettivo?");
    if (!confirmed) return;

    try {
      const r = await fetch(`/cassa/api/receipt-closures/${receiptClosureId}`, {
        method: "DELETE",
        headers: { "Accept": "application/json" },
        credentials: "same-origin"
      });

      const data = await r.json();

      if (!r.ok || !data.ok) {
        alert(data.error || "Errore eliminazione corrispettivo");
        return;
      }

      await loadReceiptClosures();
      await loadPreview(currentDay);

    } catch (err) {
      console.error("deleteReceiptClosure error:", err);
      alert("Errore di rete durante l'eliminazione del corrispettivo.");
    }
  }

  async function saveOperation() {
    if (!currentDay) {
      alert("Nessuna giornata selezionata.");
      return;
    }

    const opType = document.getElementById("opType")?.value || "sale";
    const endpoint = opType === "expense"
      ? `/cassa/api/day/${currentDay}/expenses`
      : `/cassa/api/day/${currentDay}/sales`;

    const built = await buildOperationPayload();
    if (!built.ok) {
      alert(built.error || "Dati operazione non validi.");
      return;
    }

    try {
      if (saveBtn) saveBtn.disabled = true;

      const r = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify(built.payload),
      });

      const data = await r.json();

      if (!r.ok || !data.ok) {
        alert(data.error || "Errore durante il salvataggio.");
        return;
      }

      opModal.hide();
      await refreshAgendaData();
    } catch (err) {
      console.error("saveOperation error:", err);
      alert("Errore di rete durante il salvataggio.");
    } finally {
      updatePaymentState();
    }
  }

  (function initCustomerNewModal() {
    const btnOpen = document.getElementById("btnCustomerNew");
    const modalEl = document.getElementById("customerNewModal");
    const saveBtnNewCustomer = document.getElementById("customerNewSaveBtn");

    const opCustomerInput = document.getElementById("opCustomer");
    const opCustomerIdInput = document.getElementById("opCustomerId");

    if (!btnOpen || !modalEl || !saveBtnNewCustomer || typeof bootstrap === "undefined") return;

    const bsModal = new bootstrap.Modal(modalEl);

    const fldDisplay = document.getElementById("newCustomerDisplayName");
    const fldRs = document.getElementById("newCustomerRagioneSociale");
    const fldPiva = document.getElementById("newCustomerPartitaIva");
    const fldCodice = document.getElementById("newCustomerCodiceCliente");
    const fldAliases = document.getElementById("newCustomerAliases");

    function resetForm() {
      if (fldDisplay) fldDisplay.value = "";
      if (fldRs) fldRs.value = "";
      if (fldPiva) fldPiva.value = "";
      if (fldCodice) fldCodice.value = "";
      if (fldAliases) fldAliases.value = "";
    }

    btnOpen.addEventListener("click", () => {
      resetForm();
      bsModal.show();
    });

    saveBtnNewCustomer.addEventListener("click", async () => {
      const display_name = (fldDisplay?.value || "").trim();
      const ragione_sociale = (fldRs?.value || "").trim();
      const partita_iva = (fldPiva?.value || "").trim();
      const codice_cliente = (fldCodice?.value || "").trim();

      const aliases = (fldAliases?.value || "")
        .split("\n")
        .map(x => x.trim())
        .filter(Boolean);

      const payload = {
        display_name,
        ragione_sociale,
        partita_iva,
        codice_cliente,
        aliases,
      };

      saveBtnNewCustomer.disabled = true;

      try {
        const r = await fetch("/cassa/api/customers", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify(payload),
        });

        const data = await r.json();

        if (!r.ok || !data.ok) {
          alert(data.error || "Errore durante il salvataggio cliente");
          return;
        }

        const c = data.customer || {};

        if (opCustomerIdInput) opCustomerIdInput.value = c.id ? String(c.id) : "";
        if (opCustomerInput) opCustomerInput.value = c.display || c.display_name || "";

        bsModal.hide();
      } catch (err) {
        console.error("customerNewSave error:", err);
        alert("Errore di rete durante il salvataggio cliente");
      } finally {
        saveBtnNewCustomer.disabled = false;
      }
    });
  })();

  (function initCustomerSuggest() {
    const input = document.getElementById("opCustomer");
    const list = document.getElementById("opCustomerList");
    const hiddenId = document.getElementById("opCustomerId");
    if (!input || !list || !hiddenId) return;

    let lastItems = [];
    let t = null;

    function renderDatalist(items) {
      list.innerHTML = "";
      items.forEach(it => {
        const opt = document.createElement("option");
        opt.value = it.display || "";
        list.appendChild(opt);
      });
    }

    function findByDisplay(display) {
      const d = (display || "").trim();
      return lastItems.find(x => ((x.display || "").trim() === d));
    }

    input.addEventListener("input", () => {
      hiddenId.value = "";
      const q = input.value.trim();

      if (q.length < 2) {
        lastItems = [];
        list.innerHTML = "";
        return;
      }

      clearTimeout(t);
      t = setTimeout(async () => {
        const items = await fetchCustomerSuggest(q);
        lastItems = items;
        renderDatalist(items);
      }, 180);
    });

    input.addEventListener("change", () => {
      const chosen = findByDisplay(input.value);
      hiddenId.value = chosen ? String(chosen.id) : "";
    });
  })();

  (function initCustomerSearchModal() {
    const btnOpen = document.getElementById("btnCustomerSearch");
    const modalEl = document.getElementById("customerSearchModal");
    if (!btnOpen || !modalEl || typeof bootstrap === "undefined") return;

    const bsModal = new bootstrap.Modal(modalEl);

    const qInput = document.getElementById("customerSearchInput");
    const btnGo = document.getElementById("customerSearchGo");
    const tbody = document.getElementById("customerSearchResults");
    const selId = document.getElementById("customerSelectedId");
    const selDisp = document.getElementById("customerSelectedDisplay");
    const btnConfirm = document.getElementById("customerPickConfirm");
    const opInput = document.getElementById("opCustomer");
    const opHiddenId = document.getElementById("opCustomerId");

    if (!qInput || !btnGo || !tbody || !selId || !selDisp || !btnConfirm || !opInput || !opHiddenId) return;

    function setSelected(id, display) {
      selId.value = id ? String(id) : "";
      selDisp.value = display || "";
      btnConfirm.disabled = !selId.value;
    }

    async function runSearch() {
      const q = (qInput.value || "").trim();
      setSelected("", "");

      if (q.length < 2) {
        tbody.innerHTML = `<tr><td colspan="4" class="text-muted">Inserisci almeno 2 caratteri</td></tr>`;
        return;
      }

      const items = await fetchCustomerSuggest(q);
      if (!items.length) {
        tbody.innerHTML = `<tr><td colspan="4" class="text-muted">Nessun risultato</td></tr>`;
        return;
      }

      tbody.innerHTML = "";
      items.forEach(it => {
        const tr = document.createElement("tr");
        tr.style.cursor = "pointer";
        tr.innerHTML = `
          <td class="fw-semibold">${escapeHtml(it.display || "")}</td>
          <td>${escapeHtml(it.ragione_sociale || "")}</td>
          <td>${escapeHtml(it.partita_iva || "")}</td>
          <td>${escapeHtml(it.codice_cliente || "")}</td>
        `;
        tr.addEventListener("click", () => {
          [...tbody.querySelectorAll("tr")].forEach(x => x.classList.remove("table-active"));
          tr.classList.add("table-active");
          setSelected(it.id, it.display);
        });
        tbody.appendChild(tr);
      });
    }

    btnOpen.addEventListener("click", () => {
      qInput.value = (opInput.value || "").trim();
      setSelected("", "");
      tbody.innerHTML = `<tr><td colspan="4" class="text-muted">Inserisci un testo e premi Cerca</td></tr>`;
      bsModal.show();
      setTimeout(() => qInput.focus(), 150);
    });

    btnGo.addEventListener("click", runSearch);

    qInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        runSearch();
      }
    });

    btnConfirm.addEventListener("click", () => {
      if (!selId.value) return;
      opHiddenId.value = selId.value;
      opInput.value = selDisp.value;
      bsModal.hide();
    });
  })();

  const corrispettiviBox = document.getElementById("kpiCorrispettiviBox");
  if (corrispettiviBox) {
    corrispettiviBox.addEventListener("click", openReceiptModal);
  }

  const rcAmountInput = document.getElementById("rc_amount");

  rcAmountInput?.addEventListener("blur", (e) => {
    const n = parseEuroToNumber(e.target.value);
    e.target.value = formatEuro2(n);
  });

  document.getElementById("kpiFondoCard")?.addEventListener("click", async () => {
    await openDrawerCountModal();
  });

  drawerRowsEl?.addEventListener("input", updateDrawerTotals);

  drawerSaveBtn?.addEventListener("click", async () => {
    await saveDrawerCount();
  });

  drawerDeleteBtn?.addEventListener("click", async () => {
    await deleteDrawerCount();
  });

  document.getElementById("kpiVersamentiBox")?.addEventListener("click", async () => {
    await openDepositModal();
  });

  depositTypeSelect?.addEventListener("change", async () => {
    if (!currentDay) return;
    await loadAvailableDepositChecks(currentDay);
    updateDepositTotal();
    updateDepositCashUi();
  });

  document.getElementById("btnAddReceipt")?.addEventListener("click", async () => {
    await saveReceiptClosure();
  });

  document.getElementById("rc_table")?.addEventListener("click", async (e) => {
    const editBtn = e.target.closest(".btn-receipt-edit");
    if (editBtn) {
      try {
        const row = JSON.parse(editBtn.dataset.row || "{}");
        startEditReceiptClosure(row);
      } catch (err) {
        console.error("receipt edit parse error:", err);
        alert("Errore nel caricamento del corrispettivo da modificare.");
      }
      return;
    }

    const deleteBtn = e.target.closest(".btn-receipt-delete");
    if (deleteBtn) {
      const receiptClosureId = deleteBtn.dataset.id;
      await deleteReceiptClosure(receiptClosureId);
    }
  });

  depositTableBody?.addEventListener("click", async (e) => {
    const editBtn = e.target.closest(".btn-edit-deposit");
    if (editBtn) {
      const depositId = editBtn.dataset.id;
      if (!depositId) return;

      try {
        const r = await fetch(`/cassa/api/day/${currentDay}/deposits`, {
          credentials: "same-origin",
          headers: { "Accept": "application/json" },
          cache: "no-store"
        });

        const data = await r.json();

        if (!r.ok || !data.ok) {
          alert(data.error || "Errore caricamento versamento");
          return;
        }

        const row = (data.deposits || []).find(x => String(x.id) === String(depositId));
        if (!row) {
          alert("Versamento non trovato");
          return;
        }

        editingDepositId = row.id;

        if (depositTypeSelect) depositTypeSelect.value = row.deposit_type || "versamento_incasso";
        if (depositDateInput) depositDateInput.value = row.deposit_date || currentDay;
        if (depositCashAmountInput) depositCashAmountInput.value = formatEuro2(row.cash_amount || 0);
        if (depositNoteInput) depositNoteInput.value = row.note || "";
        if (depositAddBtn) depositAddBtn.textContent = "Salva modifica";

        await loadDepositBanks(row.bank_id);
        await loadAvailableDepositChecks(currentDay);

        const selectedIds = new Set((row.checks || []).map(x => String(x.id)));

        depositChecksTableBody?.querySelectorAll(".deposit-check-select").forEach(cb => {
          cb.checked = selectedIds.has(String(cb.value));
        });

        updateDepositTotal();
        updateDepositCashUi();
        return;

      } catch (err) {
        console.error("editDeposit error:", err);
        alert("Errore di rete");
        return;
      }
    }

    const deleteBtn = e.target.closest(".btn-deposit-delete");
    if (!deleteBtn) return;

    const depositId = deleteBtn.dataset.id;
    if (!depositId) return;

    const confirmed = window.confirm("Vuoi eliminare questo versamento?");
    if (!confirmed) return;

    try {
      deleteBtn.disabled = true;

      const r = await fetch(`/cassa/api/deposits/${depositId}`, {
        method: "DELETE",
        headers: { "Accept": "application/json" },
        credentials: "same-origin",
        cache: "no-store"
      });

      const data = await r.json();

      if (!r.ok || !data.ok) {
        alert(data.error || "Errore eliminazione versamento");
        deleteBtn.disabled = false;
        return;
      }

      if (editingDepositId && String(editingDepositId) === String(depositId)) {
        await loadDepositBanks();
        resetDepositForm();
        await loadAvailableDepositChecks(currentDay);
      }

      await loadDeposits(currentDay);
      updateDepositTotal();
      await refreshAgendaData();

    } catch (err) {
      console.error("deleteDeposit error:", err);
      alert("Errore di rete");
    }
  });

  normalizeCurrencyInput(depositCashAmountInput);

  depositCashAmountInput?.addEventListener("input", () => {
    updateDepositTotal();
    updateDepositCashUi();
  });

  depositChecksTableBody?.addEventListener("change", (e) => {
    if (e.target.closest(".deposit-check-select")) {
      updateDepositTotal();
      updateDepositCashUi();
    }
  });

  depositAddBtn?.addEventListener("click", async () => {
    await saveDeposit();
  });

  document.querySelectorAll('input[name="paymentMode"]').forEach(radio => {
    radio.addEventListener("change", () => {
      const newMode = radio.value;
      const previousMode = lastPaymentMode || "cash";

      if (newMode === previousMode) {
        return;
      }

      if (previousMode === "multi" && newMode !== "multi" && multiRowsHaveData()) {
        const confirmed = window.confirm(
          "Passando a un pagamento singolo perderai le righe multiple inserite. Vuoi continuare?"
        );

        if (!confirmed) {
          const prevRadio = document.querySelector(`input[name="paymentMode"][value="${previousMode}"]`);
          if (prevRadio) prevRadio.checked = true;
          return;
        }

        resetMultiPayments();
      }

      setPaymentMode(newMode);
      refreshSingleAmountFields();
      updatePaymentState();
    });
  });

  posDeviceSelect?.addEventListener("change", async (e) => {
    await loadPosCircuits(e.target.value, posCircuitSelect);
    updatePaymentState();
  });

  normalizeCurrencyInput(document.getElementById("cashAmount"));
  normalizeCurrencyInput(document.getElementById("posAmount"));
  normalizeCurrencyInput(document.getElementById("bankAmount"));
  normalizeCurrencyInput(document.getElementById("checkAmount"));

  opAmountInput?.addEventListener("input", () => {
    refreshSingleAmountFields();
    updatePaymentState();
  });

  opAmountInput?.addEventListener("blur", (e) => {
    const n = parseEuroToNumber(e.target.value);
    e.target.value = formatEuro2(n);
    refreshSingleAmountFields();
    updatePaymentState();
  });

  opAmountInput?.addEventListener("focus", (e) => {
    e.target.select?.();
  });

  btnAddPaymentRow?.addEventListener("click", () => {
    addMultiPaymentRow();
  });

  document.getElementById("btnNewIncasso")?.addEventListener("click", () => openOpModal("sale"));
  document.getElementById("btnNewSpesa")?.addEventListener("click", () => openOpModal("expense"));

  document.getElementById("opOffCash")?.addEventListener("change", (e) => {
    const box = document.getElementById("opOffCashBox");
    if (!box) return;
    box.classList.toggle("d-none", !e.target.checked);
  });

  saveBtn?.addEventListener("click", () => {
    saveOperation();
  });

  updatePaymentState();
});

document.addEventListener("visibilitychange", function () {
  if (document.visibilityState === "visible") {
    loadAssegniScadenza(currentDay, false);
    startAssegniAutoRefresh();
  } else {
    stopAssegniAutoRefresh();
  }
});

ecoAddBtn?.addEventListener("click", async () => {
  const amountRaw = ecoAmountInput?.value;
  const description = (ecoDescriptionInput?.value || "").trim();

  if (!amountRaw || isNaN(amountRaw)) {
    alert("Inserisci un importo valido");
    return;
  }

  if (!description) {
    alert("Inserisci una descrizione");
    return;
  }

  const amount = parseFloat(amountRaw);

  try {
    const r = await fetch(`/cassa/api/day/${currentDay}/ecommerce`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      credentials: "same-origin",
      body: JSON.stringify({
        amount,
        description
      })
    });

    const data = await r.json();

    if (!data.ok) {
      alert(data.error || "Errore inserimento");
      return;
    }

    ecoAmountInput.value = "";
    ecoDescriptionInput.value = "";

    await loadEcommerce(currentDay);
    await loadPreview(currentDay);

  } catch (err) {
    console.error("ecoAdd error:", err);
    alert("Errore di rete");
  }
});

ecoTableBody?.addEventListener("click", async (e) => {
  const btn = e.target.closest(".btn-eco-delete");
  if (!btn) return;

  const ecommerceId = btn.dataset.id;
  if (!ecommerceId) return;

  const confirmed = window.confirm("Vuoi eliminare questo movimento e-commerce?");
  if (!confirmed) return;

  try {
    const r = await fetch(`/cassa/api/ecommerce/${ecommerceId}`, {
      method: "DELETE",
      headers: { "Accept": "application/json" },
      credentials: "same-origin"
    });

    const data = await r.json();

    if (!data.ok) {
      alert(data.error || "Errore eliminazione");
      return;
    }

    await loadEcommerce(currentDay);
    await loadPreview(currentDay);

  } catch (err) {
    console.error("ecoDelete error:", err);
    alert("Errore di rete");
  }
});