(() => {
  const STORAGE_KEY = "ldapp.page_tabs.v1";
  const LAST_FIXED_KEY = "ldapp.page_tabs.last_fixed.v1";
  const FIXED_PATHS = new Set(["/cassa/agenda", "/route-orders/board", "/kiosk"]);
  const PAGE_LABELS = [
    { test: path => path === "/settings", label: "Impostazioni" },
    { test: path => path === "/settings/preferences", label: "Preferenze" },
    { test: path => path === "/settings/menus", label: "Gestione menù" },
    { test: path => path === "/registry/customer-routes", label: "Associazione clienti-giri" },
    { test: path => path === "/registry/customers", label: "Rubrica clienti" },
    { test: path => path === "/registry/suppliers", label: "Rubrica fornitori" },
    { test: path => path === "/settings/import_conflicts", label: "Conflitti import" },
    { test: path => path === "/settings/import_articoli", label: "Import articoli" },
    { test: path => path === "/settings/import_ps_data", label: "Import PS data" },
    { test: path => path === "/settings/import_poleepo_products", label: "Import prodotti Poleepo" },
    { test: path => path === "/settings/import_giacenze", label: "Import giacenze" },
    { test: path => path === "/settings/import_barcode", label: "Import barcode" },
    { test: path => path === "/settings/import_anagrafiche", label: "Import anagrafiche" },
    { test: path => path === "/trello/actions", label: "Gestione azioni Trello" },
    { test: path => path === "/trello/connections", label: "Connessioni Trello" },
    { test: path => path === "/trello/connection/editor/new", label: "Nuova connessione Trello" },
    { test: path => path.startsWith("/trello/connection/editor/"), label: "Modifica connessione Trello" },
    { test: path => path.startsWith("/pwa/share/") || path === "/pwa/share_review", label: "Condivisione ordine" },
    { test: path => path === "/app_installation", label: "Installazione app" },
    { test: path => path === "/upload_photo", label: "Gestione foto profilo" },
    { test: path => path === "/edit_profile", label: "Modifica profilo" },
    { test: path => path === "/ld-selection", label: "LD Selection" },
    { test: path => path === "/wine-cards" || path === "/wine-cards/", label: "Carte vini" },
    { test: path => path === "/wine-cards/new", label: "Nuova carta vini" },
    { test: path => path.startsWith("/wine-cards/view/"), label: "Preview carta vini" },
    { test: path => path.startsWith("/wine-cards/"), label: "Modifica carta vini" },
    { test: path => path === "/kiosk", label: "Bacheca ordini" },
    { test: path => path === "/logs/view", label: "log viewer" },
  ];

  function tabKeyFromUrl(url) {
    try {
      return new URL(url, window.location.origin).pathname || "/";
    } catch (err) {
      return (url || "/").split("?")[0] || "/";
    }
  }

  function loadTabs() {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      const tabs = JSON.parse(raw || "[]");
      if (!Array.isArray(tabs)) return [];
      const seen = new Set();
      const normalized = [];
      for (const tab of tabs) {
        if (!tab || !tab.url) continue;
        const key = tab.key || tabKeyFromUrl(tab.url);
        if (seen.has(key)) continue;
        seen.add(key);
        normalized.push({ ...tab, key });
      }
      return normalized;
    } catch (err) {
      console.warn("Failed to load page tabs", err);
      return [];
    }
  }

  function saveTabs(tabs) {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(tabs));
  }

  function normalizeLabel(rawLabel) {
    const label = (rawLabel || "").trim();
    if (!label) return "";
    return label
      .replace(/\s*[-|]\s*LD Enoteca$/i, "")
      .replace(/^LD Enoteca\s*[-|]\s*/i, "")
      .replace(/\s+/g, " ")
      .trim();
  }

  function labelFromPath(path) {
    const match = PAGE_LABELS.find(entry => entry.test(path));
    if (match) return match.label;
    const tail = decodeURIComponent(path.split("/").filter(Boolean).pop() || "Pagina");
    return tail
      .replace(/[-_]+/g, " ")
      .replace(/\b\w/g, char => char.toUpperCase());
  }

  function currentTab() {
    const path = window.location.pathname || "/";
    const search = window.location.search || "";
    const url = `${path}${search}`;
    const mappedLabel = PAGE_LABELS.find(entry => entry.test(path));
    return {
      url,
      key: tabKeyFromUrl(url),
      path,
      fixed: FIXED_PATHS.has(path),
      label: mappedLabel ? mappedLabel.label : (normalizeLabel(document.title) || labelFromPath(path)),
    };
  }

  function shouldShowDynamicTabs() {
    const root = document.documentElement;
    if (root.dataset.tabsEnabled !== "1") return false;
    if (document.body.classList.contains("kiosk-body")) return false;
    const tabs = loadTabs();
    return tabs.some(tab => !tab.fixed) || !currentTab().fixed;
  }

  function updateShellState() {
    if (!document.documentElement.dataset.tabsEnabled) return;
    if (shouldShowDynamicTabs()) {
      document.documentElement.dataset.hasPageTabs = "1";
    }
  }

  function registerCurrentTab() {
    if (document.documentElement.dataset.tabsEnabled !== "1") return;
    if (document.body.classList.contains("kiosk-body")) return;
    const tab = currentTab();
    if (tab.fixed) {
      sessionStorage.setItem(LAST_FIXED_KEY, tab.url);
      return;
    }
    const tabs = loadTabs().filter(item => item.key !== tab.key);
    tabs.push({
      url: tab.url,
      key: tab.key,
      label: tab.label,
      fixed: false,
      lastActiveAt: Date.now(),
    });
    saveTabs(tabs);
    document.documentElement.dataset.hasPageTabs = "1";
  }

  function renderPageTabs() {
    const host = document.getElementById("openPageTabs");
    if (!host || document.documentElement.dataset.tabsEnabled !== "1" || document.body.classList.contains("kiosk-body")) return;
    const tabs = loadTabs();
    const activeKey = currentTab().key;
    if (!tabs.length) {
      host.innerHTML = "";
      return;
    }
    host.innerHTML = tabs.map(tab => `
      <div class="context-tab-page${tab.key === activeKey ? " active" : ""}" data-page-tab-key="${tab.key}">
        <a class="context-tab-page__link" href="${tab.url}" title="${tab.label}">
          <span class="context-tab-page__label">${tab.label}</span>
        </a>
        <button type="button" class="context-tab-page__close" data-page-tab-close="${tab.key}" aria-label="Chiudi ${tab.label}">&times;</button>
      </div>
    `).join("");
  }

  function closePageTab(closedKey) {
    const activeKey = currentTab().key;
    const tabs = loadTabs().filter(tab => tab.key !== closedKey);
    saveTabs(tabs);
    if (closedKey === activeKey) {
      if (tabs.length) {
        window.location.href = tabs[tabs.length - 1].url;
        return;
      }
      window.location.href = sessionStorage.getItem(LAST_FIXED_KEY) || "/";
      return;
    }
    document.documentElement.dataset.hasPageTabs = tabs.some(tab => !tab.fixed) ? "1" : "";
    renderPageTabs();
  }

  document.addEventListener("click", (event) => {
    const closeButton = event.target.closest("[data-page-tab-close]");
    if (!closeButton) return;
    event.preventDefault();
    event.stopPropagation();
    closePageTab(closeButton.dataset.pageTabClose);
  });

  document.addEventListener("DOMContentLoaded", () => {
    registerCurrentTab();
    updateShellState();
    renderPageTabs();

    const flash = document.getElementById("flash-message");
    if (flash) {
      flash.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });
})();
