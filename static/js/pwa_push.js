(function () {
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

  async function enablePush() {
    if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
      throw new Error("Notifiche push non supportate da questo browser");
    }

    const cfg = await api("/pwa/api/push/config");
    if (!cfg.enabled || !cfg.public_key) {
      throw new Error("Notifiche push non configurate sul server");
    }

    const permission = await Notification.requestPermission();
    if (permission !== "granted") {
      throw new Error("Permesso notifiche non concesso");
    }

    const registration = await navigator.serviceWorker.ready;
    let subscription = await registration.pushManager.getSubscription();
    const currentKey = subscription?.options?.applicationServerKey
      ? arrayBufferToBase64Url(subscription.options.applicationServerKey)
      : "";
    if (subscription && currentKey && currentKey !== cfg.public_key) {
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

  window.LDAppPush = { enablePush, disablePush, testPush };

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
})();
