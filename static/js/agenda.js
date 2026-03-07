let currentDay = null;
let calendarInstance = null;

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

/* =========================
   API helpers
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

function loadPreview(dateStr) {
  fetch(`/cassa/api/day/${dateStr}/preview?view=fiscal`)
    .then(r => r.json())
    .then(data => {
      if (!data.ok) return;

      const t = data.totals || {};

      const q = (t.q ?? t.q_versabile ?? t.Q ?? t.versabile_giornata);
      const s = (t.s ?? t.s_versabile ?? t.S ?? t.saldo_versabile);
      const ic = (t.ic ?? t.IC ?? t.incasso_calcolato);
      const df = (t.delta_fondo ?? t.deltaFondo ?? t.df);
      const dq = (t.delta_quadratura ?? t.deltaQuadratura ?? t.dq);
      const fondoInit = (t.fondo_iniziale ?? t.opening_float ?? t.fondoIniziale);
      const fondoFin = (t.fondo_finale ?? t.fondoFinale);
      const sPrev = (t.saldo_versabile_precedente ?? t.saldo_versabile_init ?? t.saldoVersabilePrecedente);
      const totMov = (t.totale_movimenti ?? t.totMovimenti);
      const totVers = (t.totale_versato_oggi ?? t.totale_versamenti ?? t.totVersamenti);
      const cor = (t.total_corrispettivi ?? t.corrispettivi ?? t.corrispettivi_totali);
      const consegnato = (t.incasso_consegnato ?? t.incassoConsegnato);

      setText("kpiSaldoVersabileInit", _fmt2(sPrev));
      setText("kpiSaldoVersabileNew", _fmt2(s));
      setText("kpiVersabileGiornata", _fmt2(q));

      setText("kpiFondoIniziale", _fmt2(fondoInit));
      setText("kpiFondoFinale", _fmt2(fondoFin));

      setText("kpiIC", _fmt2(ic));
      setText("kpiDeltaFondo", _fmt2(df));
      setText("kpiDeltaQuadratura", _fmt2(dq));

      setText("kpiTotMovimenti", _fmt2(totMov));
      setText("kpiTotVersamenti", _fmt2(totVers));
      setText("kpiCorrispettivi", _fmt2(cor));
      setText("kpiIncassoConsegnato", _fmt2(consegnato));
    })
    .catch(err => console.error("loadPreview error:", err));
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

  decorateMonth(calendarInstance.currentYear, calendarInstance.currentMonth);
  loadDay(toLocalYMD(new Date()));
  startAssegniAutoRefresh();

  const opModalEl = document.getElementById("opModal");
  const opModal = opModalEl ? new bootstrap.Modal(opModalEl) : null;

  function openOpModal(type) {
    if (!opModal) return;

    setText("opModalTitle", type === "sale" ? "Nuovo incasso" : "Nuova spesa");

    const opType = document.getElementById("opType");
    const opAmount = document.getElementById("opAmount");
    const opDesc = document.getElementById("opDesc");
    const opFlag = document.getElementById("opFlag");
    const opCustomerId = document.getElementById("opCustomerId");
    const opCustomer = document.getElementById("opCustomer");
    const opOffCash = document.getElementById("opOffCash");
    const opOffCashWho = document.getElementById("opOffCashWho");
    const opOffCashBox = document.getElementById("opOffCashBox");

    const payCash = document.getElementById("payCash");
    const payPos = document.getElementById("payPos");
    const payBank = document.getElementById("payBank");
    const payCheck = document.getElementById("payCheck");
    const payPosBox = document.getElementById("payPosBox");
    const payBankBox = document.getElementById("payBankBox");
    const payCheckBox = document.getElementById("payCheckBox");

    if (opType) opType.value = type;
    if (opAmount) opAmount.value = "0,00";
    if (opDesc) opDesc.value = "";
    if (opFlag) opFlag.value = "*";
    if (opCustomerId) opCustomerId.value = "";
    if (opCustomer) opCustomer.value = "";
    if (opOffCash) opOffCash.checked = false;
    if (opOffCashWho) opOffCashWho.value = "";
    if (opOffCashBox) opOffCashBox.classList.add("d-none");

    if (payCash) payCash.checked = true;
    if (payPos) payPos.checked = false;
    if (payBank) payBank.checked = false;
    if (payCheck) payCheck.checked = false;

    if (payPosBox) payPosBox.classList.add("d-none");
    if (payBankBox) payBankBox.classList.add("d-none");
    if (payCheckBox) payCheckBox.classList.add("d-none");

    opModal.show();
  }

  /* stacked modals */
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

  /* dropdown flag */
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

  /* nuovo cliente */
  (function initCustomerNewModal() {
    const btnOpen = document.getElementById("btnCustomerNew");
    const modalEl = document.getElementById("customerNewModal");
    const saveBtn = document.getElementById("customerNewSaveBtn");

    const opCustomerInput = document.getElementById("opCustomer");
    const opCustomerIdInput = document.getElementById("opCustomerId");

    if (!btnOpen || !modalEl || !saveBtn || typeof bootstrap === "undefined") return;

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

    saveBtn.addEventListener("click", async () => {
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

      saveBtn.disabled = true;

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
        saveBtn.disabled = false;
      }
    });
  })();

  /* suggest cliente */
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

  /* ricerca cliente avanzata */
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

  document.getElementById("opAmount")?.addEventListener("blur", (e) => {
    const n = parseEuroToNumber(e.target.value);
    e.target.value = formatEuro2(n);
  });

  document.getElementById("opAmount")?.addEventListener("focus", (e) => {
    e.target.select?.();
  });

  document.getElementById("btnNewIncasso")?.addEventListener("click", () => openOpModal("sale"));
  document.getElementById("btnNewSpesa")?.addEventListener("click", () => openOpModal("expense"));

  document.getElementById("opOffCash")?.addEventListener("change", (e) => {
    const box = document.getElementById("opOffCashBox");
    if (!box) return;
    box.classList.toggle("d-none", !e.target.checked);
  });

  document.getElementById("payPos")?.addEventListener("change", (e) => {
    document.getElementById("payPosBox")?.classList.toggle("d-none", !e.target.checked);
  });

  document.getElementById("payBank")?.addEventListener("change", (e) => {
    document.getElementById("payBankBox")?.classList.toggle("d-none", !e.target.checked);
  });

  document.getElementById("payCheck")?.addEventListener("change", (e) => {
    document.getElementById("payCheckBox")?.classList.toggle("d-none", !e.target.checked);
  });
});

document.addEventListener("visibilitychange", function () {
  if (document.visibilityState === "visible") {
    loadAssegniScadenza(currentDay, false);
    startAssegniAutoRefresh();
  } else {
    stopAssegniAutoRefresh();
  }
});