const CACHE_NAME = "ldapp-cache-v24"; // bump per forzare update
const MAX_PUSH_AGE_MS = 10 * 60 * 1000;

function supportedNotificationActions(actions) {
  if (!Array.isArray(actions)) return [];
  const maxActions =
    typeof Notification !== "undefined" && typeof Notification.maxActions === "number"
      ? Notification.maxActions
      : 2;
  if (maxActions <= 0) return [];
  return actions.slice(0, maxActions);
}

function notificationUrl(data) {
  return new URL((data && data.url) || "/", self.location.origin).href;
}

function openOrFocusUrl(targetUrl) {
  return clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
    for (const client of clientList) {
      if ("focus" in client) {
        client.navigate(targetUrl);
        return client.focus();
      }
    }
    if (clients.openWindow) return clients.openWindow(targetUrl);
    return undefined;
  });
}

function updateOrderStatus(orderId, status) {
  if (!orderId || !status) return Promise.reject(new Error("Azione ordine non valida"));
  return fetch(`/route-orders/api/orders/${orderId}/status`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ status }),
  }).then((response) => {
    if (!response.ok) throw new Error(`Aggiornamento stato fallito: ${response.status}`);
    return response.json();
  });
}

self.addEventListener("install", (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll([
        "/",
        "/static/css/style.css?v=20260628-mobile-home-10",
        "/static/css/context_tabs.css?v=20260628-mobile-home-10",
        "/static/css/task_status.css?v=20260628-mobile-home-10",
        "/static/js/menu.js?v=20260628-mobile-home-10",
        "/static/images/loghi_azienda/logo-ldenoteca-bianco.png",
        "/static/icons/icon-192.png",
        "/static/icons/icon-512.png",
      ]);
    })
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) =>
        Promise.all(keys.map((key) => (key !== CACHE_NAME ? caches.delete(key) : undefined)))
      )
      .then(() => self.clients.claim())
      .then(() => clients.matchAll({ type: "window", includeUncontrolled: true }))
      .then((clientList) => {
        clientList.forEach((client) => {
          client.postMessage({ type: "LDAPP_SW_ACTIVATED", cacheName: CACHE_NAME });
        });
      })
  );
});

self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") {
    self.skipWaiting();
  }
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);

  // Il Web Share Target apre l'app con una navigazione POST. Gestirla
  // esplicitamente nel worker evita che Android/WebAPK perda il passaggio
  // di consegna o i redirect prodotti dal server.
  if (req.method === "POST" && url.origin === self.location.origin && url.pathname === "/pwa/share") {
    event.respondWith(
      fetch(req, { credentials: "include", redirect: "follow", cache: "no-store" })
    );
    return;
  }

  // Solo GET
  if (req.method !== "GET") return;

  // ✅ Non cache-are roba non HTTP(S) (chrome-extension, data, blob, ecc.)
  if (url.protocol !== "http:" && url.protocol !== "https:") return;

  // API interne e manifest: sempre rete, mai cache forzata
  if (url.pathname.startsWith("/trello/") || url.pathname.startsWith("/pwa/") || url.pathname.endsWith("/manifest.json") || url.pathname.endsWith("/app-version.json")) {
    event.respondWith(
      fetch(req, { cache: "no-store" }).catch(() => caches.match(req))
    );
    return;
  }

  // Network-first globale con fallback cache
  event.respondWith(
    fetch(req)
      .then((res) => {
        if (!res || res.status !== 200 || res.type === "opaque") return res;
        const copy = res.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(req, copy));
        return res;
      })
      .catch(() => caches.match(req))
  );
});

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (err) {
    data = { title: "LDApp", body: event.data ? event.data.text() : "" };
  }

  if (data.sent_at) {
    const sentAtMs = Date.parse(data.sent_at);
    if (Number.isFinite(sentAtMs) && Date.now() - sentAtMs > MAX_PUSH_AGE_MS) {
      return;
    }
  }

  const title = data.title || "LDApp";
  const options = {
    body: data.body || "",
    icon: data.icon || "/static/icons/icon-192.png",
    badge: data.badge || "/static/icons/icon-192.png",
    tag: data.tag || data.notification_id || undefined,
    renotify: Boolean(data.renotify),
    timestamp: data.sent_at ? Date.parse(data.sent_at) : Date.now(),
    actions: supportedNotificationActions(data.actions),
    data: {
      url: data.url || "/",
      notification_id: data.notification_id || null,
      sent_at: data.sent_at || null,
      category: data.category || null,
      order_id: data.order_id || null,
      order_status: data.order_status || null,
      badge: data.badge || null,
      icon: data.icon || null,
    },
  };

  event.waitUntil(
    self.registration.showNotification(title, options).catch(() => {
      const fallbackOptions = {
        body: data.body || "",
        icon: "/static/icons/icon-192.png",
        badge: "/static/icons/icon-192.png",
        tag: data.tag || data.notification_id || undefined,
        data: options.data,
      };
      return self.registration.showNotification(title, fallbackOptions);
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const data = event.notification.data || {};
  const targetUrl = notificationUrl(data);
  const action = event.action || "default";

  if (action.startsWith("status:")) {
    const status = action.slice("status:".length);
    event.waitUntil(
      updateOrderStatus(data.order_id, status)
        .then(() => openOrFocusUrl(targetUrl))
        .catch(() => openOrFocusUrl(targetUrl))
    );
    return;
  }

  event.waitUntil(openOrFocusUrl(targetUrl));
});
