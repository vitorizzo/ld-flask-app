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

    const apps = getApps();
    apps.forEach((app) => {
      const opt = document.createElement("option");
      opt.value = app;
      opt.textContent = app;
      triggerAppEl.appendChild(opt);
    });
  };

  const renderTriggerTypeOptions = () => {
    const app = triggerAppEl.value;
    triggerTypeEl.innerHTML = "";

    const list = getTriggersForApp(app); // [{value,label}]
    list.forEach((t) => {
      const opt = document.createElement("option");
      opt.value = t.value;         // valore da salvare
      opt.textContent = t.label;   // testo leggibile
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
    const triggerApp = triggerAppEl.value;
    const triggerType = triggerTypeEl.value;

    // Reset advanced UI
    triggerConfigEditor.innerHTML = "";
    triggerConfigEditor.appendChild(triggerConfigJson);

    // Default payload
    const ensureDefaults = (obj) => {
      const o = obj && typeof obj === "object" ? obj : {};
      return {
        channels: Array.isArray(o.channels) ? o.channels : [],
        keywords: Array.isArray(o.keywords) ? o.keywords : [],
        visibility: typeof o.visibility === "string" && o.visibility ? o.visibility : "any",
      };
    };

    // Keep raw JSON textarea as source-of-truth
    const defaults = ensureDefaults(cfgObj);
    triggerConfigJson.value = formatJson(defaults);

    // Only Slack "message" gets the assisted editor
    if (!(triggerApp === "slack" && triggerType === "message")) {
      triggerConfigJson.style.display = "";
      return;
    }

    // Hide raw JSON textarea but keep it mounted for save payload
    triggerConfigJson.style.display = "none";

    const parseCfg = () => {
      const raw = triggerConfigJson.value?.trim();
      if (!raw) return { channels: [], keywords: [], visibility: "any" };
      try {
        const obj = JSON.parse(raw);

        const channels = Array.isArray(obj?.channels) ? obj.channels : [];
        const keywords = Array.isArray(obj?.keywords) ? obj.keywords : [];

        // visibility can be "any" (string) OR array of strings
        let visibility = obj?.visibility;
        if (Array.isArray(visibility)) {
          visibility = visibility.map((v) => String(v || "").trim()).filter(Boolean);
          if (!visibility.length) visibility = "any";
          if (visibility.includes("any")) visibility = "any"; // any must be unique
        } else {
          visibility = String(visibility || "any").trim() || "any";
        }

        return { channels, keywords, visibility };
      } catch {
        return { channels: [], keywords: [], visibility: "any" };
      }
    };

    const normalizeChannels = (arr) =>
      (Array.isArray(arr) ? arr : [])
        .map((c) => {
          if (typeof c === "string") return { id: c, label: c, is_private: false };
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

    let state = parseCfg();
    let channelsSelected = normalizeChannels(state.channels);
    let keywordsSelected = normalizeKeywords(state.keywords);
    let visibilitySelected =
      state.visibility === "any"
        ? ["any"]
        : (Array.isArray(state.visibility) ? state.visibility : [state.visibility]).filter(Boolean);

    if (!visibilitySelected.length) visibilitySelected = ["any"];
    if (visibilitySelected.includes("any") && visibilitySelected.length > 1) visibilitySelected = ["any"];


    const syncTextarea = () => {
      const visibilityOut =
        visibilitySelected.includes("any") ? "any" : visibilitySelected.slice();

      triggerConfigJson.value = formatJson({
        channels: channelsSelected,
        keywords: keywordsSelected,
        visibility: visibilityOut,
      });
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

    const section = (title, subtitle = "") => {
      const wrap = document.createElement("div");
      wrap.className = "mb-3";

      const h = document.createElement("div");
      h.className = "form-label fw-semibold";
      h.textContent = title;

      wrap.appendChild(h);

      if (subtitle) {
        const s = document.createElement("div");
        s.className = "text-muted small mb-2";
        s.textContent = subtitle;
        wrap.appendChild(s);
      }
      return wrap;
    };

    // --- Visibility ---
    const secVis = section("Visibilità canale (Slack)");

    const visWrap = document.createElement("div");
    visWrap.className = "d-flex flex-wrap gap-2";

    const VIS_OPTIONS = [
      { value: "any", label: "Any" },
      { value: "public", label: "Public" },
      { value: "private", label: "Private" },
      { value: "dm", label: "DM" },
      { value: "group_dm", label: "Group DM" },
    ];

    const visChecks = [];

    VIS_OPTIONS.forEach((o) => {
      const formCheck = document.createElement("div");
      formCheck.className = "form-check form-check-inline";

      const input = document.createElement("input");
      input.className = "form-check-input";
      input.type = "checkbox";
      input.id = `vis_${o.value}`;
      input.value = o.value;

      const label = document.createElement("label");
      label.className = "form-check-label";
      label.setAttribute("for", input.id);
      label.textContent = o.label;

      formCheck.appendChild(input);
      formCheck.appendChild(label);
      visWrap.appendChild(formCheck);

      visChecks.push(input);

      input.addEventListener("change", () => {
        const v = input.value;

        if (v === "any") {
          if (input.checked) {
            visibilitySelected = ["any"];
          } else {
            // if user unchecks any, enforce at least any
            visibilitySelected = ["any"];
          }
        } else {
          if (input.checked) {
            visibilitySelected = visibilitySelected.filter((x) => x !== "any");
            if (!visibilitySelected.includes(v)) visibilitySelected.push(v);
          } else {
            visibilitySelected = visibilitySelected.filter((x) => x !== v);
            if (!visibilitySelected.length) visibilitySelected = ["any"];
          }
        }

        // enforce rule: if any present, it's unique
        if (visibilitySelected.includes("any")) visibilitySelected = ["any"];

        renderVisibility();
        syncTextarea();
      });
    });

    secVis.appendChild(visWrap);

    // -------------------------------
    // Channels selector (button -> dialog with checkboxes)
    // -------------------------------
    const secChannels = section(
      "Canali (Slack)",
      "Seleziona uno o più canali. I canali privati sono marcati con 🔒."
    );

    const chTop = document.createElement("div");
    chTop.className = "d-flex gap-2 align-items-center flex-wrap";

    const btnPickChannels = document.createElement("button");
    btnPickChannels.type = "button";
    btnPickChannels.className = "btn btn-primary";
    btnPickChannels.textContent = "Seleziona canali";

    const btnRefreshChannels = document.createElement("button");
    btnRefreshChannels.type = "button";
    btnRefreshChannels.className = "btn btn-outline-secondary";
    btnRefreshChannels.textContent = "Aggiorna elenco";

    const chHint = document.createElement("div");
    chHint.className = "text-muted small";
    chHint.textContent = "Se non selezioni canali, il filtro canali è disattivato (channels = []).";

    chTop.appendChild(btnPickChannels);
    chTop.appendChild(btnRefreshChannels);

    const chipsChannels = document.createElement("div");
    chipsChannels.className = "mt-2";

    secChannels.appendChild(chTop);
    secChannels.appendChild(chHint);
    secChannels.appendChild(chipsChannels);

    // Native dialog (no bootstrap dependency)
    const dlg = document.createElement("dialog");
    dlg.style.width = "min(720px, 95vw)";
    dlg.style.border = "1px solid var(--bs-border-color, #ddd)";
    dlg.style.borderRadius = "12px";
    dlg.style.padding = "0";

    dlg.innerHTML = `
      <div style="padding:16px; border-bottom:1px solid var(--bs-border-color, #ddd); display:flex; align-items:center; justify-content:space-between; gap:12px;">
        <div>
          <div style="font-weight:600;">Seleziona canali Slack</div>
          <div class="text-muted small">Spunta i canali desiderati e poi “Applica”.</div>
        </div>
        <button type="button" data-close class="btn btn-sm btn-outline-secondary">Chiudi</button>
      </div>
      <div style="padding:16px;">
        <div class="text-muted small mb-2" data-connhint></div>
        <div style="max-height: 50vh; overflow:auto; border:1px solid var(--bs-border-color, #ddd); border-radius:10px; padding:10px;" data-list>
          <div class="text-muted">(caricamento...)</div>
        </div>
        <div class="d-flex gap-2 justify-content-end mt-3" style="border-top:1px solid var(--bs-border-color, #ddd); padding-top:12px;">
          <button type="button" data-cancel class="btn btn-outline-secondary">Annulla</button>
          <button type="button" data-apply class="btn btn-primary">Applica</button>
        </div>
      </div>
    `;

    const dlgList = dlg.querySelector("[data-list]");
    const dlgConnHint = dlg.querySelector("[data-connhint]");
    const dlgBtnClose = dlg.querySelector("[data-close]");
    const dlgBtnCancel = dlg.querySelector("[data-cancel]");
    const dlgBtnApply = dlg.querySelector("[data-apply]");

    const renderVisibility = () => {
      visChecks.forEach((chk) => {
        if (visibilitySelected.includes("any")) {
          chk.checked = chk.value === "any";
          chk.disabled = chk.value !== "any";
        } else {
          chk.disabled = false;
          chk.checked = visibilitySelected.includes(chk.value);
        }
      });
    };


    const renderChipsChannels = () => {
      chipsChannels.innerHTML = "";
      channelsSelected.forEach((c, idx) => {
        const label = c.is_private ? `🔒 ${c.label}` : c.label;
        chipsChannels.appendChild(
          chip(label, () => {
            channelsSelected.splice(idx, 1);
            syncTextarea();
            renderChipsChannels();
          })
        );
      });
    };

    const loadChannelsCheckboxes = async (forceRefresh = false) => {
      const connId = triggerConnEl.value;
      dlgList.innerHTML = "";
      dlgConnHint.textContent = "";

      if (!connId) {
        dlgConnHint.textContent = "Seleziona prima una connessione Slack nel trigger.";
        dlgList.innerHTML = `<div class="text-muted">(nessuna connessione selezionata)</div>`;
        return;
      }

      try {
        if (forceRefresh) clearSlackChannelsCache(connId);
        const channels = await fetchSlackChannels(connId);

        if (!channels.length) {
          dlgList.innerHTML = `<div class="text-muted">(nessun canale trovato)</div>`;
          return;
        }

        // build checkbox list
        const selectedIds = new Set(channelsSelected.map((c) => c.id));
        const frag = document.createDocumentFragment();

        channels.forEach((c) => {
          const row = document.createElement("label");
          row.style.display = "flex";
          row.style.alignItems = "center";
          row.style.justifyContent = "space-between";
          row.style.gap = "10px";
          row.style.padding = "6px 8px";
          row.style.borderRadius = "8px";
          row.style.cursor = "pointer";

          const left = document.createElement("div");
          left.style.display = "flex";
          left.style.alignItems = "center";
          left.style.gap = "10px";

          const cb = document.createElement("input");
          cb.type = "checkbox";
          cb.dataset.id = c.id;
          cb.dataset.name = c.name;
          cb.dataset.private = c.is_private ? "1" : "0";
          cb.checked = selectedIds.has(c.id);

          const name = document.createElement("div");
          name.textContent = c.name;

          left.appendChild(cb);
          left.appendChild(name);

          const badge = document.createElement("span");
          badge.className = "badge bg-secondary";
          badge.textContent = c.is_private ? "private" : "public";

          row.appendChild(left);
          row.appendChild(badge);

          frag.appendChild(row);
        });

        dlgList.appendChild(frag);
      } catch (err) {
        console.error("Slack channels load failed:", err);
        dlgList.innerHTML = `<div class="text-muted">(errore caricamento canali)</div>`;
      }
    };

    btnPickChannels.addEventListener("click", async () => {
      await loadChannelsCheckboxes(false);
      if (typeof dlg.showModal === "function") dlg.showModal();
      else dlg.open = true;
    });

    btnRefreshChannels.addEventListener("click", async () => {
      // refresh chips list is not needed; refresh affects dialog list
      // but we also clear cache now so next open is fresh
      const connId = triggerConnEl.value;
      clearSlackChannelsCache(connId);
      toast("Cache canali aggiornata (apri Seleziona canali).");
    });

    const closeDlg = () => {
      if (typeof dlg.close === "function") dlg.close();
      else dlg.open = false;
    };

    dlgBtnClose.addEventListener("click", closeDlg);
    dlgBtnCancel.addEventListener("click", closeDlg);

    dlgBtnApply.addEventListener("click", () => {
      const checkboxes = Array.from(dlgList.querySelectorAll('input[type="checkbox"][data-id]'));
      const picked = checkboxes
        .filter((cb) => cb.checked)
        .map((cb) => ({
          id: cb.dataset.id,
          label: cb.dataset.name || cb.dataset.id,
          is_private: cb.dataset.private === "1",
        }));

      channelsSelected = picked;
      syncTextarea();
      renderChipsChannels();
      closeDlg();
    });

    // -------------------------------
    // Keywords (input + chips)
    // -------------------------------
    const secKeywords = section("Keyword", "Aggiungi una o più keyword (chips). Lascia vuoto per disabilitare filtro.");
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

    const renderChipsKeywords = () => {
      chipsKeywords.innerHTML = "";
      keywordsSelected.forEach((k, idx) => {
        chipsKeywords.appendChild(
          chip(k, () => {
            keywordsSelected.splice(idx, 1);
            syncTextarea();
            renderChipsKeywords();
          })
        );
      });
    };

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
      renderChipsKeywords();
    };

    btnKwAdd.addEventListener("click", addKeyword);
    kwInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        addKeyword();
      }
    });

    secKeywords.appendChild(rowKw);
    secKeywords.appendChild(chipsKeywords);

    // Mount sections in order (visibility -> channels -> keywords) before the hidden textarea
    triggerConfigEditor.insertBefore(secVis, triggerConfigJson);
    triggerConfigEditor.insertBefore(secChannels, triggerConfigJson);
    triggerConfigEditor.insertBefore(secKeywords, triggerConfigJson);

    // Mount dialog into editor
    triggerConfigEditor.appendChild(dlg);

    // Initial render
    renderVisibility();
    syncTextarea();
    renderChipsChannels();
    renderChipsKeywords();
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
    const apps = getApps();

    el.actionEditorApp.innerHTML = "";
    apps.forEach((app) => {
      const opt = document.createElement("option");
      opt.value = app;
      opt.textContent = app;
      el.actionEditorApp.appendChild(opt);
    });

    const updateActionTypes = () => {
      const app = el.actionEditorApp.value;
      const types = getActionsForApp(app); // [{value,label}]
      el.actionEditorType.innerHTML = "";
      types.forEach((t) => {
        const opt = document.createElement("option");
        opt.value = t.value;
        opt.textContent = t.label;
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

  const getApps = () => Object.keys(capabilities || {}).sort();

  const getTriggersForApp = (app) => {
    const arr = capabilities?.[app]?.triggers || [];
    return Array.isArray(arr) ? arr : [];
  };

  const getActionsForApp = (app) => {
    const arr = capabilities?.[app]?.actions || [];
    return Array.isArray(arr) ? arr : [];
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
    const apps = getApps();
    triggerAppEl.value = auto.trigger_app || apps[0] || "";

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

    const apps = getApps();
    triggerAppEl.value = apps[0] || "slack";

    renderTriggerTypeOptions();
    renderTriggerConnectionOptions();

    triggerConnEl.value = "";
    const firstTrig = getTriggersForApp(triggerAppEl.value)[0];
    triggerTypeEl.value = firstTrig?.value || "";
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
      const firstTrig = getTriggersForApp(triggerAppEl.value)[0];
      triggerTypeEl.value = firstTrig?.value || "";
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
