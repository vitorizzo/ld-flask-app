/* static/js/automations_v2.js
 * UI Automations V2 - client
 * Usa:
 *   GET  /api/automations/capabilities
 *   GET  /api/automations
 *   POST /api/automations
 *
 * Nota: GET /api/automations/<id> attualmente risulta non disponibile (bug lato backend).
 * Questa UI funziona per: lista + nuova automazione + creazione.
 */

(() => {
  "use strict";

  // ---------- DOM helpers ----------
  const $ = (sel) => document.querySelector(sel);
  const el = (tag, attrs = {}, children = []) => {
    const n = document.createElement(tag);
    Object.entries(attrs).forEach(([k, v]) => {
      if (k === "class") n.className = v;
      else if (k === "text") n.textContent = v;
      else if (k.startsWith("on") && typeof v === "function") n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v);
    });
    children.forEach((c) => n.appendChild(c));
    return n;
  };

  const setOptions = (select, options, placeholder = "Seleziona...") => {
    select.innerHTML = "";
    select.appendChild(el("option", { value: "", text: placeholder }));
    options.forEach((opt) => {
      // opt può essere string oppure oggetto {value,label}
      const value = typeof opt === "string" ? opt : (opt.value ?? "");
      const label = typeof opt === "string" ? opt : (opt.label ?? opt.name ?? value);
      select.appendChild(el("option", { value, text: label }));
    });
  };

  const safeJsonParse = (txt) => {
    const trimmed = (txt ?? "").trim();
    if (!trimmed) return {};
    return JSON.parse(trimmed);
  };

  // ---------- API ----------
  const apiFetch = async (path, opts = {}) => {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      ...opts,
    });

    const contentType = res.headers.get("content-type") || "";
    let body;
    if (contentType.includes("application/json")) body = await res.json();
    else body = await res.text();

    if (!res.ok) {
      const msg = typeof body === "string" ? body : JSON.stringify(body);
      throw new Error(`HTTP ${res.status} - ${msg}`);
    }
    return body;
  };

  // ---------- State ----------
  const state = {
    capabilities: null,
    apps: [],                 // ["trello","slack",...]
    connectionsByApp: {},     // app -> [{id,name}...]
    triggersByApp: {},        // app -> ["moveCard", ...] o [{value,label}...]
    actionsByApp: {},         // app -> ["sendMessage", ...] o [{value,label}...]
    automations: [],          // list from GET /api/automations
    current: {
      id: null,               // selezionata (se implementeremo GET /<id>)
      isNew: true,
      name: "",
      enabled: true,
      trigger: {
        app: "",
        connection_id: "",
        type: "",
        config: {},
      },
      actions: [],            // [{app,type,config}]
    },
  };

  // ---------- UI: messages ----------
  const showEditorMessage = (type, text) => {
    const box = $("#editorMessages");
    if (!box) return;
    box.innerHTML = "";

    const cls =
      type === "success" ? "alert alert-success" :
      type === "warning" ? "alert alert-warning" :
      type === "danger" ? "alert alert-danger" :
      "alert alert-info";

    box.appendChild(el("div", { class: cls, role: "alert", text }));
  };

  // ---------- Capabilities parsing (robusto, senza assumere schema fisso) ----------
  const parseCapabilities = (cap) => {
    // Possibili shape gestite:
    // A) { apps: { trello: {connections:[], triggers:[], actions:[]}, slack:{...} } }
    // B) { trello: {connections:[], triggers:[], actions:[]}, slack:{...} }
    // C) { applications: [...] } (fallback minimale)
    const appsRoot =
      (cap && typeof cap === "object" && cap.apps && typeof cap.apps === "object") ? cap.apps :
      (cap && typeof cap === "object" && cap.applications && typeof cap.applications === "object") ? cap.applications :
      (cap && typeof cap === "object") ? cap :
      {};

    // Se appsRoot è un array, provo a estrarre name
    if (Array.isArray(appsRoot)) {
      const apps = appsRoot.map((a) => (typeof a === "string" ? a : a.name)).filter(Boolean);
      return { apps, connectionsByApp: {}, triggersByApp: {}, actionsByApp: {} };
    }

    const apps = Object.keys(appsRoot).filter((k) => typeof appsRoot[k] === "object");

    const connectionsByApp = {};
    const triggersByApp = {};
    const actionsByApp = {};

    for (const app of apps) {
      const node = appsRoot[app] || {};

      // connections
      const conns =
        node.connections ?? node.connection ?? node.available_connections ?? node.availableConnections ?? [];
      connectionsByApp[app] = Array.isArray(conns)
        ? conns.map((c) => {
            if (typeof c === "string") return { id: c, name: c };
            return {
              id: c.id ?? c.connection_id ?? c.value ?? "",
              name: c.name ?? c.label ?? c.title ?? String(c.id ?? c.value ?? ""),
            };
          }).filter((c) => c.id !== "")
        : [];

      // triggers
      const trigs = node.triggers ?? node.trigger_types ?? node.triggerTypes ?? [];
      triggersByApp[app] = Array.isArray(trigs)
        ? trigs.map((t) => {
            if (typeof t === "string") return { value: t, label: t };
            return { value: t.value ?? t.type ?? t.name ?? "", label: t.label ?? t.name ?? t.type ?? "" };
          }).filter((t) => t.value !== "")
        : [];

      // actions
      const acts = node.actions ?? node.action_types ?? node.actionTypes ?? [];
      actionsByApp[app] = Array.isArray(acts)
        ? acts.map((a) => {
            if (typeof a === "string") return { value: a, label: a };
            return { value: a.value ?? a.type ?? a.name ?? "", label: a.label ?? a.name ?? a.type ?? "" };
          }).filter((a) => a.value !== "")
        : [];
    }

    return { apps, connectionsByApp, triggersByApp, actionsByApp };
  };

  // ---------- UI wiring ----------
  const setEditorVisible = (isVisible) => {
    const empty = $("#editorEmptyState");
    const form = $("#editorForm");
    if (!empty || !form) return;

    if (isVisible) {
      empty.classList.add("d-none");
      form.classList.remove("d-none");
    } else {
      empty.classList.remove("d-none");
      form.classList.add("d-none");
    }
  };

  const renderAutomationList = () => {
    const list = $("#automationList");
    const count = $("#automationCount");
    const hint = $("#automationListHint");

    if (!list || !count || !hint) return;

    list.innerHTML = "";
    const items = filteredAutomations();
    count.textContent = String(items.length);

    if (items.length === 0) {
      hint.classList.remove("d-none");
      return;
    }
    hint.classList.add("d-none");

    items.forEach((a) => {
      // non assumiamo schema, ma ci aspettiamo almeno id e campi trigger_* (da to_dict)
      const id = a.id ?? a.automation_id ?? "";
      const triggerApp = a.trigger_app ?? a.triggerApp ?? "";
      const triggerType = a.trigger_type ?? a.triggerType ?? "";
      const createdAt = a.created_at ?? a.createdAt ?? "";

      const title = a.name ?? a.title ?? `${triggerApp}:${triggerType}`.trim();

      const row = el("button", {
        type: "button",
        class: "list-group-item list-group-item-action",
        onclick: () => onSelectAutomationFromList(a),
      }, [
        el("div", { class: "d-flex w-100 justify-content-between" }, [
          el("div", { class: "fw-semibold", text: title || `Automation #${id}` }),
          el("small", { class: "text-muted", text: createdAt ? String(createdAt) : "" }),
        ]),
        el("div", { class: "small text-muted", text: `Trigger: ${triggerApp || "?"} / ${triggerType || "?"}` }),
      ]);

      list.appendChild(row);
    });
  };

  const filteredAutomations = () => {
    const filterApp = ($("#filterTriggerApp")?.value ?? "").trim();
    const q = ($("#searchAutomation")?.value ?? "").trim().toLowerCase();

    return (state.automations || []).filter((a) => {
      const triggerApp = String(a.trigger_app ?? a.triggerApp ?? "").toLowerCase();
      const triggerType = String(a.trigger_type ?? a.triggerType ?? "").toLowerCase();
      const name = String(a.name ?? a.title ?? "").toLowerCase();

      if (filterApp && triggerApp !== filterApp.toLowerCase()) return false;
      if (!q) return true;
      return name.includes(q) || triggerApp.includes(q) || triggerType.includes(q) || String(a.id ?? "").includes(q);
    });
  };

  const populateFilterApps = () => {
    const sel = $("#filterTriggerApp");
    if (!sel) return;
    const apps = state.apps.map((a) => ({ value: a, label: a }));
    setOptions(sel, apps, "Tutte");
    sel.value = "";
  };

  const resetEditor = () => {
    state.current = {
      id: null,
      isNew: true,
      name: "",
      enabled: true,
      trigger: { app: "", connection_id: "", type: "", config: {} },
      actions: [],
    };

    $("#automationName").value = "";
    $("#automationEnabled").value = "true";
    $("#triggerApp").value = "";
    $("#triggerConnection").value = "";
    $("#triggerType").value = "";

    $("#triggerConnection").disabled = true;
    $("#triggerType").disabled = true;

    renderTriggerConfigEditor({});
    renderActions();
    showEditorMessage("info", "Nuova automazione: seleziona Trigger e aggiungi Actions.");
  };

  const onSelectAutomationFromList = async (a) => {
    // Per ora il backend non espone correttamente GET /api/automations/<id>
    // Quindi apriamo l’editor in modalità "readonly parziale" basata su to_dict.
    setEditorVisible(true);

    const id = a.id ?? a.automation_id ?? null;
    state.current.id = id;
    state.current.isNew = false;

    $("#automationName").value = a.name ?? a.title ?? "";
    $("#automationEnabled").value = String(a.enabled ?? true);

    const tApp = a.trigger_app ?? a.triggerApp ?? "";
    const tConn = a.trigger_connection_id ?? a.triggerConnectionId ?? "";
    const tType = a.trigger_type ?? a.triggerType ?? "";
    const tCfg = a.trigger_config ?? a.triggerConfig ?? {};

    state.current.trigger.app = tApp;
    state.current.trigger.connection_id = tConn;
    state.current.trigger.type = tType;
    state.current.trigger.config = tCfg;

    $("#triggerApp").value = tApp || "";
    onTriggerAppChanged(); // popola connessioni + trigger types
    $("#triggerConnection").value = tConn ? String(tConn) : "";
    $("#triggerType").value = tType || "";

    renderTriggerConfigEditor(tCfg || {});
    // Actions complete non disponibili senza to_full_dict() -> lasciamo vuote
    state.current.actions = [];
    renderActions();

    showEditorMessage(
      "warning",
      "Dettaglio Actions non disponibile finché non viene corretto l’endpoint GET /api/automations/<id>. Puoi comunque creare nuove automazioni."
    );
  };

  // ---------- Trigger editor ----------
  const onTriggerAppChanged = () => {
    const app = ($("#triggerApp")?.value ?? "").trim();
    const connSel = $("#triggerConnection");
    const trigSel = $("#triggerType");
    if (!connSel || !trigSel) return;

    if (!app) {
      connSel.disabled = true;
      trigSel.disabled = true;
      setOptions(connSel, [], "Seleziona...");
      setOptions(trigSel, [], "Seleziona...");
      return;
    }

    // connections
    const conns = (state.connectionsByApp[app] || []).map((c) => ({
      value: String(c.id),
      label: c.name || String(c.id),
    }));
    setOptions(connSel, conns, "Seleziona...");
    connSel.disabled = false;

    // triggers
    const trigs = (state.triggersByApp[app] || []).map((t) => ({
      value: String(t.value),
      label: t.label || String(t.value),
    }));
    setOptions(trigSel, trigs, "Seleziona...");
    trigSel.disabled = false;
  };

  const renderTriggerConfigEditor = (cfgObj) => {
    const container = $("#triggerConfigContainer");
    if (!container) return;
    container.innerHTML = "";

    const ta = el("textarea", {
      class: "form-control",
      id: "triggerConfigJson",
      rows: "5",
      placeholder: "{}",
    });
    ta.value = JSON.stringify(cfgObj || {}, null, 2);

    container.appendChild(ta);
    container.appendChild(el("div", { class: "form-text", text: "Inserisci JSON valido per trigger_config (opzionale)." }));
  };

  // ---------- Actions editor ----------
  const renderActions = () => {
    const container = $("#actionsContainer");
    if (!container) return;
    container.innerHTML = "";

    if (!state.current.actions.length) {
      container.appendChild(el("div", { class: "text-muted", text: "Nessuna action. Clicca “Aggiungi azione”." }));
      return;
    }

    state.current.actions.forEach((act, idx) => {
      const card = el("div", { class: "card" }, [
        el("div", { class: "card-body" }, [
          el("div", { class: "d-flex align-items-center justify-content-between mb-2" }, [
            el("div", { class: "fw-semibold", text: `Azione #${idx + 1}` }),
            el("div", { class: "d-flex gap-2" }, [
              el("button", {
                type: "button",
                class: "btn btn-sm btn-outline-secondary",
                onclick: () => moveAction(idx, -1),
                title: "Sposta su",
              }, [el("span", { text: "↑" })]),
              el("button", {
                type: "button",
                class: "btn btn-sm btn-outline-secondary",
                onclick: () => moveAction(idx, +1),
                title: "Sposta giù",
              }, [el("span", { text: "↓" })]),
              el("button", {
                type: "button",
                class: "btn btn-sm btn-outline-danger",
                onclick: () => removeAction(idx),
                title: "Rimuovi",
              }, [el("span", { text: "Rimuovi" })]),
            ]),
          ]),

          el("div", { class: "row g-3" }, [
            el("div", { class: "col-12 col-md-4" }, [
              el("label", { class: "form-label mb-1", text: "Applicazione" }),
              (() => {
                const sel = el("select", { class: "form-select", "data-idx": String(idx), "data-field": "app" });
                const apps = state.apps.map((a) => ({ value: a, label: a }));
                setOptions(sel, apps, "Seleziona...");
                sel.value = act.app || "";
                sel.addEventListener("change", onActionAppChanged);
                return sel;
              })(),
            ]),
            el("div", { class: "col-12 col-md-4" }, [
              el("label", { class: "form-label mb-1", text: "Action" }),
              (() => {
                const sel = el("select", { class: "form-select", "data-idx": String(idx), "data-field": "type" });
                // popolata in base all'app
                fillActionTypeOptions(sel, act.app || "");
                sel.value = act.type || "";
                sel.addEventListener("change", (e) => {
                  const i = Number(e.target.dataset.idx);
                  state.current.actions[i].type = e.target.value;
                });
                return sel;
              })(),
            ]),
            el("div", { class: "col-12 col-md-4" }, [
              el("label", { class: "form-label mb-1", text: "Config JSON" }),
              (() => {
                const ta = el("textarea", {
                  class: "form-control",
                  rows: "4",
                  "data-idx": String(idx),
                  "data-field": "config",
                  placeholder: "{}",
                });
                ta.value = JSON.stringify(act.config || {}, null, 2);
                ta.addEventListener("change", (e) => {
                  const i = Number(e.target.dataset.idx);
                  try {
                    state.current.actions[i].config = safeJsonParse(e.target.value);
                    showEditorMessage("info", "Config action aggiornata.");
                  } catch (err) {
                    showEditorMessage("danger", `JSON non valido nella action #${i + 1}: ${err.message}`);
                  }
                });
                return ta;
              })(),
            ]),
          ]),
        ]),
      ]);

      container.appendChild(card);
    });
  };

  const fillActionTypeOptions = (select, app) => {
    if (!select) return;
    if (!app) {
      setOptions(select, [], "Seleziona...");
      select.disabled = true;
      return;
    }
    const acts = (state.actionsByApp[app] || []).map((a) => ({ value: a.value, label: a.label }));
    setOptions(select, acts, "Seleziona...");
    select.disabled = false;
  };

  const onActionAppChanged = (e) => {
    const idx = Number(e.target.dataset.idx);
    const newApp = e.target.value;

    state.current.actions[idx].app = newApp;
    state.current.actions[idx].type = "";
    // aggiorno il select type nella stessa card
    const card = e.target.closest(".card-body");
    const typeSel = card?.querySelector('select[data-field="type"]');
    fillActionTypeOptions(typeSel, newApp);
    if (typeSel) typeSel.value = "";

    renderActions(); // re-render per coerenza
  };

  const addAction = () => {
    state.current.actions.push({ app: "", type: "", config: {} });
    renderActions();
  };

  const removeAction = (idx) => {
    state.current.actions.splice(idx, 1);
    renderActions();
  };

  const moveAction = (idx, delta) => {
    const ni = idx + delta;
    if (ni < 0 || ni >= state.current.actions.length) return;
    const tmp = state.current.actions[idx];
    state.current.actions[idx] = state.current.actions[ni];
    state.current.actions[ni] = tmp;
    renderActions();
  };

  // ---------- Save (create only) ----------
  const collectEditorData = () => {
    const name = ($("#automationName")?.value ?? "").trim();
    const enabled = ($("#automationEnabled")?.value ?? "true") === "true";

    const triggerApp = ($("#triggerApp")?.value ?? "").trim();
    const triggerConn = ($("#triggerConnection")?.value ?? "").trim();
    const triggerType = ($("#triggerType")?.value ?? "").trim();

    if (!triggerApp) throw new Error("Seleziona Trigger → Applicazione.");
    if (!triggerConn) throw new Error("Seleziona Trigger → Connessione.");
    if (!triggerType) throw new Error("Seleziona Trigger → Trigger.");

    const triggerCfgTxt = ($("#triggerConfigJson")?.value ?? "").trim();
    const triggerCfg = triggerCfgTxt ? safeJsonParse(triggerCfgTxt) : {};

    if (!Array.isArray(state.current.actions) || state.current.actions.length === 0) {
      throw new Error("Aggiungi almeno una action.");
    }

    state.current.actions.forEach((a, i) => {
      if (!a.app) throw new Error(`Action #${i + 1}: seleziona Applicazione.`);
      if (!a.type) throw new Error(`Action #${i + 1}: seleziona Action.`);
      if (a.config == null || typeof a.config !== "object") a.config = {};
    });

    // Backend create_automation si aspetta SOLO trigger + actions
    const payload = {
      trigger: {
        app: triggerApp,
        connection_id: Number(triggerConn),
        type: triggerType,
        config: triggerCfg,
      },
      actions: state.current.actions.map((a, idx) => ({
        app: a.app,
        type: a.type,
        order: idx + 1,
        config: a.config || {},
      })),
    };

    // name/enabled non sono gestiti dal backend in create_automation: li teniamo localmente
    // (li useremo quando aggiungeremo endpoint update)
    return { payload, meta: { name, enabled } };
  };

  const onSave = async () => {
    try {
      const { payload } = collectEditorData();

      showEditorMessage("info", "Salvataggio in corso...");
      const created = await apiFetch("/api/automations", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      showEditorMessage("success", `Automazione creata (id=${created.id ?? "?"}).`);
      await loadAutomations();
      // torna in modalità nuova (per evitare edit su endpoint incompleto)
      resetEditor();
    } catch (err) {
      showEditorMessage("danger", err.message);
    }
  };

  // ---------- Data loading ----------
  const loadCapabilities = async () => {
    const cap = await apiFetch("/api/automations/capabilities");
    state.capabilities = cap;

    const parsed = parseCapabilities(cap);
    state.apps = parsed.apps;
    state.connectionsByApp = parsed.connectionsByApp;
    state.triggersByApp = parsed.triggersByApp;
    state.actionsByApp = parsed.actionsByApp;

    // Popola selects
    const triggerAppSel = $("#triggerApp");
    if (triggerAppSel) {
      const apps = state.apps.map((a) => ({ value: a, label: a }));
      setOptions(triggerAppSel, apps, "Seleziona...");
    }

    populateFilterApps();
  };

  const loadAutomations = async () => {
    state.automations = await apiFetch("/api/automations");
    renderAutomationList();
  };

  // ---------- init ----------
  const bindEvents = () => {
    $("#btnNewAutomation")?.addEventListener("click", () => {
      setEditorVisible(true);
      resetEditor();
    });

    $("#btnRefreshList")?.addEventListener("click", async () => {
      try {
        await loadAutomations();
      } catch (err) {
        showEditorMessage("danger", err.message);
      }
    });

    $("#btnResetFilters")?.addEventListener("click", () => {
      if ($("#filterTriggerApp")) $("#filterTriggerApp").value = "";
      if ($("#searchAutomation")) $("#searchAutomation").value = "";
      renderAutomationList();
    });

    $("#filterTriggerApp")?.addEventListener("change", renderAutomationList);
    $("#searchAutomation")?.addEventListener("input", renderAutomationList);

    $("#triggerApp")?.addEventListener("change", () => {
      onTriggerAppChanged();
      // reset dipendenti
      $("#triggerConnection").value = "";
      $("#triggerType").value = "";
      renderTriggerConfigEditor({});
    });

    $("#triggerType")?.addEventListener("change", () => {
      // per ora config è JSON libero
      // in futuro: render campi dinamici in base al trigger selezionato + capabilities schema
    });

    $("#btnAddAction")?.addEventListener("click", addAction);
    $("#btnSaveAutomation")?.addEventListener("click", onSave);

    $("#btnCancelEdit")?.addEventListener("click", () => {
      setEditorVisible(false);
      showEditorMessage("info", "");
    });

    $("#btnDeleteAutomation")?.addEventListener("click", () => {
      showEditorMessage("warning", "Eliminazione non implementata (manca endpoint backend).");
    });

    $("#btnEnd")?.addEventListener("click", () => {
      // Azione neutra: torna alla lista
      setEditorVisible(false);
    });
  };

  const start = async () => {
    bindEvents();
    setEditorVisible(false);

    try {
      await loadCapabilities();
      await loadAutomations();
    } catch (err) {
      // Se capabilities fallisce, la UI non può popolare tendine
      showEditorMessage("danger", `Errore bootstrap UI: ${err.message}`);
    }
  };

  document.addEventListener("DOMContentLoaded", start);
})();
