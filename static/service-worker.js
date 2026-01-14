const CACHE_NAME = "ldapp-cache-v2";

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
  const req = event.request;

  // Solo GET
  if (req.method !== "GET") return;

  const url = new URL(req.url);

  // Non cache per richieste Trello/API interne (evita dati stantii)
  if (url.pathname.startsWith("/trello/")) {
    event.respondWith(
      fetch(req, { cache: "no-store" }).catch(() => caches.match(req))
    );
    return;
  }

  // Network-first globale con fallback cache
  event.respondWith(
    fetch(req)
      .then((res) => {
        // Non cache se non OK o se è un redirect opaco
        if (!res || res.status !== 200 || res.type === "opaque") return res;

        const copy = res.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(req, copy));
        return res;
      })
      .catch(() => caches.match(req))
  );
});

// API endpoints (sempre NETWORK FIRST, mai cache-first)
if (url.includes("/trello/")) {
event.respondWith(
  fetch(req, { cache: "no-store" }).catch(() => caches.match(req))
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
