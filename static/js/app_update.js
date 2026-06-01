(function () {
  "use strict";

  const VERSION_URL = "/app-version.json";
  const POLL_INTERVAL_MS = 60 * 1000;
  const RETRY_INTERVAL_MS = 15 * 1000;
  const STORAGE_KEY = "ldapp.appVersion";
  const RELOAD_KEY = "ldapp.reloadingForVersion";

  let pendingVersion = null;
  let retryTimer = null;
  let checking = false;

  function currentPageVersion() {
    const meta = document.querySelector('meta[name="ldapp-version"]');
    return meta ? meta.getAttribute("content") : null;
  }

  function normalizeVersion(value) {
    return typeof value === "string" ? value.trim() : "";
  }

  function activeFormControl() {
    const element = document.activeElement;
    if (!element) return false;
    if (element.isContentEditable) return true;
    return ["INPUT", "TEXTAREA", "SELECT"].includes(element.tagName);
  }

  function hasOpenModal() {
    return Boolean(document.querySelector(".modal.show"));
  }

  function canReloadNow() {
    return document.visibilityState === "visible" && !activeFormControl() && !hasOpenModal();
  }

  async function fetchServerVersion() {
    const response = await fetch(`${VERSION_URL}?t=${Date.now()}`, {
      cache: "no-store",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) return null;
    const payload = await response.json();
    return normalizeVersion(payload && payload.version);
  }

  async function clearAppCaches() {
    if (!("caches" in window)) return;
    const keys = await caches.keys();
    await Promise.all(
      keys
        .filter((key) => key.startsWith("ldapp-cache"))
        .map((key) => caches.delete(key))
    );
  }

  async function updateServiceWorker() {
    if (!("serviceWorker" in navigator)) return;
    const registration = await navigator.serviceWorker.getRegistration();
    if (!registration) return;
    await registration.update();
    if (registration.waiting) {
      registration.waiting.postMessage({ type: "SKIP_WAITING" });
    }
  }

  function scheduleRetry() {
    if (retryTimer) return;
    retryTimer = window.setTimeout(() => {
      retryTimer = null;
      applyPendingUpdate();
    }, RETRY_INTERVAL_MS);
  }

  async function applyPendingUpdate() {
    if (!pendingVersion) return;
    if (!canReloadNow()) {
      scheduleRetry();
      return;
    }

    const versionToApply = pendingVersion;
    pendingVersion = null;
    try {
      sessionStorage.setItem(RELOAD_KEY, versionToApply);
      localStorage.setItem(STORAGE_KEY, versionToApply);
      await updateServiceWorker();
      await clearAppCaches();
    } catch (err) {
      console.warn("Aggiornamento PWA non completato prima del reload", err);
    } finally {
      window.location.reload();
    }
  }

  async function checkVersion() {
    if (checking) return;
    checking = true;
    try {
      const serverVersion = await fetchServerVersion();
      if (!serverVersion) return;

      const pageVersion = normalizeVersion(currentPageVersion());
      const storedVersion = normalizeVersion(localStorage.getItem(STORAGE_KEY));
      const knownVersion = storedVersion || pageVersion;

      if (!knownVersion) {
        localStorage.setItem(STORAGE_KEY, serverVersion);
        return;
      }

      if (serverVersion !== knownVersion || (pageVersion && serverVersion !== pageVersion)) {
        pendingVersion = serverVersion;
        applyPendingUpdate();
      }
    } catch (err) {
      console.warn("Controllo versione PWA non riuscito", err);
    } finally {
      checking = false;
    }
  }

  function initVersionState() {
    const pageVersion = normalizeVersion(currentPageVersion());
    const reloadedForVersion = normalizeVersion(sessionStorage.getItem(RELOAD_KEY));
    if (reloadedForVersion && reloadedForVersion === pageVersion) {
      sessionStorage.removeItem(RELOAD_KEY);
    }
    if (pageVersion) {
      localStorage.setItem(STORAGE_KEY, pageVersion);
    }
  }

  window.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      if (pendingVersion) {
        applyPendingUpdate();
      } else {
        checkVersion();
      }
    }
  });
  window.addEventListener("focus", () => {
    if (pendingVersion) {
      applyPendingUpdate();
    } else {
      checkVersion();
    }
  });
  window.addEventListener("blur", () => {
    if (pendingVersion) scheduleRetry();
  });

  initVersionState();
  window.setInterval(checkVersion, POLL_INTERVAL_MS);
  window.setTimeout(checkVersion, 5000);
})();
