// static/js/automations_v2.js
(() => {
  "use strict";

  // ---------- Helpers ----------
  const qs = (sel, root = document) => root.querySelector(sel);
  const qsa = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const toast = (msg, type = "info") => {
    // Fallback minimal: alert (you can replace with Bootstrap toast if present)
    console[type === "error" ? "error" : "log"](msg);
  };

  const safeJsonParse = (txt) => {
    if (txt === null || txt === undefined) return null;
    const s = String(txt).trim();
    if (!s) return null;
    try {
      return JSON.parse(s);
    } catch (e) {
      return null;
    }
  };

  const formatJson = (obj) => {
    if (obj === undefined || obj === null) return "";
    try {
      return JSON.stringify(obj, null, 2);
    } catch {
      return "";
    }
  };

  const escapeHtml = (s) =>
    String(s ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");

  // ---------- API ----------
  const apiFetch = async (url, opts = {}) => {
    const res = await fetch(url, {
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        ...(opts.headers || {}),
      },
      ...opts,
    });

    if (!res.ok) {
      const msg = await res.text().catch(() => "");
      throw new Error(msg || `HTTP ${res.status}`);
    }

    // Some endpoints may return empty body
    const ct = res.headers.get("content-type") || "";
    if (!ct.includes("application/json")) return null;
    return res.json();
  };

  // Slack channels helper (for trigger config UI)
  const slackChannelsCache = new Map(); // key: connectionId -> array of channels

  const fetchSlackChannels = async (connectionId) => {
    if (!connectionId) return [];
    if (slackChannelsCache.has(connectionId)) return slackChannelsCache.get(connectionId);

    // Primary (preferred) endpoint (to implement in backend):
    // GET /api/connections/slack/<connectionId>/channels  -> [{id,name,is_private}]
    // Fallback endpoint:
    // GET /api/slack/channels?connection_id=<connectionId>
    const tryFetch = async (url) => {
      const res = await fetch(url, { headers: { Accept: "application/json" } });
      if (!res.ok) {
        const msg = await res.text().catch(() => "");
        const err = new Error(msg || `HTTP ${res.status}`);
        err.status = res.status;
        throw err;
      }
      return res.json();
    };

    let channels = [];
    try {
      channels = await tryFetch(`/api/connections/slack/${encodeURIComponent(connectionId)}/channels`);
    } catch (e1) {
      if (e1 && e1.status === 404) {
        channels = await tryFetch(`/api/slack/channels?connection_id=${encodeURIComponent(connectionId)}`);
      } else {
        throw e1;
      }
    }

    if (!Array.isArray(channels)) channels = [];
    // Normalize
    channels = channels
      .filter((c) => c && typeof c === "object")
      .map((c) => ({
        id: String(c.id || c.channel_id || ""),
        name: String(c.name || c.label || c.display_name || c.id || ""),
        is_private: Boolean(c.is_private ?? c.isPrivate ?? c.private ?? false),
      }))
      .filter((c) => c.id);

    slackChannelsCache.set(connectionId, channels);
    return channels;
  };

  const clearSlackChannelsCache = (connectionId) => {
    if (!connectionId) return;
    slackChannelsCache.delete(connectionId);
  };

  // ---------- State ----------
  let capabilities = null;
  let automations = [];
  let connectionsSlack = [];

  let currentAutomationId = null;
  let currentActionEditingIndex = null;

  // ---------- DOM ----------
  const el = {
    list: qs("#automationsList"),
    btnNew: qs("#btnNewAutomation"),
    btnSave: qs("#btnSaveAutomation"),
    btnDelete: qs("#btnDeleteAutomation"),

    formTitle: qs("#automationTitle"),
    formDescription: qs("#automationDescription"),
    formEnabled: qs("#automationEnabled"),

    triggerApp: qs("#triggerApp"),
    triggerConn: qs("#triggerConnection"),
    triggerType: qs("#triggerType"),
    triggerConfigEditor: qs("#triggerConfigEditor"),
    triggerConfigJson: qs("#triggerConfigJson"),

    actionsList: qs("#actionsList"),
    btnAddAction: qs("#btnAddAction"),

    actionEditor: qs("#actionEditor"),
    actionEditorApp: qs("#actionApp"),
    actionEditorType: qs("#actionType"),
    actionEditorConfig: qs("#actionConfigJson"),
    btnSaveAction: qs("#btnSaveAction"),
    btnCancelAction: qs("#btnCancelAction"),

    debugBox: qs("#debugBox"),
  };

  // Shortcuts for compatibility with your original variable names
  const triggerAppEl = el.triggerApp;
  const triggerConnEl = el.triggerConn;
  const triggerTypeEl = el.triggerType;
  const triggerConfigEditor = el.triggerConfigEditor;
  const triggerConfigJson = el.triggerConfigJson;

  // ---------- Rendering ----------
  const renderAutomationList = () => {
    if (!el.list) return;
    el.list.innerHTML = "";

    automations.forEach((a) => {
      const row = document.createElement("div");
      row.className = "automation-row d-flex justify-content-between align-items-center p-2 border rounded mb-2";

      const left = document.createElement("div");
      left.className = "d-flex flex-column";
      left.innerHTML = `
        <div class="fw-semibold">${escapeHtml(a.name || "(senza nome)")}</div>
        <div class="text-muted small">${escapeHtml(a.description || "")}</div>
        <div class="small">
          <span class="badge bg-secondary me-1">${escapeHtml(a.trigger_app || "")}</span>
          <span class="badge bg-secondary">${escapeHtml(a.trigger_type || "")}</span>
          <span class="ms-2 ${a.enabled ? "text-success" : "text-danger"}">${a.enabled ? "ON" : "OFF"}</span>
        </div>
      `;

      const right = document.createElement("div");
      right.className = "d-flex gap-2";
      const btnEdit = document.createElement("button");
      btnEdit.type = "button";
      btnEdit.className = "btn btn-sm btn-outline-primary";
      btnEdit.textContent = "Modifica";
      btnEdit.addEventListener("click", () => loadAutomation(a.id));
      right.appendChild(btnEdit);

      row.appendChild(left);
      row.appendChild(right);

      el.list.appendChild(row);
    });
  };

  const renderTriggerAppOptions = () => {
    triggerAppEl.innerHTML = "";
    (capabilities?.apps || []).forEach((app) => {
      const opt = document.createElement("option");
      opt.value = app;
      opt.textContent = app;
      triggerAppEl.appendChild(opt);
    });
  };

  const renderTriggerTypeOptions = () => {
    const app = triggerAppEl.value;
    triggerTypeEl.innerHTML = "";
    const list = (capabilities?.triggers_by_app?.[app] || []).slice();
    list.forEach((t) => {
      const opt = document.createElement("option");
      opt.value = t;
      opt.textContent = t;
      triggerTypeEl.appendChild(opt);
    });
  };

  const renderTriggerConnectionOptions = () => {
    const app = triggerAppEl.value;
    triggerConnEl.innerHTML = "";
    const opt0 = document.createElement("option");
    opt0.value = "";
    opt0.textContent = "(nessuna)";
    triggerConnEl.appendChild(opt0);

    // currently only slack connections are exposed in UI
    if (app === "slack") {
      connectionsSlack.forEach((c) => {
        const opt = document.createElement("option");
        opt.value = c.id;
        opt.textContent = c.name || `Slack #${c.id}`;
        triggerConnEl.appendChild(opt);
      });
    }
  };

  const renderTriggerConfigEditor = (cfgObj) => {
    triggerConfigJson.value = formatJson(cfgObj || null);

    const triggerApp = triggerAppEl.value;
    const triggerType = triggerTypeEl.value;

    // Reset advanced UI
    triggerConfigEditor.innerHTML = "";
    triggerConfigEditor.appendChild(triggerConfigJson);

    // Only Slack "message" gets the assisted editor (channels + keywords)
    if (!(triggerApp === "slack" && triggerType === "message")) {
      triggerConfigJson.style.display = "";
      return;
    }

    // Hide raw JSON textarea but keep it as source-of-truth for save payload.
    triggerConfigJson.style.display = "none";

    const parseCfg = () => {
      const raw = triggerConfigJson.value?.trim();
      if (!raw) return { channels: [], keywords: [] };
      try {
        const obj = JSON.parse(raw);
        const channels = Array.isArray(obj?.channels) ? obj.channels : [];
        const keywords = Array.isArray(obj?.keywords) ? obj.keywords : [];
        return { channels, keywords };
      } catch {
        return { channels: [], keywords: [] };
      }
    };

    const state = parseCfg();

    const normalizeChannels = (arr) =>
      (Array.isArray(arr) ? arr : [])
        .map((c) => {
          if (typeof c === "string") return { id: c, label: c };
          return {
            id: String(c?.id || ""),
            label: String(c?.label || c?.name || c?.id || ""),
            is_private: Boolean(c?.is_private ?? c?.isPrivate ?? false),
          };
        })
        .filter((c) => c.id);

    const normalizeKeywords = (arr) =>
      (Array.isArray(arr) ? arr : [])
        .map((k) => String(k || "").trim())
        .filter(Boolean);

    let channelsSelected = normalizeChannels(state.channels);
    let keywordsSelected = normalizeKeywords(state.keywords);

    const syncTextarea = () => {
      triggerConfigJson.value = formatJson({ channels: channelsSelected, keywords: keywordsSelected });
    };

    const chip = (label, onRemove) => {
      const el = document.createElement("span");
      el.className = "chip";
      el.style.display = "inline-flex";
      el.style.alignItems = "center";
      el.style.gap = "6px";
      el.style.padding = "4px 8px";
      el.style.border = "1px solid var(--bs-border-color, #ddd)";
      el.style.borderRadius = "999px";
      el.style.marginRight = "6px";
      el.style.marginBottom = "6px";
      el.textContent = label;

      const x = document.createElement("button");
      x.type = "button";
      x.className = "btn btn-sm btn-outline-secondary";
      x.textContent = "×";
      x.style.borderRadius = "999px";
      x.style.lineHeight = "1";
      x.style.padding = "0 6px";

      x.addEventListener("click", () => onRemove());
      el.appendChild(x);
      return el;
    };

    const renderChips = (container, items, getLabel, onRemoveAt) => {
      container.innerHTML = "";
      items.forEach((it, idx) => {
        container.appendChild(chip(getLabel(it), () => onRemoveAt(idx)));
      });
    };

    const section = (title) => {
      const wrap = document.createElement("div");
      wrap.className = "mb-3";

      const h = document.createElement("div");
      h.className = "form-label fw-semibold";
      h.textContent = title;

      wrap.appendChild(h);
      return wrap;
    };

    // --- Channels ---
    const secChannels = section("Canali (Slack)");
    const rowCh = document.createElement("div");
    rowCh.className = "d-flex gap-2 align-items-end flex-wrap";

    const selWrap = document.createElement("div");
    selWrap.className = "flex-grow-1";
    const sel = document.createElement("select");
    sel.className = "form-select";
    sel.innerHTML = `<option value="">(carica i canali...)</option>`;
    selWrap.appendChild(sel);

    const btnRefresh = document.createElement("button");
    btnRefresh.type = "button";
    btnRefresh.className = "btn btn-outline-secondary";
    btnRefresh.textContent = "Aggiorna canali";

    const btnAdd = document.createElement("button");
    btnAdd.type = "button";
    btnAdd.className = "btn btn-primary";
    btnAdd.textContent = "Aggiungi canale";

    rowCh.appendChild(selWrap);
    rowCh.appendChild(btnRefresh);
    rowCh.appendChild(btnAdd);

    const chipsChannels = document.createElement("div");
    chipsChannels.className = "mt-2";

    secChannels.appendChild(rowCh);
    secChannels.appendChild(chipsChannels);

    // --- Keywords ---
    const secKeywords = section("Keyword");
    const rowKw = document.createElement("div");
    rowKw.className = "d-flex gap-2 align-items-end flex-wrap";

    const kwWrap = document.createElement("div");
    kwWrap.className = "flex-grow-1";
    const kwInput = document.createElement("input");
    kwInput.type = "text";
    kwInput.className = "form-control";
    kwInput.placeholder = "es: ordine";
    kwWrap.appendChild(kwInput);

    const btnKwAdd = document.createElement("button");
    btnKwAdd.type = "button";
    btnKwAdd.className = "btn btn-primary";
    btnKwAdd.textContent = "Aggiungi";

    rowKw.appendChild(kwWrap);
    rowKw.appendChild(btnKwAdd);

    const chipsKeywords = document.createElement("div");
    chipsKeywords.className = "mt-2";

    secKeywords.appendChild(rowKw);
    secKeywords.appendChild(chipsKeywords);

    // Mount
    triggerConfigEditor.insertBefore(secChannels, triggerConfigJson);
    triggerConfigEditor.insertBefore(secKeywords, triggerConfigJson);

    const renderAll = () => {
      renderChips(
        chipsChannels,
        channelsSelected,
        (c) => (c.is_private ? `🔒 ${c.label}` : c.label),
        (idx) => {
          channelsSelected.splice(idx, 1);
          syncTextarea();
          renderAll();
        }
      );

      renderChips(
        chipsKeywords,
        keywordsSelected,
        (k) => k,
        (idx) => {
          keywordsSelected.splice(idx, 1);
          syncTextarea();
          renderAll();
        }
      );
    };

    const loadChannelsIntoSelect = async () => {
      const connId = triggerConnEl.value;
      sel.innerHTML = `<option value="">(seleziona...)</option>`;
      if (!connId) {
        sel.innerHTML = `<option value="">(seleziona prima una connessione)</option>`;
        return;
      }

      try {
        const channels = await fetchSlackChannels(connId);
        if (!channels.length) {
          sel.innerHTML = `<option value="">(nessun canale trovato)</option>`;
          return;
        }
        const opts = channels
          .map(
            (c) =>
              `<option value="${c.id}" data-private="${c.is_private ? "1" : "0"}">${
                c.is_private ? "🔒 " : ""
              }${escapeHtml(c.name)}</option>`
          )
          .join("");
        sel.innerHTML = `<option value="">(seleziona...)</option>` + opts;
      } catch (err) {
        console.error("Slack channels load failed:", err);
        sel.innerHTML = `<option value="">(errore caricamento canali)</option>`;
      }
    };

    btnRefresh.addEventListener("click", async () => {
      const connId = triggerConnEl.value;
      clearSlackChannelsCache(connId);
      await loadChannelsIntoSelect();
    });

    btnAdd.addEventListener("click", () => {
      const id = sel.value;
      if (!id) return;
      const opt = sel.options[sel.selectedIndex];
      const label = (opt?.textContent || id).replace(/^🔒\s*/, "");
      const is_private = opt?.dataset?.private === "1";

      if (channelsSelected.some((c) => c.id === id)) return;
      channelsSelected.push({ id, label, is_private });
      syncTextarea();
      renderAll();
    });

    const addKeyword = () => {
      const v = (kwInput.value || "").trim();
      if (!v) return;
      if (keywordsSelected.includes(v)) {
        kwInput.value = "";
        return;
      }
      keywordsSelected.push(v);
      kwInput.value = "";
      syncTextarea();
      renderAll();
    };

    btnKwAdd.addEventListener("click", addKeyword);
    kwInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        addKeyword();
      }
    });

    // Initial render
    syncTextarea();
    renderAll();
    loadChannelsIntoSelect();
  };

  const renderActionsList = (actions) => {
    el.actionsList.innerHTML = "";

    (actions || []).forEach((a, idx) => {
      const row = document.createElement("div");
      row.className = "action-row d-flex justify-content-between align-items-center p-2 border rounded mb-2";

      const left = document.createElement("div");
      left.className = "d-flex flex-column";
      left.innerHTML = `
        <div class="fw-semibold">${escapeHtml(a.action_app || "")} / ${escapeHtml(a.action_type || "")}</div>
        <div class="text-muted small">order_index=${idx}</div>
      `;

      const right = document.createElement("div");
      right.className = "d-flex gap-2";

      const btnEdit = document.createElement("button");
      btnEdit.type = "button";
      btnEdit.className = "btn btn-sm btn-outline-primary";
      btnEdit.textContent = "Modifica";
      btnEdit.addEventListener("click", () => openActionEditor(idx));

      const btnDel = document.createElement("button");
      btnDel.type = "button";
      btnDel.className = "btn btn-sm btn-outline-danger";
      btnDel.textContent = "Rimuovi";
      btnDel.addEventListener("click", () => deleteAction(idx));

      right.appendChild(btnEdit);
      right.appendChild(btnDel);

      row.appendChild(left);
      row.appendChild(right);

      el.actionsList.appendChild(row);
    });
  };

  const renderActionEditorOptions = () => {
    const apps = (capabilities?.apps || []).slice();

    el.actionEditorApp.innerHTML = "";
    apps.forEach((app) => {
      const opt = document.createElement("option");
      opt.value = app;
      opt.textContent = app;
      el.actionEditorApp.appendChild(opt);
    });

    const updateActionTypes = () => {
      const app = el.actionEditorApp.value;
      const types = (capabilities?.actions_by_app?.[app] || []).slice();
      el.actionEditorType.innerHTML = "";
      types.forEach((t) => {
        const opt = document.createElement("option");
        opt.value = t;
        opt.textContent = t;
        el.actionEditorType.appendChild(opt);
      });
    };

    el.actionEditorApp.addEventListener("change", updateActionTypes);
    updateActionTypes();
  };

  // ---------- Data operations ----------
  const loadCapabilities = async () => {
    capabilities = await apiFetch("/api/automations/capabilities");
  };

  const loadAutomations = async () => {
    automations = (await apiFetch("/api/automations")) || [];
  };

  const loadConnections = async () => {
    // For now only Slack connections are used by UI
    connectionsSlack = (await apiFetch("/api/connections/slack")) || [];
  };

  const loadAutomation = async (id) => {
    const auto = await apiFetch(`/api/automations/${id}`);
    currentAutomationId = id;

    // Fill form
    el.formTitle.value = auto.name || "";
    el.formDescription.value = auto.description || "";
    el.formEnabled.checked = !!auto.enabled;

    // Trigger
    triggerAppEl.value = auto.trigger_app || (capabilities?.apps?.[0] || "");
    renderTriggerTypeOptions();
    renderTriggerConnectionOptions();

    triggerConnEl.value = auto.trigger_connection || "";
    triggerTypeEl.value = auto.trigger_type || "";

    renderTriggerConfigEditor(auto.trigger_config || null);

    // Actions
    window.__currentActions = (auto.actions || []).slice();
    renderActionsList(window.__currentActions);

    // Hide action editor
    closeActionEditor();
  };

  const newAutomation = () => {
    currentAutomationId = null;
    el.formTitle.value = "";
    el.formDescription.value = "";
    el.formEnabled.checked = true;

    triggerAppEl.value = capabilities?.apps?.[0] || "slack";
    renderTriggerTypeOptions();
    renderTriggerConnectionOptions();

    triggerConnEl.value = "";
    triggerTypeEl.value = (capabilities?.triggers_by_app?.[triggerAppEl.value] || [])[0] || "";
    renderTriggerConfigEditor(null);

    window.__currentActions = [];
    renderActionsList(window.__currentActions);

    closeActionEditor();
  };

  const buildAutomationPayload = () => {
    return {
      name: el.formTitle.value.trim(),
      description: el.formDescription.value.trim(),
      enabled: !!el.formEnabled.checked,
      trigger: {
        app: triggerAppEl.value,
        connection_id: triggerConnEl.value ? Number(triggerConnEl.value) : null,
        type: triggerTypeEl.value,
        config: safeJsonParse(triggerConfigJson.value),
      },
      actions: (window.__currentActions || []).map((a, idx) => ({
        action_app: a.action_app,
        action_type: a.action_type,
        action_config: a.action_config || null,
        order_index: idx,
        enabled: a.enabled !== false,
      })),
    };
  };

  const saveAutomation = async () => {
    const payload = buildAutomationPayload();

    if (!payload.name) {
      toast("Nome automazione obbligatorio", "error");
      return;
    }

    try {
      await apiFetch("/api/automations", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      await loadAutomations();
      renderAutomationList();
      toast("Automazione salvata", "info");
    } catch (e) {
      console.error(e);
      toast(`Errore salvataggio: ${e.message}`, "error");
    }
  };

  // ---------- Actions editor ----------
  const openActionEditor = (idx) => {
    currentActionEditingIndex = idx;
    const a = window.__currentActions[idx];

    el.actionEditorApp.value = a.action_app;
    // Trigger change to populate types list
    el.actionEditorApp.dispatchEvent(new Event("change"));
    el.actionEditorType.value = a.action_type;

    el.actionEditorConfig.value = formatJson(a.action_config || null);

    el.actionEditor.style.display = "";
  };

  const closeActionEditor = () => {
    currentActionEditingIndex = null;
    el.actionEditor.style.display = "none";
    el.actionEditorConfig.value = "";
  };

  const addAction = () => {
    const app = el.actionEditorApp.value;
    const type = el.actionEditorType.value;

    window.__currentActions = window.__currentActions || [];
    window.__currentActions.push({
      action_app: app,
      action_type: type,
      action_config: null,
      enabled: true,
    });

    renderActionsList(window.__currentActions);
    openActionEditor(window.__currentActions.length - 1);
  };

  const saveAction = () => {
    if (currentActionEditingIndex === null) return;
    const idx = currentActionEditingIndex;

    const app = el.actionEditorApp.value;
    const type = el.actionEditorType.value;
    const cfg = safeJsonParse(el.actionEditorConfig.value);

    window.__currentActions[idx].action_app = app;
    window.__currentActions[idx].action_type = type;
    window.__currentActions[idx].action_config = cfg;

    renderActionsList(window.__currentActions);
    closeActionEditor();
  };

  const deleteAction = (idx) => {
    window.__currentActions.splice(idx, 1);
    renderActionsList(window.__currentActions);
    closeActionEditor();
  };

  // ---------- Events ----------
  const onTriggerChange = () => {
    renderTriggerTypeOptions();
    renderTriggerConnectionOptions();

    // Keep current selection if still present
    // If triggerType is empty, set default
    if (!triggerTypeEl.value) {
      triggerTypeEl.value = (capabilities?.triggers_by_app?.[triggerAppEl.value] || [])[0] || "";
    }

    // Re-render config editor (assisted UI depends on app/type)
    const cfg = safeJsonParse(triggerConfigJson.value);
    renderTriggerConfigEditor(cfg);
  };

  // ---------- Init ----------
  const init = async () => {
    await loadCapabilities();
    await loadConnections();
    await loadAutomations();

    renderTriggerAppOptions();
    renderActionEditorOptions();
    renderAutomationList();

    // Default editor state
    newAutomation();

    // UI events
    el.btnNew?.addEventListener("click", newAutomation);
    el.btnSave?.addEventListener("click", saveAutomation);

    triggerAppEl.addEventListener("change", onTriggerChange);
    triggerConnEl.addEventListener("change", onTriggerChange);
    triggerTypeEl.addEventListener("change", onTriggerChange);

    el.btnAddAction?.addEventListener("click", () => {
      // Ensure editor selects are ready
      el.actionEditorApp.dispatchEvent(new Event("change"));
      addAction();
    });

    el.btnSaveAction?.addEventListener("click", saveAction);
    el.btnCancelAction?.addEventListener("click", closeActionEditor);
  };

  document.addEventListener("DOMContentLoaded", () => {
    init().catch((e) => {
      console.error(e);
      toast(`Init error: ${e.message}`, "error");
    });
  });
})();
