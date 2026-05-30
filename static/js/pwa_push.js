(function () {
  const AUTO_REPAIR_THROTTLE_MS = 30 * 60 * 1000;

  function urlBase64ToUint8Array(base64String) {
    const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; i += 1) {
      outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
  }

  function arrayBufferToBase64Url(buffer) {
    if (!buffer) return "";
    const bytes = new Uint8Array(buffer);
    let binary = "";
    for (let i = 0; i < bytes.byteLength; i += 1) {
      binary += String.fromCharCode(bytes[i]);
    }
    return window.btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }

  async function api(url, options) {
    const res = await fetch(url, {
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      ...(options || {}),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) throw new Error(data.error || `HTTP ${res.status}`);
    return data;
  }

  async function ensurePushSubscription({ requestPermission = false } = {}) {
    if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
      throw new Error("Notifiche push non supportate da questo browser");
    }

    const cfg = await api("/pwa/api/push/config");
    if (!cfg.enabled || !cfg.public_key) {
      throw new Error("Notifiche push non configurate sul server");
    }

    const permission = requestPermission
      ? await Notification.requestPermission()
      : Notification.permission;
    if (permission !== "granted") {
      throw new Error("Permesso notifiche non concesso");
    }

    const serviceWorkerRegistration = await navigator.serviceWorker.getRegistration();
    if (serviceWorkerRegistration) {
      await serviceWorkerRegistration.update().catch(() => undefined);
    }

    const registration = await navigator.serviceWorker.ready;
    let subscription = await registration.pushManager.getSubscription();
    const currentKey = subscription?.options?.applicationServerKey
      ? arrayBufferToBase64Url(subscription.options.applicationServerKey)
      : "";
    if (subscription && currentKey && currentKey !== cfg.public_key) {
      await api("/pwa/api/push/unsubscribe", {
        method: "POST",
        body: JSON.stringify({ endpoint: subscription.endpoint }),
      }).catch(() => undefined);
      await subscription.unsubscribe();
      subscription = null;
    }
    if (!subscription) {
      subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(cfg.public_key),
      });
    }
    await api("/pwa/api/push/subscribe", {
      method: "POST",
      body: JSON.stringify(subscription.toJSON()),
    });
    return true;
  }

  async function enablePush() {
    return ensurePushSubscription({ requestPermission: true });
  }

  async function disablePush() {
    if (!("serviceWorker" in navigator)) return;
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();
    if (subscription) {
      await api("/pwa/api/push/unsubscribe", {
        method: "POST",
        body: JSON.stringify({ endpoint: subscription.endpoint }),
      });
      await subscription.unsubscribe();
    }
  }

  async function testPush() {
    return api("/pwa/api/push/test", { method: "POST", body: "{}" });
  }

  async function autoRepairPushSubscription({ force = false } = {}) {
    if (!("Notification" in window) || Notification.permission !== "granted") return false;

    const now = Date.now();
    const lastRun = Number(window.localStorage.getItem("ldappPushAutoRepairAt") || 0);
    if (!force && lastRun && now - lastRun < AUTO_REPAIR_THROTTLE_MS) return false;

    try {
      await ensurePushSubscription({ requestPermission: false });
      window.localStorage.setItem("ldappPushAutoRepairAt", String(now));
      return true;
    } catch (err) {
      console.warn("Riparazione automatica notifiche non riuscita:", err);
      window.localStorage.setItem("ldappPushAutoRepairAt", String(now));
      return false;
    }
  }

  window.LDAppPush = { enablePush, disablePush, testPush, autoRepairPushSubscription };

  document.addEventListener("click", async (event) => {
    const btn = event.target.closest("[data-pwa-push-enable]");
    if (!btn) return;
    event.preventDefault();
    btn.disabled = true;
    try {
      await enablePush();
      await testPush();
      alert("Notifiche abilitate su questo dispositivo.");
    } catch (err) {
      alert(err.message || "Errore abilitazione notifiche");
    } finally {
      btn.disabled = false;
    }
  });

  document.addEventListener("DOMContentLoaded", () => {
    autoRepairPushSubscription();
  });

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      autoRepairPushSubscription();
    }
  });

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.addEventListener("message", (event) => {
      if (event.data?.type === "LDAPP_SW_ACTIVATED") {
        autoRepairPushSubscription({ force: true });
      }
    });
  }
})();
