(function () {
  "use strict";

  const VERSION_URL = "/app-version.json";
  const POLL_INTERVAL_MS = 60 * 1000;
  const STORAGE_KEY = "ldapp.appVersion";
  const PENDING_KEY = "ldapp.pendingAppVersion";

  let checking = false;

  function currentPageVersion() {
    const meta = document.querySelector('meta[name="ldapp-version"]');
    return meta ? normalizeVersion(meta.getAttribute("content")) : "";
  }

  function normalizeVersion(value) {
    return typeof value === "string" ? value.trim() : "";
  }

  async function fetchServerVersion() {
    const response = await fetch(`${VERSION_URL}?t=${Date.now()}`, {
      cache: "no-store",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) return "";
    const payload = await response.json();
    return normalizeVersion(payload && payload.version);
  }

  async function downloadServiceWorkerUpdate() {
    if (!("serviceWorker" in navigator)) return;
    const registration = await navigator.serviceWorker.getRegistration();
    if (registration) await registration.update();
  }

  async function checkVersion() {
    if (checking) return;
    checking = true;
    try {
      const serverVersion = await fetchServerVersion();
      const pageVersion = currentPageVersion();
      if (!serverVersion || !pageVersion || serverVersion === pageVersion) return;

      // Scarica l'aggiornamento, ma non ricarica mai il documento in uso: form,
      // conteggi e modali rimangono intatti. La nuova versione verra' usata alla
      // successiva apertura o navigazione completa eseguita dall'utente.
      localStorage.setItem(PENDING_KEY, serverVersion);
      await downloadServiceWorkerUpdate();
    } catch (err) {
      console.warn("Controllo versione PWA non riuscito", err);
    } finally {
      checking = false;
    }
  }

  function initVersionState() {
    const pageVersion = currentPageVersion();
    if (!pageVersion) return;

    localStorage.setItem(STORAGE_KEY, pageVersion);
    if (normalizeVersion(localStorage.getItem(PENDING_KEY)) === pageVersion) {
      localStorage.removeItem(PENDING_KEY);
    }
  }

  window.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") checkVersion();
  });
  window.addEventListener("focus", checkVersion);

  initVersionState();
  window.setInterval(checkVersion, POLL_INTERVAL_MS);
  window.setTimeout(checkVersion, 5000);
})();
