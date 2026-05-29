const CACHE_NAME = "ldapp-cache-v8"; // bump per forzare update
const MAX_PUSH_AGE_MS = 10 * 60 * 1000;

self.addEventListener("install", (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll([
        "/",
        "/static/css/style.css",
        "/static/icons/icon-192.png",
        "/static/icons/icon-512.png",
      ]);
    })
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.map((key) => (key !== CACHE_NAME ? caches.delete(key) : undefined)))
    )
  );
  self.clients.claim();
});

self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") {
    self.skipWaiting();
  }
});

self.addEventListener("fetch", (event) => {
  const req = event.request;

  // Solo GET
  if (req.method !== "GET") return;

  const url = new URL(req.url);

  // ✅ Non cache-are roba non HTTP(S) (chrome-extension, data, blob, ecc.)
  if (url.protocol !== "http:" && url.protocol !== "https:") return;

  // API interne e manifest: sempre rete, mai cache forzata
  if (url.pathname.startsWith("/trello/") || url.pathname.startsWith("/pwa/") || url.pathname.endsWith("/manifest.json")) {
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
    icon: "/static/icons/icon-192.png",
    badge: "/static/icons/icon-192.png",
    tag: data.notification_id || undefined,
    timestamp: data.sent_at ? Date.parse(data.sent_at) : Date.now(),
    data: {
      url: data.url || "/",
      notification_id: data.notification_id || null,
      sent_at: data.sent_at || null,
    },
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const targetUrl = new URL((event.notification.data && event.notification.data.url) || "/", self.location.origin).href;

  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if ("focus" in client) {
          client.navigate(targetUrl);
          return client.focus();
        }
      }
      if (clients.openWindow) return clients.openWindow(targetUrl);
      return undefined;
    })
  );
});
