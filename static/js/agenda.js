let currentDay = null;
let calendarInstance = null;
let lastPaymentMode = "cash";
let currentPreviewTotals = {};
let editingOperationType = null;   // "sale" | "expense" | null
let editingOperationId = null;
let editingOperationCheckIds = [];
let priVaultUnlocked = false;
let lastKnownVaultState = null;
let vaultPollInterval = null;
let lastKnownVaultStateVersion = null;
let lastKnownAgendaVersion = null;
let agendaPollInterval = null;
let editingEcommerceId = null;

const EXPENSE_POS_CARDS = [
  "Carta aziendale",
  "Carta personale"
];

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

async function readJsonResponse(response, fallbackError = "Risposta non valida dal server") {
  const text = await response.text();
  try {
    return JSON.parse(text);
  } catch (err) {
    console.error(fallbackError, {
      status: response.status,
      body: text.slice(0, 500)
    });
    return { ok: false, error: fallbackError };
  }
}

function parseEuroToNumber(raw) {
  if (raw == null) return 0;

  let s = String(raw).trim();
  if (!s) return 0;

  s = s.replace(/[^\d.,-]/g, "");

  const lastComma = s.lastIndexOf(",");
  const lastDot = s.lastIndexOf(".");

  if (lastComma !== -1 || lastDot !== -1) {
    const decimalSep = lastComma > lastDot ? "," : ".";
    const thousandsSep = decimalSep === "," ? "." : ",";

    s = s
      .replaceAll(thousandsSep, "")
      .replace(decimalSep, ".");
  }

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

function formatDateIT(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";

  const match = raw.match(/^(\d{4})-(\d{2})-(\d{2})(.*)$/);
  if (match) {
    return `${match[3]}-${match[2]}-${match[1]}`;
  }

  return raw;
}

function formatDateTimeIT(value) {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return formatDateIT(value);
  return d.toLocaleString("it-IT").replaceAll("/", "-");
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

async function pollAgendaVersion() {
  if (!currentDay) return;

  try {
    const r = await fetch(`/cassa/api/day/${currentDay}/version`, {
      credentials: "same-origin",
      headers: { "Accept": "application/json" },
      cache: "no-store"
    });

    const data = await r.json();
    if (!data.ok) return;

    const version = Number(data.version || 0);

    if (lastKnownAgendaVersion === null) {
      lastKnownAgendaVersion = version;
      return;
    }

    if (version !== lastKnownAgendaVersion) {
      console.log("Agenda changed → refresh", lastKnownAgendaVersion, "→", version);

      lastKnownAgendaVersion = version;
      await refreshAgendaData();
    }
  } catch (err) {
    console.error("pollAgendaVersion error:", err);
  }
}

/* =========================
   API HELPERS
========================= */

function applyVaultHeaderState() {
  const header = document.getElementById("agendaDayHeader");
  if (!header) return;

  header.classList.toggle("vault-unlocked", priVaultUnlocked === true);
  header.classList.toggle("vault-locked", priVaultUnlocked !== true);
}

async function pollPrivateVaultStatus() {
  try {
    await refreshPrivateVaultStatus();

    const currentVersion = Number(window.currentVaultStateVersion || 0);

    if (lastKnownVaultStateVersion === null) {
      lastKnownVaultStateVersion = currentVersion;
      return;
    }

    if (currentVersion !== lastKnownVaultStateVersion) {
      console.log("Vault state version changed:", currentVersion);

      lastKnownVaultStateVersion = currentVersion;
      await refreshAgendaData();
      return;
    }

  } catch (err) {
    console.error("pollPrivateVaultStatus error:", err);
  }
}

async function refreshPrivateVaultStatus() {
  try {
    const r = await fetch("/cassa/api/private/status", {
      credentials: "same-origin",
      headers: { "Accept": "application/json" },
      cache: "no-store"
    });

    const data = await r.json();

    priVaultUnlocked = !!data?.vault?.unlocked;
    window.currentVaultStateVersion = Number(data?.vault?.state_version || 0);

    applyVaultHeaderState();

    return priVaultUnlocked;
  } catch (err) {
    console.error("refreshPrivateVaultStatus error:", err);
    priVaultUnlocked = false;
    window.currentVaultStateVersion = 0;
    applyVaultHeaderState();
    return false;
  }
}

async function lockPrivateVault() {
  const r = await fetch("/cassa/api/private/lock", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Accept": "application/json" }
  });

  const data = await r.json();

  if (!r.ok || !data.ok) {
    throw new Error(data.error || "Errore blocco vault");
  }

  await refreshPrivateVaultStatus();
  lastKnownVaultStateVersion = Number(window.currentVaultStateVersion || 0);
  await refreshAgendaSections(["preview", "incassi", "spese", "cash_moves"]);;

  return data;
}


async function unlockPrivateVault() {
  const wasUnlocked = priVaultUnlocked === true;

  const r = await fetch("/cassa/api/private/unlock", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "Accept": "application/json"
    },
    body: JSON.stringify({ password: "TEST123" })
  });

  const data = await r.json();

  if (!r.ok || !data.ok) {
    throw new Error(data.error || "Errore sblocco vault");
  }

  await refreshPrivateVaultStatus();
  lastKnownVaultStateVersion = Number(window.currentVaultStateVersion || 0);

  const isUnlocked = priVaultUnlocked === true;

  // Se non c'è stato cambio reale di stato, niente refresh quadranti
  if (wasUnlocked === isUnlocked) {
    return data;
  }

  await refreshAgendaSections(["preview", "incassi", "spese", "cash_moves"]);
  return data;
}


async function togglePrivateVault() {
  try {
    await refreshPrivateVaultStatus();

    if (priVaultUnlocked) {
      await lockPrivateVault();
    } else {
      await unlockPrivateVault();
    }

  } catch (err) {
    console.error("togglePrivateVault error:", err);
    alert(err.message || "Errore gestione vault privato");
    await refreshPrivateVaultStatus();
    await refreshAgendaData();
  }
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

function getCurrentRegistryKind() {
  return (document.getElementById("opType")?.value || "sale") === "expense" ? "supplier" : "customer";
}

async function fetchCustomerSuggest(q, kind = "customer") {
  const url = `/cassa/api/customers/suggest?q=${encodeURIComponent(q)}&kind=${encodeURIComponent(kind)}`;
  const r = await fetch(url, {
    credentials: "same-origin",
    headers: { "Accept": "application/json" }
  });
  const data = await r.json();
  if (!data.ok) return [];
  return data.customers || [];
}

async function resolveCustomerRegistry(registryId) {
  const id = Number(registryId || 0);
  if (!id) return null;
  const r = await fetch("/cassa/api/customers/resolve-registry", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "Accept": "application/json"
    },
    body: JSON.stringify({ registry_id: id })
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok || !data.ok) {
    throw new Error(data.error || "Errore selezione cliente");
  }
  return data.customer || null;
}

function isPrivateCustomerLabel(label) {
  const text = String(label || "").trim().toLowerCase();
  return text === "privato" || text === "privati";
}

/* =========================
   POS MODAL REFS
========================= */

const posModalEl = document.getElementById("posModal");
const posMoveDateInput = document.getElementById("posMoveDate");
const posMoveTypeSelect = document.getElementById("posMoveType");
const posMoveDeviceSelect = document.getElementById("posMoveDevice");
const posMoveCircuitSelect = document.getElementById("posMoveCircuit");
const posMoveAmountInput = document.getElementById("posMoveAmount");
const posMoveDocRefSelect = document.getElementById("posMoveDocRef");
const posMoveNotesInput = document.getElementById("posMoveNotes");
const posMoveSaveBtn = document.getElementById("posMoveSaveBtn");
const btnOpenPosModal = document.getElementById("btnOpenPosModal");

let posModal = null;
let editingPosMoveId = null;
let posFilters = {
  deviceId: null,
  deviceName: "",
  circuitId: null,
  circuitName: ""
};
let lastPosMoves = [];

let saleFilters = {
  method: null,
  flag: null,
  cashScope: null
};
let expenseFilters = {
  method: null,
  flag: null,
  cashScope: null
};
let cashMoveFilters = {
  kind: null,
  direction: null
};
let lastSaleRows = [];
let lastExpenseRows = [];
let lastCashMoveRows = [];

/* =========================
   CASH MOVE MODAL REFS
========================= */

const cashMoveModalEl = document.getElementById("cashMoveModal");
const cashMoveDateInput = document.getElementById("cashMoveDate");
const cashMoveKindSelect = document.getElementById("cashMoveKind");
const cashMoveAmountInput = document.getElementById("cashMoveAmount");
const cashMovePerformedByInput = document.getElementById("cashMovePerformedBy");
const cashMoveNotesInput = document.getElementById("cashMoveNotes");
const cashMoveSaveBtn = document.getElementById("cashMoveSaveBtn");
const btnOpenCashMoveModal = document.getElementById("btnOpenCashMoveModal");

let cashMoveModal = null;
let editingCashMoveId = null;

/* =========================
   SPICCI MODAL REFS
========================= */

const btnOpenSpicciModal = document.getElementById("btnOpenSpicciModal");
const spicciModalEl = document.getElementById("spicciModal");
const spicciMoveTypeSelect = document.getElementById("spicciMoveType");
const spicciMoveAmountInput = document.getElementById("spicciMoveAmount");
const spicciMovePerformedByInput = document.getElementById("spicciMovePerformedBy");
const spicciMoveNotesInput = document.getElementById("spicciMoveNotes");
const spicciMoveSaveBtn = document.getElementById("spicciMoveSaveBtn");
const spicciTableBody = document.getElementById("spicciTableBody");

let spicciModal = null;
let editingSpicciMoveId = null;

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
        <td>${escapeHtml(formatDateIT(c.received_date))}</td>
        <td>${escapeHtml(formatDateIT(c.due_date))}</td>
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
        <td>${formatDateTimeIT(row.created_at)}</td>
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
   MOVEMENT SEARCH MODALS
========================= */

const movementSearchCustomerModalEl = document.getElementById("movementSearchCustomerModal");
const movementSearchCustomerText = document.getElementById("movementSearchCustomerText");
const movementSearchCustomerFrom = document.getElementById("movementSearchCustomerFrom");
const movementSearchCustomerTo = document.getElementById("movementSearchCustomerTo");
const movementSearchCustomerBtn = document.getElementById("movementSearchCustomerBtn");
const movementSearchCustomerResults = document.getElementById("movementSearchCustomerResults");

const movementSearchAmountModalEl = document.getElementById("movementSearchAmountModal");
const movementSearchAmountValue = document.getElementById("movementSearchAmountValue");
const movementSearchAmountTolerance = document.getElementById("movementSearchAmountTolerance");
const movementSearchAmountFrom = document.getElementById("movementSearchAmountFrom");
const movementSearchAmountTo = document.getElementById("movementSearchAmountTo");
const movementSearchAmountBtn = document.getElementById("movementSearchAmountBtn");
const movementSearchAmountResults = document.getElementById("movementSearchAmountResults");

let movementSearchCustomerModal = null;
let movementSearchAmountModal = null;

const checksManagementModalEl = document.getElementById("checksManagementModal");
const checksFilterText = document.getElementById("checksFilterText");
const checksFilterStatus = document.getElementById("checksFilterStatus");
const checksFilterFrom = document.getElementById("checksFilterFrom");
const checksFilterTo = document.getElementById("checksFilterTo");
const checksReloadBtn = document.getElementById("checksReloadBtn");
const checksNewBtn = document.getElementById("checksNewBtn");
const checksManagementRows = document.getElementById("checksManagementRows");
const checksStatusBar = document.getElementById("checksStatusBar");
const checkEditId = document.getElementById("checkEditId");
const checkCustomerId = document.getElementById("checkCustomerId");
const checkCustomerLabel = document.getElementById("checkCustomerLabel");
const checkBankName = document.getElementById("checkBankName");
const checkNumber = document.getElementById("checkNumber");
const checkAbi = document.getElementById("checkAbi");
const checkCab = document.getElementById("checkCab");
const checkAmount = document.getElementById("checkAmount");
const checkStatus = document.getElementById("checkStatus");
const checkReceivedDate = document.getElementById("checkReceivedDate");
const checkDueDate = document.getElementById("checkDueDate");
const checkNote = document.getElementById("checkNote");
const checkCancelBtn = document.getElementById("checkCancelBtn");
const checkSaveBtn = document.getElementById("checkSaveBtn");

let checksManagementModal = null;
let checkStatusOptions = [
  { value: "received", label: "In pancia" },
  { value: "moved", label: "Spostato" },
  { value: "spostato", label: "Spostato" },
  { value: "anticipato", label: "Anticipato" },
  { value: "deposited", label: "Versato" },
  { value: "cashed", label: "Incassato" },
  { value: "bounced", label: "Insoluto" },
  { value: "protested", label: "Protestato" },
  { value: "withdrawn", label: "Ritirato" },
];

const issuedChecksManagementModalEl = document.getElementById("issuedChecksManagementModal");
const issuedChecksFilterText = document.getElementById("issuedChecksFilterText");
const issuedChecksFilterStatus = document.getElementById("issuedChecksFilterStatus");
const issuedChecksFilterFlag = document.getElementById("issuedChecksFilterFlag");
const issuedChecksFilterFrom = document.getElementById("issuedChecksFilterFrom");
const issuedChecksFilterTo = document.getElementById("issuedChecksFilterTo");
const issuedChecksReloadBtn = document.getElementById("issuedChecksReloadBtn");
const issuedChecksManagementRows = document.getElementById("issuedChecksManagementRows");
const issuedCheckEditId = document.getElementById("issuedCheckEditId");
const issuedCheckFlag = document.getElementById("issuedCheckFlag");
const issuedCheckBankSelect = document.getElementById("issuedCheckBankSelect");
const issuedCheckNumber = document.getElementById("issuedCheckNumber");
const issuedCheckAmount = document.getElementById("issuedCheckAmount");
const issuedCheckDueDate = document.getElementById("issuedCheckDueDate");
const issuedCheckStatus = document.getElementById("issuedCheckStatus");
const issuedCheckNote = document.getElementById("issuedCheckNote");
const issuedCheckCancelBtn = document.getElementById("issuedCheckCancelBtn");
const issuedCheckSaveBtn = document.getElementById("issuedCheckSaveBtn");

let issuedChecksManagementModal = null;
let issuedCheckStatusOptions = [
  { value: "emesso", label: "Emesso" },
  { value: "registrato", label: "Registrato" },
  { value: "rientrato", label: "Rientrato" },
];

/* =========================
   DAY / PREVIEW
========================= */

async function loadDay(dateStr) {
  return fetch(`/cassa/api/day?date=${dateStr}`)
    .then(r => readJsonResponse(r, "Errore durante il caricamento della giornata"))
    .then(async data => {
      if (!data.ok) {
        console.error(data.error || "Errore durante il caricamento della giornata");
        return;
      }

      currentDay = data.day.day_date;

      setText("dayDateTitle", formatDateIT(currentDay));
      setText("dayId", data.day.id);
      setText("dayOpeningFloat", Number(data.day.opening_float || 0).toFixed(2));
      setText("dayStatusBadge", String(data.day.status || "—").toUpperCase());
      setText("agendaLastUpdated", "Ultimo aggiornamento: " + new Date().toLocaleTimeString());

      await refreshAgendaData();
      lastKnownVaultStateVersion = Number(window.currentVaultStateVersion || 0);

      document.getElementById("btnNewIncasso")?.removeAttribute("disabled");
      document.getElementById("btnNewSpesa")?.removeAttribute("disabled");
      document.getElementById("btnNewMovimento")?.removeAttribute("disabled");
      document.getElementById("btnNewPos")?.removeAttribute("disabled");
      startPolling();
    });
}

function startPolling() {
  if (!vaultPollInterval) {
    vaultPollInterval = setInterval(pollPrivateVaultStatus, 3000);
  }

  if (!agendaPollInterval) {
    agendaPollInterval = setInterval(pollAgendaVersion, 3000);
  }
}

async function loadPreview(dateStr) {
  try {
    const view = priVaultUnlocked ? "complete" : "fiscal";

    const r = await fetch(`/cassa/api/day/${dateStr}/preview?view=${view}`, {
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
    /* const priCashNet = Number(t.pri_cash_net || 0);
    const icDisplay = priVaultUnlocked
      ? Number(ic || 0) + priCashNet
      : Number(ic || 0); */
    const df = (t.delta_fondo ?? t.deltaFondo ?? t.df);
    const dq = (t.delta_quadratura ?? t.deltaQuadratura ?? t.dq);
    const fondoInit = (t.fondo_iniziale ?? t.opening_float ?? t.fondoIniziale);
    const fondoFin = (t.fondo_finale ?? t.fondoFinale);
    const sPrev = (t.saldo_versabile_precedente ?? t.saldo_versabile_init ?? t.saldoVersabilePrecedente);
    const totEcommerce = Number(t.totale_ecommerce || 0);
    const totVers = (t.totale_versato_oggi ?? t.totale_versamenti ?? t.totVersamenti);
    const cor = (t.total_corrispettivi ?? t.corrispettivi ?? t.corrispettivi_totali);
    const consegnato = (t.incasso_consegnato ?? t.incassoConsegnato);
    const cassettoDisplay = priVaultUnlocked ? consegnato : ic;
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
    setText("kpiIncassoConsegnato", _fmt2(cassettoDisplay));

    updateDepositCashUi();
  } catch (err) {
    console.error("loadPreview error:", err);
  }
}

async function refreshAgendaSections(sections = []) {
  if (!currentDay) return;

  await refreshPrivateVaultStatus();

  const jobs = [];

  if (sections.includes("preview")) jobs.push(loadPreview(currentDay));
  if (sections.includes("incassi")) jobs.push(loadIncassi(currentDay));
  if (sections.includes("spese")) jobs.push(loadSpese(currentDay));
  if (sections.includes("pos")) jobs.push(loadPosMoves(currentDay));
  if (sections.includes("cash_moves")) jobs.push(loadCashMoves(currentDay));
  if (sections.includes("coins")) jobs.push(loadCoinsBalance(currentDay));
  if (sections.includes("assegni")) jobs.push(loadAssegniScadenza(currentDay, false));
  if (sections.includes("assegni_rientranti")) jobs.push(loadAssegniRientranti(currentDay));

  await Promise.all(jobs);
}

async function refreshAgendaData() {
  if (!currentDay) return;

  await refreshPrivateVaultStatus();

  await loadPreview(currentDay);
  await Promise.all([
    loadIncassi(currentDay),
    loadSpese(currentDay),
    loadPosMoves(currentDay),
    loadCashMoves(currentDay),
    loadCoinsBalance(currentDay),
    loadAssegniRientranti(currentDay)
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

function getDrawerInitialInput() {
  if (!drawerRowsEl) return null;
  const inputs = Array.from(drawerRowsEl.querySelectorAll(".drawer-qty"));
  return inputs.find(input => Math.abs(Number(input.dataset.denom || 0) - 0.10) < 0.001) || inputs[0] || null;
}

function focusDrawerInitialInput() {
  const input = getDrawerInitialInput();
  if (!input) return;

  const selectInput = () => {
    input.focus();
    input.select();
    if (typeof input.setSelectionRange === "function") {
      input.setSelectionRange(0, String(input.value || "").length);
    }
  };

  requestAnimationFrame(selectInput);
  setTimeout(selectInput, 120);
}

function handleDrawerModalKeydown(event) {
  if (!drawerModalEl || !drawerModalEl.classList.contains("show")) return;

  if (event.key === "Enter") {
    const target = event.target;
    const tagName = String(target?.tagName || "").toLowerCase();
    if (tagName === "textarea" || target?.isContentEditable) return;
    event.preventDefault();
    if (!drawerSaveBtn?.disabled) {
      saveDrawerCount();
    }
    return;
  }

  if (event.key === "Escape") {
    event.preventDefault();
    if (drawerModal) {
      drawerModal.hide();
    }
  }
}

function isExpenseOperation() {
  return (document.getElementById("opType")?.value || "") === "expense";
}

function renderExpensePosOptions() {
  const posDeviceWrap = document.getElementById("paymentSinglePosPanel")?.querySelector(".row");
  if (!posDeviceWrap) return;

  if (document.getElementById("expensePosCardSelect")) return;

  posDeviceWrap.innerHTML = `
    <div class="col-12">
      <label class="form-label mb-0">Carta utilizzata</label>
      <select class="form-select" id="expensePosCardSelect">
        <option value="">Seleziona...</option>
        ${EXPENSE_POS_CARDS.map(card => `<option value="${escapeHtml(card)}">${escapeHtml(card)}</option>`).join("")}
      </select>
    </div>
  `;
}

function renderSalePosOptions() {
  const posPanel = document.getElementById("paymentSinglePosPanel");
  if (!posPanel) return;

  const row = posPanel.querySelector(".row");
  if (!row) return;

  if (document.getElementById("posDeviceSelect") && document.getElementById("posCircuitSelect")) {
    return;
  }

  row.innerHTML = `
    <div class="col-12 col-md-4">
      <label class="form-label mb-0">Dispositivo POS</label>
      <select class="form-select" id="posDeviceSelect">
        <option value="">Seleziona...</option>
      </select>
    </div>

    <div class="col-12 col-md-4">
      <label class="form-label mb-0">Circuito</label>
      <select class="form-select" id="posCircuitSelect" disabled>
        <option value="">Seleziona...</option>
      </select>
    </div>

    <div class="col-12 col-md-4">
      <label class="form-label mb-0">Importo POS</label>
      <div class="input-group">
        <span class="input-group-text">€</span>
        <input
          type="text"
          class="form-control text-end"
          id="posAmount"
          placeholder="0,00"
          inputmode="decimal">
      </div>
    </div>
  `;
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
          type="text"
          min="0"
          step="1"
          inputmode="numeric"
          pattern="[0-9]*"
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
    if (drawerSaveBtn) drawerSaveBtn.disabled = true;

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
  } finally {
    if (drawerSaveBtn) drawerSaveBtn.disabled = false;
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
    title.textContent = num ? `${bank} - ${num}` : bank;

    const meta = document.createElement("div");
    meta.className = "small text-muted";
    const cust = (c.customer && (c.customer.display_name || c.customer.name || c.customer.ragione_sociale))
      ? (c.customer.display_name || c.customer.name || c.customer.ragione_sociale)
      : "Cliente?";
    const due = formatDateIT(c.due_date) || "-";
    const rec = formatDateIT(c.received_date) || "-";
    meta.textContent = `Cliente: ${cust} - Scadenza: ${due} - Ricevuto: ${rec}`;

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

function renderAssegniRientranti(items) {
  const list = document.getElementById("assegniRientrantiList");
  if (!list) return;

  list.innerHTML = "";

  if (!items || !items.length) {
    const empty = document.createElement("div");
    empty.className = "list-group-item text-muted small";
    empty.textContent = "Nessun assegno rientrante";
    list.appendChild(empty);
    return;
  }

  for (const c of items) {
    const row = document.createElement("label");
    row.className = "list-group-item d-flex justify-content-between align-items-start gap-2";
    row.dataset.issuedCheckId = String(c.id || "");

    const leftWrap = document.createElement("div");
    leftWrap.className = "d-flex align-items-start gap-2 me-2";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.className = "form-check-input mt-1 issued-check-registered";
    checkbox.checked = !!c.is_registered_today;
    checkbox.dataset.checkId = String(c.id || "");

    const textWrap = document.createElement("div");
    textWrap.className = c.is_registered_today ? "text-decoration-line-through text-muted" : "";

    const title = document.createElement("div");
    title.className = "fw-semibold";
    const bank = (c.bank_name || "Banca?").trim();
    const num = (c.check_number || "").trim();
    title.textContent = num ? `${bank} - ${num}` : bank;

    const meta = document.createElement("div");
    meta.className = "small text-muted";
    const supplier = c.supplier || "Beneficiario?";
    const due = formatDateIT(c.due_date) || "-";
    meta.textContent = `${supplier} - Rientro: ${due}`;

    textWrap.appendChild(title);
    textWrap.appendChild(meta);

    leftWrap.appendChild(checkbox);
    leftWrap.appendChild(textWrap);

    const right = document.createElement("div");
    right.className = c.is_registered_today ? "text-end text-decoration-line-through text-muted" : "text-end";

    const amt = document.createElement("div");
    amt.className = "fw-bold";
    amt.textContent = eur(c.amount);

    right.appendChild(amt);

    row.appendChild(leftWrap);
    row.appendChild(right);

    list.appendChild(row);
  }
}

function loadAssegniRientranti(dateStr = null) {
  const ref = dateStr || currentDay || toLocalYMD(new Date());
  const qs = new URLSearchParams({ date: ref });

  return fetch(`/cassa/api/issued-checks/returning?${qs.toString()}`, {
    credentials: "same-origin",
    headers: { "Accept": "application/json" },
    cache: "no-store"
  })
    .then(r => readJsonResponse(r, "Errore caricamento assegni rientranti"))
    .then(data => {
      if (!data.ok) return;
      renderAssegniRientranti(data.checks || []);
    })
    .catch(() => {
      const list = document.getElementById("assegniRientrantiList");
      if (list) {
        list.innerHTML = `<div class="list-group-item text-danger small">Errore caricamento assegni rientranti</div>`;
      }
    });
}

async function toggleAssegnoRientrante(checkId, registered) {
  if (!checkId) return;

  const r = await fetch(`/cassa/api/issued-checks/${encodeURIComponent(checkId)}/registered`, {
    method: "PUT",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "Accept": "application/json"
    },
    body: JSON.stringify({
      registered: !!registered,
      date: currentDay || toLocalYMD(new Date())
    })
  });

  const data = await readJsonResponse(r, "Errore aggiornamento assegno rientrante");
  if (!r.ok || !data.ok) {
    throw new Error(data.error || "Errore aggiornamento assegno rientrante");
  }

  await loadAssegniRientranti(currentDay);
}

document.getElementById("assegniRientrantiList")?.addEventListener("change", async (e) => {
  const checkbox = e.target.closest(".issued-check-registered");
  if (!checkbox) return;

  const previousValue = !checkbox.checked;
  checkbox.disabled = true;

  try {
    await toggleAssegnoRientrante(checkbox.dataset.checkId, checkbox.checked);
  } catch (err) {
    console.error("toggleAssegnoRientrante error:", err);
    checkbox.checked = previousValue;
    alert(err.message || "Errore aggiornamento assegno rientrante");
  } finally {
    checkbox.disabled = false;
  }
});

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
  if (totalEl) totalEl.textContent = formatFilteredTotal(0, hasActiveCashMoveFilters());

  try {
    const [movesRes, checksMap] = await Promise.all([
      fetch(`/cassa/api/day/${dayStr}/cash_moves`, { credentials: "same-origin" }),
      fetchRowChecks(Number(document.getElementById("dayId")?.textContent || 0), "cash_move")
    ]);

    const data = await movesRes.json();

    if (!data.ok) {
      listEl.innerHTML = `<div class="list-group-item text-muted small">Errore: ${data.error || "impossibile caricare movimenti"}</div>`;
      return;
    }

    const allMoves = data.cash_moves || [];
    lastCashMoveRows = allMoves;
    const moves = applyCashMoveFilters(allMoves);

    if (!allMoves.length) {
      listEl.innerHTML = `<div class="list-group-item text-muted small">Nessun movimento</div>`;
      return;
    }

    if (!moves.length) {
      listEl.innerHTML = `<div class="list-group-item text-muted small">Nessun movimento per filtro</div>`;
      if (totalEl) totalEl.textContent = formatFilteredTotal(0, true);
      return;
    }

    const tot = moves.reduce((s, m) => {
      const a = Number(m.amount || 0);
      return s + ((m.direction === "out") ? -a : a);
    }, 0);

    if (totalEl) totalEl.textContent = formatFilteredTotal(tot, hasActiveCashMoveFilters());

    listEl.innerHTML = moves.map(m => {
      const amount = Number(m.amount || 0);
      const isOut = m.direction === "out";
      const who = (m.performed_by || "").trim();
      const notes = (m.notes || "").trim();

      const tipoLabel = cashMoveDirectionLabel(m.direction);
      const kindLabel = cashMoveKindLabel(m.kind);
      const desc = [who, notes].filter(Boolean).join(" • ") || "Movimento";
      const amt = `${isOut ? "-" : ""}${Math.abs(amount).toFixed(2)}€`;
      const colorClass = isOut ? "text-danger" : "text-primary";

      const badges = [
        `<span class="badge badge-soft">${tipoLabel}</span>`,
        `<span class="badge badge-soft">${kindLabel}</span>`
      ];

      const isChecked = m.storage === "pri"
        ? !!m.is_checked
        : checksMap.get(String(m.id)) === true;

      return `
        <div
          class="list-group-item table-row cash-move-row ${isChecked ? "row-checked" : ""}"
          data-cash-move-id="${m.id}"
          data-cash-move-kind="${escapeHtml(m.kind || "altro")}"
          data-cash-move-direction="${escapeHtml(m.direction || "")}"
        >
          <div class="col-check me-2">
            <input
              type="checkbox"
              class="form-check-input cash-move-row-check"
              data-entity-type="cash_move"
              data-entity-id="${m.id}"
              ${isChecked ? "checked" : ""}
            >
          </div>
          <div class="col-desc">
            <span class="flag"></span>
            <span class="desc">${escapeHtml(desc)}</span>
          </div>
          <div class="col-badges">${badges.join("")}</div>
          <div class="col-amt ${colorClass}">${amt}</div>
          <div class="col-actions">
            <button type="button" class="btn btn-sm btn-light btn-row-menu">...</button>
          </div>
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
          <button
            type="button"
            class="btn btn-outline-secondary btn-sm btn-eco-edit"
            data-id="${row.id}"
            data-description="${escapeHtml(row.description || "")}"
            data-amount="${row.amount || 0}"
          >
            Modifica
          </button>
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

function focusEcommerceAmountInput() {
  if (!ecoAmountInput) return;

  const selectInput = () => {
    ecoAmountInput.focus();
    ecoAmountInput.select();
    if (typeof ecoAmountInput.setSelectionRange === "function") {
      ecoAmountInput.setSelectionRange(0, String(ecoAmountInput.value || "").length);
    }
  };

  requestAnimationFrame(selectInput);
  setTimeout(selectInput, 120);
}

function handleEcommerceModalKeydown(event) {
  if (!ecommerceModalEl || !ecommerceModalEl.classList.contains("show")) return;

  if (event.key === "Tab" && !event.shiftKey && event.target === ecoAmountInput && ecoDescriptionInput) {
    event.preventDefault();
    ecoDescriptionInput.focus();
    ecoDescriptionInput.select();
    return;
  }

  if (event.key === "Enter") {
    const target = event.target;
    const tagName = String(target?.tagName || "").toLowerCase();
    if (tagName === "textarea" || target?.isContentEditable) return;
    event.preventDefault();
    if (!ecoAddBtn?.disabled) {
      saveEcommerce();
    }
  }
}

async function loadIncassi(dayStr) {
  const listEl = document.getElementById("incassiList");
  const totalEl = document.getElementById("totIncassi");
  if (!listEl) return;

  listEl.innerHTML = `<div class="list-group-item text-muted small">Caricamento...</div>`;
  if (totalEl) totalEl.textContent = formatFilteredTotal(0, hasActiveSaleFilters());

  try {
    const [salesRes, checksMap] = await Promise.all([
      fetch(`/cassa/api/day/${dayStr}/sales`, { credentials: "same-origin" }),
      fetchRowChecks(Number(document.getElementById("dayId")?.textContent || 0), "sale")
    ]);

    const data = await salesRes.json();

    if (!data.ok) {
      listEl.innerHTML = `<div class="list-group-item text-muted small">Errore: ${data.error || "impossibile caricare incassi"}</div>`;
      return;
    }

    const sales = data.sales || [];
    if (!sales.length) {
      lastSaleRows = [];
      listEl.innerHTML = `<div class="list-group-item text-muted small">Nessun incasso</div>`;
      return;
    }

    const allRows = [];
    for (const s of sales) {
      for (const p of (s.payments || [])) {
        const rawDescription = (p.description || s.notes || "").trim();
        const rawCustomer = (s.customer_label || "").trim();

        let composedDesc = "";
        if (rawCustomer && rawDescription) {
          composedDesc = `${rawCustomer} - ${rawDescription}`;
        } else if (rawCustomer) {
          composedDesc = rawCustomer;
        } else {
          composedDesc = rawDescription;
        }

        allRows.push({
          sale_id: s.id,
          storage: s.storage || p.storage || "az",
          is_checked: !!s.is_checked,
          created_at: p.created_at || s.created_at,
          flag: p.flag || "",
          desc: composedDesc,
          amount: Number(p.amount || 0),
          direction: p.direction || "in",
          method: p.method || "",
          off_cash: !!p.off_cash,
        });
      }
    }

    lastSaleRows = allRows;
    const rows = applySaleFilters(allRows);

    if (!rows.length) {
      listEl.innerHTML = `<div class="list-group-item text-muted small">Nessun incasso per filtro</div>`;
      if (totalEl) totalEl.textContent = formatFilteredTotal(0, true);
      return;
    }

    listEl.innerHTML = rows.map(x => {
      const sign = x.direction === "out" ? "-" : "";
      const amt = `${sign}${x.amount.toFixed(2)}€`;

      const badges = [];
      if (x.method === "pos") badges.push(`<span class="badge badge-soft badge-pos">POS</span>`);
      if (x.method === "bank") badges.push(`<span class="badge badge-soft badge-bank">BANCA</span>`);
      if (x.method === "check") badges.push(`<span class="badge badge-soft badge-bank">ASSEGNO</span>`);
      if (x.off_cash) badges.push(`<span class="badge badge-soft badge-offcash">FUORI CASSA</span>`);

      const isChecked = x.storage === "pri"
        ? !!x.is_checked
        : checksMap.get(String(x.sale_id)) === true;

      return `
        <div
          class="list-group-item table-row sale-row ${isChecked ? "row-checked" : ""}"
          data-sale-id="${x.sale_id}"
          data-sale-method="${escapeHtml(x.method || "")}"
          data-sale-flag="${escapeHtml(x.flag || "")}"
          data-sale-off-cash="${x.off_cash ? "1" : "0"}"
        >
          <div class="col-check me-2">
            <input
              type="checkbox"
              class="form-check-input sale-row-check"
              data-entity-type="sale"
              data-entity-id="${x.sale_id}"
              ${isChecked ? "checked" : ""}
            >
          </div>
          <div class="col-desc">
            <span class="flag">${escapeHtml(x.flag || "")}</span>
            <span class="desc">${escapeHtml(x.desc)}</span>
          </div>
          <div class="col-badges">${badges.join("")}</div>
          <div class="col-amt">${amt}</div>
          <div class="col-actions">
            <button type="button" class="btn btn-sm btn-light btn-row-menu">...</button>
          </div>
        </div>
      `;
    }).join("");

    if (totalEl) {
      const tot = rows.reduce((s, x) => s + (x.direction === "out" ? -x.amount : x.amount), 0);
      totalEl.textContent = formatFilteredTotal(tot, hasActiveSaleFilters());
    }

  } catch (e) {
    console.error("loadIncassi error:", e);
    listEl.innerHTML = `<div class="list-group-item text-muted small">Errore di rete</div>`;
  }
}

async function loadSpese(dayStr) {
  const listEl = document.getElementById("speseList");
  const totalEl = document.getElementById("totSpese");
  if (!listEl) return;

  listEl.innerHTML = `<div class="list-group-item text-muted small">Caricamento...</div>`;
  if (totalEl) totalEl.textContent = formatFilteredTotal(0, hasActiveExpenseFilters());

  try {
    const [expensesRes, checksMap] = await Promise.all([
      fetch(`/cassa/api/day/${dayStr}/expenses`, { credentials: "same-origin" }),
      fetchRowChecks(Number(document.getElementById("dayId")?.textContent || 0), "expense")
    ]);

    const data = await expensesRes.json();

    if (!data.ok) {
      listEl.innerHTML = `<div class="list-group-item text-muted small">Errore: ${data.error || "impossibile caricare spese"}</div>`;
      return;
    }

    const expenses = data.expenses || [];
    if (!expenses.length) {
      lastExpenseRows = [];
      listEl.innerHTML = `<div class="list-group-item text-muted small">Nessuna spesa</div>`;
      if (totalEl) totalEl.textContent = formatFilteredTotal(0, hasActiveExpenseFilters());
      return;
    }

    const allRows = [];
    for (const e of expenses) {
      for (const p of (e.payments || [])) {
        let desc = [e.supplier, (p.description || e.notes || "")].filter(Boolean).join(" - ");
        if (p.method === "check" && p.issued_check_flag === "**" && p.due_date) {
          desc = [desc, `scad. ${formatDateIT(p.due_date)}`].filter(Boolean).join(" - ");
        }

        allRows.push({
          expense_id: e.id,
          storage: e.storage || "az",
          is_checked: !!e.is_checked,
          created_at: p.created_at || e.created_at,
          flag: p.flag || "",
          desc,
          amount: Number(p.amount || 0),
          direction: p.direction || "out",
          method: p.method || "",
          off_cash: !!p.off_cash,
          issued_check_flag: p.issued_check_flag || "",
          due_date: p.due_date || "",
        });
      }
    }

    lastExpenseRows = allRows;
    const rows = applyExpenseFilters(allRows);

    if (!rows.length) {
      listEl.innerHTML = `<div class="list-group-item text-muted small">Nessuna spesa per filtro</div>`;
      if (totalEl) totalEl.textContent = formatFilteredTotal(0, true);
      return;
    }

    if (totalEl) {
      const tot = rows.reduce((s, x) => s + (x.direction === "out" ? x.amount : -x.amount), 0);
      totalEl.textContent = formatFilteredTotal(tot, hasActiveExpenseFilters());
    }

    listEl.innerHTML = rows.map(x => {
      const amt = `${x.amount.toFixed(2)}€`;

      const badges = [];
      if (x.method === "pos") badges.push(`<span class="badge badge-soft badge-pos">POS</span>`);
      if (x.method === "bank") badges.push(`<span class="badge badge-soft badge-bank">BANCA</span>`);
      if (x.method === "check") badges.push(`<span class="badge badge-soft badge-bank">ASSEGNO</span>`);
      if (x.method === "check" && x.issued_check_flag === "**" && x.due_date) {
        badges.push(`<span class="badge badge-soft badge-bank">SCAD. ${escapeHtml(formatDateIT(x.due_date))}</span>`);
      }
      if (x.off_cash) badges.push(`<span class="badge badge-soft badge-offcash">FUORI CASSA</span>`);

      const isChecked = x.storage === "pri"
        ? !!x.is_checked
        : checksMap.get(String(x.expense_id)) === true;

      return `
        <div
          class="list-group-item table-row expense-row ${isChecked ? "row-checked" : ""}"
          data-expense-id="${x.expense_id}"
          data-expense-method="${escapeHtml(x.method || "")}"
          data-expense-flag="${escapeHtml(x.flag || "")}"
          data-expense-off-cash="${x.off_cash ? "1" : "0"}"
        >
          <div class="col-check me-2">
            <input
              type="checkbox"
              class="form-check-input expense-row-check"
              data-entity-type="expense"
              data-entity-id="${x.expense_id}"
              ${isChecked ? "checked" : ""}
            >
          </div>
          <div class="col-desc">
            <span class="flag">${escapeHtml(x.flag || "")}</span>
            <span class="desc">${escapeHtml(x.desc)}</span>
          </div>
          <div class="col-badges">${badges.join("")}</div>
          <div class="col-amt">${amt}</div>
          <div class="col-actions">
            <button type="button" class="btn btn-sm btn-light btn-row-menu">...</button>
          </div>
        </div>
      `;
    }).join("");

  } catch (e) {
    console.error("loadSpese error:", e);
    listEl.innerHTML = `<div class="list-group-item text-muted small">Errore di rete</div>`;
  }
}

async function fetchRowChecks(cashDayId, entityType) {
  if (!cashDayId || !entityType) return new Map();

  try {
    const r = await fetch(
      `/cassa/api/row-checks?cash_day_id=${encodeURIComponent(cashDayId)}&entity_type=${encodeURIComponent(entityType)}`,
      {
        credentials: "same-origin",
        headers: { "Accept": "application/json" },
        cache: "no-store"
      }
    );

    const data = await r.json();

    if (!r.ok || !data.ok) {
      return new Map();
    }

    return new Map(
      (data.checks || []).map(row => [String(row.entity_id), !!row.is_checked])
    );
  } catch (err) {
    console.error("fetchRowChecks error:", err);
    return new Map();
  }
}

async function toggleRowCheck(entityType, entityId, cashDayId, isChecked) {
  const r = await fetch("/cassa/api/row-check/toggle", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Accept": "application/json"
    },
    credentials: "same-origin",
    body: JSON.stringify({
      entity_type: entityType,
      entity_id: entityId,
      cash_day_id: cashDayId,
      is_checked: isChecked
    })
  });

  const data = await r.json();

  if (!data || data.ok !== true) {
    throw new Error(data?.error || "Errore toggle check");
  }

  return data;
}

async function loadPosMoves(dayStr) {
  const listEl = document.getElementById("posList");
  const totalEl = document.getElementById("totPos");
  if (!listEl) return;

  listEl.innerHTML = `<div class="list-group-item text-muted small">Caricamento...</div>`;
  if (totalEl) totalEl.textContent = formatPosTotal(0, hasActivePosFilters());

  try {
    const [movesRes, checksMap] = await Promise.all([
      fetch(`/cassa/api/day/${dayStr}/pos_moves`, { credentials: "same-origin" }),
      fetchRowChecks(Number(document.getElementById("dayId")?.textContent || 0), "pos_move")
    ]);

    const data = await movesRes.json();

    if (!data.ok) {
      listEl.innerHTML = `<div class="list-group-item text-muted small">Errore: ${data.error || "impossibile caricare POS"}</div>`;
      return;
    }

    const moves = data.pos_moves || [];
    lastPosMoves = moves;
    const visibleMoves = applyPosFilters(moves);
    if (!moves.length) {
      listEl.innerHTML = `<div class="list-group-item text-muted small">Nessun POS</div>`;
      return;
    }

    if (!visibleMoves.length) {
      listEl.innerHTML = `<div class="list-group-item text-muted small">Nessun POS per filtro</div>`;
      if (totalEl) totalEl.textContent = formatPosTotal(0, true);
      return;
    }

    const tot = visibleMoves.reduce((s, m) => {
      const a = Number(m.amount || 0);
      return s + (m.direction === "in" ? a : -a);
    }, 0);

    if (totalEl) totalEl.textContent = formatPosTotal(tot, hasActivePosFilters());

    listEl.innerHTML = visibleMoves.map(m => {
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
      const isChecked = checksMap.get(String(m.id)) === true;

      return `
        <div
          class="list-group-item table-row pos-row ${isChecked ? "row-checked" : ""}"
          data-pos-move-id="${m.id}"
          data-pos-device-id="${m.pos_device_id || ""}"
          data-pos-device-name="${escapeHtml(devName)}"
          data-pos-circuit-id="${m.pos_circuit_id || ""}"
          data-pos-circuit-name="${escapeHtml(circuitLabel)}"
        >
          <div class="col-check me-2">
            <input
              type="checkbox"
              class="form-check-input pos-row-check"
              data-entity-type="pos_move"
              data-entity-id="${m.id}"
              ${isChecked ? "checked" : ""}
            >
          </div>
          <div class="col-desc">
            <span class="flag"></span>
            <span class="desc">${desc}</span>
          </div>
          <div class="col-badges">${badge}</div>
          <div class="col-amt">${amt}</div>
          <div class="col-actions">
            <button class="btn btn-sm btn-light btn-row-menu">...</button>
          </div>
        </div>
      `;
    }).join("");

  } catch (e) {
    console.error(e);
    listEl.innerHTML = `<div class="list-group-item text-muted small">Errore di rete</div>`;
  }
}

function hasActivePosFilters() {
  return !!(posFilters.deviceId || posFilters.circuitId);
}

function applyPosFilters(moves) {
  return (moves || []).filter(m => {
    if (posFilters.deviceId === "__none__" && m.pos_device_id) {
      return false;
    }
    if (posFilters.deviceId && posFilters.deviceId !== "__none__" && String(m.pos_device_id || "") !== String(posFilters.deviceId)) {
      return false;
    }
    if (posFilters.circuitId === "__none__" && m.pos_circuit_id) {
      return false;
    }
    if (posFilters.circuitId && posFilters.circuitId !== "__none__" && String(m.pos_circuit_id || "") !== String(posFilters.circuitId)) {
      return false;
    }
    return true;
  });
}

function getPosFilterOptionMoves(kind) {
  return (lastPosMoves || []).filter(m => {
    if (kind !== "device") {
      if (posFilters.deviceId === "__none__" && m.pos_device_id) return false;
      if (posFilters.deviceId && posFilters.deviceId !== "__none__" && String(m.pos_device_id || "") !== String(posFilters.deviceId)) {
        return false;
      }
    }

    if (kind !== "circuit") {
      if (posFilters.circuitId === "__none__" && m.pos_circuit_id) return false;
      if (posFilters.circuitId && posFilters.circuitId !== "__none__" && String(m.pos_circuit_id || "") !== String(posFilters.circuitId)) {
        return false;
      }
    }

    return true;
  });
}

function uniquePosFilterOptions(kind) {
  const seen = new Map();
  const moves = getPosFilterOptionMoves(kind);

  for (const m of moves) {
    const id = kind === "device" ? m.pos_device_id : m.pos_circuit_id;
    if (!id) continue;

    const fallback = kind === "device" ? `POS ${id}` : "Circuito";
    const name = kind === "device"
      ? (m.pos_device_name || fallback)
      : (m.pos_circuit_name || fallback);

    if (!seen.has(String(id))) {
      seen.set(String(id), name);
    }
  }

  return Array.from(seen.entries())
    .map(([id, name]) => ({ id, name }))
    .sort((a, b) => a.name.localeCompare(b.name, "it"));
}

function formatPosTotal(total, filtered = false) {
  const text = formatEuro2(total);
  return filtered ? `(${text})` : text;
}

async function refreshPosAfterFilterChange() {
  if (!currentDay) return;
  await loadPosMoves(currentDay);
}

async function setPosDeviceFilter(value, label = "") {
  posFilters.deviceId = value || null;
  posFilters.deviceName = value ? label : "";

  await refreshPosAfterFilterChange();
}

async function setPosCircuitFilter(value, label = "") {
  posFilters.circuitId = value || null;
  posFilters.circuitName = value ? label : "";

  await refreshPosAfterFilterChange();
}

async function clearPosFilters() {
  posFilters = {
    deviceId: null,
    deviceName: "",
    circuitId: null,
    circuitName: ""
  };

  await refreshPosAfterFilterChange();
}

function formatFilteredTotal(total, filtered = false) {
  const text = formatEuro2(total);
  return filtered ? `(${text})` : text;
}

function paymentMethodLabel(method) {
  const value = String(method || "").trim();
  const labels = {
    cash: "Contanti",
    pos: "POS",
    bank: "Banca",
    check: "Assegno"
  };
  return labels[value] || (value ? value : "Nessuno");
}

function cashMoveKindLabel(kind) {
  const value = String(kind || "altro").trim() || "altro";
  const labels = {
    altro: "Movimento di cassa",
    spicci: "Spicci",
    incasso: "Incasso"
  };
  return labels[value] || value;
}

function cashMoveDirectionLabel(direction) {
  return String(direction || "").trim() === "out" ? "PRELIEVO" : "VERSAMENTO";
}

function hasActiveSaleFilters() {
  return !!(saleFilters.method || saleFilters.flag || saleFilters.cashScope);
}

function hasActiveExpenseFilters() {
  return !!(expenseFilters.method || expenseFilters.flag || expenseFilters.cashScope);
}

function hasActiveCashMoveFilters() {
  return !!(cashMoveFilters.kind || cashMoveFilters.direction);
}

function applyPaymentFilters(rows, filters) {
  return (rows || []).filter(row => {
    if (filters.method === "__none__" && row.method) return false;
    if (filters.method && filters.method !== "__none__" && String(row.method || "") !== String(filters.method)) return false;

    if (filters.flag === "__none__" && row.flag) return false;
    if (filters.flag && filters.flag !== "__none__" && String(row.flag || "") !== String(filters.flag)) return false;

    if (filters.cashScope === "in_cash" && row.off_cash) return false;
    if (filters.cashScope === "off_cash" && !row.off_cash) return false;

    return true;
  });
}

function applySaleFilters(rows) {
  return applyPaymentFilters(rows, saleFilters);
}

function applyExpenseFilters(rows) {
  return applyPaymentFilters(rows, expenseFilters);
}

function applyCashMoveFilters(rows) {
  return (rows || []).filter(row => {
    const kind = String(row.kind || "altro");
    const direction = String(row.direction || "");

    if (cashMoveFilters.kind && kind !== cashMoveFilters.kind) return false;
    if (cashMoveFilters.direction && direction !== cashMoveFilters.direction) return false;

    return true;
  });
}

function uniquePaymentFilterOptions(rows, kind, filters) {
  const seen = new Map();
  const filteredRows = applyPaymentFilters(rows || [], {
    method: kind === "method" ? null : filters.method,
    flag: kind === "flag" ? null : filters.flag,
    cashScope: kind === "cashScope" ? null : filters.cashScope
  });

  for (const row of filteredRows) {
    const value = kind === "method" ? row.method : row.flag;
    if (!value) continue;

    const label = kind === "method" ? paymentMethodLabel(value) : value;
    if (!seen.has(String(value))) {
      seen.set(String(value), label);
    }
  }

  return Array.from(seen.entries())
    .map(([value, label]) => ({ value, label }))
    .sort((a, b) => a.label.localeCompare(b.label, "it"));
}

function uniqueCashMoveFilterOptions(kind) {
  const seen = new Map();
  const filteredRows = (lastCashMoveRows || []).filter(row => {
    const rowKind = String(row.kind || "altro");
    const rowDirection = String(row.direction || "");

    if (kind !== "kind" && cashMoveFilters.kind && rowKind !== cashMoveFilters.kind) return false;
    if (kind !== "direction" && cashMoveFilters.direction && rowDirection !== cashMoveFilters.direction) return false;

    return true;
  });

  for (const row of filteredRows) {
    const value = kind === "kind"
      ? String(row.kind || "altro")
      : String(row.direction || "");
    if (!value) continue;

    const label = kind === "kind" ? cashMoveKindLabel(value) : cashMoveDirectionLabel(value);
    if (!seen.has(String(value))) {
      seen.set(String(value), label);
    }
  }

  return Array.from(seen.entries())
    .map(([value, label]) => ({ value, label }))
    .sort((a, b) => a.label.localeCompare(b.label, "it"));
}

async function refreshSaleAfterFilterChange() {
  if (!currentDay) return;
  await loadIncassi(currentDay);
}

async function refreshExpenseAfterFilterChange() {
  if (!currentDay) return;
  await loadSpese(currentDay);
}

async function refreshCashMoveAfterFilterChange() {
  if (!currentDay) return;
  await loadCashMoves(currentDay);
}

async function setSaleFilter(kind, value) {
  saleFilters[kind] = value || null;
  await refreshSaleAfterFilterChange();
}

async function setExpenseFilter(kind, value) {
  expenseFilters[kind] = value || null;
  await refreshExpenseAfterFilterChange();
}

async function setCashMoveFilter(kind, value) {
  cashMoveFilters[kind] = value || null;
  await refreshCashMoveAfterFilterChange();
}

async function clearSaleFilters() {
  saleFilters = { method: null, flag: null, cashScope: null };
  await refreshSaleAfterFilterChange();
}

async function clearExpenseFilters() {
  expenseFilters = { method: null, flag: null, cashScope: null };
  await refreshExpenseAfterFilterChange();
}

async function clearCashMoveFilters() {
  cashMoveFilters = { kind: null, direction: null };
  await refreshCashMoveAfterFilterChange();
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
      loadAssegniRientranti(currentDay);
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

function todayYmd() {
  return toLocalYMD(new Date());
}

function renderCheckStatusOptions() {
  if (checkStatus) {
    checkStatus.innerHTML = checkStatusOptions
      .map(item => `<option value="${escapeHtml(item.value)}">${escapeHtml(item.label)}</option>`)
      .join("");
  }

  if (checksFilterStatus) {
    const currentValue = checksFilterStatus.value || "in_pancia";
    checksFilterStatus.innerHTML = `
      <option value="in_pancia">In pancia</option>
      <option value="">Tutti</option>
      ${checkStatusOptions.map(item => `<option value="${escapeHtml(item.value)}">${escapeHtml(item.label)}</option>`).join("")}
    `;
    checksFilterStatus.value = currentValue;
  }
}

function resetCheckForm() {
  if (checkEditId) checkEditId.value = "";
  if (checkCustomerId) checkCustomerId.value = "";
  if (checkCustomerLabel) checkCustomerLabel.value = "";
  if (checkBankName) checkBankName.value = "";
  if (checkNumber) checkNumber.value = "";
  if (checkAbi) checkAbi.value = "";
  if (checkCab) checkCab.value = "";
  if (checkAmount) checkAmount.value = "0,00";
  if (checkStatus) checkStatus.value = "received";
  if (checkReceivedDate) checkReceivedDate.value = currentDay || todayYmd();
  if (checkDueDate) checkDueDate.value = currentDay || todayYmd();
  if (checkNote) checkNote.value = "";
  if (checkSaveBtn) checkSaveBtn.textContent = "Salva assegno";
}

function renderChecksStatusBar(summary = {}) {
  if (!checksStatusBar) return;

  const inPancia = summary.in_pancia || {};
  const deposited = summary.deposited || {};
  const bounced = summary.bounced_protested || {};

  checksStatusBar.innerHTML = `
    <span class="badge text-bg-light border">In pancia: ${eur(inPancia.amount || 0)} (${Number(inPancia.count || 0)})</span>
    <span class="badge text-bg-light border">Versati: ${eur(deposited.amount || 0)} (${Number(deposited.count || 0)})</span>
    <span class="badge text-bg-light border">Insoluti/protestati: ${eur(bounced.amount || 0)} (${Number(bounced.count || 0)})</span>
  `;
}

async function loadChecksManagement() {
  if (!checksManagementRows) return;

  const qs = new URLSearchParams();
  if (checksFilterText?.value) qs.set("q", checksFilterText.value.trim());
  if (checksFilterStatus?.value) qs.set("status", checksFilterStatus.value);
  if (checksFilterFrom?.value) qs.set("from", checksFilterFrom.value);
  if (checksFilterTo?.value) qs.set("to", checksFilterTo.value);

  checksManagementRows.innerHTML = `<tr><td colspan="8" class="text-center text-muted">Caricamento...</td></tr>`;

  try {
    const r = await fetch(`/cassa/api/checks?${qs.toString()}`, {
      credentials: "same-origin",
      headers: { "Accept": "application/json" },
      cache: "no-store"
    });
    const data = await r.json();

    if (!r.ok || !data.ok) {
      checksManagementRows.innerHTML = `<tr><td colspan="8" class="text-center text-danger">${escapeHtml(data.error || "Errore caricamento assegni")}</td></tr>`;
      return;
    }

    if (Array.isArray(data.statuses) && data.statuses.length) {
      checkStatusOptions = data.statuses;
      renderCheckStatusOptions();
    }

    renderChecksStatusBar(data.summary || {});

    const checks = data.checks || [];
    if (!checks.length) {
      checksManagementRows.innerHTML = `<tr><td colspan="8" class="text-center text-muted">Nessun assegno trovato</td></tr>`;
      return;
    }

    checksManagementRows.innerHTML = checks.map(row => `
      <tr data-check-id="${row.id}">
        <td>${escapeHtml(row.customer_display_name || "")}</td>
        <td>${escapeHtml(row.bank_name || "")}</td>
        <td>${escapeHtml(row.check_number || "")}</td>
        <td>${escapeHtml(formatDateIT(row.received_date))}</td>
        <td>${escapeHtml(formatDateIT(row.due_date))}</td>
        <td>${escapeHtml(row.status_label || row.status || "")}</td>
        <td class="text-end">${formatEuro2(row.amount || 0)}</td>
        <td class="text-end">
          <button type="button" class="btn btn-sm btn-outline-secondary btn-check-edit" data-row='${escapeHtml(JSON.stringify(row))}'>Modifica</button>
          <button type="button" class="btn btn-sm btn-outline-danger btn-check-delete" data-id="${row.id}">Elimina</button>
        </td>
      </tr>
    `).join("");
  } catch (err) {
    console.error("loadChecksManagement error:", err);
    checksManagementRows.innerHTML = `<tr><td colspan="8" class="text-center text-danger">Errore di rete</td></tr>`;
  }
}

function startEditCheck(row) {
  if (checkEditId) checkEditId.value = row.id || "";
  if (checkCustomerId) checkCustomerId.value = row.customer_id || "";
  if (checkCustomerLabel) checkCustomerLabel.value = row.customer_display_name || "";
  if (checkBankName) checkBankName.value = row.bank_name || "";
  if (checkNumber) checkNumber.value = row.check_number || "";
  if (checkAbi) checkAbi.value = row.abi || "";
  if (checkCab) checkCab.value = row.cab || "";
  if (checkAmount) checkAmount.value = formatEuro2(row.amount || 0);
  if (checkStatus) checkStatus.value = row.status || "received";
  if (checkReceivedDate) checkReceivedDate.value = row.received_date || todayYmd();
  if (checkDueDate) checkDueDate.value = row.due_date || todayYmd();
  if (checkNote) checkNote.value = row.note || "";
  if (checkSaveBtn) checkSaveBtn.textContent = "Salva modifica";
}

async function saveManagedCheck() {
  const id = (checkEditId?.value || "").trim();
  const payload = {
    customer_id: (checkCustomerId?.value || "").trim() || null,
    customer_label: (checkCustomerLabel?.value || "").trim(),
    bank_name: (checkBankName?.value || "").trim(),
    check_number: (checkNumber?.value || "").trim(),
    abi: (checkAbi?.value || "").trim(),
    cab: (checkCab?.value || "").trim(),
    amount: parseEuroToNumber(checkAmount?.value || "0"),
    status: checkStatus?.value || "received",
    received_date: checkReceivedDate?.value || "",
    due_date: checkDueDate?.value || "",
    note: (checkNote?.value || "").trim(),
  };

  const url = id ? `/cassa/api/checks/${id}` : "/cassa/api/checks";
  const method = id ? "PUT" : "POST";

  try {
    if (checkSaveBtn) checkSaveBtn.disabled = true;
    const r = await fetch(url, {
      method,
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/json"
      },
      body: JSON.stringify(payload)
    });
    const data = await r.json();

    if (!r.ok || !data.ok) {
      alert(data.error || "Errore salvataggio assegno");
      return;
    }

    resetCheckForm();
    await loadChecksManagement();
    if (currentDay) {
      await refreshAgendaSections(["preview", "incassi", "assegni"]);
    }
  } catch (err) {
    console.error("saveManagedCheck error:", err);
    alert("Errore di rete durante il salvataggio assegno");
  } finally {
    if (checkSaveBtn) checkSaveBtn.disabled = false;
  }
}

async function deleteManagedCheck(checkId) {
  if (!checkId) return;
  if (!window.confirm("Vuoi eliminare questo assegno?")) return;

  try {
    const r = await fetch(`/cassa/api/checks/${checkId}`, {
      method: "DELETE",
      credentials: "same-origin",
      headers: { "Accept": "application/json" }
    });
    const data = await r.json();
    if (!r.ok || !data.ok) {
      alert(data.error || "Errore eliminazione assegno");
      return;
    }
    await loadChecksManagement();
    if (currentDay) {
      await refreshAgendaSections(["preview", "incassi", "assegni"]);
    }
  } catch (err) {
    console.error("deleteManagedCheck error:", err);
    alert("Errore di rete durante l'eliminazione assegno");
  }
}

async function openChecksManagementModal() {
  renderCheckStatusOptions();
  resetCheckForm();
  if (!checksManagementModal) {
    alert("Modale gestione assegni non disponibile.");
    return;
  }
  checksManagementModal.show();
  await loadChecksManagement();
}

function renderIssuedCheckStatusOptions() {
  const options = issuedCheckStatusOptions
    .map(item => `<option value="${escapeHtml(item.value)}">${escapeHtml(item.label)}</option>`)
    .join("");

  if (issuedCheckStatus) issuedCheckStatus.innerHTML = options;

  if (issuedChecksFilterStatus) {
    const currentValue = issuedChecksFilterStatus.value || "";
    issuedChecksFilterStatus.innerHTML = `<option value="">Tutti</option>${options}`;
    issuedChecksFilterStatus.value = currentValue;
  }
}

function resetIssuedCheckForm() {
  if (issuedCheckEditId) issuedCheckEditId.value = "";
  if (issuedCheckFlag) issuedCheckFlag.value = "*";
  if (issuedCheckBankSelect) issuedCheckBankSelect.value = "";
  if (issuedCheckNumber) issuedCheckNumber.value = "";
  if (issuedCheckAmount) issuedCheckAmount.value = "0,00";
  if (issuedCheckDueDate) issuedCheckDueDate.value = "";
  if (issuedCheckStatus) issuedCheckStatus.value = "emesso";
  if (issuedCheckNote) issuedCheckNote.value = "";
}

async function loadIssuedChecksManagement() {
  if (!issuedChecksManagementRows) return;

  const qs = new URLSearchParams();
  if (issuedChecksFilterText?.value) qs.set("q", issuedChecksFilterText.value.trim());
  if (issuedChecksFilterStatus?.value) qs.set("status", issuedChecksFilterStatus.value);
  if (issuedChecksFilterFlag?.value) qs.set("flag", issuedChecksFilterFlag.value);
  if (issuedChecksFilterFrom?.value) qs.set("from", issuedChecksFilterFrom.value);
  if (issuedChecksFilterTo?.value) qs.set("to", issuedChecksFilterTo.value);

  issuedChecksManagementRows.innerHTML = `<tr><td colspan="8" class="text-center text-muted">Caricamento...</td></tr>`;

  try {
    const r = await fetch(`/cassa/api/issued-checks?${qs.toString()}`, {
      credentials: "same-origin",
      headers: { "Accept": "application/json" },
      cache: "no-store"
    });
    const data = await readJsonResponse(r, "Errore caricamento assegni emessi");

    if (!r.ok || !data.ok) {
      issuedChecksManagementRows.innerHTML = `<tr><td colspan="8" class="text-center text-danger">${escapeHtml(data.error || "Errore caricamento assegni emessi")}</td></tr>`;
      return;
    }

    if (Array.isArray(data.statuses) && data.statuses.length) {
      issuedCheckStatusOptions = data.statuses;
      renderIssuedCheckStatusOptions();
    }

    const rows = data.checks || [];
    if (!rows.length) {
      issuedChecksManagementRows.innerHTML = `<tr><td colspan="8" class="text-center text-muted">Nessun assegno emesso trovato</td></tr>`;
      return;
    }

    issuedChecksManagementRows.innerHTML = rows.map(row => `
      <tr data-issued-check-id="${row.id}">
        <td>${escapeHtml(row.supplier || "")}</td>
        <td>${escapeHtml(row.flag || "")}</td>
        <td>${escapeHtml(row.bank_name || "")}</td>
        <td>${escapeHtml(row.check_number || "")}</td>
        <td>${escapeHtml(formatDateIT(row.due_date))}</td>
        <td>${escapeHtml(row.status_label || row.status || "")}</td>
        <td class="text-end">${formatEuro2(row.amount || 0)}</td>
        <td class="text-end">
          <button type="button" class="btn btn-sm btn-outline-secondary btn-issued-check-edit" data-row='${escapeHtml(JSON.stringify(row))}'>Modifica</button>
          <button type="button" class="btn btn-sm btn-outline-danger btn-issued-check-delete" data-id="${row.id}">Elimina</button>
        </td>
      </tr>
    `).join("");
  } catch (err) {
    console.error("loadIssuedChecksManagement error:", err);
    issuedChecksManagementRows.innerHTML = `<tr><td colspan="8" class="text-center text-danger">Errore di rete</td></tr>`;
  }
}

async function startEditIssuedCheck(row) {
  if (issuedCheckEditId) issuedCheckEditId.value = row.id || "";
  if (issuedCheckFlag) issuedCheckFlag.value = row.flag || "*";
  await loadBanks(issuedCheckBankSelect);
  if (issuedCheckBankSelect) issuedCheckBankSelect.value = String(row.bank_id || "");
  if (issuedCheckNumber) issuedCheckNumber.value = row.check_number || "";
  if (issuedCheckAmount) issuedCheckAmount.value = formatEuro2(row.amount || 0);
  if (issuedCheckDueDate) issuedCheckDueDate.value = row.due_date || "";
  if (issuedCheckStatus) issuedCheckStatus.value = row.status || "emesso";
  if (issuedCheckNote) issuedCheckNote.value = row.description || "";
}

async function saveIssuedCheck() {
  const id = (issuedCheckEditId?.value || "").trim();
  if (!id) {
    alert("Seleziona un assegno emesso da modificare.");
    return;
  }

  const payload = {
    flag: issuedCheckFlag?.value || "*",
    bank_id: Number(issuedCheckBankSelect?.value || 0),
    check_number: (issuedCheckNumber?.value || "").trim(),
    amount: parseEuroToNumber(issuedCheckAmount?.value || "0"),
    due_date: issuedCheckDueDate?.value || "",
    status: issuedCheckStatus?.value || "emesso",
    note: (issuedCheckNote?.value || "").trim(),
  };

  try {
    if (issuedCheckSaveBtn) issuedCheckSaveBtn.disabled = true;
    const r = await fetch(`/cassa/api/issued-checks/${id}`, {
      method: "PUT",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/json"
      },
      body: JSON.stringify(payload)
    });
    const data = await r.json();
    if (!r.ok || !data.ok) {
      alert(data.error || "Errore salvataggio assegno emesso");
      return;
    }

    resetIssuedCheckForm();
    await loadIssuedChecksManagement();
    await refreshAgendaSections(["preview", "spese", "assegni_rientranti"]);
  } catch (err) {
    console.error("saveIssuedCheck error:", err);
    alert("Errore di rete durante il salvataggio assegno emesso");
  } finally {
    if (issuedCheckSaveBtn) issuedCheckSaveBtn.disabled = false;
  }
}

async function deleteIssuedCheck(checkId) {
  if (!checkId) return;
  if (!window.confirm("Vuoi eliminare questo assegno emesso?")) return;

  try {
    const r = await fetch(`/cassa/api/issued-checks/${checkId}`, {
      method: "DELETE",
      credentials: "same-origin",
      headers: { "Accept": "application/json" }
    });
    const data = await r.json();
    if (!r.ok || !data.ok) {
      alert(data.error || "Errore eliminazione assegno emesso");
      return;
    }
    await loadIssuedChecksManagement();
    await refreshAgendaSections(["preview", "spese", "assegni_rientranti"]);
  } catch (err) {
    console.error("deleteIssuedCheck error:", err);
    alert("Errore di rete durante l'eliminazione assegno emesso");
  }
}

async function openIssuedChecksManagementModal() {
  renderIssuedCheckStatusOptions();
  resetIssuedCheckForm();

  if (!issuedChecksManagementModal) {
    const modalEl = document.getElementById("issuedChecksManagementModal");
    if (modalEl && window.bootstrap?.Modal) {
      issuedChecksManagementModal = bootstrap.Modal.getOrCreateInstance(modalEl);
    }
  }

  if (!issuedChecksManagementModal) {
    console.error("Modale gestione assegni emessi non disponibile.");
    alert("Modale gestione assegni emessi non disponibile.");
    return;
  }

  issuedChecksManagementModal.show();

  try {
    await loadBanks(issuedCheckBankSelect);
    await loadIssuedChecksManagement();
  } catch (err) {
    console.error("openIssuedChecksManagementModal error:", err);
    alert("Errore durante il caricamento degli assegni emessi.");
  }
}

/* =========================
   INIT
========================= */

document.addEventListener("DOMContentLoaded", async function () {
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

  await refreshPrivateVaultStatus().catch(err => {
    console.error("initial vault status error:", err);
  });

  btnOpenPosModal?.addEventListener("click", async () => {
    await openPosModal();
  });

  document.getElementById("agendaDayHeader")?.addEventListener("click", async () => {
    await togglePrivateVault();
  });

  btnOpenCashMoveModal?.addEventListener("click", async () => {
    await openCashMoveModal();
  });

  btnOpenSpicciModal?.addEventListener("click", async () => {
    await openSpicciModal();
  });

  posMoveDeviceSelect?.addEventListener("change", async (e) => {
    await loadPosCircuits(e.target.value, posMoveCircuitSelect);
  });

  const kpiEcommerceBox = document.getElementById("kpiEcommerceBox");
  if (kpiEcommerceBox) {
    kpiEcommerceBox.addEventListener("click", () => {
      openEcommerceModal();
    });
  }

  decorateMonth(calendarInstance.currentYear, calendarInstance.currentMonth);
  await loadDay(toLocalYMD(new Date()));
  startAssegniAutoRefresh();

  if (ownerTakeModalEl) {
    ownerTakeModal = new bootstrap.Modal(ownerTakeModalEl);
  }
  if (checksManagementModalEl) {
    checksManagementModal = new bootstrap.Modal(checksManagementModalEl);
  }
  if (issuedChecksManagementModalEl) {
    issuedChecksManagementModal = new bootstrap.Modal(issuedChecksManagementModalEl);
  }

  normalizeCurrencyInput(ownerTakeCashAmountInput);
  normalizeCurrencyInput(checkAmount);
  normalizeCurrencyInput(issuedCheckAmount);

  normalizeCurrencyInput(posMoveAmountInput);
  normalizeCurrencyInput(cashMoveAmountInput);
  normalizeCurrencyInput(spicciMoveAmountInput);

  document.getElementById("kpiCassettoBox")?.addEventListener("click", async () => {
    await refreshPrivateVaultStatus();
    if (!priVaultUnlocked) return;
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

  if (opModalEl) {
    opModalEl.addEventListener("keydown", handleOperationModalKeydown);
    opModalEl.addEventListener("hidden.bs.modal", () => {
      saveBtn?.removeAttribute("disabled");
    });
  }

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
    drawerModalEl.addEventListener("shown.bs.modal", focusDrawerInitialInput);
    drawerModalEl.addEventListener("keydown", handleDrawerModalKeydown);
    drawerModalEl.addEventListener("hidden.bs.modal", () => {
      drawerSaveBtn?.removeAttribute("disabled");
    });
  }

  if (posModalEl) {
    posModal = new bootstrap.Modal(posModalEl);
    posModalEl.addEventListener("shown.bs.modal", focusPosAmountInput);
    posModalEl.addEventListener("keydown", handlePosModalKeydown);
    posModalEl.addEventListener("hidden.bs.modal", () => {
      posMoveSaveBtn?.removeAttribute("disabled");
    });
  }

  if (cashMoveModalEl) {
    cashMoveModal = new bootstrap.Modal(cashMoveModalEl);
    cashMoveModalEl.addEventListener("shown.bs.modal", focusCashMoveAmountInput);
    cashMoveModalEl.addEventListener("keydown", handleCashMoveModalKeydown);
    cashMoveModalEl.addEventListener("hidden.bs.modal", () => {
      cashMoveSaveBtn?.removeAttribute("disabled");
    });
  }

  if (spicciModalEl) {
    spicciModal = new bootstrap.Modal(spicciModalEl);
  }

  if (ecommerceModalEl) {
    ecommerceModal = new bootstrap.Modal(ecommerceModalEl);
    ecommerceModalEl.addEventListener("shown.bs.modal", focusEcommerceAmountInput);
    ecommerceModalEl.addEventListener("keydown", handleEcommerceModalKeydown);
    ecommerceModalEl.addEventListener("hidden.bs.modal", () => {
      ecoAddBtn?.removeAttribute("disabled");
    });
  }

  if (depositModalEl) {
    depositModal = new bootstrap.Modal(depositModalEl);
    depositModalEl.addEventListener("shown.bs.modal", focusDepositAmountInput);
    depositModalEl.addEventListener("keydown", handleDepositModalKeydown);
    depositModalEl.addEventListener("hidden.bs.modal", () => {
      depositAddBtn?.removeAttribute("disabled");
    });
  }

  if (movementSearchCustomerModalEl) {
    movementSearchCustomerModal = new bootstrap.Modal(movementSearchCustomerModalEl);
  }

  if (movementSearchAmountModalEl) {
    movementSearchAmountModal = new bootstrap.Modal(movementSearchAmountModalEl);
  }

  (function initModalStack3D() {
    const BASE_MODAL_Z = 2100;
    const BASE_BACKDROP_Z = 2090;
    const STEP = 20;
    const modalStack = [];

    document.querySelectorAll(".agenda-modal").forEach(modal => {
      if (modal.parentElement !== document.body) {
        document.body.appendChild(modal);
      }
    });

    if (document.body) {
      document.body.style.setProperty("--bs-modal-zindex", String(BASE_MODAL_Z));
      document.body.style.setProperty("--bs-backdrop-zindex", String(BASE_BACKDROP_Z));
    }

    function restack() {
      const modals = modalStack.filter(m => m && m.classList.contains("show") && m.classList.contains("agenda-modal"));
      modals.forEach((m, i) => {
      m.style.setProperty("z-index", String(BASE_MODAL_Z + i * STEP));
      });

      const backdrops = Array.from(document.querySelectorAll(".modal-backdrop"));
      backdrops.forEach((bd, i) => {
        bd.style.setProperty("z-index", String(BASE_BACKDROP_Z));
      });

      modals.forEach((m, i) => {
        const isTop = (i === modals.length - 1);
        m.classList.toggle("modal-underlay", !isTop);
        m.classList.toggle("modal-top", isTop);
      });
    }

    document.addEventListener("shown.bs.modal", event => {
      const modal = event.target;
      if (!modal || !modal.classList || !modal.classList.contains("modal") || !modal.classList.contains("agenda-modal")) return;
      const existing = modalStack.indexOf(modal);
      if (existing !== -1) modalStack.splice(existing, 1);
      modalStack.push(modal);
      restack();
    });

    document.addEventListener("hidden.bs.modal", event => {
      const modal = event.target;
      const idx = modalStack.indexOf(modal);
      if (idx !== -1) modalStack.splice(idx, 1);
      requestAnimationFrame(restack);
    });

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

    input.addEventListener("change", async () => {
      const flag = (input.value || "").trim();

      if (flag !== "x" && flag !== "+") {
        applyPriCarrierRules();            // riabilita tutto
        setPaymentMode(getPaymentMode());
        updatePaymentState();
        return;
      }

      const unlocked = await refreshPrivateVaultStatus();

      if (!unlocked) {
        alert("Funzione non implementata");
        input.value = "*";
        input.dispatchEvent(new Event("change"));
        return;
      }

      // vault aperto: applico regole carrier PRI
      applyPriCarrierRules();
      setPaymentMode(getPaymentMode());
      updatePaymentState();
    });

    if (!input.value) input.value = "*";
    buildMenu("");
  })();

  function getPaymentMode() {
    const checked = document.querySelector('input[name="paymentMode"]:checked');
    return checked?.value || "cash";
  }

  function updateOffCashAvailability(mode) {
    const opOffCash = document.getElementById("opOffCash");
    const opOffCashBox = document.getElementById("opOffCashBox");
    if (!opOffCash) return;

    const canBeOffCash = mode === "cash";

    if (!canBeOffCash) {
      opOffCash.checked = false;
      opOffCash.disabled = true;
      opOffCashBox?.classList.add("d-none");
      return;
    }

    opOffCash.disabled = false;
  }

  function setPaymentMode(mode) {
    const flag = (document.getElementById("opFlag")?.value || "").trim();
    if ((flag === "x" || flag === "+") && mode !== "cash") {
      mode = "cash";
    }
    const target = document.querySelector(`input[name="paymentMode"][value="${mode}"]`);
    if (target) target.checked = true;

    const opType = document.getElementById("opType")?.value || "sale";

    Object.entries(paymentPanels).forEach(([key, panel]) => {
      if (!panel) return;
      panel.classList.add("d-none");
    });

    const saleCheckPanel = document.getElementById("paymentSingleCheckSalePanel");
    const expenseCheckPanel = document.getElementById("paymentSingleCheckExpensePanel");
    const salePosPanel = document.getElementById("paymentSinglePosSalePanel");
    const expensePosPanel = document.getElementById("paymentSinglePosExpensePanel");

    saleCheckPanel?.classList.add("d-none");
    expenseCheckPanel?.classList.add("d-none");
    salePosPanel?.classList.add("d-none");
    expensePosPanel?.classList.add("d-none");

    if (mode === "cash") {
      paymentPanels.cash?.classList.remove("d-none");
    } else if (mode === "bank") {
      paymentPanels.bank?.classList.remove("d-none");
      loadBanks(bankSelect).catch(err => console.error("loadBanks setPaymentMode:", err));
    } else if (mode === "multi") {
      paymentPanels.multi?.classList.remove("d-none");
      if (!multiPaymentsList?.children.length) {
        addMultiPaymentRow();
      }
    } else if (mode === "check") {
      if (opType === "sale") {
        saleCheckPanel?.classList.remove("d-none");
      } else {
        expenseCheckPanel?.classList.remove("d-none");
        loadBanks(document.getElementById("checkExpenseBankSelect")).catch(err => console.error(err));
      }
    } else if (mode === "pos") {
      if (opType === "sale") {
        salePosPanel?.classList.remove("d-none");
        loadPosDevices().catch(err => console.error("loadPosDevices setPaymentMode:", err));
      } else {
        expensePosPanel?.classList.remove("d-none");
      }
    }

    updateOffCashAvailability(mode);
    lastPaymentMode = mode;
  }

  function applyPriCarrierRules() {
    const flag = (document.getElementById("opFlag")?.value || "").trim();
    const isPriFlag = flag === "x" || flag === "+";

    const modesToDisable = ["pos", "bank", "check", "multi"];

    for (const mode of modesToDisable) {
      const input = document.querySelector(`input[name="paymentMode"][value="${mode}"]`);
      if (!input) continue;

      input.disabled = isPriFlag;
      const label = input.closest("label");
      label?.classList.toggle("disabled", isPriFlag);
      label?.classList.toggle("opacity-50", isPriFlag);
    }

    if (isPriFlag && getPaymentMode() !== "cash") {
      setPaymentMode("cash");
    }
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
      "checkBankSelect",
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
    const opType = document.getElementById("opType")?.value || "sale";

    const cashAmount = document.getElementById("cashAmount");
    const posAmount = document.getElementById("posAmount");
    const bankAmount = document.getElementById("bankAmount");
    const checkSaleAmount = document.getElementById("checkSaleAmount");
    const checkExpenseAmount = document.getElementById("checkExpenseAmount");
    const expensePosAmount = document.getElementById("expensePosAmount");

    if (mode === "cash" && cashAmount) cashAmount.value = total;
    if (mode === "pos") {
      if (opType === "expense" && expensePosAmount) {
        expensePosAmount.value = total;
      } else if (posAmount) {
        posAmount.value = total;
      }
    }
    if (mode === "bank" && bankAmount) bankAmount.value = total;

    if (mode === "check") {
      if (opType === "sale" && checkSaleAmount) checkSaleAmount.value = total;
      if (opType === "expense" && checkExpenseAmount) checkExpenseAmount.value = total;
    }
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
      const opType = document.getElementById("opType")?.value || "sale";

      if (opType === "expense") {
        totalPayments = parseEuroToNumber(document.getElementById("expensePosAmount")?.value || "0");
      } else {
        totalPayments = parseEuroToNumber(document.getElementById("posAmount")?.value || "0");
      }
    } else if (mode === "bank") {
      totalPayments = parseEuroToNumber(document.getElementById("bankAmount")?.value || "0");
    } else if (mode === "check") {
      const opType = document.getElementById("opType")?.value || "sale";

      if (opType === "sale") {
        totalPayments = parseEuroToNumber(document.getElementById("checkSaleAmount")?.value || "0");
      } else {
        totalPayments = parseEuroToNumber(document.getElementById("checkExpenseAmount")?.value || "0");
      }
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

  function focusPosAmountInput() {
    if (!posMoveAmountInput) return;
    setTimeout(() => {
      posMoveAmountInput.focus();
      posMoveAmountInput.select();
    }, 0);
  }

  function handlePosModalKeydown(event) {
    if (!posModalEl || !posModalEl.classList.contains("show")) return;

    if (event.key === "Tab" && !event.shiftKey && event.target === posMoveAmountInput && posMoveCircuitSelect) {
      event.preventDefault();
      posMoveCircuitSelect.focus();
      return;
    }

    if (event.key === "Enter") {
      const target = event.target;
      const tagName = String(target?.tagName || "").toLowerCase();
      if (tagName === "textarea" || target?.isContentEditable) return;
      event.preventDefault();
      if (!posMoveSaveBtn?.disabled) {
        savePosMove();
      }
      return;
    }

    if (event.key === "Escape") {
      event.preventDefault();
      if (posModal) {
        posModal.hide();
      }
    }
  }

  function resetPosModalForm() {
    editingPosMoveId = null;

    if (posMoveDateInput) {
      posMoveDateInput.value = currentDay || "";
    }

    if (posMoveTypeSelect) {
      posMoveTypeSelect.value = "incasso";
    }

    if (posMoveAmountInput) {
      posMoveAmountInput.value = "0,00";
    }

    if (posMoveDocRefSelect) {
      posMoveDocRefSelect.value = "CORRISPETTIVO";
    }

    if (posMoveNotesInput) {
      posMoveNotesInput.value = "";
    }

    if (posMoveDeviceSelect) {
      posMoveDeviceSelect.innerHTML = `<option value="">Seleziona...</option>`;
    }

    if (posMoveCircuitSelect) {
      posMoveCircuitSelect.innerHTML = `<option value="">Seleziona...</option>`;
      posMoveCircuitSelect.disabled = true;
    }

    if (posMoveSaveBtn) {
      posMoveSaveBtn.textContent = "Salva";
    }
  }

  async function openPosModal() {
    if (!currentDay) {
      alert("Nessuna giornata selezionata.");
      return;
    }

    resetPosModalForm();

    if (posMoveDateInput) {
      posMoveDateInput.value = currentDay;
    }

    await loadPosDevices(posMoveDeviceSelect, true, posMoveCircuitSelect);

    if (!posModal) {
      alert("Modale POS non disponibile.");
      return;
    }

    posModal.show();
  }

  async function openEditPosModal(posMoveId) {
    if (!currentDay) {
      alert("Nessuna giornata selezionata.");
      return;
    }

    try {
      const r = await fetch(`/cassa/api/day/${currentDay}/pos_moves`, {
        credentials: "same-origin",
        headers: { "Accept": "application/json" },
        cache: "no-store"
      });

      const data = await r.json();

      if (!r.ok || !data.ok) {
        alert(data.error || "Errore caricamento movimento POS");
        return;
      }

      const row = (data.pos_moves || []).find(x => Number(x.id) === Number(posMoveId));
      if (!row) {
        alert("Movimento POS non trovato");
        return;
      }

      resetPosModalForm();
      editingPosMoveId = row.id;

      if (posMoveDateInput) {
        posMoveDateInput.value = currentDay;
      }

      if (posMoveTypeSelect) {
        posMoveTypeSelect.value = row.direction === "out" ? "storno" : "incasso";
      }

      if (posMoveAmountInput) {
        posMoveAmountInput.value = formatEuro2(row.amount || 0);
      }

      if (posMoveDocRefSelect) {
        posMoveDocRefSelect.value = row.doc_ref || "";
      }

      if (posMoveNotesInput) {
        posMoveNotesInput.value = row.notes || "";
      }

      await loadPosDevices(posMoveDeviceSelect, false, posMoveCircuitSelect);

      if (posMoveDeviceSelect) {
        posMoveDeviceSelect.value = String(row.pos_device_id || "");
      }

      await loadPosCircuits(row.pos_device_id, posMoveCircuitSelect);

      if (posMoveCircuitSelect) {
        posMoveCircuitSelect.value = String(row.pos_circuit_id || "");
      }

      if (posMoveSaveBtn) {
        posMoveSaveBtn.textContent = "Salva modifica";
      }

      if (!posModal) {
        alert("Modale POS non disponibile.");
        return;
      }

      posModal.show();

    } catch (err) {
      console.error("openEditPosModal error:", err);
      alert("Errore di rete durante il caricamento del movimento POS.");
    }
  }

  async function savePosMove() {
    if (!currentDay) {
      alert("Nessuna giornata selezionata.");
      return;
    }

    const moveType = (posMoveTypeSelect?.value || "incasso").trim();
    const posDeviceId = Number(posMoveDeviceSelect?.value || 0);
    const posCircuitId = Number(posMoveCircuitSelect?.value || 0);
    const docRef = (posMoveDocRefSelect?.value || "").trim() || null;
    const notes = (posMoveNotesInput?.value || "").trim() || null;

    let amount = parseEuroToNumber(posMoveAmountInput?.value || "0");

    if (amount <= 0) {
      alert("Inserisci un importo valido.");
      return;
    }

    if (!posDeviceId) {
      alert("Seleziona il POS utilizzato.");
      return;
    }

    if (!posCircuitId) {
      alert("Seleziona il circuito.");
      return;
    }

    if (moveType === "storno") {
      amount = -amount;
    }

    const isEdit = !!editingPosMoveId;
    const url = isEdit
      ? `/cassa/api/pos_moves/${editingPosMoveId}`
      : `/cassa/api/day/${currentDay}/pos_moves`;

    const method = isEdit ? "PUT" : "POST";

    try {
      if (posMoveSaveBtn) posMoveSaveBtn.disabled = true;

      const r = await fetch(url, {
        method,
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json"
        },
        credentials: "same-origin",
        body: JSON.stringify({
          pos_device_id: posDeviceId,
          pos_circuit_id: posCircuitId,
          amount: amount,
          doc_ref: docRef,
          notes: notes
        })
      });

      const data = await r.json();

      if (!r.ok || !data.ok) {
        alert(data.error || "Errore salvataggio movimento POS");
        return;
      }

      if (posModal) {
        posModal.hide();
      }

      resetPosModalForm();
      await refreshAgendaSections(["preview", "pos"]);

    } catch (err) {
      console.error("savePosMove error:", err);
      alert("Errore di rete durante il salvataggio del movimento POS.");
    } finally {
      if (posMoveSaveBtn) posMoveSaveBtn.disabled = false;
    }
  }

  function focusCashMoveAmountInput() {
    if (!cashMoveAmountInput) return;
    setTimeout(() => {
      cashMoveAmountInput.focus();
      cashMoveAmountInput.select();
    }, 0);
  }

  function handleCashMoveModalKeydown(event) {
    if (!cashMoveModalEl || !cashMoveModalEl.classList.contains("show")) return;

    if (event.key === "Tab" && !event.shiftKey && event.target === cashMoveAmountInput && cashMovePerformedByInput) {
      event.preventDefault();
      cashMovePerformedByInput.focus();
      cashMovePerformedByInput.select();
      return;
    }

    if (event.key === "Enter") {
      const target = event.target;
      const tagName = String(target?.tagName || "").toLowerCase();
      if (tagName === "textarea" || target?.isContentEditable) return;
      event.preventDefault();
      if (!cashMoveSaveBtn?.disabled) {
        saveCashMove();
      }
      return;
    }

    if (event.key === "Escape") {
      event.preventDefault();
      if (cashMoveModal) {
        cashMoveModal.hide();
      }
    }
  }

  function resetCashMoveModalForm() {
    editingCashMoveId = null;

    if (cashMoveDateInput) cashMoveDateInput.value = currentDay || "";
    if (cashMoveKindSelect) cashMoveKindSelect.value = "prelievo";
    if (cashMoveAmountInput) cashMoveAmountInput.value = "0,00";
    if (cashMovePerformedByInput) cashMovePerformedByInput.value = "";
    if (cashMoveNotesInput) cashMoveNotesInput.value = "";

    if (cashMoveSaveBtn) {
      cashMoveSaveBtn.textContent = "Salva";
    }
  }

  async function openCashMoveModal() {
    if (!currentDay) {
      alert("Nessuna giornata selezionata.");
      return;
    }

    const unlocked = await refreshPrivateVaultStatus();
    if (!unlocked) {
      alert("Attenzione! Funzione ancora non implementata");
      return;
    }

    resetCashMoveModalForm();

    if (cashMoveDateInput) {
      cashMoveDateInput.value = currentDay;
    }

    if (!cashMoveModal) {
      alert("Modale movimenti di cassa non disponibile.");
      return;
    }

    cashMoveModal.show();
  }

  async function openEditCashMoveModal(cashMoveId) {
    if (!currentDay) {
      alert("Nessuna giornata selezionata.");
      return;
    }

    try {
      const r = await fetch(`/cassa/api/day/${currentDay}/cash_moves`, {
        credentials: "same-origin",
        headers: { "Accept": "application/json" },
        cache: "no-store"
      });

      const data = await r.json();

      if (!r.ok || !data.ok) {
        alert(data.error || "Errore caricamento movimento di cassa");
        return;
      }

      const row = (data.cash_moves || []).find(x => String(x.id) === String(cashMoveId));
      if (!row) {
        alert("Movimento di cassa non trovato");
        return;
      }

      resetCashMoveModalForm();
      editingCashMoveId = row.id;

      if (cashMoveDateInput) cashMoveDateInput.value = currentDay;
      if (cashMoveKindSelect) {
        cashMoveKindSelect.value = row.direction === "out" ? "prelievo" : "versamento";
      }
      if (cashMoveAmountInput) {
        cashMoveAmountInput.value = formatEuro2(Math.abs(Number(row.amount || 0)));
      }
      if (cashMovePerformedByInput) cashMovePerformedByInput.value = row.performed_by || "";
      if (cashMoveNotesInput) cashMoveNotesInput.value = row.notes || "";

      if (cashMoveSaveBtn) {
        cashMoveSaveBtn.textContent = "Salva modifica";
      }

      if (!cashMoveModal) {
        alert("Modale movimenti di cassa non disponibile.");
        return;
      }

      cashMoveModal.show();

    } catch (err) {
      console.error("openEditCashMoveModal error:", err);
      alert("Errore di rete durante il caricamento del movimento.");
    }
  }

  async function saveCashMove() {
    if (!currentDay) {
      alert("Nessuna giornata selezionata.");
      return;
    }

    const moveType = (cashMoveKindSelect?.value || "prelievo").trim();
    const performed_by = (cashMovePerformedByInput?.value || "").trim();
    const notes = (cashMoveNotesInput?.value || "").trim() || null;
    const rawAmount = parseEuroToNumber(cashMoveAmountInput?.value || "0");
    const normalizedAmount = Math.abs(rawAmount);

    if (normalizedAmount === 0) {
      alert("Inserisci un importo valido.");
      return;
    }

    if (!performed_by) {
      alert("Inserisci chi esegue il movimento.");
      return;
    }

    const signedAmount = moveType === "prelievo" ? -normalizedAmount : normalizedAmount;

    const isEdit = !!editingCashMoveId;
    const url = isEdit
      ? `/cassa/api/cash_moves/${editingCashMoveId}`
      : `/cassa/api/day/${currentDay}/cash_moves`;

    const method = isEdit ? "PUT" : "POST";

    try {
      if (cashMoveSaveBtn) cashMoveSaveBtn.disabled = true;

      const r = await fetch(url, {
        method,
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json"
        },
        credentials: "same-origin",
        body: JSON.stringify({
          amount: signedAmount,
          performed_by,
          notes,
          kind: "altro"
        })
      });

      const data = await r.json();

      if (!r.ok || !data.ok) {
        alert(data.error || "Errore salvataggio movimento di cassa");
        return;
      }

      if (cashMoveModal) {
        cashMoveModal.hide();
      }

      resetCashMoveModalForm();
      await refreshAgendaSections(["preview", "cash_moves", "coins"]);

    } catch (err) {
      console.error("saveCashMove error:", err);
      alert("Errore di rete durante il salvataggio del movimento.");
    } finally {
      if (cashMoveSaveBtn) cashMoveSaveBtn.disabled = false;
    }
  }

  async function deleteCashMove(cashMoveId) {
    if (!cashMoveId) return;

    const confirmed = window.confirm("Vuoi eliminare questo movimento di cassa?");
    if (!confirmed) return;

    try {
      const r = await fetch(`/cassa/api/cash_moves/${cashMoveId}`, {
        method: "DELETE",
        headers: { "Accept": "application/json" },
        credentials: "same-origin"
      });

      const data = await r.json();

      if (!data || data.ok !== true) {
        alert(data?.error || "Errore eliminazione movimento di cassa");
        return;
      }

      await refreshAgendaSections(["preview", "cash_moves", "coins"]);

    } catch (err) {
      console.error("deleteCashMove error:", err);
      alert("Errore di rete durante l'eliminazione.");
    }
  }

  function resetSpicciModalForm() {
    editingSpicciMoveId = null;

    if (spicciMoveTypeSelect) spicciMoveTypeSelect.value = "prelievo";
    if (spicciMoveAmountInput) spicciMoveAmountInput.value = "0,00";
    if (spicciMovePerformedByInput) spicciMovePerformedByInput.value = "";
    if (spicciMoveNotesInput) spicciMoveNotesInput.value = "";

    if (spicciMoveSaveBtn) {
      spicciMoveSaveBtn.textContent = "Salva";
    }
  }

  async function loadSpicciMoves(dayStr) {
    if (!spicciTableBody) return;

    spicciTableBody.innerHTML = `
      <tr>
        <td colspan="6" class="text-center text-muted">Caricamento...</td>
      </tr>
    `;

    try {
      const r = await fetch(`/cassa/api/day/${dayStr}/cash_moves`, {
        credentials: "same-origin",
        headers: { "Accept": "application/json" },
        cache: "no-store"
      });

      const data = await r.json();

      if (!r.ok || !data.ok) {
        spicciTableBody.innerHTML = `
          <tr>
            <td colspan="6" class="text-center text-danger">
              ${escapeHtml(data.error || "Errore caricamento movimenti spicci")}
            </td>
          </tr>
        `;
        return;
      }

      const rows = (data.cash_moves || []).filter(x => (x.kind || "altro") === "spicci");

      if (!rows.length) {
        spicciTableBody.innerHTML = `
          <tr>
            <td colspan="6" class="text-center text-muted">Nessun movimento spicci</td>
          </tr>
        `;
        return;
      }

      spicciTableBody.innerHTML = rows.map(row => {
        const signedAmount = row.direction === "out"
          ? -Number(row.amount || 0)
          : Number(row.amount || 0);

        return `
          <tr data-spicci-id="${row.id}">
            <td>${formatDateTimeIT(row.created_at)}</td>
            <td>${row.direction === "out" ? "Prelievo" : "Versamento"}</td>
            <td>${escapeHtml(row.performed_by || "")}</td>
            <td>${escapeHtml(row.notes || "")}</td>
            <td class="text-end ${row.direction === "out" ? "text-danger" : "text-primary"}">
              ${formatEuro2(signedAmount)} €
            </td>
            <td class="text-end">
              <button
                type="button"
                class="btn btn-sm btn-outline-secondary btn-spicci-edit"
                data-id="${row.id}">
                Modifica
              </button>
              <button
                type="button"
                class="btn btn-sm btn-outline-danger btn-spicci-delete"
                data-id="${row.id}">
                Elimina
              </button>
            </td>
          </tr>
        `;
      }).join("");

    } catch (err) {
      console.error("loadSpicciMoves error:", err);
      spicciTableBody.innerHTML = `
        <tr>
          <td colspan="6" class="text-center text-danger">Errore di rete</td>
        </tr>
      `;
    }
  }

  async function openSpicciModal() {
    if (!currentDay) {
      alert("Nessuna giornata selezionata.");
      return;
    }

    resetSpicciModalForm();
    await loadSpicciMoves(currentDay);

    if (!spicciModal) {
      alert("Modale spicci non disponibile.");
      return;
    }

    spicciModal.show();
  }

  async function openEditSpicciMove(spicciId) {
    if (!currentDay) {
      alert("Nessuna giornata selezionata.");
      return;
    }

    try {
      const r = await fetch(`/cassa/api/day/${currentDay}/cash_moves`, {
        credentials: "same-origin",
        headers: { "Accept": "application/json" },
        cache: "no-store"
      });

      const data = await r.json();

      if (!r.ok || !data.ok) {
        alert(data.error || "Errore caricamento movimento spicci");
        return;
      }

      const row = (data.cash_moves || []).find(x => Number(x.id) === Number(spicciId) && (x.kind || "altro") === "spicci");
      if (!row) {
        alert("Movimento spicci non trovato");
        return;
      }

      editingSpicciMoveId = row.id;

      if (spicciMoveTypeSelect) {
        spicciMoveTypeSelect.value = row.direction === "out" ? "prelievo" : "versamento";
      }
      if (spicciMoveAmountInput) {
        spicciMoveAmountInput.value = formatEuro2(Math.abs(Number(row.amount || 0)));
      }
      if (spicciMovePerformedByInput) {
        spicciMovePerformedByInput.value = row.performed_by || "";
      }
      if (spicciMoveNotesInput) {
        spicciMoveNotesInput.value = row.notes || "";
      }
      if (spicciMoveSaveBtn) {
        spicciMoveSaveBtn.textContent = "Salva modifica";
      }

    } catch (err) {
      console.error("openEditSpicciMove error:", err);
      alert("Errore di rete durante il caricamento del movimento spicci.");
    }
  }

  async function saveSpicciMove() {
    if (!currentDay) {
      alert("Nessuna giornata selezionata.");
      return;
    }

    const moveType = (spicciMoveTypeSelect?.value || "prelievo").trim();
    const performed_by = (spicciMovePerformedByInput?.value || "").trim();
    const notes = (spicciMoveNotesInput?.value || "").trim() || null;
    const rawAmount = parseEuroToNumber(spicciMoveAmountInput?.value || "0");
    const normalizedAmount = Math.abs(rawAmount);

    if (normalizedAmount === 0) {
      alert("Inserisci un importo valido.");
      return;
    }

    const signedAmount = moveType === "prelievo" ? -normalizedAmount : normalizedAmount;

    const isEdit = !!editingSpicciMoveId;
    const url = isEdit
      ? `/cassa/api/cash_moves/${editingSpicciMoveId}`
      : `/cassa/api/day/${currentDay}/cash_moves`;

    const method = isEdit ? "PUT" : "POST";

    try {
      if (spicciMoveSaveBtn) spicciMoveSaveBtn.disabled = true;

      const r = await fetch(url, {
        method,
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json"
        },
        credentials: "same-origin",
        body: JSON.stringify({
          amount: signedAmount,
          performed_by,
          notes,
          kind: "spicci"
        })
      });

      const data = await r.json();

      if (!r.ok || !data.ok) {
        alert(data.error || "Errore salvataggio movimento spicci");
        return;
      }

      resetSpicciModalForm();
      await loadSpicciMoves(currentDay);
      await loadCashMoves(currentDay);
      await loadCoinsBalance(currentDay);

    } catch (err) {
      console.error("saveSpicciMove error:", err);
      alert("Errore di rete durante il salvataggio del movimento spicci.");
    } finally {
      if (spicciMoveSaveBtn) spicciMoveSaveBtn.disabled = false;
    }
  }

  async function deleteSpicciMove(spicciId) {
    if (!spicciId) return;

    const confirmed = window.confirm("Vuoi eliminare questo movimento spicci?");
    if (!confirmed) return;

    try {
      const r = await fetch(`/cassa/api/cash_moves/${spicciId}`, {
        method: "DELETE",
        headers: { "Accept": "application/json" },
        credentials: "same-origin"
      });

      const data = await r.json();

      if (!r.ok || !data.ok) {
        alert(data.error || "Errore eliminazione movimento spicci");
        return;
      }

      if (editingSpicciMoveId && Number(editingSpicciMoveId) === Number(spicciId)) {
        resetSpicciModalForm();
      }

      await loadSpicciMoves(currentDay);
      await loadCashMoves(currentDay);
      await loadCoinsBalance(currentDay);

    } catch (err) {
      console.error("deleteSpicciMove error:", err);
      alert("Errore di rete durante l'eliminazione del movimento spicci.");
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

  async function loadBanks(selectEl = null, selectedBankId = null) {
    const targetSelect = selectEl || document.getElementById("bankSelect");
    if (!targetSelect) return;

    targetSelect.innerHTML = '<option value="">Seleziona...</option>';

    try {
      const res = await fetch("/cassa/api/banks", {
        credentials: "same-origin",
        headers: { "Accept": "application/json" }
      });

      const data = await res.json();
      if (!data.ok) return;

      let defaultBankId = null;

      data.banks.forEach(b => {
        const opt = document.createElement("option");
        opt.value = String(b.id);
        opt.textContent = b.name;

        if (b.is_default) {
          defaultBankId = String(b.id);
        }

        targetSelect.appendChild(opt);
      });

      const finalValue =
        selectedBankId != null && String(selectedBankId).trim() !== ""
          ? String(selectedBankId)
          : defaultBankId;

      if (finalValue) {
        targetSelect.value = finalValue;
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
    const opType = document.getElementById("opType")?.value || "sale";

    row.querySelectorAll(".multi-pos-sale-fields").forEach(el => el.classList.add("d-none"));
    row.querySelectorAll(".multi-pos-expense-fields").forEach(el => el.classList.add("d-none"));
    row.querySelectorAll(".multi-bank-fields").forEach(el => el.classList.add("d-none"));
    row.querySelectorAll(".multi-check-sale-fields").forEach(el => el.classList.add("d-none"));
    row.querySelectorAll(".multi-check-expense-fields").forEach(el => el.classList.add("d-none"));

    if (method === "pos") {
      if (opType === "expense") {
        row.querySelectorAll(".multi-pos-expense-fields").forEach(el => el.classList.remove("d-none"));
      } else {
        row.querySelectorAll(".multi-pos-sale-fields").forEach(el => el.classList.remove("d-none"));
      }
      return;
    }

    if (method === "bank") {
      row.querySelectorAll(".multi-bank-fields").forEach(el => el.classList.remove("d-none"));
      return;
    }

    if (method === "check") {
      if (opType === "expense") {
        row.querySelectorAll(".multi-check-expense-fields").forEach(el => el.classList.remove("d-none"));
      } else {
        row.querySelectorAll(".multi-check-sale-fields").forEach(el => el.classList.remove("d-none"));
      }
    }
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
    const rowCheckBankSelect = row.querySelector(".multi-check-bank-select");
    const rowCheckExpenseBankSelect = row.querySelector(".multi-check-expense-bank-select");

    if (methodSelect) methodSelect.value = initialMethod;

    normalizeCurrencyInput(amountInput);

    methodSelect?.addEventListener("change", async () => {
      updateMultiRowFields(row);

      const method = methodSelect.value;
      const opType = document.getElementById("opType")?.value || "sale";

      if (method === "pos") {
        if (opType === "sale") {
          await loadPosDevices(rowPosDevice, true, rowPosCircuit);
        }
      } else if (method === "bank") {
        await loadBanks(rowBankSelect);
      } else if (method === "check") {
        if (opType === "expense") {
          const rowCheckBankSelect = row.querySelector(".multi-check-bank-select");
          await loadBanks(rowCheckExpenseBankSelect);
        }
      } else {
        if (rowPosDevice) rowPosDevice.innerHTML = `<option value="">Seleziona...</option>`;
        if (rowPosCircuit) {
          rowPosCircuit.innerHTML = `<option value="">Seleziona...</option>`;
          rowPosCircuit.disabled = true;
        }
        if (rowBankSelect) rowBankSelect.innerHTML = `<option value="">Seleziona...</option>`;

        const rowCheckBankSelect = row.querySelector(".multi-check-bank-select");
        if (rowCheckBankSelect) {
          rowCheckBankSelect.innerHTML = `<option value="">Seleziona...</option>`;
        }
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

    const opType = document.getElementById("opType")?.value || "sale";

    if (initialMethod === "pos") {
      if (opType === "sale") {
        await loadPosDevices(rowPosDevice, true, rowPosCircuit);
      }
    } else if (initialMethod === "bank") {
      await loadBanks(rowBankSelect);
    } else if (initialMethod === "check") {
      if (opType === "expense") {
        await loadBanks(rowCheckExpenseBankSelect);
      }
    }

    updatePaymentState();
  }

  function openOpModal(type) {
    if (!opModal) return;

    resetOperationEditState();

    setText("opModalTitle", type === "sale" ? "Nuovo incasso" : "Nuova spesa");

    const opType = document.getElementById("opType");
    const opDesc = document.getElementById("opDesc");
    const opFlag = document.getElementById("opFlag");
    const opCustomerId = document.getElementById("opCustomerId");
    const opCustomerRegistryId = document.getElementById("opCustomerRegistryId");
    const opCustomer = document.getElementById("opCustomer");
    const opCustomerLabel = document.getElementById("opCustomerLabel");
    const btnCustomerNew = document.getElementById("btnCustomerNew");
    const opOffCash = document.getElementById("opOffCash");
    const opOffCashWho = document.getElementById("opOffCashWho");
    const opOffCashBox = document.getElementById("opOffCashBox");

    if (opType) opType.value = type;
    if (opCustomerLabel) opCustomerLabel.textContent = type === "expense" ? "Fornitore" : "Cliente";
    if (opAmountInput) opAmountInput.value = "0,00";
    if (opDesc) opDesc.value = "";
    if (opFlag) opFlag.value = "*";
    if (opCustomerId) opCustomerId.value = "";
    if (opCustomerRegistryId) opCustomerRegistryId.value = "";
    if (opCustomer) {
      opCustomer.value = "";
      opCustomer.placeholder = type === "expense" ? "Cerca fornitore..." : "Cerca cliente...";
    }
    if (btnCustomerNew) btnCustomerNew.classList.toggle("d-none", type === "expense");
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

  function handleOperationModalKeydown(event) {
    if (!opModalEl || !opModalEl.classList.contains("show")) return;

    if (event.key === "Enter") {
      const target = event.target;
      const tagName = String(target?.tagName || "").toLowerCase();
      if (tagName === "textarea" || target?.isContentEditable) return;
      event.preventDefault();
      if (!saveBtn?.disabled) {
        saveOperation();
      }
      return;
    }

    if (event.key === "Escape") {
      event.preventDefault();
      if (opModal) {
        opModal.hide();
      }
    }
  }

  async function openEditSaleModal(saleId) {
    if (!currentDay) {
      alert("Nessuna giornata selezionata.");
      return;
    }

    try {
      const r = await fetch(`/cassa/api/day/${currentDay}/sales`, {
        credentials: "same-origin",
        headers: { "Accept": "application/json" },
        cache: "no-store"
      });

      const data = await r.json();

      if (!r.ok || !data.ok) {
        alert(data.error || "Errore caricamento incasso");
        return;
      }

      const sale = (data.sales || []).find(x => String(x.id) === String(saleId));
      if (!sale) {
        alert("Incasso non trovato");
        return;
      }

      openOpModal("sale");

      editingOperationType = "sale";
      editingOperationId = sale.id;

      const saveBtn = document.getElementById("opSaveBtn");
      if (saveBtn) saveBtn.textContent = "Salva modifica";

      const opDesc = document.getElementById("opDesc");
      const opFlag = document.getElementById("opFlag");
      const opCustomerId = document.getElementById("opCustomerId");
      const opCustomerRegistryId = document.getElementById("opCustomerRegistryId");
      const opCustomer = document.getElementById("opCustomer");
      const opOffCash = document.getElementById("opOffCash");
      const opOffCashWho = document.getElementById("opOffCashWho");
      const opOffCashBox = document.getElementById("opOffCashBox");

      if (opDesc) opDesc.value = sale.notes || "";
      if (opCustomerId) opCustomerId.value = sale.customer_id ? String(sale.customer_id) : "";
      if (opCustomerRegistryId) opCustomerRegistryId.value = "";
      if (opCustomer) opCustomer.value = sale.customer_label || "";

      const payments = sale.payments || [];
      if (!payments.length) return;
      editingOperationCheckIds = payments
        .filter(p => p.method === "check" && p.check_id)
        .map(p => Number(p.check_id));

      if (opFlag) opFlag.value = payments[0].flag || "*";

      const hasOffCash = payments.some(p => !!p.off_cash);
      if (opOffCash) opOffCash.checked = hasOffCash;
      if (opOffCashBox) opOffCashBox.classList.toggle("d-none", !hasOffCash);
      if (opOffCashWho) opOffCashWho.value = "";

      if (payments.length === 1) {
        const p = payments[0];
        if (opAmountInput) opAmountInput.value = formatEuro2(p.amount || 0);

        setPaymentMode(p.method || "cash");
        refreshSingleAmountFields();

        if (p.method === "pos") {
          await loadPosDevices(posDeviceSelect, false, posCircuitSelect);
          if (posDeviceSelect) posDeviceSelect.value = String(p.pos_device_id || "");
          await loadPosCircuits(p.pos_device_id, posCircuitSelect);
          if (posCircuitSelect) posCircuitSelect.value = String(p.pos_circuit_id || "");
        } else if (p.method === "bank") {
          await loadBanks(bankSelect);
          if (bankSelect) bankSelect.value = String(p.bank_id || "");
        } else if (p.method === "check") {
          const checkBankName = document.getElementById("checkSaleBankName");
          const checkBankABI = document.getElementById("checkSaleBankABI");
          const checkBankCAB = document.getElementById("checkSaleBankCAB");
          const checkNumber = document.getElementById("checkSaleNumber");
          const checkDueDate = document.getElementById("checkSaleDueDate");
          const checkAmount = document.getElementById("checkSaleAmount");

          if (checkBankName) checkBankName.value = p.bank_name || "";
          if (checkBankABI) checkBankABI.value = p.abi || "";
          if (checkBankCAB) checkBankCAB.value = p.cab || "";
          if (checkNumber) checkNumber.value = p.check_number || "";
          if (checkDueDate) checkDueDate.value = p.due_date || "";
          if (checkAmount) checkAmount.value = formatEuro2(p.amount || 0);
        }
      } else {
        setPaymentMode("multi");
        resetMultiPayments();

        for (const p of payments) {
          await addMultiPaymentRow(p.method || "cash");

          const rows = Array.from(document.querySelectorAll("#multiPaymentsList .multi-payment-row"));
          const row = rows[rows.length - 1];
          if (!row) continue;

          const amountInput = row.querySelector(".multi-amount");
          const methodSelect = row.querySelector(".multi-method");

          if (methodSelect) methodSelect.value = p.method || "cash";
          updateMultiRowFields(row);

          if (amountInput) amountInput.value = formatEuro2(p.amount || 0);

          if (p.method === "pos") {
            const rowPosDevice = row.querySelector(".multi-pos-device");
            const rowPosCircuit = row.querySelector(".multi-pos-circuit");

            await loadPosDevices(rowPosDevice, false, rowPosCircuit);
            if (rowPosDevice) rowPosDevice.value = String(p.pos_device_id || "");
            await loadPosCircuits(p.pos_device_id, rowPosCircuit);
            if (rowPosCircuit) rowPosCircuit.value = String(p.pos_circuit_id || "");
          } else if (p.method === "bank") {
            const rowBank = row.querySelector(".multi-bank-select");
            await loadBanks(rowBank);
            if (rowBank) rowBank.value = String(p.bank_id || "");
          } else if (p.method === "check") {
            const bankName = row.querySelector(".multi-check-bank-name");
            const abi = row.querySelector(".multi-check-bank-abi");
            const cab = row.querySelector(".multi-check-bank-cab");
            const checkNumber = row.querySelector(".multi-check-number");
            const dueDate = row.querySelector(".multi-check-due-date");

            if (bankName) bankName.value = p.bank_name || "";
            if (abi) abi.value = p.abi || "";
            if (cab) cab.value = p.cab || "";
            if (checkNumber) checkNumber.value = p.check_number || "";
            if (dueDate) dueDate.value = p.due_date || "";
          }
        }

        if (opAmountInput) {
          opAmountInput.value = formatEuro2(
            payments.reduce((sum, p) => sum + Number(p.amount || 0), 0)
          );
        }
      }

      updatePaymentState();

    } catch (err) {
      console.error("openEditSaleModal error:", err);
      alert("Errore di rete durante il caricamento dell'incasso.");
    }
  }

  async function openEditExpenseModal(expenseId) {
    if (!currentDay) {
      alert("Nessuna giornata selezionata.");
      return;
    }

    try {
      const r = await fetch(`/cassa/api/day/${currentDay}/expenses`, {
        credentials: "same-origin",
        headers: { "Accept": "application/json" },
        cache: "no-store"
      });

      const data = await r.json();

      if (!r.ok || !data.ok) {
        alert(data.error || "Errore caricamento spesa");
        return;
      }

      const expense = (data.expenses || []).find(x => String(x.id) === String(expenseId));
      if (!expense) {
        alert("Spesa non trovata");
        return;
      }

      openOpModal("expense");

      editingOperationType = "expense";
      editingOperationId = expense.id;

      const saveBtn = document.getElementById("opSaveBtn");
      if (saveBtn) saveBtn.textContent = "Salva modifica";

      const opDesc = document.getElementById("opDesc");
      const opFlag = document.getElementById("opFlag");
      const opCustomer = document.getElementById("opCustomer");
      const opCustomerId = document.getElementById("opCustomerId");
      const opCustomerRegistryId = document.getElementById("opCustomerRegistryId");
      const opOffCash = document.getElementById("opOffCash");
      const opOffCashWho = document.getElementById("opOffCashWho");
      const opOffCashBox = document.getElementById("opOffCashBox");

      if (opDesc) opDesc.value = expense.notes || "";
      if (opCustomer) opCustomer.value = expense.supplier || "";
      if (opCustomerId) opCustomerId.value = "";
      if (opCustomerRegistryId) opCustomerRegistryId.value = "";

      const payments = expense.payments || [];
      if (!payments.length) return;
      editingOperationCheckIds = [];

      if (opFlag) opFlag.value = payments[0].flag || "*";

      const hasOffCash = payments.some(p => !!p.off_cash);
      if (opOffCash) opOffCash.checked = hasOffCash;
      if (opOffCashBox) opOffCashBox.classList.toggle("d-none", !hasOffCash);
      if (opOffCashWho) opOffCashWho.value = "";

      if (payments.length === 1) {
        const p = payments[0];
        if (opAmountInput) opAmountInput.value = formatEuro2(p.amount || 0);

        setPaymentMode(p.method || "cash");
        refreshSingleAmountFields();

        if (p.method === "pos") {
          renderExpensePosOptions();
          const expensePosCardSelect = document.getElementById("expensePosCardSelect");
          if (expensePosCardSelect) {
            expensePosCardSelect.value = p.pos_card_label || "";
          }
        } else if (p.method === "bank") {
          await loadBanks(bankSelect);
          if (bankSelect) bankSelect.value = String(p.bank_id || "");
        } else if (p.method === "check") {
          const bankSelect = document.getElementById("checkExpenseBankSelect");

          await loadBanks(bankSelect);
          if (bankSelect) bankSelect.value = String(p.bank_id || "");

          const checkNumber = document.getElementById("checkExpenseNumber");
          const checkDueDate = document.getElementById("checkExpenseDueDate");
          const checkAmount = document.getElementById("checkExpenseAmount");

          if (checkNumber) checkNumber.value = p.check_number || "";
          if (checkDueDate) checkDueDate.value = p.due_date || "";
          if (checkAmount) checkAmount.value = formatEuro2(p.amount || 0);
        }
      } else {
        setPaymentMode("multi");
        resetMultiPayments();

        for (const p of payments) {
          await addMultiPaymentRow(p.method || "cash");

          const rows = Array.from(document.querySelectorAll("#multiPaymentsList .multi-payment-row"));
          const row = rows[rows.length - 1];
          if (!row) continue;

          const amountInput = row.querySelector(".multi-amount");
          const methodSelect = row.querySelector(".multi-method");

          if (methodSelect) methodSelect.value = p.method || "cash";
          updateMultiRowFields(row);

          if (amountInput) amountInput.value = formatEuro2(p.amount || 0);

          if (p.method === "pos") {
            const rowPosDevice = row.querySelector(".multi-pos-device");
            const rowPosCircuit = row.querySelector(".multi-pos-circuit");

            await loadPosDevices(rowPosDevice, false, rowPosCircuit);
            if (rowPosDevice) rowPosDevice.value = String(p.pos_device_id || "");
            await loadPosCircuits(p.pos_device_id, rowPosCircuit);
            if (rowPosCircuit) rowPosCircuit.value = String(p.pos_circuit_id || "");
          } else if (p.method === "bank") {
            const rowBank = row.querySelector(".multi-bank-select");
            await loadBanks(rowBank);
            if (rowBank) rowBank.value = String(p.bank_id || "");
          }
        }

        if (opAmountInput) {
          opAmountInput.value = formatEuro2(
            payments.reduce((sum, p) => sum + Number(p.amount || 0), 0)
          );
        }
      }

      updatePaymentState();

    } catch (err) {
      console.error("openEditExpenseModal error:", err);
      alert("Errore di rete durante il caricamento della spesa.");
    }
  }

  function resetOperationEditState() {
    editingOperationType = null;
    editingOperationId = null;
    editingOperationCheckIds = [];

    const saveBtn = document.getElementById("opSaveBtn");
    if (saveBtn) saveBtn.textContent = "Salva";
  }

  async function ensureSelectedCustomer() {
    const opCustomerInput = document.getElementById("opCustomer");
    const opCustomerIdInput = document.getElementById("opCustomerId");
    const opCustomerRegistryIdInput = document.getElementById("opCustomerRegistryId");
    const opType = document.getElementById("opType")?.value || "sale";

    if (!opCustomerInput || !opCustomerIdInput) {
      return { ok: true, customer_id: null, customer_registry_id: null };
    }

    if (opType === "expense") {
      return { ok: true, customer_id: null, customer_registry_id: null };
    }

    const currentId = String(opCustomerIdInput.value || "").trim();
    if (currentId) {
      return { ok: true, customer_id: Number(currentId), customer_registry_id: null };
    }

    const rawText = String(opCustomerInput.value || "").trim();
    if (!rawText) {
      return { ok: true, customer_id: null, customer_registry_id: null };
    }

    if (isPrivateCustomerLabel(rawText)) {
      return { ok: true, customer_id: null, customer_registry_id: null, is_private_customer: true };
    }

    const currentRegistryId = String(opCustomerRegistryIdInput?.value || "").trim();
    if (currentRegistryId) {
      try {
        const customer = await resolveCustomerRegistry(currentRegistryId);
        if (customer?.id) {
          opCustomerIdInput.value = String(customer.id);
          if (opCustomerRegistryIdInput) opCustomerRegistryIdInput.value = "";
          opCustomerInput.value = customer.display || customer.display_name || rawText;
          return { ok: true, customer_id: Number(customer.id), customer_registry_id: null };
        }
      } catch (err) {
        return {
          ok: false,
          error: err.message || "Cliente non selezionato correttamente."
        };
      }
    }

    const items = await fetchCustomerSuggest(rawText, "customer");
    const exact = items.find(x => String(x.display || "").trim() === rawText && x.kind === "customer" && (x.id || x.registry_id));

    if (!exact) {
      return {
        ok: false,
        error: "Cliente non selezionato correttamente. Sceglilo dalla lista o dalla ricerca avanzata."
      };
    }

    let customerId = exact.id ? Number(exact.id) : null;
    let display = exact.display || rawText;
    if (!customerId && exact.registry_id) {
      try {
        const customer = await resolveCustomerRegistry(exact.registry_id);
        customerId = customer?.id ? Number(customer.id) : null;
        display = customer?.display || customer?.display_name || display;
      } catch (err) {
        return {
          ok: false,
          error: err.message || "Cliente non selezionato correttamente."
        };
      }
    }
    if (!customerId) {
      return {
        ok: false,
        error: "Cliente non selezionato correttamente. Sceglilo dalla lista o dalla ricerca avanzata."
      };
    }

    opCustomerIdInput.value = String(customerId);
    if (opCustomerRegistryIdInput) opCustomerRegistryIdInput.value = "";
    opCustomerInput.value = display;

    return {
      ok: true,
      customer_id: customerId,
      customer_registry_id: null
    };
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
        configureDepositTabOrder();
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
          <td>${escapeHtml(formatDateIT(c.received_date))}</td>
          <td>${escapeHtml(formatDateIT(c.due_date))}</td>
          <td class="text-end">${formatEuro2(c.amount || 0)}</td>
        </tr>
      `).join("");

      updateDepositCashUi();
      configureDepositTabOrder();
    } catch (err) {
      console.error("loadAvailableDepositChecks error:", err);
      depositChecksTableBody.innerHTML = `
        <tr>
          <td colspan="7" class="text-center text-danger">Errore di rete</td>
        </tr>
      `;
      updateDepositCashUi();
      configureDepositTabOrder();
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
          <td>${escapeHtml(formatDateIT(row.deposit_date))}</td>
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

  function depositOrderedFocusTargets() {
    return [
      depositCashAmountInput,
      ...Array.from(depositChecksTableBody?.querySelectorAll(".deposit-check-select") || []),
      depositBankSelect,
      depositDateInput,
    ].filter(Boolean);
  }

  function configureDepositTabOrder() {
    const excluded = [
      depositTypeSelect,
      depositTotalAmountInput,
      depositNoteInput,
    ].filter(Boolean);

    excluded.forEach(el => {
      el.tabIndex = -1;
    });

    depositOrderedFocusTargets().forEach((el, index) => {
      el.tabIndex = index + 1;
    });
  }

  function focusDepositAmountInput() {
    configureDepositTabOrder();
    if (!depositCashAmountInput) return;

    const selectInput = () => {
      depositCashAmountInput.focus();
      depositCashAmountInput.select();
      if (typeof depositCashAmountInput.setSelectionRange === "function") {
        depositCashAmountInput.setSelectionRange(0, String(depositCashAmountInput.value || "").length);
      }
    };

    requestAnimationFrame(selectInput);
    setTimeout(selectInput, 120);
  }

  function handleDepositModalKeydown(event) {
    if (!depositModalEl || !depositModalEl.classList.contains("show")) return;

    if (event.key === "Enter") {
      const target = event.target;
      const tagName = String(target?.tagName || "").toLowerCase();
      if (tagName === "textarea" || target?.isContentEditable) return;
      event.preventDefault();
      if (!depositAddBtn?.disabled) {
        saveDeposit();
      }
    }
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
    if (!el.dataset.receiptModalBehaviorReady) {
      el.addEventListener("shown.bs.modal", focusReceiptAmountInput);
      el.addEventListener("keydown", handleReceiptModalKeydown);
      el.dataset.receiptModalBehaviorReady = "1";
    }
    if (!receiptModalInstance) {
      receiptModalInstance = new bootstrap.Modal(el);
    }
    return receiptModalInstance;
  }

  function focusReceiptAmountInput() {
    const amountInput = document.getElementById("rc_amount");
    if (!amountInput) return;

    const focusAmount = () => {
      amountInput.focus();
      amountInput.select?.();
    };

    requestAnimationFrame(focusAmount);
    window.setTimeout(focusAmount, 120);
  }

  async function handleReceiptModalKeydown(event) {
    const modalEl = document.getElementById("receiptModal");
    if (!modalEl?.classList.contains("show")) return;

    if (event.key === "Tab" && !event.shiftKey && event.target?.id === "rc_amount") {
      const typeSelect = document.getElementById("rc_type");
      if (typeSelect) {
        event.preventDefault();
        typeSelect.focus();
      }
      return;
    }

    if (event.key !== "Enter") return;

    event.preventDefault();
    const addBtn = document.getElementById("btnAddReceipt");
    if (addBtn?.disabled) return;
    await saveReceiptClosure();
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
          <td>${formatDateTimeIT(row.created_at)}</td>
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
    const description = (document.getElementById("opDesc")?.value || "").trim() || null;
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
      customer_registry_id: ensuredCustomer.customer_registry_id,
      is_private_customer: !!ensuredCustomer.is_private_customer,
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

    if (base.opType === "expense") {
      if (!base.description && !base.customer_label) {
        return { ok: false, error: "Inserisci almeno una descrizione o un fornitore/beneficiario." };
      }
    } else {
      if (!base.description && !base.customer_id && !base.customer_registry_id && !base.customer_label) {
        return { ok: false, error: "Inserisci almeno una descrizione o seleziona un cliente." };
      }
    }

    if (mode === "cash") {
      return {
        ok: true,
        payload: {
          description: base.description,
          flag: base.flag,
          customer_id: base.customer_id,
          customer_registry_id: base.customer_registry_id,
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
      if (base.opType === "expense") {
        const expensePosCardSelect = document.getElementById("expensePosCardSelect");
        const pos_card_label = (expensePosCardSelect?.value || "").trim();

        if (!pos_card_label) {
          return { ok: false, error: "Seleziona la carta utilizzata." };
        }

        const pos_is_personal = pos_card_label === "Carta personale";

        return {
          ok: true,
          payload: {
            description: base.description,
            flag: base.flag,
            customer_id: base.customer_id,
            customer_registry_id: base.customer_registry_id,
            customer_label: base.customer_label,
            off_cash: base.off_cash,
            off_cash_who: base.off_cash_who,
            payments: [
              {
                method: "pos",
                amount: amount,
                pos_card_label,
                pos_is_personal
              }
            ]
          }
        };
      }

      const dynamicPosDeviceSelect = document.getElementById("posDeviceSelect");
      const dynamicPosCircuitSelect = document.getElementById("posCircuitSelect");

      const pos_device_id = Number(dynamicPosDeviceSelect?.value || 0);
      const pos_circuit_id = Number(dynamicPosCircuitSelect?.value || 0);

      if (!pos_device_id || !pos_circuit_id) {
        return { ok: false, error: "Seleziona dispositivo e circuito POS." };
      }

      return {
        ok: true,
        payload: {
          description: base.description,
          flag: base.flag,
          customer_id: base.customer_id,
          customer_registry_id: base.customer_registry_id,
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
          customer_registry_id: base.customer_registry_id,
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
      if (base.opType === "expense") {
        if (!["*", "**"].includes(base.flag)) {
          return { ok: false, error: "Gli assegni emessi possono avere solo flag * o **." };
        }
        const bank_id = Number(document.getElementById("checkExpenseBankSelect")?.value || 0);
        const check_number = (document.getElementById("checkExpenseNumber")?.value || "").trim();
        const due_date = (document.getElementById("checkExpenseDueDate")?.value || "").trim();
        const checkAmount = parseEuroToNumber(document.getElementById("checkExpenseAmount")?.value || "0");

        if (!bank_id) {
          return { ok: false, error: "Seleziona la banca emittente." };
        }

        if (!check_number) {
          return { ok: false, error: "Inserisci il numero assegno." };
        }

        if (base.flag === "**" && !due_date) {
          return { ok: false, error: "Inserisci la data di scadenza per assegno postdatato." };
        }

        if (Math.abs(checkAmount - amount) > 0.009) {
          return { ok: false, error: "L'importo assegno non coincide con il totale dell'operazione." };
        }

        return {
          ok: true,
          payload: {
            supplier: base.customer_label,
            description: base.description,
            flag: base.flag,
            customer_id: base.customer_id,
            customer_registry_id: base.customer_registry_id,
            customer_label: base.customer_label,
            off_cash: base.off_cash,
            off_cash_who: base.off_cash_who,
            payments: [
              {
                method: "check",
                amount: amount,
                bank_id,
                check_number,
                due_date
              }
            ]
          }
        };
      }

      const bank_name = (document.getElementById("checkSaleBankName")?.value || "").trim();
      const abi = (document.getElementById("checkSaleBankABI")?.value || "").trim();
      const cab = (document.getElementById("checkSaleBankCAB")?.value || "").trim();
      const check_number = (document.getElementById("checkSaleNumber")?.value || "").trim();
      const due_date = (document.getElementById("checkSaleDueDate")?.value || "").trim();
      const checkAmount = parseEuroToNumber(document.getElementById("checkSaleAmount")?.value || "0");

      if (!base.customer_id) {
        return { ok: false, error: "Per un assegno devi selezionare un cliente." };
      }

      if (!bank_name || !check_number || !due_date) {
        return { ok: false, error: "Compila tutti i dati obbligatori dell’assegno." };
      }

      if (Math.abs(checkAmount - amount) > 0.009) {
        return { ok: false, error: "L'importo assegno non coincide con il totale dell'operazione." };
      }

      return {
        ok: true,
        payload: {
          description: base.description,
          flag: base.flag,
          customer_id: base.customer_id,
          customer_registry_id: base.customer_registry_id,
          customer_label: base.customer_label,
          off_cash: base.off_cash,
          off_cash_who: base.off_cash_who,
          payments: [
            {
              method: "check",
              check_id: editingOperationCheckIds[0] || null,
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

    if (base.opType === "expense") {
      if (!base.description && !base.customer_label) {
        return { ok: false, error: "Inserisci almeno una descrizione o un fornitore/beneficiario." };
      }
    } else {
      if (!base.description && !base.customer_id && !base.customer_registry_id && !base.customer_label) {
        return { ok: false, error: "Inserisci almeno una descrizione o seleziona un cliente." };
      }
    }

    const payments = [];
    let checkPaymentIndex = 0;

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
        if (base.opType === "expense") {
          const pos_card_label = (row.querySelector(".multi-pos-card-label")?.value || "").trim();

          if (!pos_card_label) {
            return { ok: false, error: "Ogni riga POS spesa deve avere una carta selezionata." };
          }

          const pos_is_personal = pos_card_label === "Carta personale";

          payments.push({
            method: "pos",
            amount,
            pos_card_label,
            pos_is_personal
          });
          continue;
        }

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
        if (base.opType === "expense") {
          if (!["*", "**"].includes(base.flag)) {
            return { ok: false, error: "Gli assegni emessi possono avere solo flag * o **." };
          }
          const bank_id = Number(row.querySelector(".multi-check-expense-bank-select")?.value || 0);
          const check_number = (row.querySelector(".multi-check-expense-number")?.value || "").trim();
          const due_date = (row.querySelector(".multi-check-expense-due-date")?.value || "").trim();
          if (!bank_id) {
            return { ok: false, error: "Ogni riga assegno spesa deve avere una banca selezionata." };
          }

          if (!check_number) {
            return { ok: false, error: "Inserisci il numero assegno per ogni riga assegno spesa." };
          }

          if (base.flag === "**" && !due_date) {
            return { ok: false, error: "Inserisci la scadenza per ogni riga assegno spesa postdatato." };
          }

          payments.push({
            method: "check",
            amount,
            bank_id,
            check_number,
            due_date
          });
          continue;
        }

        if (!base.customer_id) {
          return { ok: false, error: "Per gli assegni devi selezionare un cliente." };
        }

        const bank_name = (row.querySelector(".multi-check-bank-name")?.value || "").trim();
        const abi = (row.querySelector(".multi-check-bank-abi")?.value || "").trim();
        const cab = (row.querySelector(".multi-check-bank-cab")?.value || "").trim();
        const check_number = (row.querySelector(".multi-check-number")?.value || "").trim();
        const due_date = (row.querySelector(".multi-check-due-date")?.value || "").trim();

        if (!bank_name || !check_number || !due_date) {
          return { ok: false, error: "Completa tutti i dati obbligatori per ogni assegno incasso." };
        }

        payments.push({
          method: "check",
          check_id: editingOperationCheckIds[checkPaymentIndex++] || null,
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
        supplier: base.opType === "expense" ? (base.customer_label || null) : undefined,
        description: base.description,
        flag: base.flag,
        customer_id: base.customer_id,
        customer_registry_id: base.customer_registry_id,
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

  async function deletePosMove(posMoveId) {
    if (!posMoveId) return;

    const confirmed = window.confirm("Vuoi eliminare questo movimento POS?");
    if (!confirmed) return;

    try {
      const r = await fetch(`/cassa/api/pos_moves/${posMoveId}`, {
        method: "DELETE",
        headers: { "Accept": "application/json" },
        credentials: "same-origin"
      });

      const data = await r.json();

      if (!r.ok || !data.ok) {
        alert(data.error || "Errore eliminazione movimento POS");
        return;
      }

      // refresh UI
      await refreshAgendaSections(["preview", "pos"]);

    } catch (err) {
      console.error("deletePosMove error:", err);
      alert("Errore di rete durante l'eliminazione.");
    }
  }

  async function saveOperation() {
    if (!currentDay) {
      alert("Nessuna giornata selezionata.");
      return;
    }

    const opType = document.getElementById("opType")?.value || "sale";

    const isEdit =
      !!editingOperationId &&
      editingOperationType &&
      editingOperationType === opType;

    const endpoint = isEdit
      ? (opType === "expense"
          ? `/cassa/api/expenses/${editingOperationId}`
          : `/cassa/api/sales/${editingOperationId}`)
      : (opType === "expense"
          ? `/cassa/api/day/${currentDay}/expenses`
          : `/cassa/api/day/${currentDay}/sales`);

    const method = isEdit ? "PUT" : "POST";

    const built = await buildOperationPayload();
    if (!built.ok) {
      alert(built.error || "Dati operazione non validi.");
      return;
    }

    try {
      if (saveBtn) saveBtn.disabled = true;

      const r = await fetch(endpoint, {
        method,
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify(built.payload),
      });

      const data = await r.json();

      if (!r.ok || !data.ok) {
        alert(data.error || "Errore durante il salvataggio.");
        return;
      }

      resetOperationEditState();
      opModal.hide();

      await refreshAgendaSections([
        "preview",
        opType === "expense" ? "spese" : "incassi",
        opType === "sale" ? "assegni" : null,
        opType === "expense" ? "assegni_rientranti" : null,
        opType === "sale" ? "pos" : null
      ].filter(Boolean));

    } catch (err) {
      console.error("saveOperation error:", err);
      alert("Errore di rete durante il salvataggio.");
    } finally {
      if (saveBtn) saveBtn.disabled = false;
      updatePaymentState();
    }
  }

  function setSearchDefaultDates(fromEl, toEl) {
    const value = currentDay || toLocalYMD(new Date());
    if (fromEl && !fromEl.value) fromEl.value = value;
    if (toEl && !toEl.value) toEl.value = value;
  }

  function openMovementSearchCustomerModal() {
    setSearchDefaultDates(movementSearchCustomerFrom, movementSearchCustomerTo);
    if (movementSearchCustomerResults) {
      movementSearchCustomerResults.innerHTML = `<tr><td colspan="7" class="text-center text-muted">Nessuna ricerca eseguita</td></tr>`;
    }
    movementSearchCustomerModal?.show();
    setTimeout(() => movementSearchCustomerText?.focus(), 150);
  }

  function openMovementSearchAmountModal() {
    setSearchDefaultDates(movementSearchAmountFrom, movementSearchAmountTo);
    if (movementSearchAmountTolerance && !movementSearchAmountTolerance.value) {
      movementSearchAmountTolerance.value = "0,00";
    }
    if (movementSearchAmountResults) {
      movementSearchAmountResults.innerHTML = `<tr><td colspan="7" class="text-center text-muted">Nessuna ricerca eseguita</td></tr>`;
    }
    movementSearchAmountModal?.show();
    setTimeout(() => movementSearchAmountValue?.focus(), 150);
  }

  function getInitialMovementSearchAction() {
    const params = new URLSearchParams(window.location.search || "");
    const openParam = (params.get("open") || params.get("action") || "").trim().toLowerCase();
    const path = (window.location.pathname || "").replace(/\/+$/, "");

    if (["search_customer", "customer", "cliente", "ricerca_cliente"].includes(openParam)) {
      return "search_customer";
    }

    if (["search_amount", "amount", "importo", "ricerca_importo"].includes(openParam)) {
      return "search_amount";
    }

    if (["report", "day_report", "report_giornata"].includes(openParam)) {
      return "report";
    }

    if (["print_report", "stampa_report"].includes(openParam)) {
      return "print_report";
    }

    if (["checks", "assegni", "gestione_assegni"].includes(openParam)) {
      return "checks";
    }

    if ([
      "issued_checks",
      "issued-checks",
      "assegni_emessi",
      "assegni-emessi",
      "gestione_assegni_emessi",
      "gestione-assegni-emessi"
    ].includes(openParam)) {
      return "issued_checks";
    }

    if (path.endsWith("/cassa/agenda/search/customer")) {
      return "search_customer";
    }

    if (path.endsWith("/cassa/agenda/search/amount")) {
      return "search_amount";
    }

    if (path.endsWith("/cassa/agenda/report")) {
      return "report";
    }

    if (path.endsWith("/cassa/agenda/report/print")) {
      return "print_report";
    }

    if (path.endsWith("/cassa/agenda/checks")) {
      return "checks";
    }

    if (path.endsWith("/cassa/agenda/issued-checks")) {
      return "issued_checks";
    }

    return "";
  }

  function openInitialMovementSearchAction() {
    const action = getInitialMovementSearchAction();

    if (action === "search_customer") {
      openMovementSearchCustomerModal();
    } else if (action === "search_amount") {
      openMovementSearchAmountModal();
    } else if (action === "report") {
      openDayReport();
    } else if (action === "print_report") {
      printCompleteDayReport();
    } else if (action === "checks") {
      openChecksManagementModal();
    } else if (action === "issued_checks") {
      openIssuedChecksManagementModal();
    }
  }

  function renderMovementSearchRows(tbody, rows) {
    if (!tbody) return;

    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted">Nessun movimento trovato</td></tr>`;
      return;
    }

    tbody.innerHTML = rows.map(row => {
      const canEdit = !!row.editable;
      const canDelete = !!row.deletable;
      const amount = formatEuro2(row.amount || 0);

      return `
        <tr
          class="movement-search-row ${canEdit ? "cursor-pointer" : ""}"
          data-kind="${escapeHtml(row.kind || "")}"
          data-id="${escapeHtml(row.id || "")}"
          data-day-date="${escapeHtml(row.day_date || "")}"
          data-editable="${canEdit ? "1" : "0"}"
        >
          <td>${escapeHtml(formatDateIT(row.day_date))}</td>
          <td>${escapeHtml(row.kind_label || "")}</td>
          <td>${escapeHtml(row.party || "")}</td>
          <td>${escapeHtml(row.description || "")}</td>
          <td>${escapeHtml(row.method || "")}</td>
          <td class="text-end">${amount}</td>
          <td class="text-end">
            <button type="button" class="btn btn-sm btn-outline-primary movement-search-edit" ${canEdit ? "" : "disabled"}>Apri</button>
            <button type="button" class="btn btn-sm btn-outline-danger movement-search-delete" ${canDelete ? "" : "disabled"}>Elimina</button>
          </td>
        </tr>
      `;
    }).join("");
  }

  async function runMovementCustomerSearch() {
    const params = new URLSearchParams({
      customer: movementSearchCustomerText?.value || "",
      date_from: movementSearchCustomerFrom?.value || "",
      date_to: movementSearchCustomerTo?.value || ""
    });

    if (movementSearchCustomerResults) {
      movementSearchCustomerResults.innerHTML = `<tr><td colspan="7" class="text-center text-muted">Ricerca in corso...</td></tr>`;
    }

    const r = await fetch(`/cassa/api/search/customer?${params.toString()}`, {
      credentials: "same-origin",
      headers: { "Accept": "application/json" }
    });
    const data = await r.json();
    if (!r.ok || !data.ok) {
      alert(data.error || "Errore ricerca cliente");
      renderMovementSearchRows(movementSearchCustomerResults, []);
      return;
    }
    renderMovementSearchRows(movementSearchCustomerResults, data.rows || []);
  }

  async function runMovementAmountSearch() {
    const types = Array.from(document.querySelectorAll(".movement-search-type:checked"))
      .map(el => el.value)
      .join(",");
    const params = new URLSearchParams({
      amount: String(parseEuroToNumber(movementSearchAmountValue?.value || "0")),
      tolerance: String(parseEuroToNumber(movementSearchAmountTolerance?.value || "0")),
      date_from: movementSearchAmountFrom?.value || "",
      date_to: movementSearchAmountTo?.value || "",
      types
    });

    if (movementSearchAmountResults) {
      movementSearchAmountResults.innerHTML = `<tr><td colspan="7" class="text-center text-muted">Ricerca in corso...</td></tr>`;
    }

    const r = await fetch(`/cassa/api/search/amount?${params.toString()}`, {
      credentials: "same-origin",
      headers: { "Accept": "application/json" }
    });
    const data = await r.json();
    if (!r.ok || !data.ok) {
      alert(data.error || "Errore ricerca importo");
      renderMovementSearchRows(movementSearchAmountResults, []);
      return;
    }
    renderMovementSearchRows(movementSearchAmountResults, data.rows || []);
  }

  async function openMovementFromSearch(rowEl) {
    if (!rowEl) return;

    const kind = rowEl.dataset.kind;
    const id = rowEl.dataset.id;
    const dayDate = rowEl.dataset.dayDate;

    if (dayDate && dayDate !== currentDay) {
      await loadDay(dayDate);
    }

    if (kind === "sale") {
      await openEditSaleModal(id);
    } else if (kind === "expense") {
      await openEditExpenseModal(id);
    } else if (kind === "pos") {
      await openEditPosModal(id);
    } else if (kind === "cash_move") {
      await openEditCashMoveModal(id);
    }
  }

  async function deleteMovementFromSearch(rowEl) {
    if (!rowEl || rowEl.dataset.editable !== "1") return;

    const kind = rowEl.dataset.kind;
    const id = rowEl.dataset.id;
    const dayDate = rowEl.dataset.dayDate;

    if (dayDate && dayDate !== currentDay) {
      await loadDay(dayDate);
    }

    if (kind === "pos") {
      await deletePosMove(id);
    } else if (kind === "cash_move") {
      await deleteCashMove(id);
    } else if (kind === "sale") {
      const confirmed = window.confirm("Vuoi eliminare questo incasso?");
      if (!confirmed) return;
      const r = await fetch(`/cassa/api/sales/${id}`, {
        method: "DELETE",
        headers: { "Accept": "application/json" },
        credentials: "same-origin"
      });
      const data = await r.json();
      if (!r.ok || !data.ok) {
        alert(data.error || "Errore eliminazione incasso");
        return;
      }
      await refreshAgendaData();
    } else if (kind === "expense") {
      const confirmed = window.confirm("Vuoi eliminare questa spesa?");
      if (!confirmed) return;
      const r = await fetch(`/cassa/api/expenses/${id}`, {
        method: "DELETE",
        headers: { "Accept": "application/json" },
        credentials: "same-origin"
      });
      const data = await r.json();
      if (!r.ok || !data.ok) {
        alert(data.error || "Errore eliminazione spesa");
        return;
      }
      await refreshAgendaData();
    } else if (kind === "ecommerce") {
      const confirmed = window.confirm("Vuoi eliminare questo movimento e-commerce?");
      if (!confirmed) return;
      const r = await fetch(`/cassa/api/ecommerce/${id}`, {
        method: "DELETE",
        headers: { "Accept": "application/json" },
        credentials: "same-origin"
      });
      const data = await r.json();
      if (!r.ok || !data.ok) {
        alert(data.error || "Errore eliminazione eCommerce");
        return;
      }
      await refreshAgendaData();
    } else if (kind === "deposit") {
      const confirmed = window.confirm("Vuoi eliminare questo versamento?");
      if (!confirmed) return;
      const r = await fetch(`/cassa/api/deposits/${id}`, {
        method: "DELETE",
        headers: { "Accept": "application/json" },
        credentials: "same-origin"
      });
      const data = await r.json();
      if (!r.ok || !data.ok) {
        alert(data.error || "Errore eliminazione versamento");
        return;
      }
      await refreshAgendaData();
    } else if (kind === "owner_take") {
      await deleteOwnerTake(id);
    }

    rowEl.remove();
  }

  const posList = document.getElementById("posList");
  const posPanel = document.getElementById("posPanel");
  const incassiList = document.getElementById("incassiList");
  const incassiPanel = document.getElementById("incassiPanel");
  const speseList = document.getElementById("speseList");
  const spesePanel = document.getElementById("spesePanel");
  const movCassaList = document.getElementById("movCassaList");
  const movCassaPanel = document.getElementById("movCassaPanel");

  function bindPanelContextMenu(panelEl, listEl, rowSelector, datasetKey, type, panel) {
    if (!panelEl) return;

    panelEl.addEventListener("contextmenu", (e) => {
      const row = e.target.closest(rowSelector);
      const rows = Array.from(listEl.querySelectorAll(rowSelector));
      const hasRows = rows.length > 0;

      e.preventDefault();

      if (row) {
        const context = {
          type,
          id: row.dataset[datasetKey],
          panel,
          menuMode: "row",
          menuScope: "full",
          hasRows: true
        };

        if (type === "pos_move") {
          context.deviceId = row.dataset.posDeviceId || null;
          context.deviceName = row.dataset.posDeviceName || "";
          context.circuitId = row.dataset.posCircuitId || null;
          context.circuitName = row.dataset.posCircuitName || "";
        } else if (type === "cash_move") {
          context.kind = row.dataset.cashMoveKind || "";
          context.direction = row.dataset.cashMoveDirection || "";
        }

        openContextMenu(e.clientX, e.clientY, context);
        return;
      }

      openContextMenu(e.clientX, e.clientY, {
        type,
        id: null,
        panel,
        menuMode: "panel",
        menuScope: "full",
        hasRows
      });
    });

    panelEl.addEventListener("click", (e) => {
      const btn = e.target.closest(".btn-row-menu");
      if (!btn) return;

      e.preventDefault();
      e.stopPropagation();

      const row = btn.closest(rowSelector);
      if (!row) return;

      const rect = btn.getBoundingClientRect();

      const context = {
        type,
        id: row.dataset[datasetKey],
        panel,
        menuMode: "row",
        menuScope: "row",
        hasRows: true
      };

      if (type === "pos_move") {
        context.deviceId = row.dataset.posDeviceId || null;
        context.deviceName = row.dataset.posDeviceName || "";
        context.circuitId = row.dataset.posCircuitId || null;
        context.circuitName = row.dataset.posCircuitName || "";
      } else if (type === "cash_move") {
        context.kind = row.dataset.cashMoveKind || "";
        context.direction = row.dataset.cashMoveDirection || "";
      }

      openContextMenu(rect.right - 8, rect.bottom + 4, context);
    });
  }

  bindPanelContextMenu(incassiPanel, incassiList, ".sale-row", "saleId", "sale", "incassi");
  bindPanelContextMenu(spesePanel, speseList, ".expense-row", "expenseId", "expense", "spese");
  bindPanelContextMenu(movCassaPanel, movCassaList, ".cash-move-row", "cashMoveId", "cash_move", "mov_cassa");
  bindPanelContextMenu(posPanel, posList, ".pos-row", "posMoveId", "pos_move", "pos");

  document.getElementById("contextMenu")?.addEventListener("click", async (e) => {
    const item = e.target.closest(".context-menu-item");
    if (!item || item.classList.contains("disabled")) return;
    if (item.hasAttribute("disabled")) return;
    if (!currentContext) return;

    const action = item.dataset.action;
    if (!action) return;

    try {
      switch (action) {
        case "insert":
          if (currentContext.type === "pos_move") {
            await openPosModal();
          } else if (currentContext.type === "cash_move") {
            await openCashMoveModal();
          } else if (currentContext.type === "sale") {
            openOpModal("sale");
          } else if (currentContext.type === "expense") {
            openOpModal("expense");
          }
          break;

        case "edit":
          if (currentContext.type === "pos_move") {
            await openEditPosModal(currentContext.id);
          } else if (currentContext.type === "cash_move") {
            if (currentContext.kind === "spicci") {
              await openEditSpicciMove(currentContext.id);
            } else {
              await openEditCashMoveModal(currentContext.id);
            }
          } else if (currentContext.type === "sale") {
            await openEditSaleModal(currentContext.id);
          } else if (currentContext.type === "expense") {
            await openEditExpenseModal(currentContext.id);
          }
          break;

        case "delete":
          if (currentContext.type === "pos_move") {
            await deletePosMove(currentContext.id);
          } else if (currentContext.type === "cash_move") {
            if (currentContext.kind === "spicci") {
              await deleteSpicciMove(currentContext.id);
            } else {
              await deleteCashMove(currentContext.id);
            }
          } else if (currentContext.type === "sale") {
            const confirmed = window.confirm("Vuoi eliminare questo incasso?");
            if (!confirmed) return;

            const r = await fetch(`/cassa/api/sales/${currentContext.id}`, {
              method: "DELETE",
              headers: { "Accept": "application/json" },
              credentials: "same-origin"
            });

            const data = await r.json();

            if (!r.ok || !data.ok) {
              alert(data.error || "Errore eliminazione incasso");
              return;
            }

            await refreshAgendaData();

          } else if (currentContext.type === "expense") {
            const confirmed = window.confirm("Vuoi eliminare questa spesa?");
            if (!confirmed) return;

            const r = await fetch(`/cassa/api/expenses/${currentContext.id}`, {
              method: "DELETE",
              headers: { "Accept": "application/json" },
              credentials: "same-origin"
            });

            const data = await r.json();

            if (!r.ok || !data.ok) {
              alert(data.error || "Errore eliminazione spesa");
              return;
            }

            await refreshAgendaData();
          }
          break;

        case "filter_device":
          if (currentContext.type === "pos_move") {
            await setPosDeviceFilter(item.dataset.filterValue || null, item.dataset.filterLabel || "");
          }
          break;

        case "filter_circuit":
          if (currentContext.type === "pos_move") {
            await setPosCircuitFilter(item.dataset.filterValue || null, item.dataset.filterLabel || "");
          }
          break;

        case "filter_kind":
        case "filter_method":
        case "filter_offcash":
          break;

        case "filter_sale":
          await setSaleFilter(item.dataset.filterKind, item.dataset.filterValue || null);
          break;

        case "filter_expense":
          await setExpenseFilter(item.dataset.filterKind, item.dataset.filterValue || null);
          break;

        case "filter_cash_move":
          await setCashMoveFilter(item.dataset.filterKind, item.dataset.filterValue || null);
          break;

        case "clear_filters":
          if (currentContext.type === "pos_move") {
            await clearPosFilters();
          } else if (currentContext.type === "sale") {
            await clearSaleFilters();
          } else if (currentContext.type === "expense") {
            await clearExpenseFilters();
          } else if (currentContext.type === "cash_move") {
            await clearCashMoveFilters();
          } else {
            alert("Reset filtri: prossimo step");
          }
          break;

        case "search_customer":
          openMovementSearchCustomerModal();
          break;

        case "search_amount":
          openMovementSearchAmountModal();
          break;

        case "report":
          await openDayReport();
          break;

        case "print_report":
          await printCompleteDayReport();
          break;
      }
    } catch (err) {
      console.error("context menu action error:", err);
      alert("Errore durante l'azione richiesta");
    } finally {
      closeContextMenu();
    }
  });

  checksReloadBtn?.addEventListener("click", async () => {
    await loadChecksManagement();
  });

  checksNewBtn?.addEventListener("click", () => {
    resetCheckForm();
    checkCustomerLabel?.focus();
  });

  checkCancelBtn?.addEventListener("click", resetCheckForm);

  checkSaveBtn?.addEventListener("click", async () => {
    await saveManagedCheck();
  });

  checkCustomerLabel?.addEventListener("input", () => {
    if (checkCustomerId) checkCustomerId.value = "";
  });

  checksManagementRows?.addEventListener("click", async (e) => {
    const editBtn = e.target.closest(".btn-check-edit");
    if (editBtn) {
      try {
        startEditCheck(JSON.parse(editBtn.dataset.row || "{}"));
      } catch (err) {
        console.error("check edit parse error:", err);
        alert("Errore caricamento assegno");
      }
      return;
    }

    const deleteBtn = e.target.closest(".btn-check-delete");
    if (deleteBtn) {
      await deleteManagedCheck(deleteBtn.dataset.id);
    }
  });

  checksFilterText?.addEventListener("keydown", async (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      await loadChecksManagement();
    }
  });

  checksFilterStatus?.addEventListener("change", async () => {
    await loadChecksManagement();
  });

  issuedChecksReloadBtn?.addEventListener("click", async () => {
    await loadIssuedChecksManagement();
  });

  issuedCheckCancelBtn?.addEventListener("click", resetIssuedCheckForm);

  issuedCheckSaveBtn?.addEventListener("click", async () => {
    await saveIssuedCheck();
  });

  issuedCheckFlag?.addEventListener("change", () => {
    if (issuedCheckFlag.value !== "**" && issuedCheckDueDate) {
      issuedCheckDueDate.value = "";
    }
  });

  issuedChecksManagementRows?.addEventListener("click", async (e) => {
    const editBtn = e.target.closest(".btn-issued-check-edit");
    if (editBtn) {
      try {
        await startEditIssuedCheck(JSON.parse(editBtn.dataset.row || "{}"));
      } catch (err) {
        console.error("issued check edit parse error:", err);
        alert("Errore caricamento assegno emesso");
      }
      return;
    }

    const deleteBtn = e.target.closest(".btn-issued-check-delete");
    if (deleteBtn) {
      await deleteIssuedCheck(deleteBtn.dataset.id);
    }
  });

  issuedChecksFilterText?.addEventListener("keydown", async (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      await loadIssuedChecksManagement();
    }
  });

  issuedChecksFilterStatus?.addEventListener("change", loadIssuedChecksManagement);
  issuedChecksFilterFlag?.addEventListener("change", loadIssuedChecksManagement);

  movementSearchCustomerBtn?.addEventListener("click", async () => {
    try {
      await runMovementCustomerSearch();
    } catch (err) {
      console.error("runMovementCustomerSearch error:", err);
      alert("Errore di rete durante la ricerca cliente.");
    }
  });

  movementSearchAmountBtn?.addEventListener("click", async () => {
    try {
      await runMovementAmountSearch();
    } catch (err) {
      console.error("runMovementAmountSearch error:", err);
      alert("Errore di rete durante la ricerca importo.");
    }
  });

  openInitialMovementSearchAction();

  document.addEventListener("click", async (e) => {
    const editBtn = e.target.closest(".movement-search-edit");
    const deleteBtn = e.target.closest(".movement-search-delete");
    const rowEl = e.target.closest(".movement-search-row");

    if (!rowEl) return;

    e.preventDefault();
    e.stopPropagation();

    try {
      if (deleteBtn) {
        await deleteMovementFromSearch(rowEl);
      } else {
        await openMovementFromSearch(rowEl);
      }
    } catch (err) {
      console.error("movement search action error:", err);
      alert("Errore durante l'azione sul movimento.");
    }
  });

  document.addEventListener("click", (e) => {
    if (e.target.closest("#contextMenu")) return;
    if (e.target.closest(".btn-row-menu")) return;
    closeContextMenu();
  });

  document.addEventListener("scroll", closeContextMenu);


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
        if (opCustomerRegistryIdInput) opCustomerRegistryIdInput.value = "";
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
    const hiddenRegistryId = document.getElementById("opCustomerRegistryId");
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
      if (hiddenRegistryId) hiddenRegistryId.value = "";
      const q = input.value.trim();

      if (q.length < 2) {
        lastItems = [];
        list.innerHTML = "";
        return;
      }

      clearTimeout(t);
      t = setTimeout(async () => {
        const items = await fetchCustomerSuggest(q, getCurrentRegistryKind());
        lastItems = items;
        renderDatalist(items);
      }, 180);
    });

    input.addEventListener("change", async () => {
      const chosen = findByDisplay(input.value);
      hiddenId.value = "";
      if (hiddenRegistryId) hiddenRegistryId.value = "";
      if (!chosen || chosen.kind !== "customer") return;
      if (chosen.id) {
        hiddenId.value = String(chosen.id);
        return;
      }
      if (chosen.registry_id) {
        try {
          const customer = await resolveCustomerRegistry(chosen.registry_id);
          if (customer?.id) {
            hiddenId.value = String(customer.id);
            input.value = customer.display || customer.display_name || input.value;
          }
        } catch (err) {
          console.error("resolve customer registry from suggest error:", err);
          alert(err.message || "Errore selezione cliente");
        }
      }
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
    const title = document.getElementById("customerSearchTitle");
    const mainHeader = document.getElementById("customerSearchMainHeader");
    const btnConfirm = document.getElementById("customerPickConfirm");
    const opInput = document.getElementById("opCustomer");
    const opHiddenId = document.getElementById("opCustomerId");
    const opHiddenRegistryId = document.getElementById("opCustomerRegistryId");

    if (!qInput || !btnGo || !tbody || !selId || !selDisp || !btnConfirm || !opInput || !opHiddenId) return;

    let selectedItem = null;

    function setSelected(item) {
      selectedItem = item || null;
      const id = selectedItem && selectedItem.kind === "customer" && selectedItem.id ? selectedItem.id : "";
      const display = selectedItem ? selectedItem.display : "";
      selId.value = id ? String(id) : "";
      selDisp.value = display || "";
      btnConfirm.disabled = !selectedItem;
    }

    async function runSearch() {
      const q = (qInput.value || "").trim();
      const kind = getCurrentRegistryKind();
      setSelected(null);

      if (q.length < 2) {
        tbody.innerHTML = `<tr><td colspan="4" class="text-muted">Inserisci almeno 2 caratteri</td></tr>`;
        return;
      }

      let items = [];
      try {
        items = await fetchCustomerSuggest(q, kind);
        if (!items.length) {
          tbody.innerHTML = `<tr><td colspan="4" class="text-muted">Nessun risultato</td></tr>`;
          return;
        }
      } catch (err) {
        console.error("customer search error:", err);
        tbody.innerHTML = `<tr><td colspan="4" class="text-danger">Errore durante la ricerca</td></tr>`;
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
          <td>${escapeHtml(it.codice_cliente || it.codice_fornitore || "")}</td>
        `;
        tr.addEventListener("click", () => {
          [...tbody.querySelectorAll("tr")].forEach(x => x.classList.remove("table-active"));
          tr.classList.add("table-active");
          setSelected(it);
        });
        tbody.appendChild(tr);
      });
    }

    btnOpen.addEventListener("click", () => {
      const isSupplier = getCurrentRegistryKind() === "supplier";
      if (title) title.textContent = isSupplier ? "Seleziona fornitore" : "Seleziona cliente";
      if (mainHeader) mainHeader.textContent = isSupplier ? "Fornitore" : "Cliente";
      qInput.placeholder = isSupplier
        ? "Nome, ragione sociale, P.IVA, codice fornitore..."
        : "Nome/alias, ragione sociale, P.IVA, codice cliente...";
      qInput.value = (opInput.value || "").trim();
      setSelected(null);
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

    btnConfirm.addEventListener("click", async () => {
      if (!selectedItem) return;
      btnConfirm.disabled = true;
      try {
        if (selectedItem.kind === "customer" && !selectedItem.id && selectedItem.registry_id) {
          const customer = await resolveCustomerRegistry(selectedItem.registry_id);
          selectedItem = {
            ...selectedItem,
            id: customer?.id || null,
            display: customer?.display || customer?.display_name || selectedItem.display,
          };
        }
        if (selectedItem.kind === "customer" && !selectedItem.id) {
          alert("Cliente non selezionato correttamente.");
          return;
        }
        opHiddenId.value = selectedItem.kind === "customer" && selectedItem.id ? String(selectedItem.id) : "";
        if (opHiddenRegistryId) opHiddenRegistryId.value = "";
        opInput.value = selectedItem.display || selDisp.value;
        bsModal.hide();
      } catch (err) {
        console.error("resolve customer registry from modal error:", err);
        alert(err.message || "Errore selezione cliente");
      } finally {
        btnConfirm.disabled = false;
      }
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

  posMoveSaveBtn?.addEventListener("click", async () => {
    await savePosMove();
  });

  cashMoveSaveBtn?.addEventListener("click", async () => {
    await saveCashMove();
  });

    spicciMoveSaveBtn?.addEventListener("click", async () => {
    await saveSpicciMove();
  });

  spicciTableBody?.addEventListener("click", async (e) => {
    const editBtn = e.target.closest(".btn-spicci-edit");
    if (editBtn) {
      await openEditSpicciMove(editBtn.dataset.id);
      return;
    }

    const deleteBtn = e.target.closest(".btn-spicci-delete");
    if (deleteBtn) {
      await deleteSpicciMove(deleteBtn.dataset.id);
    }
  });

  posDeviceSelect?.addEventListener("change", async (e) => {
    await loadPosCircuits(e.target.value, posCircuitSelect);
    updatePaymentState();
  });

  normalizeCurrencyInput(document.getElementById("cashAmount"));
  normalizeCurrencyInput(document.getElementById("posAmount"));
  normalizeCurrencyInput(document.getElementById("bankAmount"));
  normalizeCurrencyInput(document.getElementById("checkAmount"));
  normalizeCurrencyInput(document.getElementById("checkSaleAmount"));
  normalizeCurrencyInput(document.getElementById("checkExpenseAmount"));
  normalizeCurrencyInput(document.getElementById("expensePosAmount"));


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
  document.getElementById("btnNewMovimento")?.addEventListener("click", async () => {
    await openCashMoveModal();
  });

  document.getElementById("opOffCash")?.addEventListener("change", (e) => {
    const box = document.getElementById("opOffCashBox");
    if (!box) return;
    box.classList.toggle("d-none", !e.target.checked);
  });

  document.getElementById("posList")?.addEventListener("change", async (e) => {
    const checkbox = e.target.closest(".pos-row-check");
    if (!checkbox) return;

    const entityType = checkbox.dataset.entityType;
    const entityId = String(checkbox.dataset.entityId || "").trim();
    const cashDayId = Number(document.getElementById("dayId")?.textContent || 0);

    if (!entityType || !entityId || !cashDayId) {
      alert("Dati check riga non validi");
      return;
    }

    const rowEl = checkbox.closest(".pos-row");
    const newState = checkbox.checked;

    checkbox.disabled = true;

    try {
      const result = await toggleRowCheck(entityType, entityId, cashDayId, newState);

      checkbox.checked = !!result.is_checked;
      rowEl?.classList.toggle("row-checked", !!result.is_checked);
    } catch (err) {
      console.error("toggle POS row check error:", err);
      checkbox.checked = !newState;
      alert(err.message || "Errore durante il salvataggio della spunta");
    } finally {
      checkbox.disabled = false;
    }
  });

  document.getElementById("movCassaList")?.addEventListener("change", async (e) => {
    const checkbox = e.target.closest(".cash-move-row-check");
    if (!checkbox) return;

    const entityType = checkbox.dataset.entityType;
    const entityId = String(checkbox.dataset.entityId || "").trim();
    const cashDayId = Number(document.getElementById("dayId")?.textContent || 0);

    if (!entityType || !entityId || !cashDayId) {
      alert("Dati check riga non validi");
      return;
    }

    const rowEl = checkbox.closest(".cash-move-row");
    const newState = checkbox.checked;

    checkbox.disabled = true;

    try {
      const result = await toggleRowCheck(entityType, entityId, cashDayId, newState);

      checkbox.checked = !!result.is_checked;
      rowEl?.classList.toggle("row-checked", !!result.is_checked);
    } catch (err) {
      console.error("toggle cash_move row check error:", err);
      checkbox.checked = !newState;
      alert(err.message || "Errore durante il salvataggio della spunta");
    } finally {
      checkbox.disabled = false;
    }
  });

  saveBtn?.addEventListener("click", () => {
    saveOperation();
  });

  updatePaymentState();
});

document.getElementById("incassiList")?.addEventListener("change", async (e) => {
  const checkbox = e.target.closest(".sale-row-check");
  if (!checkbox) return;

  const entityType = checkbox.dataset.entityType;
  const entityId = String(checkbox.dataset.entityId || "").trim();
  const cashDayId = Number(document.getElementById("dayId")?.textContent || 0);

  if (!entityType || !entityId || !cashDayId) {
    alert("Dati check riga non validi");
    return;
  }

  const rowEl = checkbox.closest(".sale-row");
  const newState = checkbox.checked;

  checkbox.disabled = true;

  try {
    const result = await toggleRowCheck(entityType, entityId, cashDayId, newState);

    checkbox.checked = !!result.is_checked;
    rowEl?.classList.toggle("row-checked", !!result.is_checked);
  } catch (err) {
    console.error("toggle sale row check error:", err);
    checkbox.checked = !newState;
    alert(err.message || "Errore durante il salvataggio della spunta");
  } finally {
    checkbox.disabled = false;
  }
});

document.getElementById("speseList")?.addEventListener("change", async (e) => {
  const checkbox = e.target.closest(".expense-row-check");
  if (!checkbox) return;

  const entityType = checkbox.dataset.entityType;
  const entityId = String(checkbox.dataset.entityId || "").trim();
  const cashDayId = Number(document.getElementById("dayId")?.textContent || 0);

  if (!entityType || !entityId || !cashDayId) {
    alert("Dati check riga non validi");
    return;
  }

  const rowEl = checkbox.closest(".expense-row");
  const newState = checkbox.checked;

  checkbox.disabled = true;

  try {
    const result = await toggleRowCheck(entityType, entityId, cashDayId, newState);

    checkbox.checked = !!result.is_checked;
    rowEl?.classList.toggle("row-checked", !!result.is_checked);
  } catch (err) {
    console.error("toggle expense row check error:", err);
    checkbox.checked = !newState;
    alert(err.message || "Errore durante il salvataggio della spunta");
  } finally {
    checkbox.disabled = false;
  }
});

document.addEventListener("visibilitychange", function () {
  if (document.visibilityState === "visible") {
    loadAssegniScadenza(currentDay, false);
    loadAssegniRientranti(currentDay);
    startAssegniAutoRefresh();
  } else {
    stopAssegniAutoRefresh();
  }
});

async function saveEcommerce() {
  const amountRaw = ecoAmountInput?.value;
  const description = (ecoDescriptionInput?.value || "").trim();

  const amount = parseEuroToNumber(amountRaw);

  if (!amount || amount <= 0) {
    alert("Inserisci un importo valido");
    return;
  }

  if (!description) {
    alert("Inserisci una descrizione");
    return;
  }

  const isEdit = !!editingEcommerceId;

  const url = isEdit
    ? `/cassa/api/ecommerce/${editingEcommerceId}`
    : `/cassa/api/day/${currentDay}/ecommerce`;

  const method = isEdit ? "PUT" : "POST";

  try {
    if (ecoAddBtn) ecoAddBtn.disabled = true;

    const r = await fetch(url, {
      method,
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/json"
      },
      credentials: "same-origin",
      body: JSON.stringify({
        amount,
        description
      })
    });

    const data = await r.json();

    if (!data.ok) {
      alert(data.error || "Errore salvataggio");
      return;
    }

    editingEcommerceId = null;
    ecoAmountInput.value = "";
    ecoDescriptionInput.value = "";
    if (ecoAddBtn) ecoAddBtn.textContent = "Aggiungi";

    await loadEcommerce(currentDay);
    await loadPreview(currentDay);

  } catch (err) {
    console.error("ecoSave error:", err);
    alert("Errore di rete");
  } finally {
    if (ecoAddBtn) ecoAddBtn.disabled = false;
  }
}

ecoAddBtn?.addEventListener("click", async () => {
  await saveEcommerce();
});

ecoTableBody?.addEventListener("click", async (e) => {
  const editBtn = e.target.closest(".btn-eco-edit");
  if (editBtn) {
    editingEcommerceId = editBtn.dataset.id || null;

    if (ecoDescriptionInput) {
      ecoDescriptionInput.value = editBtn.dataset.description || "";
    }

    if (ecoAmountInput) {
      ecoAmountInput.value = formatEuro2(editBtn.dataset.amount || 0);
    }

    if (ecoAddBtn) ecoAddBtn.textContent = "Salva modifica";
    return;
  }

  const deleteBtn = e.target.closest(".btn-eco-delete");
  if (!deleteBtn) return;

  const ecommerceId = deleteBtn.dataset.id;
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

    if (String(editingEcommerceId) === String(ecommerceId)) {
      editingEcommerceId = null;
      if (ecoAmountInput) ecoAmountInput.value = "";
      if (ecoDescriptionInput) ecoDescriptionInput.value = "";
      if (ecoAddBtn) ecoAddBtn.textContent = "Aggiungi";
    }

    await loadEcommerce(currentDay);
    await loadPreview(currentDay);

  } catch (err) {
    console.error("ecoDelete error:", err);
    alert("Errore di rete");
  }
});

let currentContext = null;

function buildContextMenuHtml(context) {
  const isRowMenu = context?.menuMode === "row";
  const entityType = context?.type || "";
  const hasRows = !!context?.hasRows;
  const menuScope = context?.menuScope || "full";
  const showRowMenu = isRowMenu && ["row", "full"].includes(menuScope);
  const showPanelMenu = ["panel", "full"].includes(menuScope);
  const showGeneralMenu = menuScope === "full";

  const canInsert = ["pos_move", "cash_move", "sale", "expense"].includes(entityType);
  const canEditDelete = showRowMenu && !!context?.id;
  const canFilter = showPanelMenu && hasRows;
  const canFilterPosDevice = entityType === "pos_move" && hasRows;
  const canFilterPosCircuit = entityType === "pos_move" && hasRows;
  const canClearPosFilters = entityType === "pos_move" && hasActivePosFilters();
  const canClearSaleFilters = entityType === "sale" && hasActiveSaleFilters();
  const canClearExpenseFilters = entityType === "expense" && hasActiveExpenseFilters();
  const canClearCashMoveFilters = entityType === "cash_move" && hasActiveCashMoveFilters();
  const canReport = true;

  const btn = (label, action, enabled = true, danger = false) => {
    const classes = [
      "context-menu-item",
      danger ? "danger" : "",
      enabled ? "" : "disabled"
    ].filter(Boolean).join(" ");

    return `<button type="button" class="${classes}" data-action="${action}">${label}</button>`;
  };

  const filterBtn = (label, action, value, optionLabel, active = false) => {
    const classes = [
      "context-menu-item",
      active ? "active" : ""
    ].filter(Boolean).join(" ");

    return `
      <button
        type="button"
        class="${classes}"
        data-action="${action}"
        data-filter-value="${escapeHtml(value || "")}"
        data-filter-label="${escapeHtml(optionLabel || "")}"
      >
        ${label}
      </button>
    `;
  };

  const submenu = (label, enabled, itemsHtml) => {
    const classes = [
      "context-menu-submenu-wrap",
      enabled ? "" : "disabled"
    ].filter(Boolean).join(" ");

    return `
      <div class="${classes}">
        <button type="button" class="context-menu-item has-submenu ${enabled ? "" : "disabled"}">
          <span>${label}</span>
          <span class="context-menu-submenu-arrow">›</span>
        </button>
        <div class="context-menu-submenu">
          ${itemsHtml}
        </div>
      </div>
    `;
  };

  const posFilterSubmenu = (kind) => {
    const action = kind === "device" ? "filter_device" : "filter_circuit";
    const currentValue = kind === "device" ? posFilters.deviceId : posFilters.circuitId;
    const options = uniquePosFilterOptions(kind);
    const rows = [
      filterBtn("Tutti", action, "", "Tutti", !currentValue),
      filterBtn("Nessuno", action, "__none__", "Nessuno", currentValue === "__none__"),
      ...options.map(opt => filterBtn(
        escapeHtml(opt.name),
        action,
        opt.id,
        opt.name,
        String(currentValue || "") === String(opt.id)
      ))
    ];

    return rows.join("");
  };

  const paymentFilterSubmenu = (entity, kind) => {
    const filters = entity === "sale" ? saleFilters : expenseFilters;
    const sourceRows = entity === "sale" ? lastSaleRows : lastExpenseRows;
    const action = entity === "sale" ? "filter_sale" : "filter_expense";
    const currentValue = filters[kind];

    if (kind === "cashScope") {
      return [
        filterBtn("Tutti", action, "", "Tutti", !currentValue),
        filterBtn("Cassa", action, "in_cash", "Cassa", currentValue === "in_cash"),
        filterBtn("Fuori cassa", action, "off_cash", "Fuori cassa", currentValue === "off_cash"),
      ].map(html => html.replace("data-filter-label=", `data-filter-kind="${kind}" data-filter-label=`)).join("");
    }

    const options = uniquePaymentFilterOptions(sourceRows, kind, filters);
    const rows = [
      filterBtn("Tutti", action, "", "Tutti", !currentValue),
      filterBtn("Nessuno", action, "__none__", "Nessuno", currentValue === "__none__"),
      ...options.map(opt => filterBtn(
        escapeHtml(opt.label),
        action,
        opt.value,
        opt.label,
        String(currentValue || "") === String(opt.value)
      ))
    ];

    return rows
      .map(html => html.replace("data-filter-label=", `data-filter-kind="${kind}" data-filter-label=`))
      .join("");
  };

  const cashMoveFilterSubmenu = (kind) => {
    const action = "filter_cash_move";
    const currentValue = cashMoveFilters[kind];

    if (kind === "direction") {
      return [
        filterBtn("Tutti", action, "", "Tutti", !currentValue),
        filterBtn("Prelievo", action, "out", "Prelievo", currentValue === "out"),
        filterBtn("Versamento", action, "in", "Versamento", currentValue === "in"),
      ].map(html => html.replace("data-filter-label=", `data-filter-kind="${kind}" data-filter-label=`)).join("");
    }

    const preferred = [
      { value: "altro", label: "Movimento di cassa" },
      { value: "spicci", label: "Spicci" },
    ];
    const present = uniqueCashMoveFilterOptions(kind);
    const merged = new Map(preferred.map(opt => [opt.value, opt.label]));
    for (const opt of present) merged.set(opt.value, opt.label);

    const rows = [
      filterBtn("Tutti", action, "", "Tutti", !currentValue),
      ...Array.from(merged.entries()).map(([value, label]) => filterBtn(
        escapeHtml(label),
        action,
        value,
        label,
        String(currentValue || "") === String(value)
      ))
    ];

    return rows
      .map(html => html.replace("data-filter-label=", `data-filter-kind="${kind}" data-filter-label=`))
      .join("");
  };

  const sections = [];

  const section = (title, content) => `
    <div class="context-menu-section">
      ${title ? `<div class="context-menu-section-title">${title}</div>` : ""}
      ${content}
    </div>
  `;

  if (showRowMenu && ["pos_move", "cash_move", "sale", "expense"].includes(entityType)) {
    sections.push(`
      ${section("Riga", `
        ${btn("Modifica", "edit", canEditDelete)}
        ${btn("Elimina", "delete", canEditDelete, true)}
      `)}
    `);
  }

  if (showPanelMenu && canInsert) {
    sections.push(`
      ${section("Quadrante", `
        ${btn("Inserisci", "insert", true)}
      `)}
    `);
  }

  if (showPanelMenu && entityType === "pos_move") {
    sections.push(`
      ${section(canInsert ? "" : "Quadrante", `
        ${submenu("Filtra per device", canFilterPosDevice, posFilterSubmenu("device"))}
        ${submenu("Filtra per circuito", canFilterPosCircuit, posFilterSubmenu("circuit"))}
        ${btn("Rimuovi filtri", "clear_filters", canClearPosFilters)}
      `)}
    `);
  }

  if (showPanelMenu && entityType === "cash_move") {
    sections.push(`
      ${section(canInsert ? "" : "Quadrante", `
        ${submenu("Filtra per tipo movimento", canFilter, cashMoveFilterSubmenu("kind"))}
        ${submenu("Filtra per direzione", canFilter, cashMoveFilterSubmenu("direction"))}
        ${btn("Rimuovi filtri", "clear_filters", canClearCashMoveFilters)}
      `)}
    `);
  }

  if (showPanelMenu && entityType === "sale") {
    sections.push(`
      ${section(canInsert ? "" : "Quadrante", `
        ${submenu("Filtra per tipo incasso", canFilter, paymentFilterSubmenu("sale", "method"))}
        ${submenu("Filtra per flag", canFilter, paymentFilterSubmenu("sale", "flag"))}
        ${submenu("Filtra cassa/fuori cassa", canFilter, paymentFilterSubmenu("sale", "cashScope"))}
        ${btn("Rimuovi filtri", "clear_filters", canClearSaleFilters)}
      `)}
    `);
  }

  if (showPanelMenu && entityType === "expense") {
    sections.push(`
      ${section(canInsert ? "" : "Quadrante", `
        ${submenu("Filtra per tipo spesa", canFilter, paymentFilterSubmenu("expense", "method"))}
        ${submenu("Filtra per flag", canFilter, paymentFilterSubmenu("expense", "flag"))}
        ${submenu("Filtra cassa/fuori cassa", canFilter, paymentFilterSubmenu("expense", "cashScope"))}
        ${btn("Rimuovi filtri", "clear_filters", canClearExpenseFilters)}
      `)}
    `);
  }

  if (showGeneralMenu) {
    sections.push(`
      ${section("Generale", `
      ${btn("Ricerca per cliente", "search_customer", true)}
      ${btn("Ricerca per importo", "search_amount", true)}
      ${btn("Visualizza report", "report", canReport)}
      ${btn("Stampa report", "print_report", canReport)}
      `)}
    `);
  }

  if (!sections.length) {
    return `<div class="context-menu-empty">Nessuna azione disponibile</div>`;
  }

  return sections.join(`<div class="context-menu-separator"></div>`);
}

function openContextMenu(x, y, context) {
  const menu = document.getElementById("contextMenu");
  if (!menu) return;

  currentContext = context;
  menu.innerHTML = buildContextMenuHtml(context);

  menu.classList.remove("d-none");
  menu.classList.remove("submenu-left");
  menu.style.visibility = "hidden";
  menu.style.left = "0px";
  menu.style.top = "0px";

  const menuRect = menu.getBoundingClientRect();
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const gap = 8;

  let left = x;
  let top = y;

  if (left + menuRect.width > vw - gap) {
    left = vw - menuRect.width - gap;
  }

  if (top + menuRect.height > vh - gap) {
    top = vh - menuRect.height - gap;
  }

  if (left < gap) left = gap;
  if (top < gap) top = gap;

  if (left + menuRect.width + 288 > vw - gap) {
    menu.classList.add("submenu-left");
  }

  menu.style.left = `${left}px`;
  menu.style.top = `${top}px`;
  menu.style.visibility = "visible";
}

async function openDayReport() {
  if (!currentDay) return;

  try {
    const res = await fetch(`/cassa/api/day/${currentDay}/preview`, {
      credentials: "same-origin",
      headers: { "Accept": "application/json" },
      cache: "no-store"
    });

    const data = await res.json();

    if (!res.ok || !data.ok) {
      alert(data.error || "Errore caricamento report giornata");
      return;
    }

    renderDayReport(data.totals || {});

    const modalEl = document.getElementById("dayReportModal");
    if (!modalEl) {
      alert("Modale report non trovata");
      return;
    }

    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    modal.show();

  } catch (err) {
    console.error("Errore caricamento report:", err);
    alert("Errore di rete durante il caricamento del report giornata.");
  }
}

async function fetchReportJson(url, fallback = null) {
  try {
    const res = await fetch(url, {
      credentials: "same-origin",
      headers: { "Accept": "application/json" },
      cache: "no-store"
    });
    const data = await res.json();
    if (!res.ok) return fallback;
    return data;
  } catch (err) {
    console.error("fetchReportJson error:", url, err);
    return fallback;
  }
}

function reportMoney(value) {
  const n = Number(value || 0);
  return n.toLocaleString("it-IT", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
}

function reportDateTime(value) {
  return formatDateTimeIT(value);
}

function reportText(value) {
  const s = String(value ?? "").trim();
  return s ? escapeHtml(s) : "&nbsp;";
}

function reportTable(title, headers, rows, emptyText = "Nessun movimento") {
  const head = headers.map(h => `<th>${escapeHtml(h)}</th>`).join("");
  const headerHtml = headers.length ? `<thead><tr>${head}</tr></thead>` : "";
  const body = rows.length
    ? rows.map(row => `<tr>${row.map(cell => `<td>${cell}</td>`).join("")}</tr>`).join("")
    : `<tr><td colspan="${Math.max(headers.length, 1)}" class="muted">${escapeHtml(emptyText)}</td></tr>`;

  return `
    <section class="report-section">
      <h2>${escapeHtml(title)}</h2>
      <table>
        ${headerHtml}
        <tbody>${body}</tbody>
      </table>
    </section>
  `;
}

function movementMethodLabel(method) {
  return paymentMethodLabel(method || "cash");
}

function buildCompleteDayReportHtml(payload) {
  const totals = payload.preview?.totals || {};
  const sales = payload.sales?.sales || [];
  const expenses = payload.expenses?.expenses || [];
  const posMoves = payload.pos?.pos_moves || [];
  const cashMoves = payload.cashMoves?.cash_moves || [];
  const deposits = payload.deposits?.deposits || [];
  const ownerTakes = payload.ownerTakes?.owner_takes || [];
  const ecommerce = payload.ecommerce?.ecommerce || [];
  const receipts = Array.isArray(payload.receipts) ? payload.receipts : [];
  const vaultLabel = priVaultUnlocked ? "Vault sbloccato: movimenti PRI inclusi" : "Vault bloccato: movimenti PRI esclusi";

  const summaryRows = [
    ["Fondo iniziale", totals.fondo_iniziale],
    ["Fondo finale", totals.fondo_finale],
    ["Delta fondo", totals.delta_fondo],
    ["Totale giornata", totals.totale_giornata],
    ["Incasso calcolato", totals.incasso_calcolato],
    ["Incasso consegnato", totals.incasso_consegnato],
    ["Delta quadratura", totals.delta_quadratura],
    ["Versabile iniziale", totals.saldo_versabile_precedente],
    ["Versabile giornata", totals.versabile_giornata],
    ["Versabile residuo", totals.versabile_residuo],
    ["Versabile attuale", totals.saldo_versabile],
    ["Totale versamenti", totals.totale_versato_oggi],
  ].map(([label, value]) => [reportText(label), `€ ${reportMoney(value)}`]);

  const salesRows = [];
  for (const sale of sales) {
    for (const payment of (sale.payments || [])) {
      salesRows.push([
        reportDateTime(payment.created_at || sale.created_at),
        reportText(sale.customer_label || ""),
        reportText(payment.description || sale.notes || ""),
        reportText(payment.flag || ""),
        reportText(movementMethodLabel(payment.method)),
        payment.off_cash ? "Fuori cassa" : "Cassa",
        `€ ${reportMoney(payment.amount)}`,
        reportText(sale.storage === "pri" ? "PRI" : "AZ"),
      ]);
    }
  }

  const expenseRows = [];
  for (const expense of expenses) {
    for (const payment of (expense.payments || [])) {
      expenseRows.push([
        reportDateTime(payment.created_at || expense.created_at),
        reportText(expense.supplier || ""),
        reportText(payment.description || expense.notes || ""),
        reportText(payment.flag || ""),
        reportText(movementMethodLabel(payment.method)),
        payment.off_cash ? "Fuori cassa" : "Cassa",
        `€ ${reportMoney(payment.amount)}`,
        reportText(expense.storage === "pri" ? "PRI" : "AZ"),
      ]);
    }
  }

  const posRows = posMoves.map(row => [
    reportDateTime(row.created_at),
    reportText(row.direction === "out" ? "Storno" : "Incasso"),
    reportText(row.pos_device_name || ""),
    reportText(row.pos_circuit_name || ""),
    reportText(row.doc_ref || ""),
    reportText(row.notes || ""),
    `€ ${reportMoney(row.amount)}`,
  ]);

  const cashMoveRows = cashMoves.map(row => [
    reportDateTime(row.created_at),
    reportText(cashMoveKindLabel(row.kind)),
    reportText(cashMoveDirectionLabel(row.direction)),
    reportText(row.performed_by || ""),
    reportText(row.notes || ""),
    `€ ${reportMoney(row.amount)}`,
    reportText(row.storage === "pri" ? "PRI" : "AZ"),
  ]);

  const receiptRows = receipts.map(row => [
    reportDateTime(row.created_at),
    reportText(row.closure_type || ""),
    reportText(row.description || ""),
    `€ ${reportMoney(row.amount)}`,
  ]);

  const ecommerceRows = ecommerce.map(row => [
    reportDateTime(row.created_at),
    reportText(row.description || ""),
    `€ ${reportMoney(row.amount)}`,
  ]);

  const depositRows = deposits.map(row => {
    const checksTotal = (row.checks || []).reduce((sum, check) => sum + Number(check.amount || check.check_amount || 0), 0);
    const total = Number(row.cash_amount || 0) + checksTotal;
    const checksText = (row.checks || [])
      .map(check => `${check.check_number || check.id || ""} € ${reportMoney(check.amount || check.check_amount || 0)}`)
      .join(", ");

    return [
      reportDateTime(row.created_at),
      reportText(row.deposit_type || ""),
      reportText(row.bank_name || row.bank?.name || ""),
      `€ ${reportMoney(row.cash_amount)}`,
      reportText(checksText),
      `€ ${reportMoney(total)}`,
      reportText(row.note || ""),
    ];
  });

  const ownerTakeRows = ownerTakes.map(row => {
    const checksText = (row.checks || [])
      .map(check => `${check.check_number || check.id || ""} € ${reportMoney(check.amount || 0)}`)
      .join(", ");

    return [
      reportDateTime(row.created_at),
      reportText(row.take_type || ""),
      `€ ${reportMoney(row.cash_amount)}`,
      `€ ${reportMoney(row.check_amount)}`,
      reportText(checksText),
      `€ ${reportMoney(row.total_amount)}`,
      reportText(row.notes || ""),
    ];
  });

  return `
<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <title>Report giornata ${escapeHtml(currentDay || "")}</title>
  <style>
    @page { size: A4; margin: 12mm; }
    * { box-sizing: border-box; }
    body { font-family: Arial, sans-serif; color: #111; font-size: 11px; margin: 0; }
    header { border-bottom: 2px solid #111; padding-bottom: 8px; margin-bottom: 12px; }
    h1 { font-size: 20px; margin: 0 0 4px; }
    h2 { font-size: 14px; margin: 16px 0 6px; }
    .meta { display: flex; justify-content: space-between; gap: 12px; color: #555; }
    .summary { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin-bottom: 12px; }
    .summary-item { border: 1px solid #bbb; padding: 6px; min-height: 36px; }
    .summary-label { color: #555; font-size: 10px; }
    .summary-value { font-weight: 700; font-size: 13px; text-align: right; }
    table { width: 100%; border-collapse: collapse; page-break-inside: auto; }
    tr { page-break-inside: avoid; page-break-after: auto; }
    th, td { border: 1px solid #ccc; padding: 4px 5px; vertical-align: top; }
    th { background: #eee; text-align: left; font-weight: 700; }
    td:last-child, th:last-child { text-align: right; }
    .report-section { break-inside: avoid; margin-bottom: 10px; }
    .muted { color: #777; text-align: center !important; }
    .screen-actions { margin: 12px 0; }
    .screen-actions button { padding: 7px 12px; }
    @media print {
      .screen-actions { display: none; }
      body { font-size: 10px; }
      h2 { break-after: avoid; }
    }
  </style>
</head>
<body>
  <div class="screen-actions">
    <button onclick="window.print()">Stampa</button>
  </div>
  <header>
    <h1>Report completo giornata ${escapeHtml(currentDay || "")}</h1>
    <div class="meta">
      <div>${escapeHtml(vaultLabel)}</div>
      <div>Generato: ${escapeHtml(formatDateTimeIT(new Date().toISOString()))}</div>
    </div>
  </header>

  <section class="summary">
    ${summaryRows.map(([label, value]) => `
      <div class="summary-item">
        <div class="summary-label">${label}</div>
        <div class="summary-value">${value}</div>
      </div>
    `).join("")}
  </section>

  ${reportTable("Incassi", ["Ora", "Cliente", "Descrizione", "Flag", "Metodo", "Cassa", "Importo", "Archivio"], salesRows)}
  ${reportTable("Spese", ["Ora", "Fornitore", "Descrizione", "Flag", "Metodo", "Cassa", "Importo", "Archivio"], expenseRows)}
  ${reportTable("POS", ["Ora", "Tipo", "Device", "Circuito", "Doc", "Note", "Importo"], posRows)}
  ${reportTable("Movimenti di cassa e spicci", ["Ora", "Tipo", "Direzione", "Chi", "Note", "Importo", "Archivio"], cashMoveRows)}
  ${reportTable("Corrispettivi", ["Ora", "Tipo", "Descrizione", "Importo"], receiptRows)}
  ${reportTable("E-commerce", ["Ora", "Descrizione", "Importo"], ecommerceRows)}
  ${reportTable("Versamenti", ["Ora", "Tipo", "Banca", "Contanti", "Assegni", "Totale", "Note"], depositRows)}
  ${reportTable("Cassetto / Prelievi incasso", ["Ora", "Tipo", "Contanti", "Assegni", "Dettaglio assegni", "Totale", "Note"], ownerTakeRows)}
</body>
</html>`;
}

async function printCompleteDayReport() {
  if (!currentDay) return;

  await refreshPrivateVaultStatus();

  const view = priVaultUnlocked ? "complete" : "fiscal";
  const [
    preview,
    sales,
    expenses,
    pos,
    cashMoves,
    deposits,
    ownerTakes,
    ecommerce,
    receipts,
  ] = await Promise.all([
    fetchReportJson(`/cassa/api/day/${currentDay}/preview?view=${view}`, { ok: false, totals: {} }),
    fetchReportJson(`/cassa/api/day/${currentDay}/sales`, { ok: false, sales: [] }),
    fetchReportJson(`/cassa/api/day/${currentDay}/expenses`, { ok: false, expenses: [] }),
    fetchReportJson(`/cassa/api/day/${currentDay}/pos_moves`, { ok: false, pos_moves: [] }),
    fetchReportJson(`/cassa/api/day/${currentDay}/cash_moves`, { ok: false, cash_moves: [] }),
    fetchReportJson(`/cassa/api/day/${currentDay}/deposits`, { ok: false, deposits: [] }),
    fetchReportJson(`/cassa/api/day/${currentDay}/owner-takes`, { ok: false, owner_takes: [] }),
    fetchReportJson(`/cassa/api/day/${currentDay}/ecommerce`, { ok: false, ecommerce: [] }),
    fetchReportJson(`/cassa/api/day/${currentDay}/receipt-closures`, []),
  ]);

  const html = buildCompleteDayReportHtml({
    preview,
    sales,
    expenses,
    pos,
    cashMoves,
    deposits,
    ownerTakes,
    ecommerce,
    receipts,
  });

  const win = window.open("", "_blank");
  if (!win) {
    alert("Popup bloccato dal browser. Consenti i popup per stampare il report.");
    return;
  }

  win.document.open();
  win.document.write(html);
  win.document.close();
  win.focus();
  setTimeout(() => win.print(), 300);
}

async function collectCompleteDayReportPayload() {
  await refreshPrivateVaultStatus();

  const view = priVaultUnlocked ? "complete" : "fiscal";
  const [
    preview,
    sales,
    expenses,
    pos,
    cashMoves,
    deposits,
    ownerTakes,
    ecommerce,
    receipts,
    banks,
  ] = await Promise.all([
    fetchReportJson(`/cassa/api/day/${currentDay}/preview?view=${view}`, { ok: false, totals: {} }),
    fetchReportJson(`/cassa/api/day/${currentDay}/sales`, { ok: false, sales: [] }),
    fetchReportJson(`/cassa/api/day/${currentDay}/expenses`, { ok: false, expenses: [] }),
    fetchReportJson(`/cassa/api/day/${currentDay}/pos_moves`, { ok: false, pos_moves: [] }),
    fetchReportJson(`/cassa/api/day/${currentDay}/cash_moves`, { ok: false, cash_moves: [] }),
    fetchReportJson(`/cassa/api/day/${currentDay}/deposits`, { ok: false, deposits: [], totals: {} }),
    fetchReportJson(`/cassa/api/day/${currentDay}/owner-takes`, { ok: false, owner_takes: [] }),
    fetchReportJson(`/cassa/api/day/${currentDay}/ecommerce`, { ok: false, ecommerce: [] }),
    fetchReportJson(`/cassa/api/day/${currentDay}/receipt-closures`, []),
    fetchReportJson("/cassa/api/banks", { ok: false, banks: [] }),
  ]);

  return { preview, sales, expenses, pos, cashMoves, deposits, ownerTakes, ecommerce, receipts, banks };
}

function reportDayLabel() {
  if (!currentDay) return "";
  const parts = String(currentDay).split("-");
  if (parts.length !== 3) return currentDay;
  return `${parts[2]}.${parts[1]}.${parts[0]}`;
}

function signedReportMoney(value) {
  return `€ ${reportMoney(value)}`;
}

function reportTitleText() {
  return `${priVaultUnlocked ? "Report completo" : "Report fiscale"} giornata ${reportDayLabel()}`;
}

function reportBankMap(payload) {
  return new Map((payload.banks?.banks || []).map(bank => [String(bank.id), bank.name]));
}

function reportPosMaps(payload) {
  const byId = new Map();
  const byDeviceCircuit = new Map();

  for (const move of payload.pos?.pos_moves || []) {
    if (move.id != null) byId.set(String(move.id), move);
    const key = `${move.pos_device_id || ""}|${move.pos_circuit_id || ""}`;
    byDeviceCircuit.set(key, move);
  }

  return { byId, byDeviceCircuit };
}

function compactDescription(parts) {
  return parts.map(x => String(x || "").trim()).filter(Boolean).join(" ");
}

function reportMovementDescription({ flag, party, description, suffix }) {
  const core = [party, description].map(x => String(x || "").trim()).filter(Boolean).join(" - ");
  const body = compactDescription([flag, core]);
  return suffix ? `${body} (${suffix})` : body;
}

function paymentSuffix(payment, maps, bankMap) {
  if (payment.method === "bank") {
    return bankMap.get(String(payment.bank_id || "")) || "Banca";
  }

  if (payment.off_cash) {
    return payment.off_cash_who || payment.off_cash_name || "Fuori cassa";
  }

  if (payment.method === "pos") {
    const move = maps.byId.get(String(payment.pos_move_id || ""));
    return move?.pos_device_name || "POS";
  }

  return "";
}

function isPrivateParty(label, storage) {
  const text = String(label || "").trim().toLowerCase();
  return storage === "pri" || text === "privato" || text === "privati";
}

function paymentRowsForReport(items, type, payload) {
  const bankMap = reportBankMap(payload);
  const posMaps = reportPosMaps(payload);
  const rows = [];
  let privateTotal = 0;

  for (const item of items || []) {
    const party = type === "sale" ? (item.customer_label || "") : (item.supplier || "");
    const itemIsPrivate = isPrivateParty(party, item.storage);

    for (const payment of item.payments || []) {
      const amount = Number(payment.amount || 0);
      if (itemIsPrivate) {
        privateTotal += amount;
        continue;
      }

      rows.push([
        reportText(reportMovementDescription({
          flag: payment.flag || "",
          party,
          description: payment.description || item.notes || "",
          suffix: paymentSuffix(payment, posMaps, bankMap)
        })),
        signedReportMoney(amount),
      ]);
    }
  }

  if (privateTotal) {
    rows.push([reportText("Totale Privati"), signedReportMoney(privateTotal)]);
  }

  return rows;
}

function reportPaymentGroups(items, type, payload) {
  const primary = [];
  const privateRows = [];
  const primaryFlags = new Set(["*", "**", "#", "!"]);
  const privateFlags = new Set(["x", "+"]);
  const bankMap = reportBankMap(payload);
  const posMaps = reportPosMaps(payload);
  let privateTotal = 0;

  for (const item of items || []) {
    const party = type === "sale" ? (item.customer_label || "") : (item.supplier || "");
    const isPrivateCustomer = type === "sale" && isPrivateCustomerLabel(party);

    for (const payment of item.payments || []) {
      const amount = Number(payment.amount || 0);
      const flag = payment.flag || "";

      const row = [
        reportText(reportMovementDescription({
          flag,
          party,
          description: payment.description || item.notes || "",
          suffix: paymentSuffix(payment, posMaps, bankMap)
        })),
        signedReportMoney(amount),
      ];

      if (primaryFlags.has(flag)) {
        primary.push(row);
      } else if (privateFlags.has(flag)) {
        if (flag === "x" && isPrivateCustomer) {
          privateTotal += amount;
        } else {
          privateRows.push(row);
        }
      }
    }
  }

  if (privateTotal) {
    privateRows.push([reportText("Totale Privati"), signedReportMoney(privateTotal)]);
  }

  return { primary, privateRows };
}

function reportPaymentFlagTotal(items, targetFlag) {
  let total = 0;
  for (const item of items || []) {
    for (const payment of item.payments || []) {
      if ((payment.flag || "") === targetFlag) {
        total += Number(payment.amount || 0);
      }
    }
  }
  return total;
}

function posRecapRows(payload) {
  const deviceMap = new Map();
  const circuits = new Set();

  for (const move of payload.pos?.pos_moves || []) {
    const device = move.pos_device_name || `POS ${move.pos_device_id || ""}`;
    const circuit = move.pos_circuit_name || "Circuito";
    const signed = move.direction === "out" ? -Number(move.amount || 0) : Number(move.amount || 0);
    circuits.add(circuit);

    if (!deviceMap.has(device)) {
      deviceMap.set(device, new Map());
    }

    const totals = deviceMap.get(device);
    totals.set(circuit, (totals.get(circuit) || 0) + signed);
  }

  const circuitList = Array.from(circuits).sort((a, b) => a.localeCompare(b, "it"));
  const rows = Array.from(deviceMap.entries())
    .sort(([a], [b]) => a.localeCompare(b, "it"))
    .map(([device, totals]) => {
      const values = circuitList.map(circuit => Number(totals.get(circuit) || 0));
      const total = values.reduce((sum, value) => sum + value, 0);
      return [
        reportText(device),
        ...values.map(value => signedReportMoney(value)),
        signedReportMoney(total),
      ];
    });

  return {
    headers: ["Device", ...circuitList, "Totale"],
    rows,
  };
}

function cashMoveSummaryRows(payload) {
  let inTotal = 0;
  let outTotal = 0;

  for (const move of payload.cashMoves?.cash_moves || []) {
    const amount = Number(move.amount || 0);
    if (move.direction === "out") outTotal += amount;
    else inTotal += amount;
  }

  return [[
    signedReportMoney(inTotal),
    signedReportMoney(outTotal),
    signedReportMoney(inTotal - outTotal),
  ]];
}

function ecommerceRowsForReport(payload) {
  return (payload.ecommerce?.ecommerce || []).map(row => [
    reportText(row.description || ""),
    signedReportMoney(row.amount),
  ]);
}

function sumRows(rows, selector) {
  return (rows || []).reduce((total, row) => total + Number(selector(row) || 0), 0);
}

function reportPaymentTotal(items, sign = 1) {
  let total = 0;
  for (const item of items || []) {
    for (const payment of item.payments || []) {
      total += Number(payment.amount || 0) * sign;
    }
  }
  return total;
}

function buildReportBodyHtml(payload) {
  const totals = payload.preview?.totals || {};
  const receiptTotal = sumRows(payload.receipts || [], row => row.amount);
  const ecommerceTotal = sumRows(payload.ecommerce?.ecommerce || [], row => row.amount);
  const depositTotal = Number(payload.deposits?.totals?.total_amount || 0);
  const salesTotal = reportPaymentTotal(payload.sales?.sales || [], 1);
  const expensesTotal = reportPaymentTotal(payload.expenses?.expenses || [], -1);
  const totalGiornata = salesTotal + ecommerceTotal + receiptTotal + expensesTotal;
  const saleGroups = reportPaymentGroups(payload.sales?.sales || [], "sale", payload);
  const expenseRows = paymentRowsForReport(payload.expenses?.expenses || [], "expense", payload);
  const posRecap = posRecapRows(payload);
  const closingHeaders = priVaultUnlocked ? [] : ["Voce", "Importo"];
  const deliveredTotal = priVaultUnlocked ? totals.incasso_consegnato : totals.valore_atteso_cassetto;
  const closingRows = [
    [reportText("Totale di giornata"), signedReportMoney(totalGiornata)],
    [reportText("Totale pagamenti elettronici"), signedReportMoney(totals.totale_incassi_elettronici)],
    [reportText("Totale atteso nel cassetto"), signedReportMoney(totals.valore_atteso_cassetto)],
    [reportText("Totale consegnato"), signedReportMoney(deliveredTotal)],
    [reportText("Totale Versabile"), signedReportMoney(totals.versabile_giornata)],
  ];
  if (priVaultUnlocked) {
    closingRows.push(
      [reportText("Totale x"), signedReportMoney(reportPaymentFlagTotal(payload.sales?.sales || [], "x"))],
      [reportText("Totale +"), signedReportMoney(reportPaymentFlagTotal(payload.sales?.sales || [], "+"))],
    );
  }
  closingRows.push([reportText("Delta quadratura"), signedReportMoney(totals.delta_quadratura)]);

  return `
    <header class="print-report-header">
      <div>
        <h1>${escapeHtml(reportTitleText())}</h1>
        <p>Generato il ${escapeHtml(formatDateTimeIT(new Date().toISOString()))}</p>
      </div>
      <div class="print-report-brand">LD Enoteca</div>
    </header>

    <section class="print-kpi-grid">
      <div class="print-kpi">
        <span>Differenza fondo cassa</span>
        <strong>${signedReportMoney(totals.delta_fondo)}</strong>
      </div>
      <div class="print-kpi">
        <span>Corrispettivi</span>
        <strong>${signedReportMoney(receiptTotal || totals.total_corrispettivi)}</strong>
      </div>
      <div class="print-kpi">
        <span>Versamenti</span>
        <strong>${signedReportMoney(depositTotal || totals.totale_versato_oggi)}</strong>
      </div>
      <div class="print-kpi">
        <span>E-commerce</span>
        <strong>${signedReportMoney(ecommerceTotal)}</strong>
      </div>
    </section>

    <main class="print-report-layout">
      <div class="print-band band-incassi">
        ${reportTable("Incassi", ["Descrizione", "Importo"], saleGroups.primary)}
        ${reportTable("Incassi", ["Descrizione", "Importo"], saleGroups.privateRows)}
      </div>
      <div class="print-band band-spese">
        ${reportTable("E-commerce", ["Descrizione", "Importo"], ecommerceRowsForReport(payload))}
        ${reportTable("Spese", ["Descrizione", "Importo"], expenseRows)}
      </div>
      <div class="print-band band-chiusura">
        <div>
          ${reportTable("POS", posRecap.headers, posRecap.rows)}
          ${reportTable("Movimenti di cassa e spicci", ["Tot Versamenti", "Tot Prelievi", "Tot Movimenti"], cashMoveSummaryRows(payload))}
        </div>
        ${reportTable("Chiusura", closingHeaders, closingRows)}
      </div>
    </main>
  `;
}

function buildCompleteDayReportHtml(payload) {
  return `
<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <title>${escapeHtml(reportTitleText())}</title>
  <style>${completeDayReportCss()}</style>
</head>
<body>
  <div class="screen-actions">
    <button onclick="window.print()">Stampa</button>
  </div>
  ${buildReportBodyHtml(payload)}
</body>
</html>`;
}

function completeDayReportCss() {
  return `
    @page { size: A4; margin: 11mm; }
    * { box-sizing: border-box; }
    body { font-family: Arial, sans-serif; color: #1c1c1c; font-size: 10.5px; margin: 0; background: #fff; }
    .screen-actions { margin: 12px 0; }
    .screen-actions button { padding: 7px 12px; }
    .print-report-header { display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 2px solid #222; padding-bottom: 8px; margin-bottom: 10px; }
    .print-report-header h1 { font-size: 21px; margin: 0; letter-spacing: 0; }
    .print-report-header p { margin: 4px 0 0; color: #666; }
    .print-report-brand { font-weight: 700; border: 1px solid #222; padding: 7px 10px; }
    .print-kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; margin: 10px 0; }
    .print-kpi { border: 1px solid #222; padding: 7px; min-height: 48px; }
    .print-kpi span { display: block; color: #555; font-size: 9px; text-transform: uppercase; }
    .print-kpi strong { display: block; text-align: right; margin-top: 7px; font-size: 14px; }
    .print-report-layout { display: grid; grid-template-rows: 40fr 28fr 20fr; gap: 7px; height: 238mm; }
    .print-band { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; min-height: 0; }
    .band-chiusura > div { display: grid; grid-template-rows: 1fr auto; gap: 7px; min-height: 0; }
    .report-section { border: 1px solid #333; break-inside: avoid; background: #fff; }
    .report-section h2 { font-size: 12px; margin: 0; padding: 5px 7px; background: #efefef; border-bottom: 1px solid #333; }
    table { width: 100%; border-collapse: collapse; }
    th, td { border-bottom: 1px solid #d4d4d4; padding: 3px 5px; vertical-align: top; }
    th { background: #fafafa; font-weight: 700; text-align: left; }
    td:last-child, th:last-child { text-align: right; white-space: nowrap; }
    .band-chiusura .report-section:first-child th:not(:first-child),
    .band-chiusura .report-section:first-child td:not(:first-child) { text-align: right; white-space: nowrap; }
    .band-chiusura .report-section:last-child td { white-space: nowrap; }
    .band-chiusura .report-section:last-child td:first-child { text-align: left; }
    .band-chiusura .report-section:last-child td:last-child { text-align: right; font-weight: 700; }
    .muted { color: #777; text-align: center !important; }
    @media print {
      .screen-actions { display: none; }
      .report-section { page-break-inside: avoid; }
    }
  `;
}

async function openDayReport() {
  if (!currentDay) return;

  const payload = await collectCompleteDayReportPayload();
  const modalEl = document.getElementById("dayReportModal");
  if (!modalEl) {
    alert("Modale report non trovata");
    return;
  }

  const dateEl = document.getElementById("dayReportDate");
  if (dateEl) dateEl.textContent = reportDayLabel();

  const body = modalEl.querySelector(".modal-body");
  if (body) {
    const previewCss = completeDayReportCss()
      .replace(/@page\s*\{[^}]*\}/g, "")
      .replace(/body\s*\{/g, ".report-preview {");
    body.innerHTML = `<style>${previewCss}</style><div class="report-preview">${buildReportBodyHtml(payload)}</div>`;
  }

  bootstrap.Modal.getOrCreateInstance(modalEl).show();
}

async function printCompleteDayReport() {
  if (!currentDay) return;

  const payload = await collectCompleteDayReportPayload();
  const html = buildCompleteDayReportHtml(payload);
  const win = window.open("", "_blank");
  if (!win) {
    alert("Popup bloccato dal browser. Consenti i popup per stampare il report.");
    return;
  }

  win.document.open();
  win.document.write(html);
  win.document.close();
  win.focus();
  setTimeout(() => win.print(), 300);
}

function eur(v) {
  if (v === null || v === undefined) return "—";
  return Number(v).toLocaleString("it-IT", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
}

function row(label, value) {
  return `
    <tr>
      <td>${label}</td>
      <td class="text-end fw-semibold">€ ${eur(value)}</td>
    </tr>
  `;
}

function renderDayReport(d) {
  const data = d?.totals || d || {};

  document.getElementById("dayReportDate").textContent = currentDay || "—";

  // =========================
  // SEZIONE 1 - FONDO CASSA
  // =========================
  document.getElementById("dayReportMainTable").innerHTML = `
    ${row("Fondo iniziale", data.fondo_iniziale)}
    ${row("Fondo finale", data.fondo_finale)}
    <tr class="table-light">
      <td class="fw-bold">Delta fondo</td>
      <td class="text-end fw-bold">€ ${eur(data.delta_fondo)}</td>
    </tr>
  `;

  // =========================
  // SEZIONE 2 - SPICCI
  // =========================
  document.getElementById("dayReportVersabileTable").innerHTML = `
    ${row("Prelievi di spicci", data.spicci_prelievi)}
    ${row("Versamenti di spicci", data.spicci_versamenti)}
    <tr class="table-light">
      <td class="fw-bold">Delta spicci</td>
      <td class="text-end fw-bold">€ ${eur(data.saldo_spicci)}</td>
    </tr>
  `;

  // =========================
  // SEZIONE 3 - DETTAGLIO INCASSI
  // =========================
  document.getElementById("dayReportContantiTable").innerHTML = `
    ${row("Incassi cash", data.incassi_cash)}
    ${row("Incassi fuori cassa", data.incassi_fuori_cassa)}
    ${row("Incassi POS", data.incassi_pos)}
    ${row("Incassi bank", data.incassi_bank)}
    ${row("Incassi check", data.incassi_check)}
    ${row("Corrispettivi", data.total_corrispettivi)}
    <tr class="table-light">
      <td class="fw-bold">Totale incassi fisici</td>
      <td class="text-end fw-bold">€ ${eur(data.totale_incassi_fisici)}</td>
    </tr>
    <tr class="table-light">
      <td class="fw-bold">Totale incassi elettronici</td>
      <td class="text-end fw-bold">€ ${eur(data.totale_incassi_elettronici)}</td>
    </tr>
    <tr class="table-light">
      <td class="fw-bold">Totale incassi fuori cassa</td>
      <td class="text-end fw-bold">€ ${eur(data.totale_incassi_fuori_cassa)}</td>
    </tr>
  `;

  // =========================
  // SEZIONE 4 - DETTAGLIO SPESE
  // =========================
  document.getElementById("dayReportQuadraturaTable").innerHTML = `
    ${row("Spese cash", data.spese_cash)}
    ${row("Spese fuori cassa", data.spese_fuori_cassa)}
    ${row("Spese POS", data.spese_pos)}
    ${row("Spese bank", data.spese_bank)}
    <tr class="table-light">
      <td class="fw-bold">Totale spese fisiche</td>
      <td class="text-end fw-bold">€ ${eur(data.totale_spese_fisiche)}</td>
    </tr>
    <tr class="table-light">
      <td class="fw-bold">Totale spese elettroniche</td>
      <td class="text-end fw-bold">€ ${eur(data.totale_spese_elettroniche)}</td>
    </tr>
    <tr class="table-light">
      <td class="fw-bold">Totale spese fuori cassa</td>
      <td class="text-end fw-bold">€ ${eur(data.totale_spese_fuori_cassa)}</td>
    </tr>
  `;

  // =========================
  // SEZIONE 5 - DETTAGLIO CASSETTO
  // =========================
  document.getElementById("dayReportCassettoTable").innerHTML = `
    ${row("Totale incassi fisici", data.totale_incassi_fisici)}
    ${row("Totale incassi POS", data.totale_pos)}
    ${row("Totale spese fisiche", data.totale_spese_fisiche)}
    ${row("Totale spese POS", data.spese_pos)}
    ${row("Totale movimenti di cassa", data.saldo_movimenti_cassa)}
    ${row("Totale spicci", data.saldo_spicci)}
    <tr class="table-light">
      <td class="fw-bold">Atteso cassetto operativo</td>
      <td class="text-end fw-bold">€ ${eur(data.valore_atteso_cassetto)}</td>
    </tr>
  `;

  // =========================
  // SEZIONE 6 - DETTAGLIO QUADRATURA
  // =========================
  document.getElementById("dayReportDeltaTable").innerHTML = `
    ${row("Atteso cassetto", data.valore_atteso_cassetto)}
    ${row("Delta fondo", data.delta_fondo)}
    ${row("Incasso consegnato", data.incasso_consegnato)}
    <tr class="table-light">
      <td class="fw-bold">Delta quadratura</td>
      <td class="text-end fw-bold">€ ${eur(data.delta_quadratura)}</td>
    </tr>
  `;

  document.getElementById("dayReportNote").textContent = data.note || "—";
}

function closeContextMenu() {
  const menu = document.getElementById("contextMenu");
  if (!menu) return;

  menu.classList.add("d-none");
  menu.classList.remove("submenu-left");
  menu.style.visibility = "";
  currentContext = null;
}
