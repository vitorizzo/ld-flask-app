const CACHE_NAME = "ldapp-cache-v1";

self.addEventListener("install", (event) => {
  self.skipWaiting();

  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll([
        "/",               // homepage
        "/static/css/style.css",  // i tuoi file principali
        "/static/icons/icon-192.png",
        "/static/icons/icon-512.png"
      ]);
    })
  );
});

self.addEventListener("fetch", (event) => {
  const url = event.request.url;
  const req = event.request;
  const accept = req.headers.get("accept") || "";

  // HTML navigation: NETWORK FIRST (prevents stale logged-out pages)
  if (req.mode === "navigate" || accept.includes("text/html")) {
    event.respondWith(
      fetch(req)
        .then((res) => {
          // optional: update cache for offline fallback
          const copy = res.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(req, copy));
          return res;
        })
        .catch(() => caches.match(req).then((r) => r || caches.match("/")))
    );
    return;
  }

  // Per CSS/JS specifici → network first
  if (url.includes("install_banner.css") || url.includes("install_banner.js")) {
    event.respondWith(
      fetch(event.request).then(response => {
        return response;
      }).catch(() => {
        return caches.match(event.request);  // fallback se offline
      })
    );
    return;
  }

  // Default → cache first
  event.respondWith(
    caches.match(event.request).then(cachedResponse => {
      return cachedResponse || fetch(event.request).then(networkResponse => {
        return caches.open(CACHE_NAME).then(cache => {
          cache.put(event.request, networkResponse.clone());
          return networkResponse;
        });
      });
    })
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.map((key) => {
        if (key !== CACHE_NAME) {
          return caches.delete(key); // elimina vecchie cache
        }
      }))
    )
  );
  return self.clients.claim();
});
