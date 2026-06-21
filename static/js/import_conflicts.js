let currentConflict = null;

// Puoi impostare un default oppure leggere da querystring (?type=...)
// Se vuoi, possiamo anche farlo dinamico con una select in pagina.
const DEFAULT_TYPE = "CODICE_RIASSEGNATO_O_DESC_DISCORDANTE";

function qs(name) {
  const url = new URL(window.location.href);
  return url.searchParams.get(name);
}

const TYPE = qs("type") || DEFAULT_TYPE;

const elType = document.getElementById("conflict-type");
const elKeyBox = document.getElementById("key-box");
const elKey = document.getElementById("conflict-key");
const elCompare = document.getElementById("compare-box");
const elCsvFields = document.getElementById("csv-fields");
const elDbFields = document.getElementById("db-fields");
const elActions = document.getElementById("actions");
const elStatus = document.getElementById("status-line");
const elDebug = document.getElementById("debug-out");
const elPosition = document.getElementById("conflict-position");
const elTotal = document.getElementById("conflict-total");
const elDuplicates = document.getElementById("conflict-duplicates");

// Bottoni
const btnKeepCsv = document.getElementById("btn-keep-csv");
const btnKeepDb = document.getElementById("btn-keep-db");
const btnAlwaysCsv = document.getElementById("btn-always-csv");
const btnAlwaysDb = document.getElementById("btn-always-db");
const btnSkip = document.getElementById("btn-skip");

function setStatus(msg) {
  elStatus.textContent = msg || "";
}

function setTypeLabel(text, icon = "fa-solid fa-triangle-exclamation") {
  elType.innerHTML = `
    <i class="${icon}"></i>
    <span>${escapeHtml(text)}</span>
  `;
}

function setDebug(obj) {
  // Lasciato pronto: se vuoi sempre vedere il json, togli d-none.
  elDebug.textContent = JSON.stringify(obj, null, 2);
}

function setMetrics({ pendingCount = "-", currentPosition = "-", duplicateCount = "-" } = {}) {
  elTotal.textContent = pendingCount ?? "-";
  elPosition.textContent = currentPosition && pendingCount ? `${currentPosition}/${pendingCount}` : "-";
  elDuplicates.textContent = duplicateCount ?? "-";
}

function clearUI() {
  currentConflict = null;
  elCsvFields.innerHTML = "";
  elDbFields.innerHTML = "";
  elCompare.style.display = "none";
  elActions.style.display = "none";
  elKeyBox.style.display = "none";
  elKey.textContent = "";
}

function escapeHtml(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderFieldRow(label, value) {
  return `
    <div class="conflict-field-row">
      <div class="conflict-field-label">${escapeHtml(label)}</div>
      <div class="conflict-field-value">${escapeHtml(value)}</div>
    </div>`;
}

// payload atteso (esempio):
// payload: { cod_art, csv:{...}, db:{...} }
function renderBoxes(conflict) {
  const payload = conflict.payload || {};
  const csv = payload.csv || {};
  const db = payload.db || {};

  // Tipo conflitto
  setTypeLabel(`Tipo: ${conflict.type || "-"}`);

  // Dato certo (per ora cod_art, ma puoi estenderlo per altri tipi)
  const codArt = payload.cod_art || null;
  if (codArt) {
    elKeyBox.style.display = "block";
    elKey.textContent = codArt;
  } else {
    elKeyBox.style.display = "none";
    elKey.textContent = "";
  }

  // Campi: prendiamo l’unione delle chiavi (csv + db), ordinata
  const keys = Array.from(new Set([...Object.keys(csv), ...Object.keys(db)]))
    .sort((a, b) => a.localeCompare(b));

  if (keys.length === 0) {
    elCsvFields.innerHTML = `<div class="p-3 text-muted">Nessun campo disponibile.</div>`;
    elDbFields.innerHTML = `<div class="p-3 text-muted">Nessun campo disponibile.</div>`;
  } else {
    elCsvFields.innerHTML = keys.map(k => renderFieldRow(k, csv[k])).join("");
    elDbFields.innerHTML = keys.map(k => renderFieldRow(k, db[k])).join("");
  }

  elCompare.style.display = "block";
  elActions.style.display = "flex";
}

async function fetchJson(url, opts) {
  const res = await fetch(url, opts);

  // Se non è JSON (es. redirect a login -> HTML), lo intercettiamo
  const ct = res.headers.get("content-type") || "";
  if (!ct.includes("application/json")) {
    const text = await res.text();
    // redirect login tipico: HTML con /auth/login?next=...
    if (text.includes("/auth/login")) {
      throw new Error("Non autenticato: apri la pagina e rifai login, poi riprova.");
    }
    throw new Error("Risposta non JSON dal server.");
  }

  const data = await res.json();
  return data;
}

async function loadNext() {
  clearUI();
  setStatus("Caricamento prossimo conflitto...");

  try {
    const data = await fetchJson(`/settings/next_conflict?type=${encodeURIComponent(TYPE)}`);
    setMetrics({
      pendingCount: data.pending_count,
      currentPosition: data.current_position,
      duplicateCount: data.duplicate_count,
    });

    if (!data.ok) {
      setStatus("Errore: risposta ok=false");
      setTypeLabel("Errore", "fa-solid fa-circle-exclamation");
      setDebug(data);
      elDebug.classList.remove("d-none");
      return;
    }

    if (!data.conflict) {
      setTypeLabel(`Tipo: ${TYPE}`, "fa-solid fa-check");
      setStatus("Nessun conflitto rimanente.");
      // facoltativo: mostrare confetti / messaggio
      return;
    }

    currentConflict = data.conflict;

    // Debug opzionale
    // elDebug.classList.remove("d-none");
    // setDebug(currentConflict);

    renderBoxes(currentConflict);
    setStatus(`Conflitto #${currentConflict.id} pronto. I duplicati identici verranno risolti insieme.`);
  } catch (err) {
    setTypeLabel("Errore", "fa-solid fa-circle-exclamation");
    setStatus(String(err));
    elDebug.classList.remove("d-none");
    setDebug({ error: String(err) });
  }
}

async function resolve(action, mode = "CONDITIONAL") {
  if (!currentConflict) return;

  setStatus(`Invio risoluzione: ${action}${mode === "ALWAYS" ? " (sempre)" : ""}...`);

  try {
    const payload = { id: currentConflict.id, action, mode, resolve_identical: true };
    const res = await fetchJson("/settings/resolve_conflict", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    // Debug opzionale
    // elDebug.classList.remove("d-none");
    // setDebug(res);

    if (!res.ok) {
      setStatus("Errore: resolve ok=false");
      elDebug.classList.remove("d-none");
      setDebug(res);
      return;
    }

    const duplicateInfo = res.duplicates_resolved ? ` (${res.duplicates_resolved} conflitti identici ripuliti)` : "";
    setStatus(`Risoluzione applicata${duplicateInfo}. Carico il prossimo...`);
    await loadNext();
  } catch (err) {
    setStatus(String(err));
    elDebug.classList.remove("d-none");
    setDebug({ error: String(err) });
  }
}

btnKeepCsv.addEventListener("click", () => resolve("KEEP_CSV"));
btnKeepDb.addEventListener("click", () => resolve("KEEP_DB"));
btnAlwaysCsv.addEventListener("click", () => resolve("KEEP_CSV", "ALWAYS"));
btnAlwaysDb.addEventListener("click", () => resolve("KEEP_DB", "ALWAYS"));
btnSkip.addEventListener("click", () => resolve("SKIP"));

document.addEventListener("DOMContentLoaded", loadNext);
